"""Usage: python predict.py --model both --input example.json"""
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from rental_models import predict

ROOT = Path(__file__).resolve().parent
MODELS = {'existing': 'lightgbm_existing', 'new': 'extratrees_new'}


def main():
    parser = argparse.ArgumentParser(description='Hai model dự đoán giá thuê, đơn vị triệu VNĐ/tháng')
    parser.add_argument('--model', choices=['existing', 'new', 'both'], default='both')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', action='store_true', help='So sánh với gia_thue_trieu_thang trong đầu vào')
    parser.add_argument('--plot', type=Path, help='Lưu biểu đồ PNG; cần --compare')
    args = parser.parse_args()
    if args.plot and not args.compare:
        parser.error('--plot cần --compare')
    if args.input.suffix.lower() == '.csv':
        frame = pd.read_csv(args.input)
    else:
        records = json.loads(args.input.read_text(encoding='utf-8-sig'))
        frame = pd.DataFrame([records] if isinstance(records, dict) else records)
    if args.compare:
        if 'gia_thue_trieu_thang' not in frame:
            parser.error('--compare cần cột gia_thue_trieu_thang (triệu VNĐ/tháng)')
        prices = pd.to_numeric(frame['gia_thue_trieu_thang'], errors='coerce')
        if not np.isfinite(prices).all() or (prices <= 0).any():
            parser.error('gia_thue_trieu_thang phải là số hữu hạn > 0 cho mọi tin')
    results = []
    for key in (MODELS if args.model == 'both' else [args.model]):
        name = MODELS[key]
        bundle = joblib.load(ROOT/f'models/{name}.joblib')
        result = predict(bundle, frame)
        result.insert(0, 'input_row', range(len(frame)))
        result.insert(1, 'model', name)
        if args.compare:
            for col in ['id', 'url', 'property_type', 'quan_huyen', 'dien_tich_m2']:
                if col in frame:
                    result[col] = frame[col].to_numpy()
            result['gia_rao'] = prices.to_numpy()
            result['chenh_lech'] = result['gia_rao'] - result['prediction']
            result['so_voi_du_bao'] = np.where(result['chenh_lech'] < 0, 'Dưới dự báo',
                                             np.where(result['chenh_lech'] > 0, 'Trên dự báo', 'Bằng dự báo'))
        result['unit'] = bundle['unit']
        results.append(result)
    output = pd.concat(results, ignore_index=True)
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(9, 7), layout='constrained')
        for name, group in output.groupby('model', sort=False):
            ax.scatter(group['prediction'], group['gia_rao'], s=14, alpha=0.45, label=name)
        limit = max(output['prediction'].max(), output['gia_rao'].max()) * 1.05
        ax.plot([0, limit], [0, limit], '--', color='black', label='Giá rao = giá dự đoán')
        ax.set(xlim=(0, limit), ylim=(0, limit), xlabel='Giá dự đoán (triệu VNĐ/tháng)',
               ylabel='Giá rao (triệu VNĐ/tháng)', title='Giá rao so với giá model dự đoán')
        ax.set_aspect('equal', adjustable='box')
        ax.grid(alpha=0.2)
        ax.legend()
        fig.text(0.5, 0.01, 'Dưới đường: giá rao thấp hơn dự báo; cần kiểm tra tin và chi phí thực tế.',
                 ha='center', fontsize=9)
        fig.savefig(args.plot, dpi=150, bbox_inches='tight')
        plt.close(fig)
    if args.output:
        output.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(args.output)
    else:
        print(output.to_json(orient='records', force_ascii=False, indent=2))


if __name__ == '__main__':
    main()
