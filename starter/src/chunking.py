"""Implement fixed-size and structure-aware chunking."""
import re
from .models import Chunk, DocumentPage


def _make_chunk(
    page: DocumentPage,
    strategy: str,
    index: int,
    text: str,
) -> Chunk:
    """Helper tạo Chunk với ID ổn định và giữ nguyên metadata truy vết."""
    return Chunk(
        chunk_id=f"{page.document_id}_p{page.page}_{strategy}_{index}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text.strip(),
        metadata={**page.metadata, "strategy": strategy, "chunk_index": index},
    )


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Split text into overlapping windows and retain page metadata."""
    if size <= 0:
        raise ValueError("size must be > 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")

    text = page.text.strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    idx = 0

    while start < len(text):
        end = start + size
        piece = text[start:end].strip()
        if piece:
            chunks.append(_make_chunk(page, "fixed", idx, piece))
            idx += 1
        if end >= len(text):
            break
        start += step

    return chunks


def _split_oversized_text(text: str, max_size: int) -> list[str]:
    """Tách đoạn quá dài, ưu tiên ngắt ở dấu câu hoặc khoảng trắng."""
    parts: list[str] = []
    remaining = text.strip()

    while len(remaining) > max_size:
        window = remaining[:max_size]
        # Ưu tiên cắt ở dấu chấm câu gần cuối, nếu không có thì cắt ở khoảng trắng
        split_at = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        if split_at != -1 and split_at > max_size // 2:
            split_at += 1  # giữ lại dấu câu ở chunk hiện tại
        else:
            split_at = window.rfind(" ")
            if split_at <= 0:
                split_at = max_size

        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        parts.append(remaining)
    return parts


def by_paragraph(page: DocumentPage, max_size: int = 800) -> list[Chunk]:
    """Group paragraphs, split oversized paragraphs and retain metadata."""
    if max_size <= 0:
        raise ValueError("max_size must be > 0")

    text = page.text.strip()
    if not text:
        return []

    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    # Chuẩn hóa: tách nhỏ trước những đoạn đơn lẻ vượt quá max_size
    normalized_units: list[str] = []
    for para in raw_paragraphs:
        if len(para) <= max_size:
            normalized_units.append(para)
        else:
            normalized_units.extend(_split_oversized_text(para, max_size))

    # Gom các đoạn ngắn liên tiếp lại sao cho tổng độ dài <= max_size
    grouped_texts: list[str] = []
    buffer = ""
    for unit in normalized_units:
        if not buffer:
            buffer = unit
        elif len(buffer) + 2 + len(unit) <= max_size:
            buffer = f"{buffer}\n\n{unit}"
        else:
            grouped_texts.append(buffer)
            buffer = unit
    if buffer:
        grouped_texts.append(buffer)

    return [_make_chunk(page, "paragraph", idx, chunk_text) for idx, chunk_text in enumerate(grouped_texts)]