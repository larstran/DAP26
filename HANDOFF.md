# AGENT HANDOFF: TP.HCM STUDENT RENTAL AVM PIPELINE
> **Project**: Automated Valuation Model (AVM) & Price Anomaly Detection for Student Rentals in TP.HCM  
> **Course**: Data Analysis Programming (DAP / 2101681) — Final Project (Replaces Final Exam)  
> **Status**: Exercise 2 (Data Collection & Architecture) Completed $\rightarrow$ Preparing for Exercise 3 (EDA & Visualization)  
> **Target Path**: `C:\Users\ftran\Downloads\VTLT\DAP\final_project\HANDOFF.md`  
> **Environment**: Windows OS (PowerShell / `cmd /c`), Python 3.11+ (Python 3.13 Active)

---

## 1. STRATEGIC PIVOT & CORE SPECIFICATIONS

### 1.1 Context of the Pivot
The original project plan targeted residential real estate sale prices restricted to Gò Vấp district. During preliminary validation, active sale listings on CafeLand in Gò Vấp were found to be sparse (under a few hundred rows), making it mathematically impossible to satisfy the mandatory course requirement of **$\ge 5,000$ observations** (Part B - Exercise 2, Criterion 1).

The project was strategically pivoted to:
1. **Target Persona**: University students renting accommodation in Ho Chi Minh City (TP.HCM).
2. **Target Variable ($y$)**: `gia_thue_trieu_thang` (Monthly rental price in Million VND/month, continuous float). Sale listings (`tỷ`) and negotiable listings (`Thương lượng`) are **strictly eliminated**.
3. **Geographical Boundary**: Entire TP.HCM (24 Districts / Municipalities) to easily achieve $7,000+$ raw rows.
4. **Target Property Categories (Strictly 3 Segments)**:
   * `phong_tro_ktx`: Boarding rooms, private dormitories, sleepboxes, student homestays, room sharing.
   * `can_ho`: Apartments, mini-apartments (CCMN), serviced apartments (CHDV), studio units.
   * `nha_nguyen_can`: Whole houses, townhouses rented by student groups.

---

## 2. REVISED REPOSITORY ARCHITECTURE

The project root is located at `C:\Users\ftran\Downloads\VTLT\DAP\final_project`. The codebase has been fully decoupled into an industry-standard 3-tier data lake and a modular source package:

```text
final_project/
├── HANDOFF.md                              # THIS HANDOFF DOCUMENT (Agent-to-Agent Continuity)
├── README.md                               # User-facing project manual & quickstart
├── GUIDE.md                                # Detailed specification & scoring rubric mapping
├── chi_dan.md                              # Historical guidance & initial observations
├── CRAWLER_GUIDE.md                        # Technical scraping reference
├── data/
│   ├── 01_raw/                             # Tier 1: Raw ingested CSV scrapes from CafeLand
│   │   └── raw_cafeland_thue_summary_50.csv
│   ├── 02_intermediate/                    # Tier 2: Enriched data via Two-Stage Hybrid LLM
│   │   ├── <dataset>_enriched.csv
│   │   ├── <dataset>_enriched.json
│   │   └── <dataset>_enriched_checkpoint.json
│   └── 03_processed/                       # Tier 3: Gold ML-ready dataset (Cleaned, Typed, Capped)
│       ├── gold_student_rental_train.csv   # Scikit-learn tabular format
│       └── gold_student_rental_train.json  # Comprehensive data dictionary & summary stats
└── src/
    ├── config.json                         # API Credentials & Primary Model Name (INVARIANT)
    ├── crawler_rental.py                   # High-throughput multi-threaded CafeLand rental crawler
    ├── llm_extractor.py                    # Two-Stage Hybrid Student Feature Extractor (Regex + Mega-Batch)
    ├── standardize_data.py                 # Deterministic parsing, 3-layer anti-leak filter & domain imputation
    └── main.py                             # Central CLI pipeline coordinator (Interactive + Argparse)
```

---

## 3. ROOT CAUSE ANALYSES & RESOLVED DEFECTS

### Bug 1: Nationwide Warehouse (`kho xưởng`) & Villa (`biệt thự`) Data Contamination
* **Symptom**: Scraped files were severely contaminated with industrial warehouses in Bắc Ninh/Vĩnh Phúc (400–900M VND/month), commercial office spaces in Hanoi, and luxury villas in Thảo Điền (80M VND/month).
* **Root Cause Discovered**:
  * CafeLand's web server does not support URLs of format `/cho-thue-nha-dat/tp-ho-chi-minh/`. When requested, CafeLand issues an internal HTTP 301/302 Redirect to `https://nhadat.cafeland.vn/cho-thue/` (**Nationwide General Rental Feed**).
  * On this nationwide page, CafeLand prioritizes high-paying VIP listings on the first 5 pages, which happen to be industrial factories and commercial properties across all of Vietnam.
* **Resolution Implemented**:
  1. Updated [`crawler_rental.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/crawler_rental.py) with verified, non-redirecting internal category URLs:
     * Room / Dorm: `https://nhadat.cafeland.vn/cho-thue/phong-tro-tai-tp-ho-chi-minh/`
     * Apartment / Studio: `https://nhadat.cafeland.vn/cho-thue/can-ho-chung-cu-tai-tp-ho-chi-minh/`
     * Whole House: `https://nhadat.cafeland.vn/cho-thue/nha-rieng-tai-tp-ho-chi-minh/`
  2. Balanced Multi-Category Ingestion: When crawling with `category="all"`, the crawler partitions `target_count` evenly across these 3 verified sub-endpoints.
  3. Strict 3-Layer Blacklist (`COMMERCIAL_AND_LUXURY_BLACKLIST`):
     * **Layer 1 (Crawler)**: Filters cards during ingestion matching keywords (`kho`, `xưởng`, `biệt thự`, `villa`, `văn phòng`, `mặt bằng`, `mbkd`, `shophouse`, `kcn`, `bãi xe`).
     * **Layer 2 (LLM Triage)**: Flags non-residential rentals as `SKIP_NON_RENTAL` to preserve API quota.
     * **Layer 3 (Standardization)**: Hard-drops any non-residential, non-HCM province records, or prices $> 40.0$ million VND/month.

### Bug 2: Fallback Classification Leakage in `standardize_data.py`
* **Symptom**: Unmatched warehouses and villas were forcibly assigned to `phong_tro_ktx`.
* **Root Cause Discovered**: Line 120 of `categorize_student_property()` ended with `return "phong_tro_ktx"`.
* **Resolution Implemented**: Changed fallback to `return None`. In `standardize_student_rental_dataset()`, records where `prop_type is None` are incremented in `dropped_commercial_or_villa` and skipped.

### Bug 3: Google Gemini API `503 UNAVAILABLE` ("High Demand") on `gemini-3.8-flash`
* **Symptom**: Model calls to `gemini-3.8-flash` intermittently fail with `503 Service Unavailable`.
* **Root Cause Discovered**:
  * `gemini-3.8-flash` is an experimental/preview frontier tier with limited GPU server capacity. When traffic spikes globally, Google's gateway returns `503 UNAVAILABLE`.
  * The original fallback list in `llm_extractor.py` referenced deprecated models (`gemini-1.5-flash`, `gemini-2.0-flash`), which threw 404 errors.
* **Resolution Implemented**:
  1. Updated fallback candidate list in [`llm_extractor.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/llm_extractor.py) to verified active models:
     `["gemini-flash-latest", "gemini-2.5-flash", "gemini-3.5-flash"]`.
  2. Added automated failover on HTTP 503 and HTTP 500: If `gemini-3.8-flash` encounters high-demand spikes, the pipeline automatically switches in-flight to `gemini-2.5-flash` or `gemini-flash-latest` without terminating execution.

---

## 4. MODULE ARCHITECTURE & PIPELINE USAGE

All production scripts reside in `src/` and are fully compiled and verified (`python -m py_compile` exits with code 0).

### 4.1 Script Summary
1. **[`src/config.json`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/config.json)**:
   * Contains `"api_key": "AIza...."`, `"name": "Gemini 3.8 Flash"`.
   * **Rule**: Treat as immutable. Do not alter credentials.
2. **[`src/crawler_rental.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/crawler_rental.py)**:
   * `crawl_rental_summary(target_count, output_path, max_workers, category)`: High-speed card extraction (7 fields).
   * `crawl_rental_detailed(target_count, output_path, max_workers, category)`: Deep scraping (20 fields) using `ThreadPoolExecutor`.
3. **[`src/llm_extractor.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/llm_extractor.py)**:
   * **Pass 1 (Regex Triage)**: Fast deterministic extraction of explicit bedroom, toilet, and amenity counts. Flags `DONE_REGEX`, `SKIP_NON_RENTAL`, `NEEDS_LLM`.
   * **Pass 2 (Mega-Batch LLM)**: Chunks ambiguous records into batches of 100–500 rows. Key-Value ID mapping eliminates index drift. Atomic checkpoint written to disk (`*_checkpoint.json`) after each batch.
4. **[`src/standardize_data.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/standardize_data.py)**:
   * Numeric parsing: `price_raw` $\rightarrow$ `gia_thue_trieu_thang` (Float, Million VND/mo), `area_raw` $\rightarrow$ `dien_tich_m2`.
   * Geographic mapping: Maps major student wards (Bến Thành, Thảo Điền, Tân Thuận, Tăng Nhơn Phú,...) to standard HCMC districts. Drops out-of-province listings.
   * Domain-based imputation: Imputes `so_phong_ngu = 1` for rooms/studios; imputes `so_toilet = 1` if `has_wc_rieng == 1`.
   * Dual export: `gold_student_rental_train.csv` (tabular ML) and `gold_student_rental_train.json` (metadata & dictionary).
5. **[`src/main.py`](file:///C:/Users/ftran/Downloads/VTLT/DAP/final_project/src/main.py)**:
   * CLI entry point supporting interactive mode (`python main.py`) and argument mode (`--step [crawl_summary|crawl_detail|enrich|standardize|pipeline|status]`).

### 4.2 Standard Execution Commands
All commands MUST be executed through Windows `cmd /c`:

```cmd
:: 1. Check data directory health and file counts
cmd /c python src/main.py --step status

:: 2. Crawl 7,000 raw summary records (takes ~3-5 mins)
cmd /c python src/main.py --step crawl_summary --count 7000 --category all

:: 3. Run Two-Stage Hybrid LLM Enrichment
cmd /c python src/main.py --step enrich --batch_size 100

:: 4. Clean, Impute & Export Gold ML Datasets
cmd /c python src/main.py --step standardize

:: 5. Or execute end-to-end pipeline automatically
cmd /c python src/main.py --step pipeline --count 7000
```

---

## 5. GOLD TRAINING DATASET SPECIFICATION (`data/03_processed/`)

| Column Name | Data Type | Description & Domain Significance |
| :--- | :--- | :--- |
| `gia_thue_trieu_thang` | `Float64` | **Target Variable ($y$)**: Monthly rent in Million VND/month ($0.5 \le y \le 40.0$). |
| `dien_tich_m2` | `Float64` | Usable floor area in $m^2$ ($5.0 \le \text{area} \le 350.0$). |
| `don_gia_nghin_m2` | `Float64` | Unit price ($1,000\text{ VND}/m^2$). Calculated as $\frac{y \times 1000}{\text{area}}$. |
| `quan_huyen` | `Category` | District in TP.HCM (Quận 1, 7, 10, Bình Thạnh, Gò Vấp, Thủ Đức,...). |
| `property_type` | `Category` | Strict 3-class partition: `phong_tro_ktx`, `can_ho`, `nha_nguyen_can`. |
| `so_phong_ngu` | `Int8` | Bedroom count (Dorm / Room / Studio default = 1). |
| `so_toilet` | `Int8` | Bathroom count. |
| `has_wc_rieng` | `Int8 (0/1)`| Binary: 1 = Private/en-suite bathroom; 0 = Shared bathroom. |
| `has_gac_lung` | `Int8 (0/1)`| Binary: 1 = Mezzanine/loft present (effectively doubles usable space). |
| `has_may_lanh` | `Int8 (0/1)`| Binary: 1 = Air conditioner equipped; 0 = Not equipped. |
| `gio_tu_do` | `Int8 (0/1)`| Binary: 1 = Curfew-free / biometric access; 0 = Shared with landlord / curfew. |
| `cho_nau_an` | `Int8 (0/1)`| Binary: 1 = Kitchen / cooking permitted; 0 = Cooking prohibited. |
| `is_full_furniture`| `Int8 (0/1)`| Binary: 1 = Fully furnished (bed, mattress, fridge, wardrobe); 0 = Unfurnished. |

---

## 6. ROADMAP & INSTRUCTIONS FOR INCOMING AGENTS

The incoming agent should proceed in the following order:

### Phase 1: Full-Scale Data Ingestion (Target: $\ge 5,000$ clean rows)
* Execute `main.py --step crawl_summary --count 7500`.
* Run `main.py --step standardize` to verify the resulting `gold_student_rental_train.csv` contains $\ge 5,000$ clean records.
* Verify zero contamination from keywords (`kho`, `xưởng`, `biệt thự`, `villa`, `mặt bằng`).

### Phase 2: Exercise 3 — Exploratory Data Analysis & Visualization (Tuần 8, LO3, LO4, LO5 — 25 pts)
* Create `notebooks/01_eda_student_rental.ipynb` (or `src/eda_visualization.py`).
* Generate mandatory analytical visualizations:
  1. **Univariate Analysis**: Histogram and KDE plots of `gia_thue_trieu_thang` (demonstrate right-skewness to justify log-transformation).
  2. **Bivariate Analysis**: Boxplots of `gia_thue_trieu_thang` broken down by `property_type` and `quan_huyen`.
  3. **Amenity Value Impact**: Boxplots comparing price distributions with vs. without key amenities (`has_gac_lung`, `has_may_lanh`, `has_wc_rieng`).
  4. **Geographic Pricing Heatmap**: Average unit rental price per $m^2$ across major university hubs (Thủ Đức, Quận 10, Bình Thạnh, Gò Vấp, Quận 7).
  5. **Multivariate Correlation Matrix**: Heatmap of numerical and binary features against target rent.

### Phase 3: Exercise 4 — Regression Modeling & AVM Valuation (Tuần 9, LO6 — 25 pts)
* Create `src/train_avm.py` implementing `sklearn.pipeline.Pipeline`:
  * Split: 80% Train, 20% Test (`random_state=42`).
  * Transformation: `Winsorizer` for numerical capping, `OneHotEncoder(drop_last=True)` for categorical features, `TransformedTargetRegressor` with `np.log1p`.
  * Algorithms:
    * Baseline: Ridge Regression ($\alpha$ tuned via `RidgeCV`).
    * Champion 1: `RandomForestRegressor`.
    * Champion 2: `XGBoost` or `LightGBM`.
  * Metrics: Compute MAE (Million VND), RMSE, $R^2$, and MAPE.
  * AVM Application: Calculate residuals $y - \hat{y}$ to identify **Overpriced** vs. **Bargain** listings for university students.

---

## 7. CRITICAL AGENT CONSTRAINTS & BEHAVIORAL PROTOCOLS

1. **Operating System Shell Rule**: All commands executed on the system MUST use `cmd /c <command>` to ensure proper EOF signal handling on Windows. (e.g., `cmd /c python main.py --step status`).
2. **Do Not Hallucinate API Keys or Models**: Keep `src/config.json` intact. Use candidate model fallback logic already coded in `src/llm_extractor.py`.
3. **Data Leakage Prohibition**: Never fit transformers, scalers, or encoders on the combined dataset. Always split Train/Test first.
4. **File Path Discipline**: Always refer to project files using forward-slash clickable markdown links with `file:///` scheme.
