import csv
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Thiết lập encoding UTF-8 cho console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Danh mục 24 Quận / Huyện / TP thuộc TP.HCM chuẩn hóa kèm các phường trọng điểm
DISTRICT_KEYWORDS = {
    "Quận 1": [r"quận 1\b", r"q\.?1\b", r"q 1\b", r"bến thành\b", r"cầu ông lãnh\b", r"đa kao\b", r"tân định\b", r"bến nghé\b", r"nguyễn cư trinh\b", r"phạm ngũ lão\b"],
    "Quận 3": [r"quận 3\b", r"q\.?3\b", r"q 3\b", r"võ thị sáu\b", r"lê văn sỹ\b"],
    "Quận 4": [r"quận 4\b", r"q\.?4\b", r"q 4\b", r"bến vân đồn\b", r"đoàn văn bơ\b"],
    "Quận 5": [r"quận 5\b", r"q\.?5\b", r"q 5\b", r"hải thượng lãn ông\b", r"an đông\b"],
    "Quận 6": [r"quận 6\b", r"q\.?6\b", r"q 6\b", r"bình tây\b", r"hậu giang\b"],
    "Quận 7": [r"quận 7\b", r"q\.?7\b", r"q 7\b", r"tân thuận\b", r"phú mỹ hưng\b", r"tân phong\b", r"tân quy\b", r"tân kiểng\b", r"phú thuận\b", r"nguyễn thị thập\b"],
    "Quận 8": [r"quận 8\b", r"q\.?8\b", r"q 8\b", r"tạ quang bửu\b", r"phạm thế hiển\b"],
    "Quận 10": [r"quận 10\b", r"q\.?10\b", r"q 10\b", r"tô hiến thành\b", r"sư vạn hạnh\b", r"ba tháng hai\b", r"3/2\b"],
    "Quận 11": [r"quận 11\b", r"q\.?11\b", r"q 11\b", r"đầm sen\b", r"lạc long quân\b"],
    "Quận 12": [r"quận 12\b", r"q\.?12\b", r"q 12\b", r"an phú đông\b", r"thạnh lộc\b", r"tân thới hiệp\b", r"tân thới nhất\b"],
    "Bình Thạnh": [r"bình thạnh\b", r"q\.?bình thạnh\b", r"hàng xanh\b", r"thanh đa\b", r"phường 25\b", r"phường 15\b", r"nơ trang long\b", r"điện biên phủ\b"],
    "Gò Vấp": [r"gò vấp\b", r"q\.?gò vấp\b", r"quang trung\b", r"phan văn trị\b", r"nguyễn oanh\b", r"lê đức thọ\b", r"phường 11 gò vấp\b"],
    "Phú Nhuận": [r"phú nhuận\b", r"q\.?phú nhuận\b", r"phan xích long\b", r"hoàng văn thụ\b"],
    "Tân Bình": [r"tân bình\b", r"q\.?tân bình\b", r"cộng hòa\b", r"trường chinh\b", r"sân bay tân sơn nhất\b", r"bàu cát\b"],
    "Tân Phú": [r"tân phú\b", r"q\.?tân phú\b", r"tây thạnh\b", r"tân sơn nhì\b", r"lũy bán bích\b"],
    "Bình Tân": [r"bình tân\b", r"q\.?bình tân\b", r"tên lửa\b", r"an lạc\b", r"bình hưng hòa\b", r"bình trị đông\b"],
    "TP. Thủ Đức": [r"thủ đức\b", r"tp\.?\s*thủ đức\b", r"quận 2\b", r"q\.?2\b", r"quận 9\b", r"q\.?9\b", r"thảo điền\b", r"an khánh\b", r"an phú\b", r"bình trưng\b", r"tăng nhơn phú\b", r"linh trung\b", r"linh chiểu\b", r"hiệp phú\b", r"phước long\b", r"long thạnh mỹ\b"],
    "Nhà Bè": [r"nhà bè\b", r"huyện nhà bè\b", r"phước kiển\b", r"hiệp phước\b", r"phú xuân\b", r"nhơn đức\b", r"nguyễn hữu thọ\b"],
    "Hóc Môn": [r"hóc môn\b", r"huyện hóc môn\b", r"bà điểm\b", r"xuân thới thượng\b", r"tân xuân\b"],
    "Bình Chánh": [r"bình chánh\b", r"huyện bình chánh\b", r"bình hưng\b", r"phong phú\b", r"vĩnh lộc\b", r"trung sơn\b"],
    "Củ Chi": [r"củ chi\b", r"huyện củ chi\b"],
    "Cần Giờ": [r"cần giờ\b", r"huyện cần giờ\b"]
}

def parse_rental_price(price_str: str) -> Optional[float]:
    """
    Quy đổi giá thuê về đơn vị Triệu VNĐ / Tháng (Float).
    Bỏ qua nếu là 'Thương lượng', 'Thỏa thuận' hoặc giá bán ('tỷ').
    """
    if not price_str:
        return None
    s = price_str.lower().strip()
    if any(k in s for k in ["thương lượng", "thỏa thuận", "liên hệ", "chờ cập nhật"]):
        return None
    if "tỷ" in s:
        # Giá bán nhầm lẫn trong dữ liệu thuê
        return None

    # Trường hợp ghi rõ triệu (vd: 3.5 triệu/tháng, 4tr, 5 triệu)
    m_trieu = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:triệu|tr|tr/tháng|triệu/tháng)', s)
    if m_trieu:
        return round(float(m_trieu.group(1).replace(',', '.')), 2)

    # Trường hợp ghi nghìn/k (vd: 800 nghìn, 500k/tháng)
    m_k = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:nghìn|ngàn|k)\b', s)
    if m_k:
        val = float(m_k.group(1).replace(',', '.'))
        return round(val / 1000.0, 3)

    # Trường hợp số trần (vd: 4500000 hoặc 4.5)
    m_num = re.search(r'(\d+(?:[.,]\d+)?)', s)
    if m_num:
        val = float(m_num.group(1).replace(',', '.'))
        if val > 100000:
            return round(val / 1_000_000.0, 2)
        elif val > 0:
            return round(val, 2)

    return None

def parse_area(area_str: str) -> Optional[float]:
    """Bóc tách diện tích sử dụng m2."""
    if not area_str:
        return None
    s = area_str.lower().strip()
    if "liên hệ" in s or "chưa rõ" in s:
        return None
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:m2|m²)', s)
    if m:
        val = float(m.group(1).replace(',', '.'))
        if 5.0 <= val <= 1000.0:  # Ngưỡng diện tích hợp lý
            return round(val, 2)
    return None

def extract_district(location_text: str, title_text: str = "") -> str:
    """Chuẩn hóa Quận/Huyện tại TP.HCM."""
    combined = f"{location_text} {title_text}".lower()
    for dist_name, patterns in DISTRICT_KEYWORDS.items():
        for pat in patterns:
            if re.search(pat, combined):
                return dist_name
    return "Khác"

# Danh mục từ khóa LOẠI BỎ TRIỆT ĐỂ (Kho xưởng, Biệt thự xa xỉ, Văn phòng, Mặt bằng kinh doanh)
COMMERCIAL_AND_LUXURY_BLACKLIST = [
    r"\bkho\b", r"\bxưởng\b", r"kho bãi", r"nhà xưởng", r"\bkcn\b", r"khu công nghiệp",
    r"biệt thự", r"\bvilla\b", r"mặt bằng", r"\bmbkd\b", r"văn phòng", r"\boffice\b",
    r"tòa nhà", r"shophouse", r"bãi xe", r"nhà máy", r"sang quán", r"sang nhượng",
    r"đất nền", r"bán đất", r"bán nhà", r"nghỉ dưỡng", r"resort"
]

NON_HCM_PROVINCES = [
    "bắc ninh", "hà nội", "thanh hóa", "hưng yên", "đồng nai", "bình dương", 
    "long an", "hải phòng", "đà nẵng", "quảng ninh", "thái nguyên", "bắc giang",
    "vĩnh phúc", "hải dương", "hà nam", "nam định", "ninh bình", "nghệ an",
    "bà rịa", "vũng tàu", "tiền giang", "bến tre", "cần thơ", "hòa bình"
]

def categorize_student_property(row: Dict[str, Any]) -> Optional[str]:
    """
    Phân loại chính xác vào DUY NHẤT 1 trong 3 nhóm mục tiêu sinh viên:
    1. phong_tro_ktx: Phòng trọ, ký túc xá, sleepbox, homestay sinh viên.
    2. can_ho: Căn hộ chung cư, chung cư mini (CCMN), căn hộ dịch vụ (CHDV), studio.
    3. nha_nguyen_can: Nhà nguyên căn, nhà riêng.
    Trả về None nếu thuộc kho xưởng, biệt thự, mặt bằng hoặc không thể xác định.
    """
    title = str(row.get("title_raw", "")).lower()
    desc = str(row.get("description_raw", "")).lower()
    raw_type = str(row.get("loai_bds", "")).lower()
    combined = f"{title} {desc} {raw_type}"

    # 1. Kiểm tra blacklist loại trừ ngay lập tức
    if any(re.search(pat, combined) for pat in COMMERCIAL_AND_LUXURY_BLACKLIST):
        # Trường hợp ngoại lệ duy nhất: phòng trọ nằm gần KCN (ví dụ: 'phòng trọ gần KCN Tân Bình')
        is_true_room = any(k in combined for k in ["phòng trọ", "nhà trọ", "ktx", "ký túc xá", "sleepbox", "ở ghép"])
        is_pure_commercial = any(k in combined for k in ["kho xưởng", "kho bãi", "nhà xưởng", "biệt thự", "villa", "mặt bằng kinh doanh", "sang quán", "văn phòng"])
        if is_pure_commercial or not is_true_room:
            return None

    # 2. Khớp chính xác 3 phân khúc mục tiêu
    explicit = str(row.get("property_type_target", "")).strip().lower()
    if explicit in ["phong_tro_ktx", "can_ho", "nha_nguyen_can"]:
        return explicit

    if any(k in combined for k in ["phòng trọ", "nhà trọ", "ktx", "ký túc xá", "sleepbox", "ở ghép", "homestay sinh viên", "phòng cho thuê", "phòng ở"]):
        return "phong_tro_ktx"
    if any(k in combined for k in ["căn hộ", "chung cư", "studio", "ccmn", "chdv", "condotel", "căn 1pn", "căn 2pn"]):
        return "can_ho"
    if any(k in combined for k in ["nguyên căn", "nhà riêng", "nhà cấp 4", "nhà phố cho thuê ở", "thuê nhà ở"]):
        return "nha_nguyen_can"

    return None  # TUYỆT ĐỐI KHÔNG GÁN BỪA BÃI!

def to_int(val: Any) -> Optional[int]:
    """Chuyển đổi an toàn sang int."""
    if val is None or val == "":
        return None
    try:
        return int(float(str(val).strip()))
    except Exception:
        return None

def get_val(row: Dict[str, Any], *aliases: str, default: str = "") -> str:
    """Lấy giá trị từ hàng dữ liệu theo nhiều tên cột (hỗ trợ cả tiếng Anh lẫn tiếng Việt)."""
    for a in aliases:
        if a in row and row[a] is not None:
            v = str(row[a]).strip()
            if v:
                return v
    return default

def standardize_student_rental_dataset(
    input_path: str,
    output_csv: Optional[str] = None,
    output_json: Optional[str] = None
) -> Tuple[str, str, int]:
    """
    Tiến trình làm sạch và chuẩn hóa chuyên biệt cho Bài toán Định giá Thuê trọ Sinh viên (AVM):
    1. Đọc dữ liệu từ file cào thô hoặc file đã qua trích xuất LLM.
    2. Bóc tách giá thuê (Triệu VNĐ/tháng), diện tích (m2), đơn giá (Triệu/m2).
    3. Chuẩn hóa địa lý (Quận/Huyện tại TP.HCM).
    4. Phân nhóm chuẩn 3 loại hình: phong_tro_ktx, can_ho, nha_nguyen_can.
    5. Áp dụng quy tắc nội suy nghiệp vụ (Domain-based Imputation).
    6. Lưu song song bảng dữ liệu huấn luyện CSV và tài liệu đặc tả JSON.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {input_path}")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)
    proc_dir = os.path.join(project_dir, "data", "03_processed")
    os.makedirs(proc_dir, exist_ok=True)

    if output_csv is None:
        output_csv = os.path.join(proc_dir, "gold_student_rental_train.csv")
    if output_json is None:
        output_json = os.path.join(proc_dir, "gold_student_rental_train.json")

    with open(input_path, mode="r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    print("=" * 80)
    print("🧹 CHUẨN HÓA DỮ LIỆU ĐỊNH GIÁ THUÊ TRỌ SINH VIÊN (DATA STANDARDIZATION)")
    print(f"  File đầu vào      : {input_path} ({len(rows)} bản ghi)")
    print(f"  File CSV đầu ra   : {output_csv}")
    print(f"  File JSON đầu ra  : {output_json}")
    print("=" * 80)

    clean_records = []
    summary_stats = {
        "total_input": len(rows),
        "valid_target_rows": 0,
        "dropped_negotiated_price": 0,
        "dropped_missing_area": 0,
        "by_property_type": {},
        "by_district": {}
    }

    for idx, r in enumerate(rows):
        # 1. Bóc tách biến mục tiêu Giá thuê
        price_raw = get_val(r, "price_raw", "Giá thuê", "price", "gia_thue")
        gia_thue = parse_rental_price(price_raw)
        if gia_thue is None:
            summary_stats["dropped_negotiated_price"] += 1
            continue

        # Lọc ngưỡng giá trần sinh viên (tối đa 40 triệu/tháng cho nhóm thuê nhà nguyên căn, trên 40 triệu là biệt thự/kho/toà nhà)
        if gia_thue > 40.0 or gia_thue < 0.5:
            summary_stats["dropped_price_outlier"] = summary_stats.get("dropped_price_outlier", 0) + 1
            continue

        # 2. Bóc tách Diện tích
        area_raw = get_val(r, "area_raw", "Diện tích", "area", "dien_tich")
        dien_tich = parse_area(area_raw)
        if dien_tich is None or dien_tich <= 0 or dien_tich > 350.0:
            summary_stats["dropped_missing_area"] += 1
            continue

        title_raw = get_val(r, "title_raw", "Tiêu đề", "title")
        desc_raw = get_val(r, "description_raw", "Mô tả", "description", "desc")
        url_raw = get_val(r, "url", "Đường dẫn", "link")
        loc_str = get_val(r, "location_raw", "Khu vực", "location", "quan_huyen")

        # Loại bỏ triệt để tin thuộc các tỉnh thành ngoài TP.HCM
        if any(p in loc_str.lower() for p in NON_HCM_PROVINCES):
            summary_stats["dropped_non_hcm_province"] = summary_stats.get("dropped_non_hcm_province", 0) + 1
            continue

        # Đồng bộ lại vào dict để các hàm phụ trợ dùng chung
        r_normalized = dict(r)
        r_normalized["title_raw"] = title_raw
        r_normalized["description_raw"] = desc_raw

        # 3. Phân loại hình mục tiêu (Bắt buộc thuộc 1 trong 3 nhóm, loại thẳng kho xưởng/biệt thự)
        prop_type = categorize_student_property(r_normalized)
        if prop_type is None:
            summary_stats["dropped_commercial_or_villa"] = summary_stats.get("dropped_commercial_or_villa", 0) + 1
            continue

        # 4. Chuẩn hóa Quận/Huyện
        quan_huyen = extract_district(loc_str, title_raw)
        if quan_huyen == "Khác" and not any(k in loc_str.lower() for k in ["hồ chí minh", "tp.hcm", "tphcm", "sài gòn", "hcm"]):
            summary_stats["dropped_non_hcm_province"] = summary_stats.get("dropped_non_hcm_province", 0) + 1
            continue

        summary_stats["by_property_type"][prop_type] = summary_stats["by_property_type"].get(prop_type, 0) + 1
        summary_stats["by_district"][quan_huyen] = summary_stats["by_district"].get(quan_huyen, 0) + 1

        # 5. Bóc tách và nội suy các đặc trưng phòng ốc
        so_pn = to_int(r.get("so_phong_ngu"))
        so_wc = to_int(r.get("so_toilet"))
        has_wc_rieng = to_int(r.get("has_wc_rieng"))
        has_gac = to_int(r.get("has_gac_lung")) or 0
        has_ac = to_int(r.get("has_may_lanh")) or 0
        gio_tu_do = to_int(r.get("gio_tu_do"))
        cho_nau_an = to_int(r.get("cho_nau_an"))
        is_full_nt = to_int(r.get("is_full_furniture")) or 0

        # Domain Imputation:
        # Với phòng trọ/KTX: số phòng ngủ mặc định = 1
        if prop_type == "phong_tro_ktx":
            if so_pn is None:
                so_pn = 1
            if has_wc_rieng is None:
                has_wc_rieng = 1  # Đa số phòng trọ hiện đại có WC riêng
            if so_wc is None:
                so_wc = 1 if has_wc_rieng == 1 else 0

        elif prop_type == "can_ho":
            if so_pn is None:
                so_pn = 1
            if so_wc is None:
                so_wc = 1
            has_wc_rieng = 1  # Căn hộ luôn có WC riêng

        elif prop_type == "nha_nguyen_can":
            if so_pn is None:
                so_pn = 2  # Nhà nguyên căn thường tối thiểu 2 phòng ngủ
            if so_wc is None:
                so_wc = 1
            has_wc_rieng = 1

        # Giờ tự do và Nấu ăn: nếu chưa rõ, gán 1 (sinh viên ưu tiên chọn chỗ tự do)
        if gio_tu_do is None:
            gio_tu_do = 1
        if cho_nau_an is None:
            cho_nau_an = 1

        don_gia_m2 = round((gia_thue * 1000.0) / dien_tich, 2)  # Nghìn VNĐ / m2

        # 6. Đóng gói dòng dữ liệu đã làm sạch
        clean_row = {
            "id": idx + 1,
            "title_raw": title_raw,
            "url": url_raw,
            "quan_huyen": quan_huyen,
            "tinh_thanh": "TP. Hồ Chí Minh",
            "property_type": prop_type,
            "gia_thue_trieu_thang": gia_thue,
            "dien_tich_m2": dien_tich,
            "don_gia_nghin_m2": don_gia_m2,
            "so_phong_ngu": so_pn,
            "so_toilet": so_wc,
            "has_wc_rieng": has_wc_rieng,
            "has_gac_lung": has_gac,
            "has_may_lanh": has_ac,
            "gio_tu_do": gio_tu_do,
            "cho_nau_an": cho_nau_an,
            "is_full_furniture": is_full_nt,
            "source_flag": r.get("parsing_flag", "CLEANED")
        }
        clean_records.append(clean_row)

    summary_stats["valid_target_rows"] = len(clean_records)

    # Xuất file CSV
    if clean_records:
        csv_headers = list(clean_records[0].keys())
        with open(output_csv, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_headers)
            writer.writeheader()
            for row in clean_records:
                writer.writerow(row)

    # Xuất file JSON có cấu trúc
    json_data = {
        "metadata": {
            "title": "Tập dữ liệu Huấn luyện Định giá Thuê trọ Sinh viên TP.HCM (Gold ML Ready)",
            "source_file": os.path.basename(input_path),
            "target_variable": "gia_thue_trieu_thang (Triệu VNĐ/tháng)",
            "summary_statistics": summary_stats,
            "feature_dictionary": {
                "gia_thue_trieu_thang": "Biến mục tiêu liên tục (y): Giá thuê niêm yết tính bằng Triệu VNĐ/tháng",
                "dien_tich_m2": "Diện tích mặt sàn sử dụng (m2)",
                "don_gia_nghin_m2": "Đơn giá thuê tính theo nghìn VNĐ / m2",
                "quan_huyen": "Quận/Huyện thuộc địa bàn TP.HCM",
                "property_type": "Phân khúc (phong_tro_ktx | can_ho | nha_nguyen_can)",
                "so_phong_ngu": "Số phòng ngủ (Int)",
                "so_toilet": "Số nhà vệ sinh/toilet (Int)",
                "has_wc_rieng": "1: WC riêng/khép kín; 0: WC chung",
                "has_gac_lung": "1: Có gác lửng/gác xép; 0: Không",
                "has_may_lanh": "1: Đã trang bị máy lạnh; 0: Không",
                "gio_tu_do": "1: Giờ giấc tự do/khóa vân tay; 0: Có giờ giới nghiêm/chung chủ",
                "cho_nau_an": "1: Cho phép nấu ăn/có khu bếp; 0: Không",
                "is_full_furniture": "1: Đầy đủ nội thất; 0: Phòng trống"
            }
        },
        "records": clean_records
    }

    with open(output_json, mode="w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("✓ QUÁ TRÌNH CHUẨN HÓA DỮ LIỆU HOÀN TẤT!")
    print(f"  • Số bản ghi hợp lệ cho ML       : {len(clean_records)} / {len(rows)}")
    print(f"  • Bỏ qua do giá thương lượng     : {summary_stats['dropped_negotiated_price']}")
    print(f"  • Bỏ qua do thiếu diện tích      : {summary_stats['dropped_missing_area']}")
    print(f"  • File CSV huấn luyện            : {output_csv}")
    print(f"  • File JSON báo cáo đặc tả       : {output_json}")
    print("=" * 80)

    return output_csv, output_json, len(clean_records)

if __name__ == "__main__":
    in_file = sys.argv[1] if len(sys.argv) > 1 else None
    if not in_file:
        # Mặc định tìm file raw trong data/01_raw hoặc file test
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        proj_dir = os.path.dirname(curr_dir)
        candidates = [
            os.path.join(proj_dir, "data", "02_intermediate", "raw_cafeland_thue_hcm_enriched.csv"),
            os.path.join(proj_dir, "data", "01_raw", "raw_cafeland_thue_hcm.csv"),
            os.path.join(proj_dir, "cafeland_chothue_1k_clean.csv"),
            os.path.join(proj_dir, "test", "raw_cafeland_30_newest_hybrid_enriched.csv")
        ]
        for c in candidates:
            if os.path.exists(c):
                in_file = c
                break

    if in_file and os.path.exists(in_file):
        standardize_student_rental_dataset(in_file)
    else:
        print("Vui lòng cung cấp đường dẫn file CSV đầu vào hợp lệ.")
