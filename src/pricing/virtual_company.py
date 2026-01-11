from __future__ import annotations

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

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VirtualCompanySpec:
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

    start_year: int = 2025
    years: int = 5

    # 規模（初年度）
    new_policies_0: int = 12_000
    inforce_avg_0: int = 90_000
    premium_income_0: int = 72_000_000_000  # 円

    # 年成長率（決定論）
    new_policies_growth: float = 0.03
    inforce_growth: float = 0.02
    premium_income_growth: float = 0.03

    # 単価・率（初年度）
    acq_var_per_policy: int = 150_000      # 円 / 新契約
    acq_fixed_total: int = 600_000_000     # 円 / 年
    maint_var_per_inforce: int = 10_000    # 円 / 保有（平均）
    maint_fixed_total: int = 500_000_000   # 円 / 年
    coll_rate: float = 0.003               # 集金費 / 保険料収入
    overhead_total: int = 400_000_000      # 円 / 年

    # ノイズ（費用総額へ乗算）
    noise_sd_ratio: float = 0.02


def _noisy(rng: np.random.Generator, x: int, sd_ratio: float) -> int:
    """
    乗算ノイズ（1 + 正規ノイズ）を適用し、整数円へ丸める。
    - sd_ratio は標準偏差（比率）であり、0.02 は 2% 程度の揺らぎを意味する。
    """
    z = rng.normal(loc=0.0, scale=sd_ratio)
    return int(round(x * (1.0 + z)))


def generate_company_expense_df(seed: int, spec: VirtualCompanySpec) -> pd.DataFrame:
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
    rng = np.random.default_rng(seed)
    years = [spec.start_year + i for i in range(spec.years)]

    # 規模系列（決定論で生成）
    new_policies = [int(round(spec.new_policies_0 * (1.0 + spec.new_policies_growth) ** i)) for i in range(spec.years)]
    inforce_avg = [int(round(spec.inforce_avg_0 * (1.0 + spec.inforce_growth) ** i)) for i in range(spec.years)]
    premium_income = [int(round(spec.premium_income_0 * (1.0 + spec.premium_income_growth) ** i)) for i in range(spec.years)]

    # 変動費（総額）を構成し、微小ノイズを付与する
    acq_var_total = [
        _noisy(rng, spec.acq_var_per_policy * new_policies[i], spec.noise_sd_ratio) for i in range(spec.years)
    ]
    maint_var_total = [
        _noisy(rng, spec.maint_var_per_inforce * inforce_avg[i], spec.noise_sd_ratio) for i in range(spec.years)
    ]
    coll_var_total = [
        _noisy(rng, int(round(spec.coll_rate * premium_income[i])), spec.noise_sd_ratio) for i in range(spec.years)
    ]
    overhead_total = [
        _noisy(rng, spec.overhead_total, spec.noise_sd_ratio) for _ in range(spec.years)
    ]

    # 固定費は初期実装として年次一定とする（後で成長率等を追加可能）
    df = pd.DataFrame(
        {
            "year": years,
            "new_policies": new_policies,
            "inforce_avg": inforce_avg,
            "premium_income": premium_income,
            "acq_var_total": acq_var_total,
            "acq_fixed_total": [spec.acq_fixed_total] * spec.years,
            "maint_var_total": maint_var_total,
            "maint_fixed_total": [spec.maint_fixed_total] * spec.years,
            "coll_var_total": coll_var_total,
            "overhead_total": overhead_total,
        }
    )
    return df


def write_company_expense_csv(path: str | Path, seed: int, spec: VirtualCompanySpec) -> Path:
    """
    CSVとして保存する。
    - data/ は .gitignore で追跡対象外にする運用を想定する（実データ混入を防止するため）。
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = generate_company_expense_df(seed=seed, spec=spec)
    df.to_csv(out_path, index=False, encoding="utf-8")
    return out_path