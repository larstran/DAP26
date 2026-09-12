"""
=============================================================================
DỰ ÁN DAP - BỘ ĐIỀU KHIỂN TRUNG TÂM (MAIN PIPELINE CONTROLLER)
Thư mục: C:\\IUH_Industrial University\\Năm 3\\DAP
=============================================================================
Hỗ trợ menu tương tác dòng lệnh (CLI) để khởi chạy:
  [1] Xử lý dữ liệu Bán CafeLand (xu_ly_cafeland_ban.py)
  [2] Xử lý dữ liệu Cho thuê CafeLand (xu_ly_cafeland_thue.py)
  [3] Chạy xử lý đồng thời cả 2 file (Toàn bộ Pipeline)
  [0] Thoát
=============================================================================
"""

import os
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Import các hàm xử lý từ 2 script đã tạo cùng thư mục
try:
    from xu_ly_cafeland_ban import process_cafeland_ban
    from xu_ly_cafeland_thue import process_cafeland_chothue
except ImportError as e:
    print(f"Lỗi import module: {e}")
    sys.exit(1)

# Các đường dẫn file mặc định
DEFAULT_BAN_PATH = r"C:\IUH_Industrial University\Năm 3\DAP\crawl\src\raw_cafeland_1000.csv"
DEFAULT_THUE_PATH = r"C:\IUH_Industrial University\Năm 3\Xử lý ảnh\cafeland_chothue_1k_clean.csv"

def run_ban():
    print("\n" + "=" * 65)
    print(">>> [1] TIẾN TRÌNH XỬ LÝ DỮ LIỆU BÁN CAFELAND")
    print("=" * 65)
    
    file_in = DEFAULT_BAN_PATH
    if not os.path.exists(file_in):
        # Fallback tìm trong thư mục DAP/cao_dl
        alt_path = r"C:\IUH_Industrial University\Năm 3\DAP\cao_dl\raw_cafeland_1000.csv"
        if os.path.exists(alt_path):
            file_in = alt_path
        else:
            print(f"Không tìm thấy file mặc định: {file_in}")
            inp = input("Vui lòng nhập đường dẫn file .csv bán cần xử lý: ").strip(' "\'')
            if inp:
                file_in = inp

    start = time.perf_counter()
    process_cafeland_ban(file_in)
    elapsed = time.perf_counter() - start
    print(f"\nThời gian xử lý: {elapsed:.2f} giây.")

def run_thue():
    print("\n" + "=" * 65)
    print(">>> [2] TIẾN TRÌNH XỬ LÝ DỮ LIỆU CHO THUÊ CAFELAND")
    print("=" * 65)
    
    file_in = DEFAULT_THUE_PATH
    if not os.path.exists(file_in):
        print(f"Không tìm thấy file mặc định: {file_in}")
        inp = input("Vui lòng nhập đường dẫn file .csv thuê cần xử lý: ").strip(' "\'')
        if inp:
            file_in = inp

    start = time.perf_counter()
    process_cafeland_chothue(file_in)
    elapsed = time.perf_counter() - start
    print(f"\nThời gian xử lý: {elapsed:.2f} giây.")

def run_all():
    print("\n" + "=" * 65)
    print(">>> [3] TIẾN TRÌNH XỬ LÝ TOÀN BỘ (BÁN + CHO THUÊ)")
    print("=" * 65)
    start_total = time.perf_counter()
    run_ban()
    run_thue()
    total_elapsed = time.perf_counter() - start_total
    print("\n" + "=" * 65)
    print(f"HOÀN THÀNH TOÀN BỘ PIPELINE TRONG {total_elapsed:.2f} GIÂY!")
    print("=" * 65)

def main():
    while True:
        print("\n" + "=" * 65)
        print("          HỆ THỐNG XỬ LÝ & BÓC TÁCH DỮ LIỆU BĐS (DAP)")
        print("=" * 65)
        print("  [1] Xử lý dữ liệu BÁN CafeLand (raw_cafeland_1000.csv)")
        print("  [2] Xử lý dữ liệu CHO THUÊ CafeLand (cafeland_chothue_1k_clean.csv)")
        print("  [3] Chạy xử lý CẢ 2 FILE (Toàn bộ Pipeline)")
        print("  [0] Thoát chương trình")
        print("=" * 65)

        choice = input("Nhập lựa chọn của bạn (0-3): ").strip()

        if choice == "1":
            run_ban()
        elif choice == "2":
            run_thue()
        elif choice == "3":
            run_all()
        elif choice == "0":
            print("\nĐã thoát chương trình. Tạm biệt!")
            break
        else:
            print("\n[!] Lựa chọn không hợp lệ, vui lòng nhập lại từ 0 đến 3.")

if __name__ == "__main__":
    # Nếu có tham số dòng lệnh: python main.py 1 / python main.py 2 / python main.py 3
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg == "1":
            run_ban()
        elif arg == "2":
            run_thue()
        elif arg == "3":
            run_all()
        else:
            main()
    else:
        main()
