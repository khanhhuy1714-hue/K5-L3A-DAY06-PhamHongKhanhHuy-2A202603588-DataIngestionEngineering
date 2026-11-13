import unicodedata
from pathlib import Path
from pypdf import PdfReader
from src.models import DocumentPage


def load_pdf_pages(pdf_path: str, start_page: int = 18, end_page: int = 48) -> list[DocumentPage]:
    """
    Đọc các trang từ start_page đến end_page (theo số trang 1-based trên PDF viewer).
    """
    path = Path(pdf_path)
    reader = PdfReader(path)
    total_pages = len(reader.pages)

    if start_page < 1 or end_page > total_pages or start_page > end_page:
        raise ValueError(f"Khoảng trang không hợp lệ ({start_page}-{end_page}), tổng số trang: {total_pages}")

    documents: list[DocumentPage] = []
    for idx in range(start_page - 1, end_page):
        page_num = idx + 1
        raw_text = reader.pages[idx].extract_text() or ""
        normalized_text = unicodedata.normalize("NFC", raw_text).strip()

        if not normalized_text:
            print(f"[WARNING] Trang {page_num} không trích xuất được text (trang trống hoặc scan).")
            continue

        documents.append(
            DocumentPage(
                document_id=path.stem,
                source=path.name,
                page=page_num,
                text=normalized_text,
                metadata={"total_pages": total_pages},
            )
        )

    return documents


if __name__ == "__main__":
    pages = load_pdf_pages("data/Introduction_To_Computer_Science_-_WEB.pdf", start_page=18, end_page=48)
    print(f"Đã đọc thành công {len(pages)} trang.")
    print("Mẫu trang đầu tiên:", pages[0].page, "-", pages[0].text[:200])