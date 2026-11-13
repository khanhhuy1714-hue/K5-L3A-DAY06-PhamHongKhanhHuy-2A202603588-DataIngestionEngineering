"""Pipeline entry point: Ingestion -> Chunking -> Embedding -> PgVectorStore."""
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

from src.ingestion import load_pdf_pages
from src.chunking import fixed_size, by_paragraph
from src.embeddings import MyEmbedder
from src.store import PgVectorStore
from src.models import Chunk, DocumentPage
from src.evaluation import evaluate_query, summarize


PDF_PATH = "data/Introduction_To_Computer_Science_-_WEB.pdf"
RESULTS_DIR = Path("results")


def _attach_section_metadata(pages: list[DocumentPage]) -> list[DocumentPage]:
    """Gắn metadata chapter và section thật dựa trên mục lục PDF."""
    for p in pages:
        if p.page == 18:
            p.metadata["chapter"] = "Preface"
            p.metadata["section"] = "Preface"
        elif 19 <= p.page <= 48:
            p.metadata["chapter"] = "Chapter 1 Introduction to Computer Science"
            if p.page == 19:
                p.metadata["section"] = "Introduction"
            elif 20 <= p.page <= 29:
                p.metadata["section"] = "1.1 Computer Science"
            elif 30 <= p.page <= 34:
                p.metadata["section"] = "1.2 Computer Science across the Disciplines"
            elif 35 <= p.page <= 42:
                p.metadata["section"] = "1.3 Computer Science and the Future of Society"
            else:
                p.metadata["section"] = "Chapter Review"
        else:
            p.metadata["chapter"] = "Chapter 2 Computational Thinking and Design Reusability"
            if p.page == 49:
                p.metadata["section"] = "Introduction"
            else:
                p.metadata["section"] = "2.1 Computational Thinking"
    return pages


def _compute_stats(strategy: str, chunks: list[Chunk], elapsed_sec: float) -> dict:
    """Đo số lượng chunk, phân bố độ dài, tổng ký tự và thời gian ingest."""
    lengths = [len(c.text) for c in chunks]
    return {
        "strategy": strategy,
        "num_chunks": len(chunks),
        "total_chars": sum(lengths),
        "min_chunk_len": min(lengths) if lengths else 0,
        "avg_chunk_len": round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
        "max_chunk_len": max(lengths) if lengths else 0,
        "ingest_seconds": round(elapsed_sec, 2),
    }


def _ingest_strategy(
    strategy_name: str,
    chunks: list[Chunk],
    embedder: MyEmbedder,
    store: PgVectorStore,
) -> dict:
    """Tạo embedding, lưu vào pgvector và trả về thống kê vận hành."""
    t0 = time.perf_counter()
    vectors = embedder.embed_documents([c.text for c in chunks])
    store.upsert(strategy_name, chunks, vectors)
    elapsed = time.perf_counter() - t0
    return _compute_stats(strategy_name, chunks, elapsed)


def main() -> None:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("Missing DATABASE_URL in .env")

    # 1. Ingestion & kiểm tra mốc tối thiểu 30 trang
    pages = load_pdf_pages(PDF_PATH, start_page=19, end_page=52)
    if len(pages) < 30:
        raise ValueError(f"Cần tối thiểu 30 trang nội dung, hiện tại chỉ có {len(pages)} trang.")
    pages = _attach_section_metadata(pages)
    print(f"[1/4] Đã đọc {len(pages)} trang từ {PDF_PATH}")

    # 2. Khởi tạo Embedder và Vector Store
    embedder = MyEmbedder()
    store = PgVectorStore(database_url=database_url, dimensions=embedder.dimensions)
    store.create_schema()
    print(f"[2/4] Kết nối PgVectorStore OK (model={embedder.model_name}, dim={embedder.dimensions})")

    # 3. Chạy ingestion cho Cấu hình A và B (C dùng chung vector với B)
    chunks_a = [c for p in pages for c in fixed_size(p, size=500, overlap=50)]
    chunks_b = [c for p in pages for c in by_paragraph(p, max_size=800)]

    stats = [
        _ingest_strategy("A_fixed", chunks_a, embedder, store),
        _ingest_strategy("B_paragraph", chunks_b, embedder, store),
    ]
    print("[3/4] Hoàn tất ingest A_fixed và B_paragraph:")
    for s in stats:
        print("   ", s)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "ingestion_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 4. Smoke test truy xuất trên cả 3 cấu hình A, B, C
    sample_q = "What is computer science?"
    q_vec = embedder.embed_query(sample_q)
    print(f"\n[4/4] Smoke test truy xuất cho câu hỏi: '{sample_q}'")
    for label, strat, flt in [
        ("A (fixed, no filter)", "A_fixed", None),
        ("B (paragraph, no filter)", "B_paragraph", None),
        ("C (paragraph + filter 1.1)", "B_paragraph", {"section": "1.1 Computer Science"}),
    ]:
        hits = store.search(strat, q_vec, top_k=3, filters=flt)
        top1 = hits[0] if hits else {}
        print(
            f"  - {label}: top1={top1.get('chunk_id')} "
            f"(page={top1.get('page')}, score={top1.get('score', 0):.4f})"
        )

    benchmark_path = Path("data/benchmark.json")
    if benchmark_path.exists():
        questions = json.loads(benchmark_path.read_text(encoding="utf-8"))
        traces: list[dict] = []

        for q in questions:
            q_vec = embedder.embed_query(q["question"])
            for strat_label, db_strat, use_filter in [
                ("A_fixed", "A_fixed", False),
                ("B_paragraph", "B_paragraph", False),
                ("C_paragraph_filter", "B_paragraph", True),
            ]:
                flt = q.get("filter") if use_filter else None
                hits = store.search(db_strat, q_vec, top_k=3, filters=flt)
                trace = evaluate_query(q, hits)
                trace["strategy"] = strat_label
                traces.append(trace)

        report = summarize(traces)
        (RESULTS_DIR / "traces.json").write_text(
            json.dumps(traces, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (RESULTS_DIR / "summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print("\n[5/5] Kết quả Benchmark:")
        for k, v in report.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()