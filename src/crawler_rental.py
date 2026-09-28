import csv
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

# Thiết lập encoding UTF-8 cho console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Bảng 20 trường dữ liệu chi tiết chuyên sâu cho Bất động sản thuê sinh viên (DAP Final Project)
DETAILED_HEADERS = [
    "ma_tin",
    "title_raw",
    "price_raw",
    "area_raw",
    "location_raw",
    "quan_huyen",
    "tinh_thanh",
    "date_raw",
    "loai_bds",
    "so_phong_ngu",
    "so_tang",
    "so_toilet",
    "huong_nha",
    "duong_truoc_nha",
    "so_phong_khach",
    "phap_ly",
    "du_an",
    "nguoi_dang",
    "description_raw",
    "url"
]

# Bảng 7 trường tóm tắt chuẩn từ thẻ danh sách (Listing Cards)
SUMMARY_HEADERS = [
    "title_raw",
    "price_raw",
    "area_raw",
    "location_raw",
    "date_raw",
    "description_raw",
    "url"
]

# URL danh mục BĐS cho thuê CHUẨN XÁC tại TP.HCM trên CafeLand
# Tuyệt đối không dùng URL tổng /cho-thue/ vì sẽ bị dính tin VIP kho xưởng toàn quốc
RENTAL_CATEGORIES = {
    "phong_tro": ["https://nhadat.cafeland.vn/cho-thue/phong-tro-tai-tp-ho-chi-minh/"],
    "can_ho": ["https://nhadat.cafeland.vn/cho-thue/can-ho-chung-cu-tai-tp-ho-chi-minh/"],
    "nha_rieng": ["https://nhadat.cafeland.vn/cho-thue/nha-rieng-tai-tp-ho-chi-minh/"],
    "all": [
        "https://nhadat.cafeland.vn/cho-thue/phong-tro-tai-tp-ho-chi-minh/",
        "https://nhadat.cafeland.vn/cho-thue/can-ho-chung-cu-tai-tp-ho-chi-minh/",
        "https://nhadat.cafeland.vn/cho-thue/nha-rieng-tai-tp-ho-chi-minh/"
    ]
}

# Danh sách từ khóa loại bỏ nghiêm ngặt ngay tại tầng cào dữ liệu
CRAWL_BLACKLIST = [
    "kho xưởng", "kho bãi", "nhà xưởng", "kcn", "khu công nghiệp",
    "biệt thự", "villa", "mặt bằng", "mbkd", "văn phòng", "office",
    "tòa nhà", "shophouse", "bãi xe", "nhà máy", "sang quán",
    "sang nhượng", "đất nền", "bán nhà", "bán đất", "nghỉ dưỡng", "resort"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
    'Referer': 'https://nhadat.cafeland.vn/'
}

def clean_text(text: str) -> str:
    """Làm sạch chuỗi văn bản HTML, loại bỏ khoảng trắng thừa và ký tự rác."""
    if not text:
        return ""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    res = " ".join(" ".join(lines).split())
    return re.sub(r'^[·•\-\s]+', '', res).strip()

def is_student_rental_item(title: str, desc: str = "") -> bool:
    """
    Bộ lọc chốt chặn: Loại bỏ 100% kho xưởng, biệt thự triệu đô, mặt bằng buôn bán.
    """
    text = f"{title} {desc}".lower()
    if any(b in text for b in CRAWL_BLACKLIST):
        # Trường hợp ngoại lệ duy nhất: phòng trọ nằm gần khu công nghiệp (vd: 'phòng trọ gần KCN Tân Bình')
        if any(k in text for k in ["phòng trọ", "nhà trọ", "ktx", "sleepbox"]) and not any(k in text for k in ["kho", "xưởng", "biệt thự", "villa", "mặt bằng"]):
            return True
        return False
    return True

def format_page_url(base_url: str, page_num: int) -> str:
    """Chuẩn hóa URL phân trang tự động thích ứng với cấu trúc URL Cafeland."""
    base_url = base_url.strip()
    if "{page}" in base_url:
        return base_url.format(page=page_num)
    if "{page_num}" in base_url:
        return base_url.format(page_num=page_num)

    if page_num == 1:
        if re.search(r'/page-?\d+/?$', base_url, re.IGNORECASE):
            return re.sub(r'/page-?\d+/?$', '/', base_url, flags=re.IGNORECASE)
        return base_url

    if re.search(r'/page-?\d+/?', base_url, re.IGNORECASE):
        return re.sub(r'/page-?\d+/?', f'/page-{page_num}/', base_url, flags=re.IGNORECASE)

    clean_base = base_url.rstrip('/')
    return f"{clean_base}/page-{page_num}/"

def create_session(workers: int = 12) -> requests.Session:
    """Khởi tạo session HTTP tối ưu với connection pooling và cơ chế retry tự động."""
    session = requests.Session()
    session.headers.update(HEADERS)
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries, pool_connections=workers * 2, pool_maxsize=workers * 2)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

def get_default_raw_path(filename: str = "raw_cafeland_thue_hcm.csv") -> str:
    """Xác định đường dẫn lưu trữ mặc định vào thư mục data/01_raw/."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)
    data_dir = os.path.join(project_dir, "data", "01_raw")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, filename)

def parse_detail_page(session: requests.Session, url: str) -> dict:
    """
    Bóc tách 20 trường thông tin chi tiết từ từng trang bài viết con của Cafeland.
    """
    data = {k: "" for k in DETAILED_HEADERS}
    data["url"] = url

    try:
        r = session.get(url, timeout=12)
        if r.status_code != 200:
            return data

        soup = BeautifulSoup(r.content, 'html.parser')

        # 1. Tiêu đề bài viết
        h1 = soup.select_one('h1.head-title, h1.title-detail, h1')
        if h1:
            data["title_raw"] = clean_text(h1.get_text())

        # Kiểm tra lọc blacklist ngay khi cào chi tiết
        if not is_student_rental_item(data["title_raw"]):
            return {}

        # 2. Mã tin, Ngày đăng, Vị trí (Địa chỉ)
        infor_blocks = soup.select('.infor, div[class*="infor"]')
        for blk in infor_blocks:
            txt = blk.get_text(strip=True)
            if 'Mã tài sản:' in txt or 'Mã tin:' in txt:
                m_code = re.search(r'(?:Mã tài sản|Mã tin):\s*(\d+)', txt)
                if m_code:
                    data["ma_tin"] = m_code.group(1)
                m_date = re.search(r'Ngày đăng:\s*([0-9\-/]+)', txt)
                if m_date:
                    data["date_raw"] = m_date.group(1)
            if 'Vị trí:' in txt:
                raw_loc = re.sub(r'^Vị trí:\s*', '', txt)
                raw_loc = re.sub(r'Lưu tin$', '', raw_loc).strip()
                data["location_raw"] = clean_text(raw_loc)

        # Bóc tách Quận/Huyện và Tỉnh/Thành từ location_raw
        if data["location_raw"]:
            parts = [p.strip() for p in data["location_raw"].split(',') if p.strip()]
            if len(parts) >= 1:
                data["tinh_thanh"] = parts[-1]
            if len(parts) >= 2:
                data["quan_huyen"] = parts[-2]

        # 3. Giá thuê, Diện tích, Số phòng ngủ (từ header cards .col-item)
        col_items = soup.select('.col-item, .item-infor')
        for it in col_items:
            note = it.select_one('.infor-note, .note')
            val = it.select_one('.infor-data, .data')
            if note and val:
                n_str = note.get_text(strip=True).lower()
                v_str = clean_text(val.get_text())
                if 'giá' in n_str and not data["price_raw"]:
                    data["price_raw"] = v_str
                elif 'diện tích' in n_str and not data["area_raw"]:
                    data["area_raw"] = v_str
                elif 'phòng ngủ' in n_str and not data["so_phong_ngu"]:
                    data["so_phong_ngu"] = v_str

        # Fallback nếu chưa lấy được giá hoặc diện tích
        if not data["price_raw"]:
            p_alt = soup.select_one('.reales-price, .price-detail, span.price')
            if p_alt:
                data["price_raw"] = clean_text(p_alt.get_text())
        if not data["area_raw"]:
            a_alt = soup.select_one('.reales-dientich, .area-detail, span.area')
            if a_alt:
                data["area_raw"] = clean_text(a_alt.get_text())

        # 4. Thuộc tính kiến trúc & Tiện ích (.reals-architecture / .reals-house-item)
        arch_items = soup.select('.reals-house-item, .item-property, .prop-item')
        for item in arch_items:
            t_el = item.select_one('.title-item, .title, label')
            v_el = item.select_one('.value-item, .value, span:last-child')
            if t_el and v_el:
                key = t_el.get_text(strip=True).lower()
                val = clean_text(v_el.get_text())
                if 'loại địa ốc' in key or 'loại bđs' in key or 'loại hình' in key:
                    data["loai_bds"] = val
                elif 'hướng nhà' in key or 'hướng' in key:
                    data["huong_nha"] = val
                elif 'số tầng' in key:
                    data["so_tang"] = val
                elif 'số toilet' in key or 'số wc' in key or 'phòng tắm' in key:
                    data["so_toilet"] = val
                elif 'đường trước nhà' in key or 'lộ giới' in key:
                    data["duong_truoc_nha"] = val
                elif 'số phòng khách' in key:
                    data["so_phong_khach"] = val
                elif 'số phòng ngủ' in key:
                    data["so_phong_ngu"] = val
                elif 'pháp lý' in key or 'tình trạng pháp lý' in key:
                    data["phap_ly"] = val

        # 5. Dự án / Tòa nhà
        prj_el = soup.select_one('.project-infor a, .project-name, .reals-project a')
        if prj_el:
            data["du_an"] = clean_text(prj_el.get_text())

        # 6. Người đăng / Môi giới
        contact_box = soup.select_one('.block-contact-infor, .contact-info, .author-info')
        if contact_box:
            name_el = contact_box.select_one('b, strong, .name, .author-name')
            if name_el:
                data["nguoi_dang"] = clean_text(name_el.get_text())

        # 7. Nội dung mô tả chi tiết bài viết (.reals-description)
        desc_el = soup.select_one('.reals-description .content, .reals-description, .content-detail, .detail-content')
        if desc_el:
            desc_raw = desc_el.get_text()
            desc_cleaned = re.sub(r'^Thông tin mô tả\s*', '', desc_raw, flags=re.I)
            data["description_raw"] = clean_text(desc_cleaned)

        # Lọc lại với cả mô tả
        if not is_student_rental_item(data["title_raw"], data["description_raw"]):
            return {}

    except Exception:
        pass

    return data

def crawl_rental_summary(
    target_count: int = 50,
    output_path: str = None,
    max_workers: int = 12,
    category: str = "all"
) -> tuple:
    """
    Cào nhanh 7 trường cơ bản trực tiếp từ thẻ danh sách (Listing Cards) cho BĐS Cho Thuê Sinh Viên.
    Tự động chia đều cho 3 nhóm danh mục: phòng trọ, căn hộ, nhà riêng tại TP.HCM.
    """
    if output_path is None:
        output_path = get_default_raw_path(f"raw_cafeland_thue_summary_{target_count}.csv")

    target_urls = RENTAL_CATEGORIES.get(category, RENTAL_CATEGORIES["all"])
    per_cat_count = (target_count + len(target_urls) - 1) // len(target_urls)

    print("=" * 80)
    print("⚡ CAFELAND STUDENT RENTAL FAST CRAWLER (7 TRƯỜNG DỮ LIỆU TÓM TẮT - TP.HCM)")
    print(f"  Phân bổ chuyên mục : {category} ({len(target_urls)} nhóm URL chuẩn)")
    print(f"  Chỉ tiêu tổng cộng : {target_count} bài viết sinh viên (phòng trọ, căn hộ, nhà riêng)")
    print(f"  File xuất kết quả  : {output_path}")
    print("=" * 80)

    start_time = time.perf_counter()
    session = create_session(max_workers)
    collected_records = []
    seen = set()

    for cat_idx, cat_url in enumerate(target_urls, 1):
        print(f"\n📂 [Danh mục {cat_idx}/{len(target_urls)}]: {cat_url}")
        cat_collected = 0
        page = 1

        while cat_collected < per_cat_count and len(collected_records) < target_count and page <= 100:
            page_url = format_page_url(cat_url, page)
            try:
                r = session.get(page_url, timeout=10)
                if r.status_code == 404 or r.status_code != 200:
                    break

                soup = BeautifulSoup(r.content, 'html.parser')
                items = soup.select('.row-item, .re-item, .item-re-content, .box-item-content')

                new_in_page = 0
                for it in items:
                    t_el = it.select_one('.realTitle, h3 a, .re-title a, a.title, h2 a, h3')
                    if not t_el:
                        continue
                    href = t_el.get('href', '').strip() if t_el.name == 'a' else ''
                    if not href:
                        a_tag = it.select_one('a[href*=".html"]')
                        if a_tag:
                            href = a_tag.get('href', '').strip()

                    if not href or href in seen or not href.endswith('.html'):
                        continue

                    title = clean_text(t_el.get_text())
                    desc_el = it.select_one('.reales-preview, .re-description, .desc, p.text-summary')
                    desc = clean_text(desc_el.get_text()) if desc_el else ''

                    # BỘ LỌC CHỐT CHẶN TẠI TẦNG THẺ TIN: Loại ngay kho xưởng, biệt thự, văn phòng
                    if not is_student_rental_item(title, desc):
                        continue

                    seen.add(href)
                    full_href = urljoin('https://nhadat.cafeland.vn', href)
                    price_el = it.select_one('.reales-price, .re-price, .price, span.price-value')
                    area_el = it.select_one('.reales-dientich, .reales-area, .area, span.area-value')
                    loc_el = it.select_one('.reales-location, .info-location, .location, span.address')
                    date_el = it.select_one('.reals-update-time, .re-date, .date, span.time')

                    rec = {
                        'title_raw': title,
                        'price_raw': clean_text(price_el.get_text()) if price_el else '',
                        'area_raw': clean_text(area_el.get_text()) if area_el else '',
                        'location_raw': clean_text(loc_el.get_text()) if loc_el else '',
                        'date_raw': clean_text(date_el.get_text()) if date_el else '',
                        'description_raw': desc,
                        'url': full_href
                    }

                    if rec['title_raw'] and (rec['price_raw'] or rec['url']):
                        collected_records.append(rec)
                        cat_collected += 1
                        new_in_page += 1
                        if len(collected_records) >= target_count or cat_collected >= per_cat_count:
                            break

                print(f"  [Trang {page:2d}] +{new_in_page:2d} tin hợp lệ | Danh mục này: {cat_collected}/{per_cat_count} | Tổng: {len(collected_records)}/{target_count}")
                if new_in_page == 0:
                    break

            except Exception as e:
                print(f"  [Trang {page:2d}] Lỗi mạng: {e}")

            page += 1
            time.sleep(0.3)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_HEADERS)
        writer.writeheader()
        for r in collected_records:
            writer.writerow(r)

    total_time = time.perf_counter() - start_time
    print(f"\n✓ Cào tóm tắt hoàn tất: Thu thập {len(collected_records)} tin sinh viên trong {total_time:.2f} giây.")
    return output_path, len(collected_records), total_time

def crawl_rental_detailed(
    target_count: int = 50,
    output_path: str = None,
    max_workers: int = 12,
    category: str = "all"
) -> tuple:
    """
    Cào sâu 20 trường dữ liệu chi tiết cho thuê sinh viên tại TP.HCM.
    Tự động chia đều cho 3 nhóm danh mục con: phòng trọ, căn hộ, nhà riêng.
    """
    if output_path is None:
        output_path = get_default_raw_path(f"raw_cafeland_thue_detailed_{target_count}.csv")

    target_urls = RENTAL_CATEGORIES.get(category, RENTAL_CATEGORIES["all"])
    per_cat_count = (target_count + len(target_urls) - 1) // len(target_urls)

    print("=" * 80)
    print("🚀 CAFELAND STUDENT RENTAL DEEP CRAWLER - 20 TRƯỜNG CHI TIẾT (TP.HCM)")
    print(f"  Phân bổ chuyên mục : {category} ({len(target_urls)} nhóm URL chuẩn)")
    print(f"  Chỉ tiêu tổng cộng : {target_count} bài viết đầy đủ chi tiết")
    print(f"  Số luồng worker    : {max_workers} luồng song song")
    print(f"  File xuất kết quả  : {output_path}")
    print("=" * 80)

    start_time = time.perf_counter()
    session = create_session(max_workers)
    candidate_urls = []
    seen_urls = set()

    for cat_idx, cat_url in enumerate(target_urls, 1):
        print(f"\n🔍 [Quét URL Nhóm {cat_idx}/{len(target_urls)}]: {cat_url}")
        cat_links = 0
        page = 1
        needed_per_cat = int(per_cat_count * 1.3) + 5

        while cat_links < needed_per_cat and page <= 100:
            page_url = format_page_url(cat_url, page)
            try:
                r = session.get(page_url, timeout=10)
                if r.status_code == 404 or r.status_code != 200:
                    break

                soup = BeautifulSoup(r.content, 'html.parser')
                items = soup.select('.row-item, .re-item, .item-re-content, .box-item-content')

                new_on_page = 0
                for it in items:
                    link_el = it.select_one('.realTitle, h3 a, .re-title a, a.title, h2 a, a[href*=".html"]')
                    if not link_el:
                        continue
                    title = clean_text(link_el.get_text())
                    if not is_student_rental_item(title):
                        continue

                    href = link_el.get('href', '').strip()
                    if not href or not href.endswith('.html'):
                        continue
                    full_href = urljoin('https://nhadat.cafeland.vn', href)
                    if full_href not in seen_urls:
                        seen_urls.add(full_href)
                        candidate_urls.append(full_href)
                        cat_links += 1
                        new_on_page += 1
                        if cat_links >= needed_per_cat:
                            break

                print(f"  [Trang {page:2d}] +{new_on_page:2d} liên kết hợp lệ | Nhóm này: {cat_links}/{needed_per_cat} | Tổng: {len(candidate_urls)}")
                if new_on_page == 0:
                    break

            except Exception as e:
                print(f"  [Trang {page:2d}] Lỗi mạng: {e}")

            page += 1
            time.sleep(0.3)

    if not candidate_urls:
        print("❌ Không tìm thấy liên kết bài thuê trọ nào!")
        return output_path, 0, 0

    print(f"\n⚡ Bắt đầu cào chi tiết {target_count} bài viết với {max_workers} luồng CPU...")
    collected_records = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(parse_detail_page, session, u): u for u in candidate_urls}
        for future in as_completed(future_to_url):
            try:
                res = future.result()
                if res and res.get("title_raw"):
                    collected_records.append(res)
                    count = len(collected_records)
                    display_title = res['title_raw'][:35] + '...' if len(res['title_raw']) > 35 else res['title_raw']
                    display_price = res['price_raw'] or 'Thỏa thuận'
                    display_area = res['area_raw'] or 'N/A'
                    display_type = res['loai_bds'] or 'BĐS Thuê'
                    print(f"  [{count:4d}/{target_count}] ✓ [{display_type}] {display_title} ({display_area} | {display_price})")
                    if len(collected_records) >= target_count:
                        for f in future_to_url:
                            f.cancel()
                        break
            except Exception:
                pass

    collected_records = collected_records[:target_count]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DETAILED_HEADERS)
        writer.writeheader()
        for r in collected_records:
            writer.writerow(r)

    total_time = time.perf_counter() - start_time
    print("=" * 80)
    print("🎉 CÀO CHI TIẾT BĐS THUÊ SINH VIÊN HOÀN TẤT!")
    print(f"  Tổng số tin thu thập : {len(collected_records)}/{target_count} bài viết")
    print(f"  Vị trí file lưu trữ  : {output_path}")
    print(f"  Tổng thời gian cào   : {total_time:.2f} giây")
    print("=" * 80)
    return output_path, len(collected_records), total_time

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    outfile = sys.argv[2] if len(sys.argv) > 2 else None
    mode = sys.argv[3] if len(sys.argv) > 3 else "summary"
    cat = sys.argv[4] if len(sys.argv) > 4 else "all"

    if mode == "detail":
        crawl_rental_detailed(target_count=count, output_path=outfile, category=cat)
    else:
        crawl_rental_summary(target_count=count, output_path=outfile, category=cat)
