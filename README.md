# Hệ Thống Tự Động Định Giá BĐS Thuê Trọ Sinh Viên (AVM TP.HCM)
> **Môn học**: Lập trình Phân tích Dữ liệu (DAP / 2101681) - Final Project  
> **Phạm vi**: Toàn TP.HCM | **Biến mục tiêu ($y$)**: `gia_thue_trieu_thang` (Triệu VNĐ/tháng)  
> **3 Nhóm hình thức**: `phong_tro_ktx`, `can_ho`, `nha_nguyen_can`

---

## 1. Cấu Trúc Thư Mục Dự Án

```text
final_project/
├── README.md                               # Hướng dẫn toàn diện dự án
├── GUIDE.md                                # Hướng dẫn nghiệp vụ định giá
├── chi_dan.md                              # Ghi chú & chỉ dẫn thực hiện
├── CRAWLER_GUIDE.md                        # Hướng dẫn chi tiết kỹ thuật cào
├── data/
│   ├── 01_raw/                             # Dữ liệu cào thô (CSV) từ CafeLand
│   ├── 02_intermediate/                    # Dữ liệu đã làm giàu qua Hybrid LLM (CSV, JSON, Checkpoint)
│   └── 03_processed/                       # Tập dữ liệu vàng chuẩn hóa sẵn sàng cho ML
│       ├── gold_student_rental_train.csv   # Bảng dữ liệu huấn luyện (593+ dòng)
│       └── gold_student_rental_train.json  # Dữ liệu JSON kèm metadata & đặc tả biến
└── src/
    ├── .env.example                        # Mẫu cấu hình Gemini API Key (sao chép thành .env khi chạy)
    ├── config.example.json                 # Cấu hình JSON mẫu không chứa khóa bí mật
    ├── crawler_rental.py                   # Bộ cào dữ liệu thuê trọ TP.HCM (Summary & Detail)
    ├── llm_extractor.py                    # Trích xuất tiện ích sinh viên (Regex + Mega-Batch LLM)
    ├── standardize_data.py                 # Chuẩn hóa giá thuê, diện tích, quận huyện & nội suy
    └── main.py                             # Điều phối toàn bộ pipeline (CLI & tương tác)
```

---

## 2. Hướng Dẫn Sử Dụng Nhanh

Mở Terminal tại thư mục `src/`:
```cmd
cd src
```

### Cách 1: Giao diện dòng lệnh tương tác (Menu CLI)
```cmd
cmd /c python main.py
```
Hệ thống sẽ hiển thị menu tương tác từ `1` đến `6` để bạn chọn thao tác (Cào tóm tắt, Cào chi tiết, Làm giàu LLM, Chuẩn hóa dữ liệu, Xem tình trạng kho dữ liệu).

### Cách 2: Chạy trực tiếp từng bước qua tham số CLI
* **Kiểm tra tình trạng kho dữ liệu `data/`**:
  ```cmd
  cmd /c python main.py --step status
  ```
* **Cào sâu 100 tin thuê trọ chi tiết vào `data/01_raw/`**:
  ```cmd
  cmd /c python main.py --step crawl_detail --count 100
  ```
* **Làm giàu tiện ích sinh viên bằng Two-Stage Hybrid LLM**:
  ```cmd
  cmd /c python main.py --step enrich
  ```
* **Làm sạch và xuất tập dữ liệu vàng vào `data/03_processed/`**:
  ```cmd
  cmd /c python main.py --step standardize
  ```
* **Chạy tự động liên hoàn từ cào đến ra tập dữ liệu ML hoàn chỉnh**:
  ```cmd
  cmd /c python main.py --step pipeline --count 100
  ```

---

## 3. Đặc Tả Các Biến Dữ Liệu Huấn Luyện (Gold Features)

| Tên biến | Kiểu | Ý nghĩa định giá sinh viên |
| :--- | :--- | :--- |
| `gia_thue_trieu_thang` | `Float` | **Biến mục tiêu ($y$)**: Giá thuê hàng tháng (Triệu VNĐ/tháng) |
| `dien_tich_m2` | `Float` | Diện tích mặt sàn sử dụng ($m^2$) |
| `don_gia_nghin_m2` | `Float` | Đơn giá thuê ($1.000$ VNĐ / $m^2$) |
| `quan_huyen` | `Category` | Quận/Huyện thuộc địa bàn TP.HCM |
| `property_type` | `Category` | 1 trong 3 loại: `phong_tro_ktx`, `can_ho`, `nha_nguyen_can` |
| `so_phong_ngu` | `Integer` | Số phòng ngủ (Phòng trọ / Studio mặc định = 1) |
| `so_toilet` | `Integer` | Số nhà vệ sinh / WC |
| `has_wc_rieng` | `Binary (0/1)`| 1: WC riêng/khép kín; 0: WC chung dãy/tầng |
| `has_gac_lung` | `Binary (0/1)`| 1: Có gác lửng/gác xép tăng diện tích; 0: Không |
| `has_may_lanh` | `Binary (0/1)`| 1: Đã lắp máy lạnh; 0: Không |
| `gio_tu_do` | `Binary (0/1)`| 1: Giờ giấc tự do/khóa vân tay; 0: Chung chủ/giới nghiêm |
| `cho_nau_an` | `Binary (0/1)`| 1: Cho phép nấu ăn/có khu bếp; 0: Không |
| `is_full_furniture` | `Binary (0/1)`| 1: Đầy đủ nội thất (giường, tủ, lạnh); 0: Phòng trống |
