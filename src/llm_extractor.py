import csv
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import requests

# Thiết lập encoding UTF-8 cho console Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Bảng các trường đặc trưng cho thuê sinh viên chuyên sâu (Student Rental Features)
ENRICHED_HEADERS = [
    "so_phong_ngu",
    "so_toilet",
    "has_wc_rieng",
    "has_gac_lung",
    "has_may_lanh",
    "gio_tu_do",
    "cho_nau_an",
    "is_full_furniture",
    "property_type_target",  # phong_tro_ktx | can_ho | nha_nguyen_can | khac
    "parsing_flag"           # DONE_REGEX | SKIP_NON_RENTAL | RESOLVED_LLM | FALLBACK_REGEX
]

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Đọc cấu hình bảo mật với thứ tự ưu tiên:
    1. Biến môi trường hệ thống hoặc file .env (GEMINI_API_KEY, GEMINI_MODEL).
    2. File config.json cục bộ (bảo toàn tính tương thích ngược cho dự án).
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(base_dir)

    # 1. Thử tải biến môi trường từ .env qua python-dotenv
    try:
        from dotenv import load_dotenv
        env_candidates = [
            os.path.join(base_dir, ".env"),
            os.path.join(project_root, ".env"),
            os.path.join(os.getcwd(), ".env")
        ]
        for ec in env_candidates:
            if os.path.isfile(ec):
                load_dotenv(ec, override=True)
                break
    except ImportError:
        pass

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model_name = os.getenv("GEMINI_MODEL") or os.getenv("MODEL_NAME")

    # 2. Fallback sang file config.json nếu chưa cấu hình biến môi trường
    if config_path is None:
        config_path = os.path.join(base_dir, "config.json")

    config_data: Dict[str, Any] = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"    [Cảnh báo] Không thể đọc {config_path}: {e}")

    if not api_key:
        api_key = config_data.get("api_key")

    if not model_name:
        model_name = config_data.get("name", "Gemini 3.1 Flash Lite")

    if not api_key or str(api_key).strip() in ("", "YOUR_GEMINI_API_KEY_HERE", "your_gemini_api_key_here"):
        raise ValueError(
            "Không tìm thấy 'api_key' hoặc 'GEMINI_API_KEY' hợp lệ!\n"
            "Vui lòng cấu hình biến GEMINI_API_KEY trong file .env (khuyến nghị bảo mật) "
            "hoặc thiết lập trong file config.json."
        )

    return {
        "api_key": str(api_key).strip(),
        "name": str(model_name).strip()
    }

def get_candidate_models(configured_name: str) -> List[str]:
    """
    Tạo danh sách các model ứng viên để gửi tới Google Gemini API.
    Ưu tiên tên chỉ định từ config.json, kèm danh sách fallback chuẩn nếu tên model là định danh nội bộ/UI.
    """
    cleaned = configured_name.strip()
    slug = re.sub(r'[^a-zA-Z0-9_\-\.]+', '-', cleaned.lower()).strip('-')

    candidates = []
    if slug:
        candidates.append(slug)

    # Danh sách model Flash ổn định và có dung lượng máy chủ cao nhất hiện tại
    stable_fallbacks = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-3.5-flash"]
    for fb in stable_fallbacks:
        if fb not in candidates:
            candidates.append(fb)

    return candidates

# -----------------------------------------------------------------------------
# GIAI ĐOẠN 1: BỘ LỌC TỐI ƯU REGEX & PHÂN LOẠI CỜ (PASS 1: REGEX TRIAGE)
# -----------------------------------------------------------------------------

def triage_student_rental_record(row: Dict[str, str]) -> Tuple[Dict[str, Any], str]:
    """
    Phân loại và bóc tách nhanh 1 dòng dữ liệu cho thuê sinh viên bằng Regex:
    - SKIP_NON_RENTAL: Mặt bằng kinh doanh, kho bãi, sang nhượng, bán BĐS (loại bỏ).
    - DONE_REGEX: Bóc tách thành công đầy đủ số lượng tường minh (không tốn API).
    - NEEDS_LLM: Có mô tả tiện ích/phòng ốc phức tạp, ngầm định cần LLM phân tích.
    """
    title = row.get("title_raw", "") or row.get("Tiêu đề", "") or row.get("title", "")
    desc = row.get("description_raw", "") or row.get("Mô tả", "") or row.get("description", "")
    full_text = f"{title} {desc}".strip().lower()

    extracted = {k: None for k in ENRICHED_HEADERS}

    # 1. Loại bỏ TRIỆT ĐỂ kho xưởng, biệt thự xa xỉ, văn phòng, mặt bằng kinh doanh
    blacklist = [
        "kho xưởng", "kho bãi", "nhà xưởng", "kcn", "khu công nghiệp",
        "biệt thự", "villa", "mặt bằng", "mbkd", "văn phòng", "office",
        "tòa nhà", "shophouse", "bãi xe", "nhà máy", "sang quán",
        "sang nhượng", "đất nền", "bán nhà", "bán đất", "nghỉ dưỡng", "resort"
    ]
    is_commercial_or_luxury = any(b in full_text for b in blacklist)
    is_true_room = any(k in full_text for k in ["phòng trọ", "nhà trọ", "ktx", "ký túc xá", "sleepbox", "ở ghép"])

    if is_commercial_or_luxury and not is_true_room:
        extracted["property_type_target"] = "khac"
        extracted["parsing_flag"] = "SKIP_NON_RENTAL"
        return extracted, "SKIP_NON_RENTAL"

    # 2. Nhận diện CHÍNH XÁC 3 phân khúc mục tiêu sinh viên (Tuyệt đối không gán bừa)
    if any(k in full_text for k in ["phòng trọ", "nhà trọ", "ktx", "ký túc xá", "sleepbox", "sleep box", "ở ghép", "homestay sinh viên", "phòng cho thuê", "phòng ở"]):
        extracted["property_type_target"] = "phong_tro_ktx"
    elif any(k in full_text for k in ["căn hộ", "chung cư", "studio", "ccmn", "chdv", "condotel", "căn 1pn", "căn 2pn"]):
        extracted["property_type_target"] = "can_ho"
    elif any(k in full_text for k in ["nguyên căn", "nhà riêng", "nhà phố cho thuê ở", "nhà cấp 4"]):
        extracted["property_type_target"] = "nha_nguyen_can"
    else:
        extracted["property_type_target"] = "khac"
        extracted["parsing_flag"] = "SKIP_NON_RENTAL"
        return extracted, "SKIP_NON_RENTAL"

    # 3. Bóc tách số phòng ngủ tường minh
    match_pn = re.search(r'(\d+)\s*(?:pn|phòng ngủ|p\.ngủ|phong ngu|bedroom)', full_text)
    if match_pn:
        extracted["so_phong_ngu"] = int(match_pn.group(1))
    elif extracted["property_type_target"] == "phong_tro_ktx" or "studio" in full_text:
        extracted["so_phong_ngu"] = 1

    # 4. Bóc tách số toilet / WC
    match_wc = re.search(r'(\d+)\s*(?:wc|toilet|nhà vệ sinh|phòng vệ sinh|phòng tắm|pt)', full_text)
    if match_wc:
        extracted["so_toilet"] = int(match_wc.group(1))

    # 5. Bóc tách các tiện ích giá trị cao của sinh viên
    # a. WC riêng / Khép kín
    if any(k in full_text for k in ["wc riêng", "toilet riêng", "vệ sinh riêng", "khép kín", "toilet trong phòng", "wc trong phòng"]):
        extracted["has_wc_rieng"] = 1
    elif any(k in full_text for k in ["wc chung", "toilet chung", "vệ sinh chung"]):
        extracted["has_wc_rieng"] = 0

    # b. Gác lửng (tăng gấp đôi diện tích sử dụng)
    if any(k in full_text for k in ["gác lửng", "gác xép", "có gác", "gác đúc", "gác gỗ", "mezzanine"]):
        extracted["has_gac_lung"] = 1
    elif "không gác" in full_text:
        extracted["has_gac_lung"] = 0

    # c. Máy lạnh / Điều hòa
    if any(k in full_text for k in ["máy lạnh", "điều hòa", "máy điều hòa", "ac"]):
        extracted["has_may_lanh"] = 1
    elif "không máy lạnh" in full_text:
        extracted["has_may_lanh"] = 0

    # d. Giờ giấc tự do
    if any(k in full_text for k in ["giờ giấc tự do", "tự do giờ giấc", "không chung chủ", "khóa vân tay", "cửa cuốn", "chìa khóa riêng", "ra vào tự do"]):
        extracted["gio_tu_do"] = 1
    elif any(k in full_text for k in ["chung chủ", "đóng cửa lúc", "khóa cổng 23h", "giới nghiêm"]):
        extracted["gio_tu_do"] = 0

    # e. Chỗ nấu ăn / Bếp
    if any(k in full_text for k in ["cho nấu ăn", "được nấu ăn", "kệ bếp", "bếp riêng", "có bếp", "khu bếp", "nấu ăn tự do"]):
        extracted["cho_nau_an"] = 1
    elif any(k in full_text for k in ["không nấu ăn", "cấm nấu ăn"]):
        extracted["cho_nau_an"] = 0

    # f. Full nội thất
    if any(k in full_text for k in ["full nội thất", "đầy đủ nội thất", "full đồ", "chỉ việc dọn vào ở", "đầy đủ tiện nghi", "full nt"]):
        extracted["is_full_furniture"] = 1
    elif any(k in full_text for k in ["nhà trống", "phòng trống", "không nội thất"]):
        extracted["is_full_furniture"] = 0

    # 6. Quyết định cờ triage:
    # Nếu đã xác định được ít nhất số phòng ngủ, số toilet hoặc phân khúc phòng trọ rõ ràng
    has_sufficient_info = (
        extracted["so_phong_ngu"] is not None and 
        (extracted["has_wc_rieng"] is not None or extracted["so_toilet"] is not None)
    )

    if has_sufficient_info:
        extracted["parsing_flag"] = "DONE_REGEX"
        return extracted, "DONE_REGEX"

    # Nếu xuất hiện từ ngữ mô tả phòng ốc nhưng cấu trúc câu phức tạp
    has_implicit_room = any(k in full_text for k in ["phòng ngủ", "toilet", "vệ sinh", "nội thất", "tiện nghi", "ban công"])
    if has_implicit_room:
        extracted["parsing_flag"] = "NEEDS_LLM"
        return extracted, "NEEDS_LLM"

    extracted["parsing_flag"] = "DONE_REGEX"
    return extracted, "DONE_REGEX"

# -----------------------------------------------------------------------------
# GIAI ĐOẠN 2: MEGA-BATCH LLM ENGINE (TỐI ƯU 20 RPD / 250K TPM / 250K OUTPUT)
# -----------------------------------------------------------------------------

def get_checkpoint_path(output_csv: str) -> str:
    base, _ = os.path.splitext(output_csv)
    return f"{base}_checkpoint.json"

def load_checkpoint(checkpoint_file: str) -> Dict[str, Dict[str, Any]]:
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_checkpoint(checkpoint_file: str, data: Dict[str, Dict[str, Any]]):
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def build_student_rental_prompt(batch_dict: Dict[str, str]) -> str:
    """
    Xây dựng prompt tối ưu nén dữ liệu theo Key-Value ID cho bài toán thuê trọ sinh viên.
    Ép model trả ra JSON Object ánh xạ trực tiếp theo ID để chống 100% rủi ro lệch dòng (Index Drift).
    """
    prompt = """Bạn là chuyên gia thẩm định và chuẩn hóa dữ liệu Nhà trọ & Bất động sản Cho thuê dành cho Sinh viên tại TP.HCM.
Nhiệm vụ: Phân tích danh sách tin đăng được cung cấp dưới dạng JSON Object {id: "mô tả"} và trích xuất các tiện ích sinh viên.

CÁC TIÊU CHÍ BẮT BUỘC:
1. property_type_target: Bắt buộc chọn 1 trong 3 nhóm:
   - "phong_tro_ktx": Phòng trọ, dãy trọ, KTX tư nhân, Sleepbox, Homestay sinh viên, ở ghép.
   - "can_ho": Căn hộ chung cư, chung cư mini (CCMN), căn hộ dịch vụ (CHDV), Studio.
   - "nha_nguyen_can": Nhà nguyên căn, nhà phố, nhà riêng cho nhóm sinh viên thuê chung.
2. so_phong_ngu: Số phòng ngủ (int). Nếu là phòng trọ/sleepbox/studio -> Bắt buộc gán 1.
3. so_toilet: Số lượng toilet/WC (int).
4. has_wc_rieng: 1 nếu WC riêng/khép kín; 0 nếu WC chung dãy/chung tầng; null nếu không rõ.
5. has_gac_lung: 1 nếu có gác lửng/gác xép/mezzanine; 0 nếu không.
6. has_may_lanh: 1 nếu có máy lạnh/điều hòa; 0 nếu không.
7. gio_tu_do: 1 nếu giờ giấc tự do, không chung chủ, khóa vân tay; 0 nếu chung chủ hoặc có giờ đóng cửa.
8. cho_nau_an: 1 nếu cho nấu ăn, có kệ bếp, khu bếp; 0 nếu cấm nấu ăn.
9. is_full_furniture: 1 nếu full nội thất (giường nệm tủ lạnh máy giặt); 0 nếu phòng trống.

ĐỊNH DẠNG ĐẦU RA BẮT BUỘC:
Trả về DUY NHẤT một JSON Object dạng:
{
  "ID_TIN": {
    "property_type_target": "phong_tro_ktx" | "can_ho" | "nha_nguyen_can",
    "so_phong_ngu": int,
    "so_toilet": int hoặc null,
    "has_wc_rieng": 1 hoặc 0 hoặc null,
    "has_gac_lung": 1 hoặc 0,
    "has_may_lanh": 1 hoặc 0,
    "gio_tu_do": 1 hoặc 0 hoặc null,
    "cho_nau_an": 1 hoặc 0 hoặc null,
    "is_full_furniture": 1 hoặc 0
  }
}

DANH SÁCH BÀI ĐĂNG CẦN TRÍCH XUẤT:
"""
    prompt += json.dumps(batch_dict, ensure_ascii=False, indent=2)
    return prompt

def call_gemini_mega_batch(
    prompt: str,
    api_key: str,
    model_name: str,
    active_model_holder: List[Optional[str]]
) -> Optional[Dict[str, Any]]:
    """
    Gọi Gemini API cho Mega-Batch (lên đến 500 dòng/lần), tận dụng hạn mức 250k output token.
    Tự động thử các model fallback hợp lệ nếu tên cấu hình là bí danh.
    """
    candidate_models = get_candidate_models(model_name)
    if active_model_holder[0] and active_model_holder[0] in candidate_models:
        candidate_models.remove(active_model_holder[0])
        candidate_models.insert(0, active_model_holder[0])

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "maxOutputTokens": 65536
        }
    }

    for model_candidate in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_candidate}:generateContent"
        try:
            print(f"    [Mega-Batch API] Đang gửi yêu cầu tới model '{model_candidate}'...")
            res = requests.post(url, headers=headers, json=payload, timeout=300)

            if res.status_code == 404:
                print(f"    [404 Not Found] Model '{model_candidate}' không khả dụng. Thử model tiếp theo...")
                continue

            if res.status_code == 503:
                print(f"    [503 Quá tải máy chủ] Model '{model_candidate}' đang có lượng truy cập đột biến (High Demand). Đang tự động chuyển sang model dự phòng tiếp theo...")
                continue

            if res.status_code == 429:
                print(f"    [429 Quota] Model '{model_candidate}' chạm giới hạn RPM/TPM. Tạm dừng 10s...")
                time.sleep(10)
                res = requests.post(url, headers=headers, json=payload, timeout=300)

            if res.status_code == 200:
                active_model_holder[0] = model_candidate
                data = res.json()
                cand = data.get("candidates", [])
                if cand:
                    parts = cand[0].get("content", {}).get("parts", [])
                    if parts:
                        raw_text = parts[0].get("text", "").strip()
                        cleaned = re.sub(r"^```json\s*", "", raw_text)
                        cleaned = re.sub(r"\s*```$", "", cleaned)
                        try:
                            return json.loads(cleaned)
                        except Exception as je:
                            print(f"    [JSON Parse Error] Không phân tích được phản hồi: {je}")
                            return None
            else:
                print(f"    [HTTP Error {res.status_code}]: {res.text[:200]}")
                continue

        except Exception as e:
            print(f"    [Request Exception]: {e}")

    return None

def run_hybrid_extraction(
    input_csv: str,
    output_csv: Optional[str] = None,
    output_json: Optional[str] = None,
    batch_size: int = 100,
    config_path: Optional[str] = None
) -> Tuple[str, str, int]:
    """
    Tiến trình Hai Giai Đoạn (Two-Stage Hybrid Pipeline):
    - Giai đoạn 1: Regex Triage bóc tách nhanh & gắn cờ dòng cần LLM.
    - Giai đoạn 2: Mega-Batch Gemini API cho các dòng còn mơ hồ (có Checkpoint đĩa).
    """
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"File đầu vào không tồn tại: {input_csv}")

    # Xác định đường dẫn thư mục data/02_intermediate/
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)
    inter_dir = os.path.join(project_dir, "data", "02_intermediate")
    os.makedirs(inter_dir, exist_ok=True)

    if output_csv is None:
        base_name = os.path.splitext(os.path.basename(input_csv))[0]
        output_csv = os.path.join(inter_dir, f"{base_name}_enriched.csv")

    if output_json is None:
        base_name = os.path.splitext(os.path.basename(input_csv))[0]
        output_json = os.path.join(inter_dir, f"{base_name}_enriched.json")

    checkpoint_file = get_checkpoint_path(output_csv)
    checkpoint_data = load_checkpoint(checkpoint_file)

    # Đọc dữ liệu đầu vào
    with open(input_csv, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    total_rows = len(rows)
    print("=" * 80)
    print("🚀 HYBRID LLM EXTRACTOR: CHUẨN HÓA ĐẶC TRƯNG THUÊ TRỌ SINH VIÊN (2-PASS)")
    print(f"  File đầu vào      : {input_csv} ({total_rows} dòng)")
    print(f"  File CSV đầu ra   : {output_csv}")
    print(f"  File JSON đầu ra  : {output_json}")
    print(f"  Kích thước Batch  : {batch_size} dòng/request (Tối ưu 20 RPD / 250k TPM)")
    print("=" * 80)

    # Đọc cấu hình Gemini API
    config = load_config(config_path)
    api_key = config["api_key"]
    model_name = config.get("name", "Gemini 3.8 Flash")
    active_model_holder: List[Optional[str]] = [None]

    # -------------------------------------------------------------
    # GIAI ĐOẠN 1: PASS 1 - REGEX TRIAGE TOÀN BỘ DATASET
    # -------------------------------------------------------------
    print("\n🔍 [PASS 1]: Khởi chạy Regex Triage phân loại cờ và bóc tách đặc trưng tiện ích...")
    enriched_rows = []
    needs_llm_queue = []

    triage_counts = {"DONE_REGEX": 0, "SKIP_NON_RENTAL": 0, "NEEDS_LLM": 0}

    for idx, r in enumerate(rows):
        row_id = str(idx + 1)
        r["row_id"] = row_id

        # Kiểm tra nếu đã có trong Checkpoint từ phiên trước
        if row_id in checkpoint_data:
            c_val = checkpoint_data[row_id]
            for hk in ENRICHED_HEADERS:
                r[hk] = c_val.get(hk, "")
            r["parsing_flag"] = "RESOLVED_LLM"
            enriched_rows.append(r)
            continue

        extracted, flag = triage_student_rental_record(r)
        for hk in ENRICHED_HEADERS:
            r[hk] = extracted.get(hk, "")

        triage_counts[flag] = triage_counts.get(flag, 0) + 1

        if flag == "NEEDS_LLM":
            needs_llm_queue.append(r)
        
        enriched_rows.append(r)

    print("📊 Kết quả phân tích Pass 1:")
    print(f"  • Đã bóc tách chuẩn bằng Regex (DONE_REGEX)       : {triage_counts.get('DONE_REGEX', 0):4d} tin (0 tốn API)")
    print(f"  • Bỏ qua không phải BĐS thuê ở (SKIP_NON_RENTAL)   : {triage_counts.get('SKIP_NON_RENTAL', 0):4d} tin (0 tốn API)")
    print(f"  • Cần Mega-Batch LLM can thiệp (NEEDS_LLM)        : {len(needs_llm_queue):4d} tin")

    # -------------------------------------------------------------
    # GIAI ĐOẠN 2: PASS 2 - MEGA-BATCH LLM CHO CÁC TIN CÒN MƠ HỒ
    # -------------------------------------------------------------
    if needs_llm_queue:
        num_batches = (len(needs_llm_queue) + batch_size - 1) // batch_size
        print(f"\n⚡ [PASS 2]: Bắt đầu gửi Mega-Batch LLM ({len(needs_llm_queue)} tin chia thành {num_batches} lượt gọi API)...")

        for b_idx in range(num_batches):
            chunk = needs_llm_queue[b_idx * batch_size : (b_idx + 1) * batch_size]
            batch_dict = {}
            for row in chunk:
                rid = row["row_id"]
                t_val = row.get("title_raw", "") or row.get("Tiêu đề", "") or row.get("title", "")
                d_val = row.get("description_raw", "") or row.get("Mô tả", "") or row.get("description", "")
                t_snip = t_val[:80]
                d_snip = d_val[:350]
                batch_dict[rid] = f"{t_snip}. {d_snip}".strip()

            print(f"\n  [Batch {b_idx + 1}/{num_batches}] Đang đóng gói {len(chunk)} tin (ID {chunk[0]['row_id']} -> {chunk[-1]['row_id']})...")
            prompt = build_student_rental_prompt(batch_dict)

            resp_dict = call_gemini_mega_batch(prompt, api_key, model_name, active_model_holder)

            if resp_dict and isinstance(resp_dict, dict):
                matched = 0
                for row in chunk:
                    rid = row["row_id"]
                    if rid in resp_dict and isinstance(resp_dict[rid], dict):
                        llm_res = resp_dict[rid]
                        for fld in ENRICHED_HEADERS:
                            if fld in llm_res and llm_res[fld] is not None:
                                row[fld] = llm_res[fld]
                        row["parsing_flag"] = "RESOLVED_LLM"
                        checkpoint_data[rid] = {fld: row.get(fld, "") for fld in ENRICHED_HEADERS}
                        matched += 1
                    else:
                        row["parsing_flag"] = "FALLBACK_REGEX"

                save_checkpoint(checkpoint_file, checkpoint_data)
                print(f"  ✓ [Batch {b_idx + 1}/{num_batches}] Thành công! Khớp {matched}/{len(chunk)} tin -> Đã lưu Checkpoint đĩa.")
            else:
                print(f"  ⚠️ [Batch {b_idx + 1}/{num_batches}] Không nhận được phản hồi hợp lệ. Áp dụng Fallback Regex.")
                for row in chunk:
                    row["parsing_flag"] = "FALLBACK_REGEX"

            # Tạm dừng ngắn tuân thủ RPM (20 RPM = tối thiểu 3s/request)
            time.sleep(3.5)
    else:
        print("\n⚡ [PASS 2]: Không có tin đăng nào cần gọi LLM! Tiết kiệm 100% hạn ngạch API.")

    # -------------------------------------------------------------
    # GIAI ĐOẠN 3: XUẤT KẾT QUẢ ĐỒNG THỜI CSV VÀ JSON
    # -------------------------------------------------------------
    final_fields = list(fieldnames)
    if "row_id" not in final_fields:
        final_fields.insert(0, "row_id")
    for hk in ENRICHED_HEADERS:
        if hk not in final_fields:
            final_fields.append(hk)

    # 1. Xuất CSV UTF-8-BOM
    with open(output_csv, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=final_fields)
        writer.writeheader()
        for r in enriched_rows:
            writer.writerow(r)

    # 2. Xuất JSON có cấu trúc metadata
    json_payload = {
        "metadata": {
            "title": "Dữ liệu Cho Thuê TP.HCM đã làm giàu thuộc tính sinh viên (Hybrid Enriched)",
            "source_file": os.path.basename(input_csv),
            "total_records": len(enriched_rows),
            "enriched_headers": ENRICHED_HEADERS,
            "triage_summary": triage_counts
        },
        "records": enriched_rows
    }
    with open(output_json, mode="w", encoding="utf-8") as f:
        json.dump(json_payload, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("🎉 TIẾN TRÌNH LÀM GIÀU DỮ LIỆU HOÀN TẤT THÀNH CÔNG!")
    print(f"  • File CSV  : {output_csv}")
    print(f"  • File JSON : {output_json}")
    print("=" * 80)

    return output_csv, output_json, len(enriched_rows)

if __name__ == "__main__":
    in_file = sys.argv[1] if len(sys.argv) > 1 else None
    if not in_file:
        print("Vui lòng cung cấp đường dẫn file CSV đầu vào.")
    else:
        run_hybrid_extraction(in_file)
