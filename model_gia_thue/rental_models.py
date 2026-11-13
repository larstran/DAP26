"""Two rental estimators; all prices in million VND/month."""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder
from train_avm import prepare_features, NUM, BIN, CAT

FEATURES = ['dien_tich_m2', 'property_type', 'quan_huyen', 'title_raw',
            'so_phong_ngu', 'so_toilet', 'has_gac_lung', 'has_may_lanh', 'is_full_furniture']


def validate(frame):
    missing = sorted(set(FEATURES) - set(frame.columns))
    if missing:
        raise ValueError(f'Missing input columns: {missing}')
    if frame.empty:
        raise ValueError('Input contains no listings')
    frame = frame[FEATURES].copy()
    for col in ['dien_tich_m2', 'so_phong_ngu', 'so_toilet'] + BIN:
        frame[col] = pd.to_numeric(frame[col], errors='raise')
        if not np.isfinite(frame[col]).all():
            raise ValueError(f'{col} must be finite')
    if (frame.dien_tich_m2 <= 0).any():
        raise ValueError('dien_tich_m2 must be positive')
    for col in CAT:
        if frame[col].isna().any() or frame[col].astype(str).str.strip().eq('').any():
            raise ValueError(f'{col} must not be empty')
    return frame


def build_extra_trees(min_samples_leaf=2):
    features = ColumnTransformer([
        ('numeric', 'passthrough', NUM + BIN),
        ('category', OneHotEncoder(handle_unknown='ignore', sparse_output=False), CAT),
    ])
    estimator = Pipeline([
        ('features', features),
        ('trees', ExtraTreesRegressor(n_estimators=400, min_samples_leaf=min_samples_leaf,
                                     max_features=1.0, random_state=42, n_jobs=2)),
    ])
    return Pipeline([
        ('prepare', FunctionTransformer(prepare_features)),
        ('estimator', TransformedTargetRegressor(regressor=estimator,
                                                func=np.log1p, inverse_func=np.expm1)),
    ])


def predict(bundle, frame):
    frame = validate(frame)
    point = np.maximum(bundle['model'].predict(frame), 0)
    radius = bundle['calibration_log_radius']
    result = pd.DataFrame({'prediction': point,
                          'lower_90': np.maximum(np.expm1(np.log1p(point) - radius), 0),
                          'upper_90': np.expm1(np.log1p(point) + radius)})
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError('Nonfinite prediction')
    return result
