# Kiến Trúc Mã Nguồn & Kho Dữ Liệu: Định Giá Bất Động Sản Thuê Trọ Sinh Viên TP.HCM

> **Đề tài**: Xây dựng Mô hình Tự động Định giá BĐS (AVM) và Nhận diện Lệch chuẩn Giá trị Thuê trọ Sinh viên tại TP.HCM  
> **Phạm vi**: Toàn TP.HCM | **Biến mục tiêu ($y$)**: `gia_thue_trieu_thang` (Triệu VNĐ/tháng)  
> **3 Nhóm hình thức**: `phong_tro_ktx`, `can_ho`, `nha_nguyen_can`

---

## 1. Cấu Trúc Dự Án Hoàn Chỉnh

```
final_project/
├── data/
│   ├── 01_raw/                             # Dữ liệu cào thô (CSV) từ CafeLand
│   │   └── raw_cafeland_thue_hcm.csv
│   ├── 02_intermediate/                    # Dữ liệu đã làm giàu qua Hybrid LLM
│   │   ├── cafeland_enriched.csv
│   │   ├── cafeland_enriched.json
│   │   └── cafeland_enriched_checkpoint.json
│   └── 03_processed/                       # Tập dữ liệu vàng chuẩn hóa sẵn sàng cho ML
│       ├── gold_student_rental_train.csv   # Dữ liệu dạng bảng cho mô hình hồi quy
│       └── gold_student_rental_train.json  # Dữ liệu JSON kèm metadata & đặc tả biến
└── src/
    ├── .env                                # Khóa API bí mật cục bộ (được bảo vệ bởi .gitignore, KHÔNG commit)
    ├── .env.example                        # Mẫu cấu hình môi trường chuẩn để commit lên Git
    ├── .gitignore                          # Bộ quy tắc chặn commit secrets, cache, checkpoints
    ├── config.example.json                 # Cấu hình JSON mẫu không chứa khóa nhạy cảm
    ├── config.json                         # Cấu hình cục bộ (tùy chọn / fallback, nằm trong .gitignore)
    ├── requirements.txt                    # Danh mục gói phụ thuộc chuẩn (requests, beautifulsoup4, python-dotenv)
    ├── crawler_rental.py                   # Bộ cào dữ liệu chuyên sâu cho BĐS thuê TP.HCM
    ├── llm_extractor.py                    # Trích xuất tiện ích sinh viên 2 giai đoạn (Regex + Mega-Batch LLM)
    ├── standardize_data.py                 # Chuẩn hóa giá thuê, diện tích, quận huyện & nội suy nghiệp vụ
    └── main.py                             # Điều phối toàn bộ pipeline (CLI tương tác & tham số)
```

## 2. Chi Tiết Các Mô-đun Trong `src/`

### 2.1. Quản Trị Bảo Mật & Cấu Hình Môi Trường ([`.env`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/.env) & [`.gitignore`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/.gitignore))
- **Bảo mật API Key**: API Key được tách hoàn toàn ra khỏi mã nguồn và quản lý qua biến môi trường `GEMINI_API_KEY`, `GEMINI_MODEL` trong file [`.env`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/.env).
- **Chia sẻ an toàn**: File [`.env.example`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/.env.example) và [`config.example.json`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/config.example.json) được dùng làm mẫu khi làm việc nhóm hoặc đưa lên repository công khai.
- **Chống rò rỉ (Git Leak Prevention)**: File [`.gitignore`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/.gitignore) loại trừ triệt để `.env`, `config.json`, bytecache `__pycache__/`, tệp tạm và checkpoint.
- **Cơ chế nạp thông minh**: [`llm_extractor.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/llm_extractor.py) tự động nạp từ [`.env`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/.env) và hỗ trợ fallback về [`config.json`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/config.json) nhằm bảo toàn tính tương thích ngược 100%. Đồng thời, xác thực API key qua Header bảo mật `x-goog-api-key` để tránh rò rỉ trong log URL.

### 2.2. [`src/crawler_rental.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/crawler_rental.py)
- **Mục tiêu**: Bóc tách bài đăng từ danh mục BĐS Cho Thuê TP.HCM trên CafeLand (`https://nhadat.cafeland.vn/cho-thue-nha-dat/tp-ho-chi-minh/`).
- **2 Chế độ cào**:
  - `crawl_rental_summary`: Cào nhanh 7 trường từ thẻ tin (Listing Cards) để quét số lượng lớn.
  - `crawl_rental_detailed`: Cào sâu 20 trường thông tin chi tiết bằng đa luồng `ThreadPoolExecutor` với connection pool và auto-retry.
- **Thư mục xuất mặc định**: `data/01_raw/`.

### 2.3. [`src/llm_extractor.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/llm_extractor.py)
- **Kiến trúc Two-Stage Hybrid (2-Pass)** tối ưu triệt để hạn mức thử nghiệm (20 RPD / 250k TPM):
  - **Pass 1 (Regex Triage)**: Tự động phân loại cờ `DONE_REGEX`, `SKIP_NON_RENTAL` (loại bỏ mặt bằng buôn bán, kho bãi) và `NEEDS_LLM` (tiêu tốn 0 token API).
  - **Pass 2 (Mega-Batch LLM)**: Đóng gói 100-500 bài/request dưới định dạng Key-Value ID nhằm loại bỏ 100% rủi ro lệch dòng (Index Drift).
- **Trích xuất đặc trưng sinh viên**: `has_wc_rieng`, `has_gac_lung`, `has_may_lanh`, `gio_tu_do`, `cho_nau_an`, `is_full_furniture`, `property_type_target`.
- **Cơ chế Checkpoint**: Tự động lưu checkpoint đĩa `*_checkpoint.json` sau mỗi batch để không mất dữ liệu hay lãng phí quota khi bị gián đoạn mạng.
- **Thư mục xuất**: `data/02_intermediate/`.

### 2.4. [`src/standardize_data.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/standardize_data.py)
- **Chuẩn hóa giá trị định lượng**:
  - `gia_thue_trieu_thang`: Quy đổi mọi mệnh giá ("3.5 triệu/tháng", "500k", "12tr") về float Triệu VNĐ/tháng. Gán `null` và loại bỏ tin thương lượng/giá bán ("tỷ").
  - `dien_tich_m2` & `don_gia_nghin_m2`: Tính đơn giá m2 mặt sàn.
- **Chuẩn hóa địa lý**: Phân tích từ khóa và ánh xạ các phường trọng điểm ("Bến Thành", "Thảo Điền", "Tăng Nhơn Phú",...) về đúng Quận/Huyện/TP tại TP.HCM.
- **Nội suy nghiệp vụ (Domain-based Imputation)**:
  - Phòng trọ/KTX: Mặc định `so_phong_ngu = 1`. Nếu có `has_wc_rieng == 1`, gán `so_toilet = 1`.
  - Căn hộ: Mặc định `so_phong_ngu = 1` (nếu là studio/mini) và `so_toilet = 1`, `has_wc_rieng = 1`.
  - Nhà nguyên căn: Mặc định `so_phong_ngu = 2` nếu thiếu số lượng.
- **Thư mục xuất**: `data/03_processed/gold_student_rental_train.csv` và `.json`.

### 2.5. [`src/main.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/main.py)
- Trình điều phối trung tâm hỗ trợ cả **giao diện dòng lệnh tương tác** lẫn **tham số CLI**:
  - `python main.py --step status`: Kiểm tra tình trạng kho dữ liệu `data/`.
  - `python main.py --step crawl_detail --count 100`: Cào 100 bài thuê chi tiết.
  - `python main.py --step enrich --input <file_csv>`: Làm giàu thuộc tính bằng LLM.
  - `python main.py --step standardize --input <file_csv>`: Làm sạch và chuẩn hóa sang tập vàng huấn luyện.
  - `python main.py --step pipeline --count 100`: Chạy tự động khép kín toàn bộ quy trình.

---

## 3. Trạng Thái Kiểm Thử Cú Pháp (py_compile)

Tất cả các file mã nguồn đã được biên dịch cú pháp thành công 100% với Python 3.13 trên hệ điều hành Windows:
```powershell
cmd /c "python -m py_compile src/crawler_rental.py src/llm_extractor.py src/standardize_data.py src/main.py"
# Exited with code 0 (No syntax errors)
```
