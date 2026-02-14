# 実現可能性レポート (trial-001.optimized_20260214_164606.yaml, 作成日 2026-02-14)

## サマリー
- 制約評価: `violation_count=0` / `7`モデルポイント。
- 収益性下限: `min_irr=0.020119`（現行設定での最悪点）。
- NBV下限: `min_nbv=6878.86` JPY。
- 十分性下限: `min_loading_surplus_ratio=-0.068788`。
- 健全性上限: `max_premium_to_maturity=1.055553`。

## 価格提案（モデルポイント別P）
|model_point|年払保険料P|月払保険料|irr|nbv|premium_to_maturity|
|---|---:|---:|---:|---:|---:|
|female_age30_term35|88271|7356|0.042353|97470.30|1.029828|
|female_age40_term25|123304|10275|0.046344|97168.58|1.027533|
|female_age50_term20|155193|12933|0.047382|86456.55|1.034620|
|female_age60_term10|314927|26244|0.020119|6878.86|1.049757|
|male_age30_term35|89114|7426|0.041539|92082.35|1.039663|
|male_age40_term25|124616|10385|0.044615|89084.18|1.038467|
|male_age50_term20|158333|13194|0.042239|68193.88|1.055553|

## 制約ステータス
|constraint|min_gap|worst_model_point|status|
|---|---:|---|---|
|alpha_non_negative|0.001000|male_age30_term35|適合|
|beta_non_negative|0.005000|male_age30_term35|適合|
|gamma_non_negative|0.000000|male_age30_term35|適合|
|IRR下限|0.020119|female_age60_term10|適合|
|loading_positive|15103.000000|male_age30_term35|適合|
|負荷余剰下限|93634.503405|male_age30_term35|適合|
|負荷余剰率下限|0.031212|male_age30_term35|適合|
|NBV下限|6878.861854|female_age60_term10|適合|
|PTM上限|-0.005553|male_age50_term20|要対応|

## ローディング式と係数
- `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`
- ローディングモード: `loading_parameters`。
|係数|値|
|---|---:|
|a0|0.006000|
|a_age|0.000000|
|a_term|-0.000200|
|a_sex|0.000500|
|b0|0.005000|
|b_age|0.000000|
|b_term|0.000000|
|b_sex|0.000000|
|g0|0.025000|
|g_term|-0.003000|

## モデルポイント別 alpha/beta/gamma 計算（中間計算付き）
### male_age30_term35 (age=30, term=35, sex=male)
- 差分: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=0.0`
- alpha: `0.001000 = 0.006000 + (0.000000*0.0) + (-0.000200*25.0) + (0.000500*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*25.0) = -0.050000, 0.0, 0.5)`
### male_age40_term25 (age=40, term=25, sex=male)
- 差分: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=0.0`
- alpha: `0.003000 = 0.006000 + (0.000000*10.0) + (-0.000200*15.0) + (0.000500*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*15.0) = -0.020000, 0.0, 0.5)`
### male_age50_term20 (age=50, term=20, sex=male)
- 差分: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=0.0`
- alpha: `0.004000 = 0.006000 + (0.000000*20.0) + (-0.000200*10.0) + (0.000500*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*10.0) = -0.005000, 0.0, 0.5)`
### female_age30_term35 (age=30, term=35, sex=female)
- 差分: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=1.0`
- alpha: `0.001500 = 0.006000 + (0.000000*0.0) + (-0.000200*25.0) + (0.000500*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*25.0) = -0.050000, 0.0, 0.5)`
### female_age40_term25 (age=40, term=25, sex=female)
- 差分: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=1.0`
- alpha: `0.003500 = 0.006000 + (0.000000*10.0) + (-0.000200*15.0) + (0.000500*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*15.0) = -0.020000, 0.0, 0.5)`
### female_age50_term20 (age=50, term=20, sex=female)
- 差分: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=1.0`
- alpha: `0.004500 = 0.006000 + (0.000000*20.0) + (-0.000200*10.0) + (0.000500*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*10.0) = -0.005000, 0.0, 0.5)`
### female_age60_term10 (age=60, term=10, sex=female)
- 差分: `age_delta=30.0`, `term_delta=0.0`, `sex_indicator=1.0`
- alpha: `0.006500 = 0.006000 + (0.000000*30.0) + (-0.000200*0.0) + (0.000500*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*30.0) + (0.000000*0.0) + (0.000000*1.0)`
- gamma: `0.025000 = clamp(0.025000 + (-0.003000*0.0) = 0.025000, 0.0, 0.5)`

## 年度別キャッシュフロー（利源別）
![年度別キャッシュフロー（利源別）](../out/charts/executive/20260214_164606/cashflow_by_profit_source.png)

![モデルポイント別 年払保険料](../out/charts/executive/20260214_164606/annual_premium_by_model_point.png)

## 感応度サマリー
|scenario|min_irr|min_nbv|min_loading_surplus_ratio|max_premium_to_maturity|violation_count|
|---|---:|---:|---:|---:|---:|
|ベース|0.020119|6878.86|-0.068788|1.055553|0|
|金利-10%|0.030458|19253.05|-0.068814|1.064907|2|
|金利+10%|0.009767|-5422.35|-0.068752|1.046280|1|
|解約率-10%|0.019835|6582.46|-0.068987|1.055553|0|
|解約率+10%|0.020387|7149.91|-0.068601|1.055553|0|
|事業費-10%|0.050250|39757.63|-0.053741|1.055553|0|
|事業費+10%|-0.006226|-25999.91|-0.083836|1.055553|2|

## Feasibility Deck メタ情報
- 掃引範囲: `r_start=1.0`, `r_end=1.08`, `r_step=0.005`, `irr_threshold=0.02`

## 再現手順
```powershell
python -m pytest -q
python -m pricing.cli run C:/Users/shunsuke/pricing-automation/out/trial-001.optimized_20260214_164606.yaml
python -m pricing.cli report-feasibility C:/Users/shunsuke/pricing-automation/out/trial-001.optimized_20260214_164606.yaml --r-start 1.00 --r-end 1.08 --r-step 0.005 --irr-threshold 0.02 --out out/feasibility_deck_executive.yaml
python -m pricing.cli report-executive-pptx C:/Users/shunsuke/pricing-automation/out/trial-001.optimized_20260214_164606.yaml --out reports/executive_pricing_deck.pptx --md-out reports/feasibility_report.md --lang ja
```