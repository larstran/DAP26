import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

def show_menu():
    print("=" * 65)
    print("   HỆ THỐNG CÀO DỮ LIỆU NHÀ ĐẤT CAFELAND (CHUẨN 7 TRƯỜNG DỮ LIỆU)")
    print("=" * 65)
    print("1. Chạy Playwright (Route Abort chặn Ảnh/CSS/Font) - 1,000 bài viết")
    print("2. Chạy Playwright (Route Abort chặn Ảnh/CSS/Font) - 30 bài viết")
    print("3. Chạy Multi-Thread (Tối ưu 12 luồng CPU) - 30 bài viết")
    print("4. Chạy Multi-Thread (Tối ưu 12 luồng CPU) - 1,000 bài viết")
    print("5. Thoát")
    print("=" * 65)

def main():
    show_menu()
    choice = input("Nhập lựa chọn của bạn (1-5, mặc định 1): ").strip() or "1"
    
    if choice == "1":
        from crawler_playwright import run_playwright_crawler
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(run_playwright_crawler(target_count=1000, output_filename="raw_cafeland_1000.csv", concurrency=5))
    elif choice == "2":
        from crawler_playwright import run_playwright_crawler
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(run_playwright_crawler(target_count=30, output_filename="raw_cafeland_30_newest.csv", concurrency=5))
    elif choice == "3":
        from crawler_threaded import crawl_threaded
        crawl_threaded(target_count=30, output_filename="raw_cafeland_30_newest.csv", max_workers=12)
    elif choice == "4":
        from crawler_threaded import crawl_threaded
        crawl_threaded(target_count=1000, output_filename="raw_cafeland_1000.csv", max_workers=12)
    else:
        print("Đã thoát chương trình.")

if __name__ == "__main__":
    main()
