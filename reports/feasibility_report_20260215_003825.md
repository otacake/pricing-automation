# 実現可能性レポート (trial-001.executive.optimized.yaml, 作成日 2026-02-14)

## サマリー
- 制約評価: `violation_count=0` / `7`モデルポイント。
- 収益性下限: `min_irr=0.034190`（現行設定での最悪点）。
- NBV下限: `min_nbv=23581.10` JPY。
- 十分性下限: `min_loading_surplus_ratio=-0.068228`。
- 健全性上限: `max_premium_to_maturity=1.055767`。

## 価格提案（モデルポイント別P）
|model_point|年払保険料P|月払保険料|irr|nbv|premium_to_maturity|
|---|---:|---:|---:|---:|---:|
|female_age30_term35|88939|7412|0.044901|110887.23|1.037622|
|female_age40_term25|124197|10350|0.050261|112543.92|1.034975|
|female_age50_term20|156122|13010|0.051798|100492.55|1.040813|
|female_age60_term10|316730|26394|0.034190|23581.10|1.055767|
|male_age30_term35|89218|7435|0.041933|94156.93|1.040877|
|male_age40_term25|124755|10396|0.045221|91456.41|1.039625|
|male_age50_term20|158333|13194|0.042239|68193.88|1.055553|

## 制約ステータス
|constraint|min_gap|worst_model_point|status|
|---|---:|---|---|
|alpha_non_negative|0.002000|male_age30_term35|適合|
|beta_non_negative|0.005000|male_age30_term35|適合|
|gamma_non_negative|0.000000|male_age30_term35|適合|
|IRR下限|0.014190|female_age60_term10|適合|
|loading_positive|15207.000000|male_age30_term35|適合|
|負荷余剰下限|95317.138172|male_age30_term35|適合|
|負荷余剰率下限|0.031772|male_age30_term35|適合|
|NBV下限|23581.100627|female_age60_term10|適合|
|PTM上限|0.000233|female_age60_term10|適合|

## ローディング式と係数
- `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`
- ローディングモード: `loading_parameters`。
|係数|値|
|---|---:|
|a0|0.012000|
|a_age|-0.000200|
|a_term|-0.000400|
|a_sex|0.006000|
|b0|0.005000|
|b_age|0.000000|
|b_term|0.000000|
|b_sex|0.000000|
|g0|0.025000|
|g_term|-0.003000|

## モデルポイント別 alpha/beta/gamma 計算（中間計算付き）
### male_age30_term35 (age=30, term=35, sex=male)
- 差分: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=0.0`
- alpha: `0.002000 = 0.012000 + (-0.000200*0.0) + (-0.000400*25.0) + (0.006000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*25.0) = -0.050000, 0.0, 0.5)`
### male_age40_term25 (age=40, term=25, sex=male)
- 差分: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=0.0`
- alpha: `0.004000 = 0.012000 + (-0.000200*10.0) + (-0.000400*15.0) + (0.006000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*15.0) = -0.020000, 0.0, 0.5)`
### male_age50_term20 (age=50, term=20, sex=male)
- 差分: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=0.0`
- alpha: `0.004000 = 0.012000 + (-0.000200*20.0) + (-0.000400*10.0) + (0.006000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*10.0) = -0.005000, 0.0, 0.5)`
### female_age30_term35 (age=30, term=35, sex=female)
- 差分: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=1.0`
- alpha: `0.008000 = 0.012000 + (-0.000200*0.0) + (-0.000400*25.0) + (0.006000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*25.0) = -0.050000, 0.0, 0.5)`
### female_age40_term25 (age=40, term=25, sex=female)
- 差分: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=1.0`
- alpha: `0.010000 = 0.012000 + (-0.000200*10.0) + (-0.000400*15.0) + (0.006000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*15.0) = -0.020000, 0.0, 0.5)`
### female_age50_term20 (age=50, term=20, sex=female)
- 差分: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=1.0`
- alpha: `0.010000 = 0.012000 + (-0.000200*20.0) + (-0.000400*10.0) + (0.006000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*10.0) = -0.005000, 0.0, 0.5)`
### female_age60_term10 (age=60, term=10, sex=female)
- 差分: `age_delta=30.0`, `term_delta=0.0`, `sex_indicator=1.0`
- alpha: `0.012000 = 0.012000 + (-0.000200*30.0) + (-0.000400*0.0) + (0.006000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*30.0) + (0.000000*0.0) + (0.000000*1.0)`
- gamma: `0.025000 = clamp(0.025000 + (-0.003000*0.0) = 0.025000, 0.0, 0.5)`

## 年度別キャッシュフロー（利源別）
![年度別キャッシュフロー（利源別）](../out/charts/executive/20260215_003825/cashflow_by_profit_source.png)

![モデルポイント別 年払保険料](../out/charts/executive/20260215_003825/annual_premium_by_model_point.png)

## 感応度サマリー
|scenario|min_irr|min_nbv|min_loading_surplus_ratio|max_premium_to_maturity|violation_count|
|---|---:|---:|---:|---:|---:|
|ベース|0.034190|23581.10|-0.068228|1.055767|0|
|金利-10%|0.044463|35889.74|-0.068264|1.064907|3|
|金利+10%|0.023918|11345.43|-0.068186|1.050547|0|
|解約率-10%|0.033763|23296.41|-0.068405|1.055767|0|
|解約率+10%|0.034603|23840.07|-0.068059|1.055767|0|
|事業費-10%|0.051935|56464.06|-0.053180|1.055767|0|
|事業費+10%|0.006936|-9301.85|-0.083275|1.055767|2|

## Feasibility Deck メタ情報
- 掃引範囲: `r_start=1.0`, `r_end=1.08`, `r_step=0.005`, `irr_threshold=0.02`

## 再現手順
```powershell
python -m pytest -q
python -m pricing.cli run C:/Users/shunsuke/pricing-automation/configs/trial-001.executive.optimized.yaml
python -m pricing.cli report-feasibility C:/Users/shunsuke/pricing-automation/configs/trial-001.executive.optimized.yaml --r-start 1.00 --r-end 1.08 --r-step 0.005 --irr-threshold 0.02 --out out/feasibility_deck_executive.yaml
python -m pricing.cli report-executive-pptx C:/Users/shunsuke/pricing-automation/configs/trial-001.executive.optimized.yaml --out reports/executive_pricing_deck.pptx --md-out reports/feasibility_report.md --lang ja
```