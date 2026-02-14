# Feasibility Report (trial-001.executive.optimized.yaml, generated 2026-02-14)

## Summary
- Constraint status: `violation_count=0` across `7` model points.
- Profitability floor: `min_irr=0.034190` (worst model point at current setting).
- NBV floor: `min_nbv=23581.10` JPY.
- Adequacy floor: `min_loading_surplus_ratio=-0.068228`.
- Soundness ceiling: `max_premium_to_maturity=1.055767`.

## Pricing Recommendation (P by Model Point)
|model_point|gross_annual_premium|monthly_premium|irr|nbv|premium_to_maturity|
|---|---:|---:|---:|---:|---:|
|female_age30_term35|88939|7412|0.044901|110887.23|1.037622|
|female_age40_term25|124197|10350|0.050261|112543.92|1.034975|
|female_age50_term20|156122|13010|0.051798|100492.55|1.040813|
|female_age60_term10|316730|26394|0.034190|23581.10|1.055767|
|male_age30_term35|89218|7435|0.041933|94156.93|1.040877|
|male_age40_term25|124755|10396|0.045221|91456.41|1.039625|
|male_age50_term20|158333|13194|0.042239|68193.88|1.055553|

## Constraint Status
|constraint|min_gap|worst_model_point|status|
|---|---:|---|---|
|alpha_non_negative|0.002000|male_age30_term35|PASS|
|beta_non_negative|0.005000|male_age30_term35|PASS|
|gamma_non_negative|0.000000|male_age30_term35|PASS|
|irr_hard|0.014190|female_age60_term10|PASS|
|loading_positive|15207.000000|male_age30_term35|PASS|
|loading_surplus_hard|95317.138172|male_age30_term35|PASS|
|loading_surplus_ratio_hard|0.031772|male_age30_term35|PASS|
|nbv_hard|23581.100627|female_age60_term10|PASS|
|premium_to_maturity_hard_max|0.000233|female_age60_term10|PASS|

## Loading Formula and Coefficients
- `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`
- Loading mode: `loading_parameters`.
|coefficient|value|
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

## Per-model-point alpha/beta/gamma Calculations (with intermediate steps)
### male_age30_term35 (age=30, term=35, sex=male)
- deltas: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=0.0`
- alpha: `0.002000 = 0.012000 + (-0.000200*0.0) + (-0.000400*25.0) + (0.006000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*25.0) = -0.050000, 0.0, 0.5)`
### male_age40_term25 (age=40, term=25, sex=male)
- deltas: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=0.0`
- alpha: `0.004000 = 0.012000 + (-0.000200*10.0) + (-0.000400*15.0) + (0.006000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*15.0) = -0.020000, 0.0, 0.5)`
### male_age50_term20 (age=50, term=20, sex=male)
- deltas: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=0.0`
- alpha: `0.004000 = 0.012000 + (-0.000200*20.0) + (-0.000400*10.0) + (0.006000*0.0)`
- beta: `0.005000 = 0.005000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*0.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*10.0) = -0.005000, 0.0, 0.5)`
### female_age30_term35 (age=30, term=35, sex=female)
- deltas: `age_delta=0.0`, `term_delta=25.0`, `sex_indicator=1.0`
- alpha: `0.008000 = 0.012000 + (-0.000200*0.0) + (-0.000400*25.0) + (0.006000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*0.0) + (0.000000*25.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*25.0) = -0.050000, 0.0, 0.5)`
### female_age40_term25 (age=40, term=25, sex=female)
- deltas: `age_delta=10.0`, `term_delta=15.0`, `sex_indicator=1.0`
- alpha: `0.010000 = 0.012000 + (-0.000200*10.0) + (-0.000400*15.0) + (0.006000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*10.0) + (0.000000*15.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*15.0) = -0.020000, 0.0, 0.5)`
### female_age50_term20 (age=50, term=20, sex=female)
- deltas: `age_delta=20.0`, `term_delta=10.0`, `sex_indicator=1.0`
- alpha: `0.010000 = 0.012000 + (-0.000200*20.0) + (-0.000400*10.0) + (0.006000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*20.0) + (0.000000*10.0) + (0.000000*1.0)`
- gamma: `0.000000 = clamp(0.025000 + (-0.003000*10.0) = -0.005000, 0.0, 0.5)`
### female_age60_term10 (age=60, term=10, sex=female)
- deltas: `age_delta=30.0`, `term_delta=0.0`, `sex_indicator=1.0`
- alpha: `0.012000 = 0.012000 + (-0.000200*30.0) + (-0.000400*0.0) + (0.006000*1.0)`
- beta: `0.005000 = 0.005000 + (0.000000*30.0) + (0.000000*0.0) + (0.000000*1.0)`
- gamma: `0.025000 = clamp(0.025000 + (-0.003000*0.0) = 0.025000, 0.0, 0.5)`

## Yearly Cashflow by Profit Source
![Yearly Cashflow by Profit Source](../out/charts/executive/cashflow_by_profit_source.png)

![Annual Premium by Model Point](../out/charts/executive/annual_premium_by_model_point.png)

## Sensitivity Summary
|scenario|min_irr|min_nbv|min_loading_surplus_ratio|max_premium_to_maturity|violation_count|
|---|---:|---:|---:|---:|---:|
|base|0.034190|23581.10|-0.068228|1.055767|0|
|interest_down_10pct|0.044463|35889.74|-0.068264|1.064907|3|
|interest_up_10pct|0.023918|11345.43|-0.068186|1.050547|0|
|lapse_down_10pct|0.033763|23296.41|-0.068405|1.055767|0|
|lapse_up_10pct|0.034603|23840.07|-0.068059|1.055767|0|
|expense_down_10pct|0.051935|56464.06|-0.053180|1.055767|0|
|expense_up_10pct|0.006936|-9301.85|-0.083275|1.055767|2|

## Feasibility Deck Meta
- sweep range: `r_start=1.0`, `r_end=1.08`, `r_step=0.005`, `irr_threshold=0.02`

## Reproducibility
```powershell
python -m pytest -q
python -m pricing.cli run C:/Users/shunsuke/pricing-automation/configs/trial-001.executive.optimized.yaml
python -m pricing.cli report-feasibility C:/Users/shunsuke/pricing-automation/configs/trial-001.executive.optimized.yaml --r-start 1.00 --r-end 1.08 --r-step 0.005 --irr-threshold 0.02 --out out/feasibility_deck_executive.yaml
python -m pricing.cli report-executive-pptx C:/Users/shunsuke/pricing-automation/configs/trial-001.executive.optimized.yaml --out reports/executive_pricing_deck.pptx --md-out reports/feasibility_report.md
```