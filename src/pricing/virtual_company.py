from __future__ import annotations  # 型注釈の前方参照を許可し、循環参照を避けるため

"""
仮想会社データ（company_expense.csv）を再現性つきで生成するモジュール。

目的
- 本プロジェクトでは、収益性検証（プロフィットテスティング）で必要となる事業費前提を、
  実データが手元にない段階でも一貫した規約で生成できる状態にする。
- 「妥当に見える」ことよりも、「再現性」と「入力パラメータの意味が明確である」ことを優先する。

生成物（data/company_expense.csv）
- 年次パネル（year をキー）として、件数・保有・保険料収入・費用総額を収録する。
- 費用総額は、新契約費・維持費・集金費・共通費（間接費）に分割している。
- ここで生成するのは「会社の総額データ」であり、個別契約の費用ではない。

重要な規約
- 乱数は seed で固定する。seed が同一なら出力CSVも同一になる。
- ノイズは費用総額に対して乗算（1 + 正規ノイズ）で付与する。
  -> 金額の桁と整合しやすく、年次のスケールに比例して揺らぎが増える。
- 固定費（*_fixed_total）と共通費（overhead_total）は、初期値として年次一定とする。
  -> 後で「成長率」や「物価上昇」等の仮定を追加して差し替え可能。

後段（収益性検証側）での利用方法（予定）
- 新契約費（1件あたり）＝（acq_var_total + acq_fixed_total + overhead_total×配賦比率）/ new_policies
- 維持費（1件あたり）＝（maint_var_total + maint_fixed_total + overhead_total×配賦比率）/ inforce_avg
- 集金費（保険料比例率）＝ coll_var_total / premium_income
- 配賦比率は configs/*.yaml で指定する（例：共通費を獲得:50%・維持:50% など）。
"""

from dataclasses import dataclass  # 入力パラメータを構造化するため
from pathlib import Path  # ファイルパスをOS非依存で扱うため

import numpy as np  # 乱数と配列計算に使うため
import pandas as pd  # データフレーム作成に使うため


@dataclass(frozen=True)  # 入力パラメータを不変で扱うため
class VirtualCompanySpec:  # 仮想会社データの前提条件をまとめる
    """
    仮想会社生成の入力パラメータ。

    単位
    - 金額：円
    - 率：年率（例：0.03 は 3%）
    - 件数：件（年次の新契約件数、期中平均保有契約件数）

    位置づけ
    - ここでの premium_income は「当年度の保険料収入総額」を想定する。
    - coll_rate は「集金費総額 / 保険料収入総額」の比率を想定する。
    """

    start_year: int = 2025  # 開始年
    years: int = 5  # 生成する年数

    # 規模（初年度）
    new_policies_0: int = 12_000  # 初年度の新契約件数
    inforce_avg_0: int = 90_000  # 初年度の平均保有件数
    premium_income_0: int = 72_000_000_000  # 初年度の保険料収入総額（円）

    # 年成長率（決定論）
    new_policies_growth: float = 0.03  # 新契約件数の年成長率
    inforce_growth: float = 0.02  # 保有件数の年成長率
    premium_income_growth: float = 0.03  # 保険料収入の年成長率

    # 単価・率（初年度）
    acq_var_per_policy: int = 150_000  # 獲得変動費（円/新契約）
    acq_fixed_total: int = 600_000_000  # 獲得固定費（円/年）
    maint_var_per_inforce: int = 10_000  # 維持変動費（円/保有）
    maint_fixed_total: int = 500_000_000  # 維持固定費（円/年）
    coll_rate: float = 0.003  # 集金費率（保険料収入比）
    overhead_total: int = 400_000_000  # 共通費（円/年）

    # ノイズ（費用総額へ乗算）
    noise_sd_ratio: float = 0.02  # 乱数ノイズの標準偏差比率


def _noisy(rng: np.random.Generator, x: int, sd_ratio: float) -> int:  # 乱数ノイズを付与して整数に丸める
    """
    乗算ノイズ（1 + 正規ノイズ）を適用し、整数円へ丸める。
    - sd_ratio は標準偏差（比率）であり、0.02 は 2% 程度の揺らぎを意味する。
    """
    z = rng.normal(loc=0.0, scale=sd_ratio)  # 正規乱数を生成する
    return int(round(x * (1.0 + z)))  # 乗算ノイズを適用して円単位に丸める


def generate_company_expense_df(seed: int, spec: VirtualCompanySpec) -> pd.DataFrame:  # 仮想会社データを生成する
    """
    仮想会社の年次データフレームを生成する。

    返却列（company_expense.csv と一致）
    - year
    - new_policies
    - inforce_avg
    - premium_income
    - acq_var_total, acq_fixed_total
    - maint_var_total, maint_fixed_total
    - coll_var_total
    - overhead_total
    """
    rng = np.random.default_rng(seed)  # 再現性のある乱数生成器を作る
    years = [spec.start_year + i for i in range(spec.years)]  # 年の配列を作る

    # 規模系列（決定論で生成）
    new_policies = [int(round(spec.new_policies_0 * (1.0 + spec.new_policies_growth) ** i)) for i in range(spec.years)]  # 新契約件数系列
    inforce_avg = [int(round(spec.inforce_avg_0 * (1.0 + spec.inforce_growth) ** i)) for i in range(spec.years)]  # 保有件数系列
    premium_income = [int(round(spec.premium_income_0 * (1.0 + spec.premium_income_growth) ** i)) for i in range(spec.years)]  # 収入系列

    # 変動費（総額）を構成し、微小ノイズを付与する
    acq_var_total = [  # 獲得変動費の系列
        _noisy(rng, spec.acq_var_per_policy * new_policies[i], spec.noise_sd_ratio) for i in range(spec.years)
    ]
    maint_var_total = [  # 維持変動費の系列
        _noisy(rng, spec.maint_var_per_inforce * inforce_avg[i], spec.noise_sd_ratio) for i in range(spec.years)
    ]
    coll_var_total = [  # 集金変動費の系列
        _noisy(rng, int(round(spec.coll_rate * premium_income[i])), spec.noise_sd_ratio) for i in range(spec.years)
    ]
    overhead_total = [  # 共通費の系列
        _noisy(rng, spec.overhead_total, spec.noise_sd_ratio) for _ in range(spec.years)
    ]

    # 固定費は初期実装として年次一定とする（後で成長率等を追加可能）
    df = pd.DataFrame(  # 生成した系列をデータフレームにまとめる
        {
            "year": years,  # 年
            "new_policies": new_policies,  # 新契約件数
            "inforce_avg": inforce_avg,  # 平均保有件数
            "premium_income": premium_income,  # 保険料収入
            "acq_var_total": acq_var_total,  # 獲得変動費
            "acq_fixed_total": [spec.acq_fixed_total] * spec.years,  # 獲得固定費
            "maint_var_total": maint_var_total,  # 維持変動費
            "maint_fixed_total": [spec.maint_fixed_total] * spec.years,  # 維持固定費
            "coll_var_total": coll_var_total,  # 集金変動費
            "overhead_total": overhead_total,  # 共通費
        }
    )  # データフレーム作成
    return df  # データフレームを返す


def write_company_expense_csv(path: str | Path, seed: int, spec: VirtualCompanySpec) -> Path:  # CSVとして保存する
    """
    CSVとして保存する。
    - data/ は .gitignore で追跡対象外にする運用を想定する（実データ混入を防止するため）。
    """
    out_path = Path(path)  # 文字列をPathに変換する
    out_path.parent.mkdir(parents=True, exist_ok=True)  # 出力先ディレクトリを作る
    df = generate_company_expense_df(seed=seed, spec=spec)  # データフレームを生成する
    df.to_csv(out_path, index=False, encoding="utf-8")  # CSVとして保存する
    return out_path  # 保存先を返す
