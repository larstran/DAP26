"""AVM giá thuê trọ sinh viên TP.HCM (DAP26 - Exercise 4).

Chạy:  python train_avm.py
Đầu vào : gold_student_rental_train_from_20000.csv (cùng thư mục)
Đầu ra  : outputs/  (metrics, model .joblib, bảng AVM overpriced/bargain, hình)
"""
import re
import sys
from pathlib import Path

import joblib
import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import RidgeCV
from sklearn.metrics import (mean_absolute_error, mean_absolute_percentage_error,
                             r2_score, root_mean_squared_error)
from sklearn.model_selection import (GroupKFold, GroupShuffleSplit,
                                     cross_val_predict, cross_validate)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "gold_student_rental_train_from_20000.csv"
OUT = ROOT / "outputs"
SEED = 42
TARGET = "gia_thue_trieu_thang"

NUM = ["dien_tich_m2", "log_area", "so_phong_ngu", "so_toilet"]
BIN = ["has_gac_lung", "has_may_lanh", "is_full_furniture"]
CAT = ["property_type", "quan_huyen"]
TEXT = "title_clean"
# Bị loại khỏi feature:
#  - don_gia_nghin_m2 = y*1000/area  -> rò rỉ trực tiếp biến mục tiêu
#  - has_wc_rieng, gio_tu_do, cho_nau_an: ~99.9% = 1 (do imputation) -> không mang thông tin
#  - source_flag: metadata pipeline, không có khi định giá tin mới
# Chữ ký tin rao (dùng để khử trùng lặp và làm group khi chia train/test)
SIGNATURE = ["property_type", "quan_huyen", TARGET, "dien_tich_m2",
             "so_phong_ngu", "so_toilet", "has_gac_lung", "has_may_lanh", "is_full_furniture"]

PREFIX = re.compile(r"(cho thuê )?(phòng trọ|nhà riêng|căn hộ chung cư)\s*:")
PRICE_AFTER_GIA = re.compile(r"giá\s*(?:(?:chỉ|thuê|tốt|rẻ|từ)\s*)*:?\s*\d+(?:[.,]\d+)*")
PRICE_TOKEN = re.compile(
    r"\d+(?:[.,]\d+)*\s*(?:triệu\b|tr(?:\d+(?:[.,]\d+)*|\b)|củ\b|k\b|nghìn\b|ngàn\b|t\b|đồng\b|đ\b|vnd\b)",
    re.IGNORECASE,
)


def clean_title(s: str) -> str:
    """Xóa biểu thức giá có đơn vị và giá ghi rõ, giữ số diện tích/phòng/tầng."""
    s = PREFIX.sub("", s.lower())
    s = PRICE_TOKEN.sub(" ", s)
    s = PRICE_AFTER_GIA.sub(" giá ", s)
    return re.sub(r"\s+", " ", s).strip()


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cùng phép biến đổi xác định cho dữ liệu huấn luyện và tin mới."""
    df = df.copy()
    if not np.isfinite(df.dien_tich_m2).all() or (df.dien_tich_m2 <= 0).any():
        raise ValueError("dien_tich_m2 phải hữu hạn và > 0")
    df["has_may_lanh"] = df.has_may_lanh.clip(0, 1)
    for col in ["so_phong_ngu", "so_toilet"]:
        df[col] = df[col].clip(0, 10)
    df["log_area"] = np.log(df.dien_tich_m2)
    df[TEXT] = df.title_raw.fillna("").map(clean_title)
    return df


def listing_groups(df: pd.DataFrame) -> np.ndarray:
    """Thành phần liên thông: cùng slug HOẶC chữ ký luôn cùng fold."""
    parent = np.arange(len(df))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    signatures = pd.MultiIndex.from_frame(df[SIGNATURE]).factorize()[0]
    for keys in (signatures, df.slug):
        first = {}
        for i, key in enumerate(keys):
            if pd.isna(key) or key == "":
                continue
            if key in first:
                parent[find(i)] = find(first[key])
            else:
                first[key] = i
    return np.array([find(i) for i in range(len(df))])


def predict_listing(model, **kw) -> float:
    """Định giá tin mới; không cần giá rao hoặc các cột audit."""
    return float(model.predict(prepare_features(pd.DataFrame([kw])))[0])


def load_and_audit(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    print(f"[1] Đọc {path.name}: {df.shape[0]:,} dòng x {df.shape[1]} cột, NaN = {int(df.isna().sum().sum())}")
    assert not df.id.duplicated().any() and not df.url.duplicated().any(), "id/url trùng"
    gap = (df[TARGET] * 1000 / df.dien_tich_m2 - df.don_gia_nghin_m2).abs().max()
    print(f"    don_gia_nghin_m2 = y*1000/diện tích (sai lệch tối đa {gap:.4f}) -> LOẠI (rò rỉ)")
    print(f"    quan_huyen = 'Khác': {(df.quan_huyen == 'Khác').mean():.1%} số dòng (bước trích quận yếu)")
    for c in ["has_wc_rieng", "gio_tu_do", "cho_nau_an"]:
        print(f"    {c}: tỷ lệ = 1 là {df[c].mean():.2%} -> LOẠI (gần hằng số)")
    print(f"    has_may_lanh có giá trị ngoài {{0,1}}: {int((~df.has_may_lanh.isin([0, 1])).sum())} -> clip về 1")
    print(f"    so_phong_ngu > 10: {int((df.so_phong_ngu > 10).sum())}, so_toilet > 10: {int((df.so_toilet > 10).sum())} -> clip 10")

    df = prepare_features(df)

    # Tin đăng lại: cùng slug URL + cùng toàn bộ thuộc tính = cùng một tin, chỉ khác mã tin.
    df["slug"] = df.url.str.extract(r"cafeland\.vn/(.*)-\d+\.html")[0]
    n0 = len(df)
    df = df.drop_duplicates(subset=SIGNATURE + ["slug"]).reset_index(drop=True)
    print(f"    Xóa {n0 - len(df):,} tin đăng lại (trùng slug + thuộc tính) -> còn {len(df):,} dòng")

    # Liên kết cả tin đăng lại đổi giá/thuộc tính, không chỉ chữ ký giống hệt.
    df["grp"] = listing_groups(df)
    print(f"    {df.grp.nunique():,} nhóm liên thông slug/thuộc tính (split/CV)")
    return df


def preprocessor(scale: bool, text: bool) -> ColumnTransformer:
    parts = [("num", StandardScaler() if scale else "passthrough", NUM + BIN),
             ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10), CAT)]
    if text:
        parts.append(("txt", TfidfVectorizer(ngram_range=(1, 2), min_df=5, max_features=3000,
                                             sublinear_tf=True), TEXT))
    return ColumnTransformer(parts)


def log_target(est) -> TransformedTargetRegressor:
    return TransformedTargetRegressor(est, func=np.log1p, inverse_func=np.expm1)


def build_models() -> dict:
    lgbm = dict(learning_rate=0.03, subsample=0.8, subsample_freq=1, verbose=-1, random_state=SEED)
    return {
        "Ridge (bảng)": log_target(make_pipeline(preprocessor(True, False), RidgeCV(alphas=np.logspace(-3, 3, 13)))),
        "RandomForest (bảng)": log_target(make_pipeline(preprocessor(False, False),
                                                        RandomForestRegressor(400, min_samples_leaf=3, n_jobs=-1, random_state=SEED))),
        "LightGBM (bảng)": log_target(make_pipeline(preprocessor(False, False),
                                                    lgb.LGBMRegressor(n_estimators=800, num_leaves=31, colsample_bytree=0.8, **lgbm))),
        "Ridge (bảng+tiêu đề)": log_target(make_pipeline(preprocessor(True, True), RidgeCV(alphas=np.logspace(-2, 3, 11)))),
        "LightGBM (bảng+tiêu đề)": log_target(make_pipeline(preprocessor(False, True),
                                                            lgb.LGBMRegressor(n_estimators=1500, num_leaves=63, min_child_samples=15,
                                                                              colsample_bytree=0.5, **lgbm))),
    }


def metrics(y, p) -> dict:
    return {"MAE": mean_absolute_error(y, p), "RMSE": root_mean_squared_error(y, p),
            "R2": r2_score(y, p), "MAPE%": 100 * mean_absolute_percentage_error(y, p)}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    df = load_and_audit(DATA)
    y = df[TARGET].to_numpy()

    tr, te = next(GroupShuffleSplit(1, test_size=0.2, random_state=SEED).split(df, y, df.grp))
    Xtr, Xte, ytr, yte = df.iloc[tr], df.iloc[te], y[tr], y[te]
    print(f"\n[2] Chia nhóm 80/20 (random_state={SEED}): train {len(tr):,} | test {len(te):,}")

    models = build_models()
    cv = GroupKFold(5)
    rows = []
    print("\n[3] 5-fold GroupKFold trên train + đánh giá test (đơn vị: triệu VNĐ/tháng)")
    for name, model in models.items():
        s = cross_validate(model, Xtr, ytr, groups=Xtr.grp, cv=cv, scoring="neg_mean_absolute_error")
        model.fit(Xtr, ytr)
        row = {"model": name, "CV_MAE": -s["test_score"].mean(), "CV_MAE_sd": s["test_score"].std(),
               **{f"test_{k}": v for k, v in metrics(yte, model.predict(Xte)).items()}}
        rows.append(row)
        print(f"    {name:<26} CV MAE {row['CV_MAE']:.3f}±{row['CV_MAE_sd']:.3f} | test MAE {row['test_MAE']:.3f} "
              f"RMSE {row['test_RMSE']:.3f} R² {row['test_R2']:.3f} MAPE {row['test_MAPE%']:.1f}%")
    res = pd.DataFrame(rows)
    res.round(4).to_csv(OUT / "metrics.csv", index=False, encoding="utf-8-sig")

    best = res.loc[res.CV_MAE.idxmin(), "model"]          # chọn theo CV, không theo test
    champ = models[best]
    p_te = champ.predict(Xte)
    print(f"\n[4] Champion (theo CV MAE): {best}")
    seg = pd.DataFrame({"type": Xte.property_type.values, "y": yte, "p": p_te}).groupby("type")[["y", "p"]].apply(
        lambda g: pd.Series({"n": len(g), "MAE": mean_absolute_error(g.y, g.p),
                             "MAPE%": 100 * mean_absolute_percentage_error(g.y, g.p)}))
    print(seg.round(2).to_string())
    seg.round(4).to_csv(OUT / "metrics_by_property_type.csv", encoding="utf-8-sig")

    # Kiểm tra rò rỉ qua tiêu đề: lợi ích của text phải tồn tại cả ở tin KHÔNG ghi giá trong tiêu đề
    has_price = Xte.title_raw.map(lambda s: bool(PRICE_TOKEN.search(s) or PRICE_AFTER_GIA.search(s.lower()))).to_numpy()
    p_tab = models["LightGBM (bảng)"].predict(Xte)
    for lab, m in [("tiêu đề có giá", has_price), ("tiêu đề không có giá", ~has_price)]:
        if not m.any():
            continue
        print(f"    {lab:<22} n={m.sum():>4}  MAE champion {mean_absolute_error(yte[m], p_te[m]):.3f} | "
              f"LightGBM bảng {mean_absolute_error(yte[m], p_tab[m]):.3f}")

    # AVM: dự báo out-of-fold trên TOÀN bộ dữ liệu -> mỗi tin được định giá bởi mô hình chưa từng thấy nó.
    oof = cross_val_predict(champ, df, y, groups=df.grp, cv=GroupKFold(5))
    ratio = y / oof
    avm = df[["id", "url", "title_raw", "property_type", "quan_huyen", "dien_tich_m2", TARGET]].assign(
        gia_du_bao=oof.round(2), chenh_lech=(y - oof).round(2), ty_le_gia=ratio.round(3),
        nhan=np.select([ratio >= 1.25, ratio <= 0.80], ["Overpriced", "Bargain"], "Fair"))
    avm.sort_values("ty_le_gia").to_csv(OUT / "avm_valuation.csv", index=False, encoding="utf-8-sig")
    print(f"\n[5] AVM (OOF, ngưỡng +25%/−20%): {avm.nhan.value_counts().to_dict()}")
    print("    Nhãn là chênh lệch với model, không phải khuyến nghị đầu tư; OOF không phải nested CV.")
    print("    5 tin cần kiểm tra giá/dữ liệu trước (không mặc định là món hời):")
    print(avm.nsmallest(5, "ty_le_gia")[["title_raw", TARGET, "gia_du_bao", "ty_le_gia"]].to_string(index=False))

    champ.fit(df, y)                                     # model cuối fit trên toàn bộ dữ liệu sạch
    joblib.dump(champ, OUT / "avm_champion.joblib")

    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    res.set_index("model")[["test_MAE"]].plot.barh(ax=ax[0], legend=False, color="#4C72B0")
    ax[0].set(title="MAE trên tập test (triệu/tháng)", xlabel="MAE", ylabel="")
    ax[1].scatter(yte, p_te, s=6, alpha=0.35)
    ax[1].plot([0, 40], [0, 40], "r--", lw=1)
    ax[1].set(title=f"{best}: thực tế vs dự báo (test)", xlabel="Giá thực tế", ylabel="Giá dự báo")
    ax[2].hist(np.log(ratio), bins=80, color="#55A868")
    for v in (np.log(0.8), np.log(1.25)):
        ax[2].axvline(v, color="r", ls="--", lw=1)
    ax[2].set(title="log(giá thực / giá AVM) - OOF", xlabel="log ratio")
    fig.tight_layout()
    fig.savefig(OUT / "model_report.png", dpi=130)
    plt.close(fig)
    print(f"\n[6] Đã lưu vào {OUT}: metrics.csv, metrics_by_property_type.csv, avm_valuation.csv, "
          f"avm_champion.joblib, model_report.png")


if __name__ == "__main__":
    main()
