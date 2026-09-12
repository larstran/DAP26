"""
=============================================================================
DỰ ÁN DAP - BÓC TÁCH & CHUẨN HOÁ DỮ LIỆU BẤT ĐỘNG SẢN MUA BÁN (CAFELAND BAN)
=============================================================================
File đầu vào mặc định:
  - C:\\IUH_Industrial University\\Năm 3\\DAP\\crawl\\src\\raw_cafeland_1000.csv
  - hoặc C:\\IUH_Industrial University\\Năm 3\\DAP\\cao_dl\\raw_cafeland_1000.csv

Cột ban đầu gồm 7 trường:
  ['title_raw', 'price_raw', 'area_raw', 'location_raw', 'date_raw', 'description_raw', 'url']

Xử lý NLP và biểu thức chính quy (Regex) trích xuất thành 14 trường chuẩn:
  1. gia              : Numeric (Tỷ VNĐ) - Target y
  2. dien_tich        : Numeric (m²) - Feature
  3. so_phong_ngu     : Integer - Feature
  4. so_phong_ve_sinh : Integer - Feature
  5. loai_hinh        : Categorical (Chung cư / Nhà phố / Đất nền / Biệt thự)
  6. huong_nha        : Categorical (Đông / Tây / Nam / Bắc / Đông Nam / ...)
  7. phap_ly          : Categorical (Sổ hồng / Sổ đỏ / HĐMB / Đang chờ sổ / ...)
  8. phuong_xa        : Categorical (Phường/xã khu vực)
  9. toa_do           : Numeric (để trống nếu không có GPS)
  10. ngay_dang       : Datetime (YYYY-MM-DD)
  11. gia_tren_m2     : Numeric derived (gia / dien_tich)
  12. nguon_du_lieu   : Categorical (CafeLand)
  13. link_goc        : Text (URL gốc)
  14. description_raw : Text (Giữ nguyên mô tả ban đầu)
=============================================================================
"""

import os
import sys
import re
import unicodedata
import pandas as pd
from datetime import datetime, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Từ điển số tiếng Việt
WORD_NUMS = {
    "một": 1, "mot": 1, "mốt": 1,
    "hai": 2,
    "ba": 3,
    "bốn": 4, "bon": 4, "tư": 4, "tu": 4,
    "năm": 5, "nam": 5,
    "sáu": 6, "sau": 6,
    "bảy": 7, "bay": 7,
    "tám": 8, "tam": 8,
    "chín": 9, "chin": 9,
    "mười": 10, "muoi": 10
}

def clean_text(text):
    if not text or pd.isna(text):
        return ""
    # Chuẩn hoá Unicode NFC và xoá khoảng trắng thừa
    s = unicodedata.normalize('NFKC', str(text))
    s = unicodedata.normalize('NFC', s)
    return " ".join(s.split())

def parse_number_token(tok: str):
    tok = tok.strip().lower()
    if tok.isdigit():
        return int(tok)
    if tok in WORD_NUMS:
        return WORD_NUMS[tok]
    return None

def parse_gia(raw: str, desc: str = "") -> str:
    """
    Chuẩn hoá giá về đơn vị TỶ (float dạng chuỗi hoặc số).
    Ví dụ: '10 tỷ 800 triệu' -> '10.8'
           '980 triệu' -> '0.98'
           '1.453.842.000 VNĐ' -> '1.4538'
    """
    targets = [str(raw)]
    if desc and not pd.isna(desc):
        targets.append(str(desc))

    for target in targets:
        if not target or pd.isna(target):
            continue
        s = clean_text(target).lower().replace(",", ".").replace("\xa0", " ")
        if target == targets[0] and ("thỏa thuận" in s or "thương lượng" in s or "liên hệ" in s):
            continue

        ty = 0.0
        found = False

        m_ty = re.search(r"(\d+(?:\.\d+)?)\s*tỷ", s)
        if m_ty:
            ty += float(m_ty.group(1))
            found = True

        m_tr = re.search(r"(\d+(?:\.\d+)?)\s*triệu", s)
        if m_tr:
            ty += float(m_tr.group(1)) / 1000.0
            found = True

        if found and ty > 0:
            return f"{ty:.4f}".rstrip('0').rstrip('.')

        clean_digits = re.sub(r"[^\d]", "", s)
        if clean_digits and len(clean_digits) >= 7:
            val_vnd = float(clean_digits)
            val_ty = val_vnd / 1_000_000_000.0
            return f"{val_ty:.4f}".rstrip('0').rstrip('.')

    return ""

def parse_dien_tich(raw: str, desc: str = "") -> str:
    """
    Trích diện tích m2 từ area_raw hoặc trong description_raw
    """
    if raw and not pd.isna(raw):
        s = clean_text(str(raw)).lower().replace(",", ".")
        if "liên hệ" not in s and "thương lượng" not in s:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m2|m²|mét vuông)?", s)
            if m and float(m.group(1)) > 0:
                return f"{float(m.group(1)):.2f}".rstrip('0').rstrip('.')

    if desc and not pd.isna(desc):
        s_desc = clean_text(str(desc)).lower().replace(",", ".")
        m_desc = re.search(r"(?:diện tích|dt|dtsd|công nhận|cn)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:m2|m²)", s_desc)
        if m_desc:
            return f"{float(m_desc.group(1)):.2f}".rstrip('0').rstrip('.')
        m_nen = re.search(r"(\d+(?:\.\d+)?)\s*(?:m2|m²)", s_desc)
        if m_nen:
            val = float(m_nen.group(1))
            if 10 <= val <= 100000:
                return f"{val:.2f}".rstrip('0').rstrip('.')
    return ""

def parse_so_phong_ngu(text: str) -> str:
    if not text or pd.isna(text):
        return ""
    s = clean_text(str(text)).lower()

    m = re.search(r"(\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s*(?:phòng\s*ngủ|pn\b|phòng\s*nghi|bedroom)", s)
    if m:
        val = parse_number_token(m.group(1))
        if val and 0 < val <= 50:
            return str(val)

    m2 = re.search(r"(?:phòng\s*ngủ|pn)\s*[:=]\s*(\d+)", s)
    if m2:
        val = int(m2.group(1))
        if 0 < val <= 50:
            return str(val)

    m3 = re.search(r"(\d+)\s*pn", s)
    if m3:
        val = int(m3.group(1))
        if 0 < val <= 50:
            return str(val)

    return ""

def parse_so_phong_ve_sinh(text: str) -> str:
    if not text or pd.isna(text):
        return ""
    s = clean_text(str(text)).lower()

    m = re.search(r"(\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s*(?:phòng\s*(?:vệ\s*sinh|tắm)|wc\b|toilet\b|bathroom\b|pvs\b|tolet\b)", s)
    if m:
        val = parse_number_token(m.group(1))
        if val and 0 < val <= 50:
            return str(val)

    m2 = re.search(r"(?:phòng\s*vệ\s*sinh|wc|toilet|pvs)\s*[:=]\s*(\d+)", s)
    if m2:
        val = int(m2.group(1))
        if 0 < val <= 50:
            return str(val)

    m3 = re.search(r"(\d+)\s*(?:wc|toilet|tolet)", s)
    if m3:
        val = int(m3.group(1))
        if 0 < val <= 50:
            return str(val)

    return ""

def parse_loai_hinh(title: str, desc: str) -> str:
    combined = clean_text(f"{str(title)} {str(desc)}").lower()
    if any(k in combined for k in ["chung cư", "căn hộ", "apartment", "condo", "penthouse", "officetel", "tập thể"]):
        return "Chung cư"
    if any(k in combined for k in ["biệt thự", "villa", "dinh thự"]):
        return "Biệt thự"
    if any(k in combined for k in ["đất nền", "đất thổ", "lô đất", "đất phân lô", "thổ cư", "nền đất", "bán đất", "mảnh đất"]):
        return "Đất nền"
    if any(k in combined for k in ["nhà phố", "nhà mặt tiền", "nhà hẻm", "nhà riêng", "nhà cấp 4", "nhà trệt", "nhà 1 trệt", "nhà ống", "shophouse", "liền kề"]):
        return "Nhà phố"
    if "nhà" in combined:
        return "Nhà phố"
    if "đất" in combined:
        return "Đất nền"
    return ""

def parse_huong_nha(text: str) -> str:
    if not text or pd.isna(text):
        return ""
    s = clean_text(str(text)).lower()
    directions = [
        ("đông nam", "Đông Nam"),
        ("đông bắc", "Đông Bắc"),
        ("tây nam", "Tây Nam"),
        ("tây bắc", "Tây Bắc"),
        ("đông", "Đông"),
        ("tây", "Tây"),
        ("nam", "Nam"),
        ("bắc", "Bắc"),
    ]
    for key, val in directions:
        if re.search(rf"(?:hướng|huong)\s*[:=]?\s*{key}\b", s):
            return val
        if re.search(rf"\b{key}\b", s) and ("hướng" in s or "cửa chính" in s or "ban công" in s or "cửa" in s):
            m = re.search(rf"hướng[^,.\n;]{{0,20}}{key}\b", s)
            if m:
                return val
    return ""

def parse_phap_ly(text: str) -> str:
    if not text or pd.isna(text):
        return ""
    s = clean_text(str(text)).lower()
    if "sổ hồng riêng" in s or "shr" in s or "sổ hồng" in s:
        return "Sổ hồng"
    if "sổ đỏ" in s:
        return "Sổ đỏ"
    if "hợp đồng mua bán" in s or "hđmb" in s:
        return "HĐMB"
    if "đang chờ sổ" in s or "chờ sổ" in s:
        return "Đang chờ sổ"
    if "sổ chung" in s or "đồng sở hữu" in s:
        return "Sổ chung"
    if "vi bằng" in s:
        return "Vi bằng"
    if "giấy tờ hợp lệ" in s or "pháp lý chuẩn" in s or "chính chủ" in s:
        return "Sổ hồng"
    return ""

def parse_phuong_xa(location_raw: str, desc: str = "", title: str = "") -> str:
    combined = clean_text(f"{str(location_raw)} {str(desc)} {str(title)}")
    loc = clean_text(str(location_raw)).replace("Vị trí:", "").replace("Vi trí:", "").strip()

    if "gò vấp" in combined.lower():
        m_govap_p = re.search(r"(?:phường|p\.?)\s*([0-9]{1,2}|tân sơn|an nhơn|thông tây hội|hạnh thông tây|bình hưng hòa)\b", combined, re.IGNORECASE)
        if m_govap_p:
            p_name = m_govap_p.group(1).strip()
            return f"Phường {p_name}" if p_name.isdigit() else f"Phường {p_name.title()}"
        return "Gò Vấp"

    parts = [p.strip() for p in loc.split(",") if p.strip()]
    if parts:
        first_part = parts[0]
        if not any(k == first_part.lower() for k in ["tp", "tp.", "thành phố", "tỉnh", "việt nam", "tp. hồ chí minh", "tp.hcm", "hồ chí minh", "hà nội"]):
            return first_part

    m = re.search(r"\b(phường\s+[0-9a-zA-Z_À-ỹ\s]{2,20}?|xã\s+[0-9a-zA-Z_À-ỹ\s]{2,20}?)(?:,|[.\n\-–()]|$)", combined, re.IGNORECASE)
    if m:
        return m.group(1).strip(" ,-(").title()

    return ""

def parse_ngay_dang(date_raw: str) -> str:
    if not date_raw or pd.isna(date_raw):
        return ""
    s = clean_text(str(date_raw)).lower().replace("cập nhật:", "").strip()
    base_date = datetime(2026, 9, 12)

    if "hôm nay" in s or "today" in s or "vừa xong" in s or "giờ trước" in s or "phút trước" in s:
        return base_date.strftime("%Y-%m-%d")

    m_ngay = re.search(r"(\d+)\s*ngày\s*trước", s)
    if m_ngay:
        days = int(m_ngay.group(1))
        d = base_date - timedelta(days=days)
        return d.strftime("%Y-%m-%d")

    m_tuan = re.search(r"(\d+)\s*tuần\s*trước", s)
    if m_tuan:
        weeks = int(m_tuan.group(1))
        d = base_date - timedelta(weeks=weeks)
        return d.strftime("%Y-%m-%d")

    m_thang = re.search(r"(\d+)\s*tháng\s*trước", s)
    if m_thang:
        months = int(m_thang.group(1))
        d = base_date - timedelta(days=months * 30)
        return d.strftime("%Y-%m-%d")

    m_date = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if m_date:
        d, mo, y = m_date.group(1), m_date.group(2), m_date.group(3)
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    return s

def compute_gia_tren_m2(gia_str: str, dt_str: str) -> str:
    try:
        if gia_str and dt_str:
            g = float(gia_str)
            dt = float(dt_str)
            if g > 0 and dt > 0:
                val = g / dt
                return f"{val:.6f}".rstrip('0').rstrip('.')
    except Exception:
        pass
    return ""

def process_cafeland_ban(input_path: str, output_path: str = None):
    if not output_path:
        output_path = input_path.replace(".csv", "_processed.csv")

    print(f"[XỬ LÝ DỮ LIỆU BÁN CAFELAND]")
    print(f"  Input : {input_path}")
    print(f"  Output: {output_path}")

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    print(f"  Tổng số dòng: {len(df)}")

    processed_rows = []
    for idx, row in df.iterrows():
        title = clean_text(row.get("title_raw", ""))
        price_raw = clean_text(row.get("price_raw", ""))
        area_raw = clean_text(row.get("area_raw", ""))
        loc_raw = clean_text(row.get("location_raw", ""))
        date_raw = clean_text(row.get("date_raw", ""))
        desc_raw = clean_text(row.get("description_raw", ""))
        url = clean_text(row.get("url", ""))

        combined_desc = f"{title}. {desc_raw}"

        gia_val = parse_gia(price_raw, desc_raw)
        dt_val = parse_dien_tich(area_raw, desc_raw)
        spn_val = parse_so_phong_ngu(combined_desc)
        spvs_val = parse_so_phong_ve_sinh(combined_desc)
        lh_val = parse_loai_hinh(title, desc_raw)
        hn_val = parse_huong_nha(combined_desc)
        pl_val = parse_phap_ly(combined_desc)
        px_val = parse_phuong_xa(loc_raw, desc_raw, title)
        toa_do_val = ""
        nd_val = parse_ngay_dang(date_raw)
        gtm2_val = compute_gia_tren_m2(gia_val, dt_val)
        nguon_val = "CafeLand"
        link_val = url

        rec = {
            "gia": gia_val,
            "dien_tich": dt_val,
            "so_phong_ngu": spn_val,
            "so_phong_ve_sinh": spvs_val,
            "loai_hinh": lh_val,
            "huong_nha": hn_val,
            "phap_ly": pl_val,
            "phuong_xa": px_val,
            "toa_do": toa_do_val,
            "ngay_dang": nd_val,
            "gia_tren_m2": gtm2_val,
            "nguon_du_lieu": nguon_val,
            "link_goc": link_val,
            "description_raw": row.get("description_raw", "")
        }
        processed_rows.append(rec)

    df_out = pd.DataFrame(processed_rows)
    try:
        df_out.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"  --> Hoàn tất! Lưu thành công tại: {output_path}")
    except PermissionError:
        fallback_path = output_path.replace(".csv", "_new.csv")
        df_out.to_csv(fallback_path, index=False, encoding="utf-8-sig")
        print(f"  [Lưu ý] File đích đang mở trong Excel/ứng dụng khác. Đã lưu tại: {fallback_path}")

    # In thống kê
    print("\n--- THỐNG KÊ CÁC TRƯỜNG DỮ LIỆU ---")
    for col in df_out.columns:
        cnt = (df_out[col] != "").sum()
        print(f"  {col:<20}: {cnt}/{len(df_out)} giá trị có dữ liệu")
    return df_out

if __name__ == "__main__":
    default_in = r"C:\IUH_Industrial University\Năm 3\DAP\crawl\src\raw_cafeland_1000.csv"
    if len(sys.argv) > 1:
        default_in = sys.argv[1]
    process_cafeland_ban(default_in)
