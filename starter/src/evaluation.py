"""Evaluate retrieved evidence and preserve per-query traces."""
from typing import Any


def _normalize_text(text: str) -> str:
    """Chuẩn hóa khoảng trắng và chữ thường để so khớp evidence ổn định."""
    return " ".join(text.split()).lower()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _is_hit(chunk: dict[str, Any], question: dict[str, Any]) -> bool:
    """Kiểm tra chunk có khớp gold_source_id, gold_page và chứa gold evidence không."""
    gold_source = question.get("gold_source_id")
    if gold_source and chunk.get("document_id") != gold_source:
        return False

    gold_pages = set(_as_list(question.get("gold_page")))
    if gold_pages and chunk.get("page") not in gold_pages:
        return False

    quotes = [_normalize_text(q) for q in _as_list(question.get("evidence_quote")) if q]
    if not quotes:
        return False

    chunk_text = _normalize_text(chunk.get("text", ""))
    return any(q in chunk_text for q in quotes)


def _check_filter_compliance(hits: list[dict[str, Any]], flt: dict[str, Any] | None) -> bool | None:
    """Trả về None nếu câu hỏi không có filter; True/False nếu có filter."""
    if not flt:
        return None
    if not hits:
        return False
    for h in hits:
        meta = h.get("metadata") or {}
        if any(meta.get(k) != v for k, v in flt.items()):
            return False
    return True


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and gold evidence; keep hit@1, hit@3 and full top-3 trace."""
    top3 = hits[:3]
    hit_flags = [_is_hit(h, question) for h in top3]

    hit_at_1 = bool(hit_flags[0]) if hit_flags else False
    hit_at_3 = any(hit_flags)
    filter_ok = _check_filter_compliance(top3, question.get("filter"))

    return {
        "question_id": question["id"],
        "split": question["split"],
        "question": question["question"],
        "filter": question.get("filter"),
        "gold_page": question.get("gold_page"),
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "filter_compliant": filter_ok,
        "top_3": [
            {
                "rank": idx + 1,
                "chunk_id": h.get("chunk_id"),
                "page": h.get("page"),
                "score": round(float(h.get("score", 0.0)), 4),
                "is_hit": hit_flags[idx],
                "metadata": h.get("metadata"),
                "text": h.get("text"),
            }
            for idx, h in enumerate(top3)
        ],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and dev/test split."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for t in traces:
        key = (t["strategy"], t["split"])
        grouped.setdefault(key, []).append(t)

    summary: dict[str, Any] = {}
    for (strategy, split), items in sorted(grouped.items()):
        total = len(items)
        h1_cnt = sum(1 for x in items if x["hit_at_1"])
        h3_cnt = sum(1 for x in items if x["hit_at_3"])

        filtered_items = [x for x in items if x["filter_compliant"] is not None]
        if filtered_items:
            flt_ok = sum(1 for x in filtered_items if x["filter_compliant"])
            filter_report: str | None = f"{flt_ok}/{len(filtered_items)} ({flt_ok / len(filtered_items):.1%})"
        else:
            filter_report = "N/A"

        summary[f"{strategy} | {split}"] = {
            "total": total,
            "hit@1": f"{h1_cnt}/{total} ({h1_cnt / total:.1%})" if total else "0/0",
            "hit@3": f"{h3_cnt}/{total} ({h3_cnt / total:.1%})" if total else "0/0",
            "filter_compliance": filter_report,
        }

    return summary