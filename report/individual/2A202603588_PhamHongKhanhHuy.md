# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline
- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - Chủ đề: Nhập môn Khoa học Máy tính (*Introduction to Computer Science*).
  - Nguồn & quyền: Sách giáo trình mở OpenStax *Introduction to Computer Science* (`starter/data/Introduction_To_Computer_Science_-_WEB.pdf`, giấy phép CC BY / OpenStax).
  - Số trang & quy tắc tính: **34 trang nội dung hữu ích** (trang vật lý `19–52` trong PDF, gồm trọn Chương 1: *Introduction to Computer Science* từ trang `19–48` và phần mở đầu Chương 2: *Computational Thinking and Design Reusability* từ trang `49–52`). Loại bỏ trang bìa, mục lục đầu sách và trang `18` (cuối phần *Preface*).
- **Chuẩn hóa, lỗi và giới hạn:**
  - Đọc PDF bằng `pypdf` (`PdfReader`), chuẩn hóa Unicode dạng `NFC` (`unicodedata.normalize("NFC", text).strip()`), bỏ qua và cảnh báo nếu có trang trống/không trích xuất được text.
  - Giới hạn: `pypdf` đôi khi giữ ngắt dòng đơn `\n` theo bố cục cột/trang của PDF; một số số chú thích chân trang hoặc chú thích hình ảnh (Figure caption) được trích xuất xen lẫn vào mạch văn bản.
- **Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí:**
  - Embedding: OpenAI `text-embedding-3-small`, **1536 chiều** (gọi qua SDK `openai`, batch size = 64).
  - Vector store: PostgreSQL 16 + pgvector (`pgvector/pgvector:0.8.7-pg16` chạy qua Docker Compose tại `127.0.0.1:55433`, database `day6_lab`, bảng `document_chunks` với khóa chính kép `(strategy, chunk_id)` và index `GIN` trên cột `metadata JSONB`).
  - Metric: Cosine distance (`<=>` trong pgvector), quy đổi sang similarity score `1 - (embedding <=> query_vector)`.
  - Lệnh chạy: Từ `starter/`, kích hoạt `.venv`, bật Docker (`docker compose -p day6_student_starter up -d --wait`) và chạy `python -m src.run`.
  - Chi phí: ~\$0.001–\$0.002 USD cho toàn bộ ~45.000–65.000 tokens (2 chiến lược ingest + 20 câu query).
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - Metadata bắt buộc: `document_id`, `source`, `page`, `chunk_id`.
  - Trường lọc bổ sung: `chapter` và `section` (trích xuất chính xác từ mục lục/outline thật của PDF theo từng khoảng trang: `Introduction`, `1.1 Computer Science`, `1.2 Computer Science across the Disciplines`, `1.3 Computer Science and the Future of Society`, `Chapter Review`, `2.1 Computational Thinking`).
  - Lý do chọn: Sách giáo trình có cấu trúc chương/mục rõ ràng; lọc theo `section` giúp thu hẹp phạm vi tìm kiếm khi câu hỏi chỉ định rõ mục cần tra cứu, tránh nhiễu từ phần tóm tắt cuối chương (`Chapter Review`).

## Cấu hình và benchmark
- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):**
  - **A (`A_fixed`):** `fixed_size(size=500, overlap=50)`, không lọc metadata (`filters=None`).
  - **B (`B_paragraph`):** `by_paragraph(max_size=800)` (tách theo đoạn `\n\n`, gom đoạn ngắn, tách đoạn dài tại ranh giới câu/từ), không lọc metadata (`filters=None`).
  - **C (`C_paragraph_filter`):** Dùng chung chunking và vector với **B** (`by_paragraph(max_size=800)`), **khác biệt duy nhất** là áp dụng SQL filter `metadata @> %s::jsonb` khi câu hỏi có trường `filter`.
- **≥20 câu: phân chia ≥15 dev / ≥5 test, câu metadata filter và cách kiểm chứng evidence:**
  - Tổng cộng **20 câu hỏi** (`starter/data/benchmark.json`), chia trước khi chạy benchmark thành **15 `dev`** (`q01`–`q15`) và **5 `test`** (`q16`–`q20`).
  - Có **4 câu kiểm tra metadata filter** (3 câu `dev`: `q08`, `q10`, `q13`; 1 câu `test`: `q19`).
  - Kiểm chứng evidence: Mỗi câu có `gold_page` và `evidence_quote` trích nguyên văn từ text đã đọc của PDF; đã chạy script kiểm tra tự động xác nhận 20/20 câu có `evidence_quote` tồn tại trên đúng `gold_page`.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test:**
  - Ưu tiên **Evidence Hit@3** trên tập `dev`, sau đó đến **tỷ lệ tuân thủ filter** và **tính mạch lạc của chunk (Coherence)**, cuối cùng là chi phí/thời gian ingest.

## Kết quả
| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| `A_fixed` | `dev` | 8/15 (53.3%) | 10/15 (66.7%) | 256 | 4.92s | ~\$0.001 |
| `A_fixed` | `test` | 0/5 (0.0%) | 0/5 (0.0%) | 256 | 4.92s | ~\$0.001 |
| `B_paragraph` | `dev` | 7/15 (46.7%) | 14/15 (93.3%) | 171 | 1.80s | ~\$0.001 |
| `B_paragraph` | `test` | 5/5 (100.0%) | 5/5 (100.0%) | 171 | 1.80s | ~\$0.001 |
| `C_paragraph_filter` | `dev` | 7/15 (46.7%) | 14/15 (93.3%) | 171 *(dùng lại B)* | 0s ingest thêm | \$0 thêm |
| `C_paragraph_filter` | `test` | 5/5 (100.0%) | 5/5 (100.0%) | 171 *(dùng lại B)* | 0s ingest thêm | \$0 thêm |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| `A_fixed` | `0.8 / 2.0` (n=10: 0×2, 8×1, 2×0) | `15/15` (100.0% trên test) | `dev: 2/3 (66.7%)` \| `test: 1/1 (100.0%)` | `0/5/0` — TB `1.0 / 2.0` (n=5 test) |
| `B_paragraph` | `1.9 / 2.0` (n=10: 9×2, 1×1, 0×0) | `15/15` (100.0% trên test) | `dev: 2/3 (66.7%)` \| `test: 1/1 (100.0%)` | `0/0/5` — TB `2.0 / 2.0` (n=5 test) |
| `C_paragraph_filter` | `1.9 / 2.0` (n=10: 9×2, 1×1, 0×0) | `15/15` (100.0% trên test) | `dev: 3/3 (100.0%)` \| `test: 1/1 (100.0%)` | `0/0/5` — TB `2.0 / 2.0` (n=5 test) |

Đường dẫn trace, nhãn thủ công và cách chọn mẫu:
- Trace đầy đủ: `starter/results/traces.json`
- Bảng tổng hợp tự động: `starter/results/summary.json`
- Thống kê ingest: `starter/results/ingestion_stats.json`
- Cách chọn mẫu & lý do chấm thủ công:
  - **Coherence (10 vị trí đầu tiên: chunk đầu của các trang 19–28):** `A_fixed` có 10/10 chunk bị cắt giữa từ/giữa câu (2 chunk đầu trang 21, 24 chỉ là chú thích hình cắt dở = 0 điểm; 8 chunk còn lại giữ được một vài câu hoàn chỉnh trước chỗ cắt = 1 điểm). `B_paragraph` & `C_paragraph_filter` có 9/10 chunk kết thúc trọn câu = 2 điểm, riêng trang 22 dính thêm tiêu đề cuối chunk = 1 điểm.
  - **Metadata & Grounding (5 câu `test`: `q16`–`q20` × top-3 = 15 bản ghi/chiến lược):** Cả 3 chiến lược đều giữ đủ và đúng `page`, `chapter`, `section` (15/15). Về Grounding, `A_fixed` bị cắt đôi định nghĩa/điều kiện giữa các chunk ở cả 5 câu test (phải ghép nhiều chunk mới đủ ý = 1 điểm/câu), trong khi `B` và `C` đều chứa trọn vẹn đoạn bằng chứng ngay ở top-1 (2 điểm/câu).

## Phân tích và kết luận
- **So sánh A–B và B–C; 2 ví dụ sai có ID câu và nguồn:**
  - **A vs B (Chunking):** `B_paragraph` vượt trội `A_fixed` về Evidence Hit@3 trên cả `dev` (14/15 = 93.3% vs 10/15 = 66.7%) và `test` (5/5 = 100.0% vs 0/5 = 0.0%). Ngoài ra `B_paragraph` tạo ít chunk hơn (171 vs 256), không bị dư ký tự lặp do overlap (109.056 vs 120.243 ký tự) và ingest nhanh hơn 2.7 lần (1.80s vs 4.92s).
  - **Ví dụ sai 1 (`q16`, tập `test`, nguồn `Introduction_To_Computer_Science_-_WEB.pdf` trang 22):** `A_fixed` truy xuất đúng trang 22 ở cả top-3 (`[22, 22, 22]`), nhưng vì cắt cứng `size=500` ký tự nên đoạn bằng chứng về George E. Forsythe bị **tách làm đôi qua 2 chunk**, dẫn đến không chunk nào chứa trọn `evidence_quote` (`Hit@3 = False`). Trong khi đó `B_paragraph` giữ trọn đoạn văn nên đạt `Hit@1 = True`.
  - **B vs C (Metadata Filter):** `C_paragraph_filter` giữ nguyên hiệu năng truy xuất của B (`93.3% dev`, `100% test`) nhưng nâng tỷ lệ tuân thủ filter trên `dev` từ **2/3 (66.7%)** lên **3/3 (100.0%)**.
  - **Ví dụ sai 2 (`q10`, tập `dev`, nguồn `Introduction_To_Computer_Science_-_WEB.pdf` trang 32):** Câu hỏi yêu cầu thông tin thuộc mục `1.2 Computer Science across the Disciplines`. Do không lọc, `B_paragraph` trả về trang `32` ở top-1 nhưng top-2 và top-3 lại lẫn sang trang `35` (mục `1.3`) và trang `44` (`Chapter Review`). Khi bật filter ở `C`, các trang ngoài mục `1.2` bị loại bỏ hoàn toàn.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - Chọn **`C_paragraph_filter`**. Đánh đổi: Cần bước gắn metadata `section` chuẩn xác ở khâu ingestion và người dùng/hệ thống phải cung cấp được ngữ cảnh `filter` trước khi truy xuất; khi không có filter, C tự động quay về hành vi của B.
- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí:**
  - Tập `test` nhỏ (5 câu) và số câu có filter ít (4 câu) nên kết quả chỉ mang tính minh họa trên 34 trang giáo trình này, chưa thể suy rộng cho toàn bộ corpus khác. Nhãn thủ công do chính tác giả tự chấm nên có thể tồn tại thiên lệch đánh giá. Thời gian ingest đo qua mạng phụ thuộc độ trễ API tại thời điểm chạy.
- **Nếu làm lại hoặc mở rộng, cải tiến gì?**
  - Làm sạch header/footer lặp lại ở mỗi trang PDF (`Access for free at openstax.org`, số trang in) trước khi chunking để giảm nhiễu vector.
  - Thử nghiệm thêm Hybrid Retrieval (kết hợp dense vector với BM25) cho các câu hỏi định nghĩa ngắn như `q01` (câu mà cả A, B, C đều trượt `Hit@3` trên `dev`).
