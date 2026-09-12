"""
=============================================================================
DỰ ÁN DAP - BÓC TÁCH & CHUẨN HOÁ DỮ LIỆU BẤT ĐỘNG SẢN CHO THUÊ (CAFELAND THUÊ)
=============================================================================
File đầu vào:
  C:\\IUH_Industrial University\\Năm 3\\Xử lý ảnh\\cafeland_chothue_1k_clean.csv

Cột ban đầu gồm 8 trường:
  ['STT', 'Tiêu đề', 'Giá thuê', 'Diện tích', 'Khu vực', 'Ngày cập nhật', 'Mô tả', 'Đường dẫn']

Giữ nguyên các cột cũ và bổ sung 13 trường chuẩn mới trích xuất từ Mô tả:
  - gia               : Numeric (Tỷ VNĐ) - Target y
  - dien_tich         : Numeric (m²) - Feature
  - so_phong_ngu      : Integer - Feature
  - so_phong_ve_sinh  : Integer - Feature
  - loai_hinh         : Categorical (Chung cư / Nhà phố / Đất nền / Biệt thự)
  - huong_nha         : Categorical (Đông / Tây / Nam / Bắc / ...)
  - phap_ly           : Categorical (Sổ hồng / Sổ đỏ / HĐMB / ...)
  - phuong_xa         : Categorical (Phường/xã khu vực)
  - toa_do (lat/long) : Numeric (độ) - để trống nếu không có GPS
  - ngay_dang         : Datetime (YYYY-MM-DD)
  - gia_tren_m2       : Numeric derived (gia / dien_tich)
  - nguon_du_lieu     : Categorical (CafeLand)
  - link_goc          : Text (URL gốc)
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
    # Chuẩn hoá Unicode NFKC & NFC để bóc tách chính xác ký tự toán học/in đậm
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

def parse_gia(gia_thue: str, desc: str = "") -> str:
    targets = [str(gia_thue)]
    if desc and not pd.isna(desc):
        targets.append(str(desc))

    for raw in targets:
        if not raw or pd.isna(raw):
            continue
        s = clean_text(raw).lower().replace(",", ".").replace("\xa0", " ")
        if raw == targets[0] and ("thương lượng" in s or "thỏa thuận" in s or "liên hệ" in s):
            continue

        ty = 0.0
        found = False

        m_ty = re.search(r"(\d+(?:\.\d+)?)\s*tỷ", s)
        if m_ty:
            ty += float(m_ty.group(1))
            found = True

        m_tr = re.search(r"(\d+(?:\.\d+)?)\s*(?:triệu|tr\b)", s)
        if m_tr:
            val_tr = float(m_tr.group(1))
            if val_tr > 0:
                ty += val_tr / 1000.0
                found = True

        if found and ty > 0:
            return f"{ty:.6f}".rstrip('0').rstrip('.')

        m_vnd = re.search(r"(\d{1,3}(?:\.\d{3})+)\s*(?:đ|vnd|vnđ)", s)
        if m_vnd:
            digits = m_vnd.group(1).replace(".", "")
            val_ty = float(digits) / 1_000_000_000.0
            return f"{val_ty:.6f}".rstrip('0').rstrip('.')

    return ""

def parse_dien_tich(dt_raw: str, desc: str = "") -> str:
    if dt_raw and not pd.isna(dt_raw):
        s = clean_text(str(dt_raw)).lower().replace(",", ".")
        if "liên hệ" not in s and "thương lượng" not in s:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m2|m²)?", s)
            if m and float(m.group(1)) > 0:
                return f"{float(m.group(1)):.2f}".rstrip('0').rstrip('.')

    if desc and not pd.isna(desc):
        s_desc = clean_text(str(desc)).lower().replace(",", ".")
        m_desc = re.search(r"(?:diện tích|dt|dtsd|công nhận|cn)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:m2|m²)", s_desc)
        if m_desc:
            return f"{float(m_desc.group(1)):.2f}".rstrip('0').rstrip('.')
        m_m2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:m2|m²)", s_desc)
        if m_m2:
            val = float(m_m2.group(1))
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
    if any(k in combined for k in ["chung cư", "căn hộ", "apartment", "condo", "penthouse", "officetel", "tập thể", "phòng trọ", "phòng cao cấp", "phòng cho thuê", "studio"]):
        return "Chung cư"
    if any(k in combined for k in ["biệt thự", "villa", "dinh thự"]):
        return "Biệt thự"
    if any(k in combined for k in ["đất nền", "đất thổ", "lô đất", "đất phân lô", "thổ cư", "nền đất", "bán đất", "mảnh đất", "kho bãi", "kho logistics", "kho xưởng", "nhà xưởng", "mặt bằng", "kho"]):
        return "Đất nền"
    if any(k in combined for k in ["nhà phố", "nhà mặt tiền", "nhà hẻm", "nhà riêng", "nhà nguyên căn", "nhà cấp 4", "nhà trệt", "shophouse", "liền kề", "tòa nhà"]):
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
    if "hợp đồng mua bán" in s or "hđmb" in s or "hợp đồng thuê" in s or "hợp đồng dài hạn" in s or "hđ thuê" in s:
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
        m_govap_p = re.search(r"(?:phường|p\.?)\s*([0-9]{1,2}|tân sơn|an nhơn|thông tây hội|hạnh thông tây)\b", combined, re.IGNORECASE)
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

def process_cafeland_chothue(input_path: str, output_path: str = None):
    if not output_path:
        output_path = input_path.replace(".csv", "_processed.csv")

    print(f"[XỬ LÝ DỮ LIỆU CHO THUÊ CAFELAND]")
    print(f"  Input : {input_path}")
    print(f"  Output: {output_path}")

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    print(f"  Tổng số dòng: {len(df)}")

    gias = []
    dien_tichs = []
    so_phong_ngus = []
    so_phong_ve_sinhs = []
    loai_hinhs = []
    huong_nhas = []
    phap_lys = []
    phuong_xas = []
    toa_dos = []
    ngay_dangs = []
    gia_tren_m2s = []
    nguon_du_lieus = []
    link_gocs = []

    for _, row in df.iterrows():
        title = clean_text(row.get("Tiêu đề", ""))
        price_raw = clean_text(row.get("Giá thuê", ""))
        dt_raw = clean_text(row.get("Diện tích", ""))
        loc_raw = clean_text(row.get("Khu vực", ""))
        date_raw = clean_text(row.get("Ngày cập nhật", ""))
        desc_raw = clean_text(row.get("Mô tả", ""))
        url_raw = clean_text(row.get("Đường dẫn", ""))

        combined_desc = f"{title}. {desc_raw}"

        g_val = parse_gia(price_raw, desc_raw)
        gias.append(g_val)

        dt_val = parse_dien_tich(dt_raw, desc_raw)
        dien_tichs.append(dt_val)

        spn_val = parse_so_phong_ngu(combined_desc)
        so_phong_ngus.append(spn_val)

        spvs_val = parse_so_phong_ve_sinh(combined_desc)
        so_phong_ve_sinhs.append(spvs_val)

        lh_val = parse_loai_hinh(title, desc_raw)
        loai_hinhs.append(lh_val)

        hn_val = parse_huong_nha(combined_desc)
        huong_nhas.append(hn_val)

        pl_val = parse_phap_ly(combined_desc)
        phap_lys.append(pl_val)

        px_val = parse_phuong_xa(loc_raw, desc_raw, title)
        phuong_xas.append(px_val)

        toa_dos.append("")

        nd_val = parse_ngay_dang(date_raw)
        ngay_dangs.append(nd_val)

        gtm2_val = compute_gia_tren_m2(g_val, dt_val)
        gia_tren_m2s.append(gtm2_val)

        nguon_du_lieus.append("CafeLand")
        link_gocs.append(url_raw)

    # Giữ nguyên 8 cột ban đầu
    base_cols = ['STT', 'Tiêu đề', 'Giá thuê', 'Diện tích', 'Khu vực', 'Ngày cập nhật', 'Mô tả', 'Đường dẫn']
    existing_base = [c for c in base_cols if c in df.columns]
    df_out = df[existing_base].copy() if existing_base else df.copy()

    df_out["gia"] = gias
    df_out["dien_tich"] = dien_tichs
    df_out["so_phong_ngu"] = so_phong_ngus
    df_out["so_phong_ve_sinh"] = so_phong_ve_sinhs
    df_out["loai_hinh"] = loai_hinhs
    df_out["huong_nha"] = huong_nhas
    df_out["phap_ly"] = phap_lys
    df_out["phuong_xa"] = phuong_xas
    df_out["toa_do (lat/long)"] = toa_dos
    df_out["ngay_dang"] = ngay_dangs
    df_out["gia_tren_m2"] = gia_tren_m2s
    df_out["nguon_du_lieu"] = nguon_du_lieus
    df_out["link_goc"] = link_gocs

    try:
        df_out.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"  --> Hoàn tất! Lưu thành công tại: {output_path}")
    except PermissionError:
        fallback_path = output_path.replace(".csv", "_new.csv")
        df_out.to_csv(fallback_path, index=False, encoding="utf-8-sig")
        print(f"  [Lưu ý] File đích đang mở trong Excel/ứng dụng khác. Đã lưu tại: {fallback_path}")

    print("\n--- THỐNG KÊ CÁC TRƯỜNG DỮ LIỆU ---")
    new_cols = [
        "gia", "dien_tich", "so_phong_ngu", "so_phong_ve_sinh",
        "loai_hinh", "huong_nha", "phap_ly", "phuong_xa",
        "toa_do (lat/long)", "ngay_dang", "gia_tren_m2",
        "nguon_du_lieu", "link_goc"
    ]
    for col in new_cols:
        cnt = (df_out[col] != "").sum()
        print(f"  {col:<20}: {cnt}/{len(df_out)} giá trị có dữ liệu")
    return df_out

if __name__ == "__main__":
    default_in = r"C:\IUH_Industrial University\Năm 3\Xử lý ảnh\cafeland_chothue_1k_clean.csv"
    if len(sys.argv) > 1:
        default_in = sys.argv[1]
    process_cafeland_chothue(default_in)
