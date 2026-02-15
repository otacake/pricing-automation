# 実現可能性レポート (trial-001.optimized_20260215_054016.yaml, 作成日 2026-02-15)

## サマリー
- 制約評価: `violation_count=0` / `7`モデルポイント。
- 収益性下限: `min_irr=0.068760`（現行設定での最悪点）。
- NBV下限: `min_nbv=78837.20` JPY。
- 十分性下限: `min_loading_surplus_ratio=-0.067473`。
- 健全性上限: `max_premium_to_maturity=1.069947`。

## 価格提案（モデルポイント別P）
|model_point|年払保険料P|月払保険料|irr|nbv|premium_to_maturity|
|---|---:|---:|---:|---:|---:|
|female_age30_term35|88332|7361|0.068884|178699.28|1.030540|
|female_age40_term25|124308|10359|0.088743|254818.38|1.035900|
|female_age50_term20|157074|13090|0.097234|238794.44|1.047160|
|female_age60_term10|313129|26094|0.081448|78837.20|1.043763|
|male_age30_term35|89312|7443|0.068760|176336.88|1.041973|
|male_age40_term25|125806|10484|0.087887|247423.03|1.048383|
|male_age50_term20|160492|13374|0.093541|220327.93|1.069947|

## 制約ステータス
|constraint|min_gap|worst_model_point|status|
|---|---:|---|---|
|alpha_non_negative|0.005500|female_age30_term35|適合|
|beta_non_negative|0.004000|male_age30_term35|適合|
|gamma_non_negative|0.030000|male_age30_term35|適合|
|IRR下限|0.068760|male_age30_term35|適合|
|loading_positive|15215.000000|female_age30_term35|適合|
|負荷余剰下限|97579.972666|female_age30_term35|適合|
|負荷余剰率下限|0.032527|female_age30_term35|適合|
|NBV下限|78837.197195|female_age60_term10|適合|
|PTM上限|-0.019947|male_age50_term20|要対応|

## ローディング式と係数
- `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`
- ローディングモード: `loading_parameters`。
|係数|値|
|---|---:|
|a0|0.006000|
|a_age|0.000000|
|a_term|0.000000|
|a_sex|-0.000500|
|b0|0.004000|
|b_age|0.000000|
|b_term|0.000000|
|b_sex|0.000000|
|g0|0.030000|
|g_term|0.000000|

## モデルポイント別 alpha/beta/gamma 計算（中間計算付き）
### male_age30_term35 (age=30, term=35, sex=male)
- 差分: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=0.0`
- alpha: `0.006000 = 0.006000 + (0.000000*0.0) + (0.000000*25.0) + (-0.000500*0.0)`
- beta: `0.004000 = 0.004000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*0.0)`
- gamma: `0.030000 = clamp(0.030000 + (0.000000*25.0) = 0.030000, 0.0, 0.5)`
### male_age40_term25 (age=40, term=25, sex=male)
- 差分: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=0.0`
- alpha: `0.006000 = 0.006000 + (0.000000*10.0) + (0.000000*15.0) + (-0.000500*0.0)`
- beta: `0.004000 = 0.004000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*0.0)`
- gamma: `0.030000 = clamp(0.030000 + (0.000000*15.0) = 0.030000, 0.0, 0.5)`
### male_age50_term20 (age=50, term=20, sex=male)
- 差分: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=0.0`
- alpha: `0.006000 = 0.006000 + (0.000000*20.0) + (0.000000*10.0) + (-0.000500*0.0)`
- beta: `0.004000 = 0.004000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*0.0)`
- gamma: `0.030000 = clamp(0.030000 + (0.000000*10.0) = 0.030000, 0.0, 0.5)`
### female_age30_term35 (age=30, term=35, sex=female)
- 差分: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=1.0`
- alpha: `0.005500 = 0.006000 + (0.000000*0.0) + (0.000000*25.0) + (-0.000500*1.0)`
- beta: `0.004000 = 0.004000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*1.0)`
- gamma: `0.030000 = clamp(0.030000 + (0.000000*25.0) = 0.030000, 0.0, 0.5)`
### female_age40_term25 (age=40, term=25, sex=female)
- 差分: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=1.0`
- alpha: `0.005500 = 0.006000 + (0.000000*10.0) + (0.000000*15.0) + (-0.000500*1.0)`
- beta: `0.004000 = 0.004000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*1.0)`
- gamma: `0.030000 = clamp(0.030000 + (0.000000*15.0) = 0.030000, 0.0, 0.5)`
### female_age50_term20 (age=50, term=20, sex=female)
- 差分: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=1.0`
- alpha: `0.005500 = 0.006000 + (0.000000*20.0) + (0.000000*10.0) + (-0.000500*1.0)`
- beta: `0.004000 = 0.004000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*1.0)`
- gamma: `0.030000 = clamp(0.030000 + (0.000000*10.0) = 0.030000, 0.0, 0.5)`
### female_age60_term10 (age=60, term=10, sex=female)
- 差分: `age_delta=30.0`, `term_delta=0.0`, `sex_indicator=1.0`
- alpha: `0.005500 = 0.006000 + (0.000000*30.0) + (0.000000*0.0) + (-0.000500*1.0)`
- beta: `0.004000 = 0.004000 + (0.000000*30.0) + (0.000000*0.0) + (0.000000*1.0)`
- gamma: `0.030000 = clamp(0.030000 + (0.000000*0.0) = 0.030000, 0.0, 0.5)`

## 年度別キャッシュフロー（利源別）
![年度別キャッシュフロー（利源別）](../out/charts/executive/20260215_054016/cashflow_by_profit_source.png)

![モデルポイント別 年払保険料](../out/charts/executive/20260215_054016/annual_premium_by_model_point.png)

## 感応度サマリー
|scenario|min_irr|min_nbv|min_loading_surplus_ratio|max_premium_to_maturity|violation_count|
|---|---:|---:|---:|---:|---:|
|ベース|0.068760|78837.20|-0.067473|1.069947|0|
|金利-10%|0.072045|90980.95|-0.067336|1.079573|3|
|金利+10%|0.065556|66756.61|-0.067606|1.060407|0|
|解約率-10%|0.071295|80240.64|-0.067620|1.069947|0|
|解約率+10%|0.066224|77443.64|-0.067334|1.069947|0|
|事業費-10%|0.079657|111373.02|-0.053308|1.069947|0|
|事業費+10%|0.054733|46301.37|-0.081638|1.069947|0|

## Feasibility Deck メタ情報
- 掃引範囲: `r_start=1.0`, `r_end=1.08`, `r_step=0.005`, `irr_threshold=0.02`

## 再現手順
```powershell
python -m pytest -q
python -m pricing.cli run C:/Users/shunsuke/pricing-automation/out/trial-001.optimized_20260215_054016.yaml
python -m pricing.cli report-feasibility C:/Users/shunsuke/pricing-automation/out/trial-001.optimized_20260215_054016.yaml --r-start 1.00 --r-end 1.08 --r-step 0.005 --irr-threshold 0.02 --out out/feasibility_deck_executive.yaml
python -m pricing.cli report-executive-pptx C:/Users/shunsuke/pricing-automation/out/trial-001.optimized_20260215_054016.yaml --out reports/executive_pricing_deck.pptx --md-out reports/feasibility_report.md --lang ja
```