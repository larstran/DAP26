import csv
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

CSV_HEADERS = [
    "title_raw",
    "price_raw",
    "area_raw",
    "location_raw",
    "date_raw",
    "description_raw",
    "url"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
}

def clean_text(text):
    if not text:
        return ""
    return " ".join(text.split())

def create_session(workers=12):
    session = requests.Session()
    session.headers.update(HEADERS)
    retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries, pool_connections=workers, pool_maxsize=workers)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

def crawl_threaded(target_count=30, output_filename="raw_cafeland_30_newest.csv", max_workers=12):
    target_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(target_dir, output_filename)

    print("=" * 70)
    print("THREADED FAST CRAWLER (TỐI ƯU THEO PHẦN CỨNG 12 LUỒNG CPU)")
    print(f"  Mục tiêu: {target_count} bài viết đủ 7 trường")
    print(f"  Số luồng: {max_workers} worker threads")
    print(f"  File xuất kết quả: {output_path}")
    print("=" * 70)

    start_time = time.perf_counter()
    session = create_session(max_workers)

    # Thu thập danh sách tin
    candidates = []
    seen = set()
    page = 1
    while len(candidates) < target_count * 1.5 and page <= 50:
        url = f"https://nhadat.cafeland.vn/nha-dat-ban/page-{page}/" if page > 1 else "https://nhadat.cafeland.vn/"
        try:
            r = session.get(url, timeout=10)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.content, 'html.parser')
            items = soup.select('.row-item')
            for it in items:
                t_el = it.select_one('.realTitle, h3 a, .re-title a, a.title')
                if not t_el:
                    continue
                href = t_el.get('href', '').strip()
                if not href or href in seen or not href.endswith('.html'):
                    continue
                seen.add(href)
                if not href.startswith('http'):
                    href = 'https://nhadat.cafeland.vn' + href

                price_el = it.select_one('.reales-price, .price, span.price-value')
                area_el = it.select_one('.reales-dientich, .reales-area, .area')
                loc_el = it.select_one('.reales-location, .info-location, .location')
                date_el = it.select_one('.reals-update-time, .date')
                desc_el = it.select_one('.reales-preview, .desc, p.text-summary')

                rec = {
                    'title_raw': clean_text(t_el.get_text()),
                    'price_raw': clean_text(price_el.get_text()) if price_el else '',
                    'area_raw': clean_text(area_el.get_text()) if area_el else '',
                    'location_raw': clean_text(loc_el.get_text()) if loc_el else '',
                    'date_raw': clean_text(date_el.get_text()) if date_el else '',
                    'description_raw': clean_text(desc_el.get_text()) if desc_el else '',
                    'url': href
                }
                candidates.append(rec)
        except Exception as e:
            pass
        page += 1

    valid_records = [r for r in candidates if all(r[k] for k in CSV_HEADERS)][:target_count]

    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for r in valid_records:
            writer.writerow(r)

    end_time = time.perf_counter()
    total_time = end_time - start_time
    print(f"Cào hoàn tất {len(valid_records)} tin trong {total_time:.2f} giây.")
    return output_path, len(valid_records), total_time

if __name__ == "__main__":
    crawl_threaded()
