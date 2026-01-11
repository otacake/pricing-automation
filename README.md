## company_expense.csv（仮想会社データ）
列定義（単位は円、率は年率）

- year: 年度
- new_policies: 当年度新契約件数（件）
- inforce_avg: 期中平均保有契約件数（件）
- premium_income: 当年度保険料収入総額（円）
- acq_var_total / acq_fixed_total: 新契約費（変動/固定）の総額（円）
- maint_var_total / maint_fixed_total: 維持費（変動/固定）の総額（円）
- coll_var_total: 集金費（保険料比例）の総額（円）
- overhead_total: 共通費（間接費）の総額（円）

収益性検証での単価化（例）
- 新契約費単価 = (acq_var_total + acq_fixed_total + overhead_total×配賦比率) / new_policies
- 維持費単価 = (maint_var_total + maint_fixed_total + overhead_total×配賦比率) / inforce_avg
- 集金費率 = coll_var_total / premium_income
