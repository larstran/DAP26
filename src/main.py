import argparse
import os
import sys
from typing import Optional

# Thiết lập encoding UTF-8 cho console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from crawler_rental import crawl_rental_summary, crawl_rental_detailed, RENTAL_CATEGORIES
from llm_extractor import run_hybrid_extraction
from standardize_data import standardize_student_rental_dataset

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
DATA_RAW = os.path.join(PROJECT_ROOT, "data", "01_raw")
DATA_INTER = os.path.join(PROJECT_ROOT, "data", "02_intermediate")
DATA_PROC = os.path.join(PROJECT_ROOT, "data", "03_processed")

def show_pipeline_status():
    """Kiểm tra và hiển thị tình trạng các thư mục dữ liệu."""
    print("\n" + "=" * 80)
    print("📊 TÌNH TRẠNG KHO DỮ LIỆU DỰ ÁN (DATA PIPELINE STATUS)")
    print(f"  Thư mục dự án: {PROJECT_ROOT}")
    print("=" * 80)

    stages = [
        ("1. Dữ liệu thô (01_raw)", DATA_RAW),
        ("2. Dữ liệu làm giàu LLM (02_intermediate)", DATA_INTER),
        ("3. Dữ liệu sạch huấn luyện ML (03_processed)", DATA_PROC)
    ]

    for label, folder in stages:
        print(f"\n📂 [{label}]: {folder}")
        if not os.path.exists(folder):
            print("   (Thư mục chưa được khởi tạo)")
            continue
        files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
        if not files:
            print("   (Chưa có file nào)")
        else:
            for f in files:
                fpath = os.path.join(folder, f)
                size_kb = os.path.getsize(fpath) / 1024
                print(f"   • {f:<40} ({size_kb:8.1f} KB)")
    print("=" * 80)

def step_crawl_summary(count: int = 50, category: str = "all", workers: int = 12):
    base_url = RENTAL_CATEGORIES.get(category, RENTAL_CATEGORIES["all"])
    out_file = os.path.join(DATA_RAW, f"raw_cafeland_thue_summary_{count}.csv")
    crawl_rental_summary(target_count=count, output_path=out_file, max_workers=workers, base_url=base_url)

def step_crawl_detail(count: int = 50, category: str = "all", workers: int = 12):
    base_url = RENTAL_CATEGORIES.get(category, RENTAL_CATEGORIES["all"])
    out_file = os.path.join(DATA_RAW, f"raw_cafeland_thue_detailed_{count}.csv")
    crawl_rental_detailed(target_count=count, output_path=out_file, max_workers=workers, base_url=base_url)

def step_enrich(input_file: Optional[str] = None, batch_size: int = 100):
    if not input_file:
        # Tự động tìm file mới nhất trong data/01_raw
        raw_files = [os.path.join(DATA_RAW, f) for f in os.listdir(DATA_RAW) if f.endswith('.csv')] if os.path.exists(DATA_RAW) else []
        if raw_files:
            raw_files.sort(key=os.path.getmtime, reverse=True)
            input_file = raw_files[0]
        else:
            # Fallback file có sẵn trong project nếu chưa cào
            fallbacks = [
                os.path.join(PROJECT_ROOT, "cafeland_chothue_1k_clean.csv"),
                os.path.join(PROJECT_ROOT, "test", "raw_cafeland_30_newest.csv")
            ]
            for fb in fallbacks:
                if os.path.exists(fb):
                    input_file = fb
                    break

    if not input_file or not os.path.exists(input_file):
        print("❌ Không tìm thấy file dữ liệu đầu vào để làm giàu LLM!")
        return

    base_name = os.path.splitext(os.path.basename(input_file))[0]
    out_csv = os.path.join(DATA_INTER, f"{base_name}_enriched.csv")
    out_json = os.path.join(DATA_INTER, f"{base_name}_enriched.json")
    run_hybrid_extraction(input_csv=input_file, output_csv=out_csv, output_json=out_json, batch_size=batch_size)

def step_standardize(input_file: Optional[str] = None):
    if not input_file:
        # Tự động tìm file từ data/02_intermediate hoặc data/01_raw
        candidates = []
        if os.path.exists(DATA_INTER):
            candidates.extend([os.path.join(DATA_INTER, f) for f in os.listdir(DATA_INTER) if f.endswith('_enriched.csv')])
        if os.path.exists(DATA_RAW):
            candidates.extend([os.path.join(DATA_RAW, f) for f in os.listdir(DATA_RAW) if f.endswith('.csv')])
        candidates.extend([
            os.path.join(PROJECT_ROOT, "cafeland_chothue_1k_clean.csv"),
            os.path.join(PROJECT_ROOT, "test", "raw_cafeland_30_newest_hybrid_enriched.csv")
        ])

        for c in candidates:
            if os.path.exists(c):
                input_file = c
                break

    if not input_file or not os.path.exists(input_file):
        print("❌ Không tìm thấy file dữ liệu nguồn để chuẩn hóa!")
        return

    out_csv = os.path.join(DATA_PROC, "gold_student_rental_train.csv")
    out_json = os.path.join(DATA_PROC, "gold_student_rental_train.json")
    standardize_student_rental_dataset(input_path=input_file, output_csv=out_csv, output_json=out_json)

def step_full_pipeline(count: int = 50, batch_size: int = 100):
    print("\n🚀 KHỞI CHẠY PIPELINE TỰ ĐỘNG TỪ ĐẦU ĐẾN CUỐI (END-TO-END)")
    raw_out = os.path.join(DATA_RAW, f"raw_cafeland_thue_detailed_{count}.csv")
    crawl_rental_detailed(target_count=count, output_path=raw_out)
    
    inter_csv = os.path.join(DATA_INTER, f"raw_cafeland_thue_detailed_{count}_enriched.csv")
    inter_json = os.path.join(DATA_INTER, f"raw_cafeland_thue_detailed_{count}_enriched.json")
    run_hybrid_extraction(input_csv=raw_out, output_csv=inter_csv, output_json=inter_json, batch_size=batch_size)
    
    proc_csv = os.path.join(DATA_PROC, "gold_student_rental_train.csv")
    proc_json = os.path.join(DATA_PROC, "gold_student_rental_train.json")
    standardize_student_rental_dataset(input_path=inter_csv, output_csv=proc_csv, output_json=proc_json)
    print("\n🎉 TOÀN BỘ PIPELINE ĐÃ HOÀN TẤT THÀNH CÔNG!")

def interactive_menu():
    """Giao diện dòng lệnh tương tác trực quan."""
    while True:
        print("\n" + "=" * 80)
        print("🎓 DAP FINAL PROJECT: HỆ THỐNG ĐỊNH GIÁ BĐS CHO THUÊ SINH VIÊN TP.HCM")
        print("=" * 80)
        print("  1. Cào tóm tắt 7 trường dữ liệu từ Thẻ tin (Fast Summary Crawler)")
        print("  2. Cào sâu 20 trường dữ liệu chi tiết từng tin đăng (Deep Crawler)")
        print("  3. Làm giàu đặc trưng tiện ích sinh viên bằng Hybrid LLM (Pass 1 & Pass 2)")
        print("  4. Làm sạch & Chuẩn hóa tập dữ liệu huấn luyện ML (Gold Dataset Ready)")
        print("  5. Chạy toàn bộ Pipeline tự động (Crawl -> Enrich -> Standardize)")
        print("  6. Kiểm tra trạng thái và danh sách file trong kho data/")
        print("  0. Thoát chương trình")
        print("=" * 80)

        choice = input("👉 Vui lòng chọn chức năng (0-6): ").strip()
        if choice == "1":
            cnt = int(input("Nhập số lượng bài viết cần cào (mặc định 50): ") or "50")
            step_crawl_summary(count=cnt)
        elif choice == "2":
            cnt = int(input("Nhập số lượng bài viết cần cào sâu (mặc định 50): ") or "50")
            step_crawl_detail(count=cnt)
        elif choice == "3":
            inp = input("Nhập đường dẫn file CSV nguồn (nhấn Enter để tự động tìm): ").strip() or None
            step_enrich(input_file=inp)
        elif choice == "4":
            inp = input("Nhập đường dẫn file CSV nguồn (nhấn Enter để tự động tìm): ").strip() or None
            step_standardize(input_file=inp)
        elif choice == "5":
            cnt = int(input("Nhập số lượng bài viết muốn chạy trọn gói (mặc định 50): ") or "50")
            step_full_pipeline(count=cnt)
        elif choice == "6":
            show_pipeline_status()
        elif choice == "0":
            print("Tạm biệt!")
            break
        else:
            print("Lựa chọn không hợp lệ, vui lòng thử lại.")

def main():
    parser = argparse.ArgumentParser(description="DAP Final Project: Student Rental Valuation Pipeline")
    parser.add_argument("--step", choices=["crawl_summary", "crawl_detail", "enrich", "standardize", "pipeline", "status"], help="Bước cần thực hiện")
    parser.add_argument("--count", type=int, default=50, help="Số lượng tin cần thu thập")
    parser.add_argument("--input", type=str, default=None, help="Đường dẫn file đầu vào")
    parser.add_argument("--output", type=str, default=None, help="Đường dẫn file đầu ra")
    parser.add_argument("--batch_size", type=int, default=100, help="Kích thước Mega-Batch cho LLM")
    parser.add_argument("--workers", type=int, default=12, help="Số luồng worker khi cào dữ liệu")
    parser.add_argument("--category", choices=["all", "phong_tro", "can_ho", "nha_rieng"], default="all", help="Danh mục cho thuê CafeLand")

    args = parser.parse_args()

    if args.step == "crawl_summary":
        step_crawl_summary(count=args.count, category=args.category, workers=args.workers)
    elif args.step == "crawl_detail":
        step_crawl_detail(count=args.count, category=args.category, workers=args.workers)
    elif args.step == "enrich":
        step_enrich(input_file=args.input, batch_size=args.batch_size)
    elif args.step == "standardize":
        step_standardize(input_file=args.input)
    elif args.step == "pipeline":
        step_full_pipeline(count=args.count, batch_size=args.batch_size)
    elif args.step == "status":
        show_pipeline_status()
    else:
        interactive_menu()

if __name__ == "__main__":
    main()
