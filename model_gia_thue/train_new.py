"""Train ExtraTrees without modifying the preserved LightGBM artifact."""
import hashlib
import json
import math
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score, mean_absolute_percentage_error
from sklearn.model_selection import GroupKFold
from train_avm import load_and_audit, TARGET
from rental_models import build_extra_trees, predict

ROOT = Path(__file__).resolve().parent


def scores(y, p):
    return dict(MAE=float(mean_absolute_error(y, p)), RMSE=float(root_mean_squared_error(y, p)),
                R2=float(r2_score(y, p)), MAPE_percent=float(100 * mean_absolute_percentage_error(y, p)),
                within_20_percent=float(np.mean(np.abs(y-p)/y <= .2)))


def main():
    source = ROOT/'data/rental.csv'
    old = json.loads((ROOT/'evaluation/existing_metrics.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != old['source_sha256']:
        raise ValueError('Dataset differs from the existing model source')
    df = load_and_audit(source)
    membership = pd.read_csv(ROOT/'data/split_membership.csv')
    if len(df) != len(membership) or not np.array_equal(membership.row, np.arange(len(df))) or not np.array_equal(membership.group, df.grp):
        raise ValueError('Partition alignment mismatch')
    parts = {name: np.flatnonzero(membership.partition.eq(name)) for name in ['fit', 'calibration', 'test']}
    for a, b in [('fit', 'calibration'), ('fit', 'test'), ('calibration', 'test')]:
        if set(df.iloc[parts[a]].grp) & set(df.iloc[parts[b]].grp):
            raise ValueError('Group leakage')
    fit, cal, test = (parts[name] for name in ['fit', 'calibration', 'test'])
    y = df[TARGET].to_numpy()
    candidates = {f'extratrees_leaf_{leaf}': build_extra_trees(leaf) for leaf in [1, 2, 4]}
    rows = []
    for name, estimator in candidates.items():
        fold_scores = []
        for fold, (a, b) in enumerate(GroupKFold(5).split(fit, groups=df.iloc[fit].grp), 1):
            model = clone(estimator).fit(df.iloc[fit[a]], y[fit[a]])
            value = float(mean_absolute_error(y[fit[b]], model.predict(df.iloc[fit[b]])))
            fold_scores.append(value)
            print(f'{name} fold {fold}: MAE={value:.6f}', flush=True)
        rows.append(dict(candidate=name, CV_MAE=float(np.mean(fold_scores)), CV_sd=float(np.std(fold_scores)),
                         **{f'fold_{i+1}': v for i, v in enumerate(fold_scores)}))
    pd.DataFrame(rows).to_csv(ROOT/'evaluation/new_cv.csv', index=False)
    best = min(rows, key=lambda row: row['CV_MAE'])
    model = clone(candidates[best['candidate']]).fit(df.iloc[fit], y[fit])
    residual = np.abs(np.log1p(y[cal])-np.log1p(np.maximum(model.predict(df.iloc[cal]), 0)))
    grouped = pd.Series(residual).groupby(df.iloc[cal].grp.to_numpy()).max().to_numpy()
    rank = math.ceil((len(grouped)+1)*.9)
    if rank > len(grouped):
        raise ValueError('Insufficient calibration groups')
    radius = float(np.partition(grouped, rank-1)[rank-1])
    bundle = dict(model=model, task='rental', target=TARGET, unit='triệu VNĐ/tháng',
                  candidate=best['candidate'], calibration_log_radius=radius, interval_nominal=.9)
    joblib.dump(bundle, ROOT/'models/extratrees_new.joblib')
    comparison, segments = [], []
    for name in ['lightgbm_existing', 'extratrees_new']:
        loaded = joblib.load(ROOT/f'models/{name}.joblib')
        pred = predict(loaded, df.iloc[test])
        covered = (y[test] >= pred.lower_90) & (y[test] <= pred.upper_90)
        row = dict(model=name, **scores(y[test], pred.prediction),
                   coverage_90_rows=float(covered.mean()),
                   coverage_90_groups=float(pd.Series(covered.to_numpy()).groupby(df.iloc[test].grp.to_numpy()).all().mean()),
                   median_interval_width=float(np.median(pred.upper_90-pred.lower_90)))
        comparison.append(row)
        result = df.iloc[test][['id', 'property_type', 'quan_huyen', TARGET]].reset_index(drop=True).join(pred)
        result.to_csv(ROOT/f'evaluation/{name}_test.csv', index=False, encoding='utf-8-sig')
        for label, group in result.groupby('property_type'):
            segments.append(dict(model=name, property_type=label, n=len(group), **scores(group[TARGET], group.prediction)))
        if name == 'lightgbm_existing' and not np.isclose(row['MAE'], old['test']['MAE'], atol=1e-8):
            raise ValueError('Existing-model evaluation does not match recorded baseline')
    pd.DataFrame(comparison).to_csv(ROOT/'evaluation/comparison.csv', index=False)
    pd.DataFrame(segments).to_csv(ROOT/'evaluation/segments.csv', index=False)
    metadata = dict(source_sha256=digest, source_github='https://github.com/larstran/DAP26',
                    partitions={k: len(v) for k, v in parts.items()}, selected_cv=best,
                    new_interval_log_radius=radius, comparison=comparison,
                    limitations=['Historical asking rents, not transaction prices or current market appraisal.',
                                 'Previously inspected holdout, not a fresh independent benchmark.',
                                 'Grouping is heuristic; source location and rental-unit errors remain.',
                                 '90% intervals assume exchangeable groups; no individual guarantee.'])
    (ROOT/'evaluation/report.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
