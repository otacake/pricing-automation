# 実現可能性レポート (trial-001.autonomous-best_20260214_162546.yaml, 作成日 2026-02-14)

## サマリー
- 制約評価: `violation_count=0` / `7`モデルポイント。
- 収益性下限: `min_irr=0.037736`（現行設定での最悪点）。
- NBV下限: `min_nbv=27811.94` JPY。
- 十分性下限: `min_loading_surplus_ratio=-0.067667`。
- 健全性上限: `max_premium_to_maturity=1.057917`。

## 価格提案（モデルポイント別P）
|model_point|年払保険料P|月払保険料|irr|nbv|premium_to_maturity|
|---|---:|---:|---:|---:|---:|
|female_age30_term35|88528|7377|0.043328|102631.94|1.032827|
|female_age40_term25|123647|10304|0.047843|103075.41|1.030392|
|female_age50_term20|155615|12968|0.049382|92833.00|1.037433|
|female_age60_term10|317375|26448|0.037736|27811.94|1.057917|
|male_age30_term35|89322|7444|0.042329|96231.51|1.042090|
|male_age40_term25|124893|10408|0.045826|93814.12|1.040775|
|male_age50_term20|158677|13223|0.043864|73297.85|1.057847|

## 制約ステータス
|constraint|min_gap|worst_model_point|status|
|---|---:|---|---|
|alpha_non_negative|0.003000|male_age30_term35|適合|
|beta_non_negative|0.005000|male_age30_term35|適合|
|gamma_non_negative|0.000000|male_age30_term35|適合|
|IRR下限|0.017736|female_age60_term10|適合|
|loading_positive|15311.000000|male_age30_term35|適合|
|負荷余剰下限|96999.772939|male_age30_term35|適合|
|負荷余剰率下限|0.032333|male_age30_term35|適合|
|NBV下限|27811.939578|female_age60_term10|適合|
|PTM上限|0.000083|female_age60_term10|適合|

## ローディング式と係数
- `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`
- ローディングモード: `loading_parameters`。
|係数|値|
|---|---:|
|a0|0.008000|
|a_age|0.000000|
|a_term|-0.000200|
|a_sex|0.001000|
|b0|0.005000|
|b_age|0.000000|
|b_term|0.000000|
|b_sex|0.000000|
|g0|0.030000|
|g_term|-0.003000|

## モデルポイント別 alpha/beta/gamma 計算（中間計算付き）
### male_age30_term35 (age=30, term=35, sex=male)
- 差分: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=0.0`
- alpha: `0.003000 = 0.008000 + (0.000000*0.0) + (-0.000200*25.0) + (0.001000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.030000 + (-0.003000*25.0) = -0.045000, 0.0, 0.5)`
### male_age40_term25 (age=40, term=25, sex=male)
- 差分: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=0.0`
- alpha: `0.005000 = 0.008000 + (0.000000*10.0) + (-0.000200*15.0) + (0.001000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.030000 + (-0.003000*15.0) = -0.015000, 0.0, 0.5)`
### male_age50_term20 (age=50, term=20, sex=male)
- 差分: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=0.0`
- alpha: `0.006000 = 0.008000 + (0.000000*20.0) + (-0.000200*10.0) + (0.001000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.030000 + (-0.003000*10.0) = 0.000000, 0.0, 0.5)`
### female_age30_term35 (age=30, term=35, sex=female)
- 差分: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=1.0`
- alpha: `0.004000 = 0.008000 + (0.000000*0.0) + (-0.000200*25.0) + (0.001000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.030000 + (-0.003000*25.0) = -0.045000, 0.0, 0.5)`
### female_age40_term25 (age=40, term=25, sex=female)
- 差分: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=1.0`
- alpha: `0.006000 = 0.008000 + (0.000000*10.0) + (-0.000200*15.0) + (0.001000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.030000 + (-0.003000*15.0) = -0.015000, 0.0, 0.5)`
### female_age50_term20 (age=50, term=20, sex=female)
- 差分: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=1.0`
- alpha: `0.007000 = 0.008000 + (0.000000*20.0) + (-0.000200*10.0) + (0.001000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.030000 + (-0.003000*10.0) = 0.000000, 0.0, 0.5)`
### female_age60_term10 (age=60, term=10, sex=female)
- 差分: `age_delta=30.0`, `term_delta=0.0`, `sex_indicator=1.0`
- alpha: `0.009000 = 0.008000 + (0.000000*30.0) + (-0.000200*0.0) + (0.001000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*30.0) + (0.000000*0.0) + (0.000000*1.0)`
- gamma: `0.030000 = clamp(0.030000 + (-0.003000*0.0) = 0.030000, 0.0, 0.5)`

## 年度別キャッシュフロー（利源別）
![年度別キャッシュフロー（利源別）](../out/charts/executive/20260214_162654/cashflow_by_profit_source.png)

![モデルポイント別 年払保険料](../out/charts/executive/20260214_162654/annual_premium_by_model_point.png)

## 感応度サマリー
|scenario|min_irr|min_nbv|min_loading_surplus_ratio|max_premium_to_maturity|violation_count|
|---|---:|---:|---:|---:|---:|
|ベース|0.037736|27811.94|-0.067667|1.057917|0|
|金利-10%|0.045643|40218.89|-0.067714|1.067187|2|
|金利+10%|0.027392|15469.76|-0.067620|1.052653|0|
|解約率-10%|0.037409|27691.57|-0.067824|1.057917|0|
|解約率+10%|0.038049|27909.46|-0.067517|1.057917|0|
|事業費-10%|0.052371|60696.39|-0.052619|1.057917|0|
|事業費+10%|0.010282|-5072.51|-0.082714|1.057917|2|

## Feasibility Deck メタ情報
- 掃引範囲: `r_start=1.0`, `r_end=1.08`, `r_step=0.005`, `irr_threshold=0.02`

## 再現手順
```powershell
python -m pytest -q
python -m pricing.cli run C:/Users/shunsuke/pricing-automation/out/trial-001.autonomous-best_20260214_162546.yaml
python -m pricing.cli report-feasibility C:/Users/shunsuke/pricing-automation/out/trial-001.autonomous-best_20260214_162546.yaml --r-start 1.00 --r-end 1.08 --r-step 0.005 --irr-threshold 0.02 --out out/feasibility_deck_executive.yaml
python -m pricing.cli report-executive-pptx C:/Users/shunsuke/pricing-automation/out/trial-001.autonomous-best_20260214_162546.yaml --out reports/executive_pricing_deck.pptx --md-out reports/feasibility_report.md --lang ja
```