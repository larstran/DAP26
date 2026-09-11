import asyncio
import csv
import os
import sys
import time
from playwright.async_api import async_playwright

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

def clean_text(text):
    if not text:
        return ""
    return " ".join(text.split())

async def block_unnecessary_resources(route):
    """
    Can thiệp vào network của Playwright bằng route abort:
    Chặn tải hình ảnh, font, css, media, trackers để tối ưu hóa tốc độ cào tối đa.
    """
    request = route.request
    resource_type = request.resource_type

    if resource_type in ["image", "stylesheet", "font", "media", "other"]:
        await route.abort()
        return

    url = request.url.lower()
    if any(ext in url for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".css"]):
        await route.abort()
        return

    if any(tracker in url for tracker in ["google-analytics", "googletagmanager", "facebook", "doubleclick", "connect.facebook.net"]):
        await route.abort()
        return

    await route.continue_()

async def crawl_page(context, page_num, semaphore, stop_event, collected_records, lock, target_count):
    if stop_event.is_set():
        return

    url = f"https://nhadat.cafeland.vn/nha-dat-ban/page-{page_num}/"

    async with semaphore:
        if stop_event.is_set():
            return

        page = await context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            status = response.status if response else 0

            if status == 404:
                stop_event.set()
                return

            cards_data = await page.evaluate('''() => {
                const items = document.querySelectorAll('.row-item');
                const results = [];
                for (const it of items) {
                    const titleEl = it.querySelector('.realTitle, h3 a, .re-title a, a.title');
                    if (!titleEl) continue;
                    const title = titleEl.innerText ? titleEl.innerText.trim() : '';
                    let href = titleEl.getAttribute('href') || '';
                    if (href && !href.startsWith('http')) {
                        href = 'https://nhadat.cafeland.vn' + href;
                    }

                    const priceEl = it.querySelector('.reales-price, .re-price, .price, span.price-value, span.money');
                    const price = priceEl ? priceEl.innerText.trim() : '';

                    const areaEl = it.querySelector('.reales-area, .reales-dientich, .re-area, .area, span.area-value');
                    const area = areaEl ? areaEl.innerText.trim() : '';

                    const locEl = it.querySelector('.info-location, .reales-location, .re-location, .location, span.address');
                    const loc = locEl ? locEl.innerText.trim() : '';

                    const dateEl = it.querySelector('.reals-update-time, .re-date, .date, span.post-time, span.time');
                    const date = dateEl ? dateEl.innerText.trim() : '';

                    const descEl = it.querySelector('.reales-preview, .re-description, .desc, p.text-summary');
                    const desc = descEl ? descEl.innerText.trim() : '';

                    results.push({
                        title_raw: title,
                        price_raw: price,
                        area_raw: area,
                        location_raw: loc,
                        date_raw: date,
                        description_raw: desc,
                        url: href
                    });
                }
                return results;
            }''')

            valid_batch = []
            for c in cards_data:
                cleaned = {k: clean_text(c.get(k, '')) for k in CSV_HEADERS}
                if all(cleaned[k] for k in CSV_HEADERS):
                    valid_batch.append(cleaned)

            async with lock:
                for rec in valid_batch:
                    if len(collected_records) < target_count:
                        collected_records.append(rec)
                    else:
                        stop_event.set()
                        break
                current_count = len(collected_records)

            print(f"  [Trang {page_num:2d}] +{len(valid_batch):2d} tin hợp lệ | Tổng: {current_count:4d}/{target_count}")

            if current_count >= target_count:
                stop_event.set()

        except Exception as e:
            pass
        finally:
            await page.close()

async def run_playwright_crawler(target_count=1000, output_filename="raw_cafeland_1000.csv", concurrency=5):
    target_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(target_dir, output_filename)

    print("=" * 70)
    print("PLAYWRIGHT ROUTE-ABORT HIGH SPEED CRAWLER")
    print(f"  Mục tiêu: {target_count} bài viết đủ 7 trường dữ liệu")
    print(f"  Network Interception: Đang chặn image, font, css, media, trackers...")
    print(f"  Số tab trình duyệt song song: {concurrency}")
    print(f"  File xuất kết quả: {output_path}")
    print("=" * 70)

    start_time = time.perf_counter()
    collected_records = []
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)
    stop_event = asyncio.Event()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        # Kích hoạt can thiệp Network Route Abort
        await context.route("**/*", block_unnecessary_resources)

        max_pages = (target_count // 25) + 15
        tasks = []
        for page_num in range(1, max_pages + 1):
            if stop_event.is_set():
                break
            task = asyncio.create_task(crawl_page(context, page_num, semaphore, stop_event, collected_records, lock, target_count))
            tasks.append(task)
            await asyncio.sleep(0.04)

        await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()

    # Ghi file CSV định dạng UTF-8-BOM chuẩn
    with open(output_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for r in collected_records:
            writer.writerow(r)

    end_time = time.perf_counter()
    total_time = end_time - start_time

    print("=" * 70)
    print("CÀO DỮ LIỆU HOÀN TẤT THÀNH CÔNG!")
    print(f"  Tổng số tin thu thập: {len(collected_records)}/{target_count}")
    print(f"  Vị trí file lưu: {output_path}")
    print(f"  Tổng thời gian cào: {total_time:.2f} giây")
    if total_time > 0:
        print(f"  Tốc độ trung bình: {len(collected_records) / total_time:.1f} tin/giây")
    print("=" * 70)
    return output_path, len(collected_records), total_time

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_playwright_crawler(1000, "raw_cafeland_1000.csv", 5))
