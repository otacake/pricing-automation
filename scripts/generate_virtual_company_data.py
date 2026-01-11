from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

import argparse  # CLI引数を扱うため
from pathlib import Path  # パスをOS非依存で扱うため

from pricing.virtual_company import VirtualCompanySpec, write_company_expense_csv  # 仮想会社データ生成に使うため


def main() -> int:  # スクリプトのメイン処理をまとめる
    parser = argparse.ArgumentParser()  # 引数パーサを作る
    parser.add_argument("--out", default="data/company_expense.csv")  # 出力先CSVの指定
    parser.add_argument("--seed", type=int, default=12345)  # 乱数シードの指定
    parser.add_argument("--start-year", type=int, default=2025)  # 開始年の指定
    parser.add_argument("--years", type=int, default=5)  # 生成年数の指定
    args = parser.parse_args()  # 引数を解析する

    spec = VirtualCompanySpec(start_year=args.start_year, years=args.years)  # 入力仕様を構築する
    out_path = write_company_expense_csv(Path(args.out), seed=args.seed, spec=spec)  # CSVを書き出す
    print(f"Wrote: {out_path}")  # 出力先を表示する
    return 0  # 正常終了コードを返す


if __name__ == "__main__":  # 直接実行時のみmainを呼ぶ
    raise SystemExit(main())  # 終了コードを返す
