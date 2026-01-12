# Feasibility Report (trial-001, irr_threshold=0.06, r_end=1.05)

## 結論
- 支配制約: 該当なし（r_end=1.05時点で違反0件）
- not found: 0件（7/7でmin_r検出）
- 次の意思決定点: r=1.05に張り付く2点（male_age50_term20, female_age60_term10）を監視対象として扱い、付加保険料はmin_rに合わせて設定する

## 前提と走査条件
|項目|値|
|---|---|
|r_start|1.0|
|r_end|1.05|
|r_step|0.01|
|irr_threshold|0.06|
|対象モデルポイント数|7|
|pricing_interest_rate|0.01|
|valuation_interest_rate|0.0025|
|lapse_rate|0.03|
|loading_alpha|0.03|
|loading_beta|0.007|
|loading_gamma|0.03|

## KPIサマリー
単位: IRR/ratioはrate、NBVはJPY

|指標|値|
|---|---|
|max premium_to_maturity|1.05|
|min IRR|-0.0986235910327119|
|min NBV|-70191.17194549802|
|min loading_surplus_ratio|-0.09098095313360245|
|not found件数|0|

## モデルポイント別の境界
|model_point_id|min_r|min_r_irr|min_r_nbv|min_r_loading_surplus_ratio|r_end_irr|r_end_nbv|r_end_loading_surplus_ratio|
|---|---|---|---|---|---|---|---|
|male_age30_term35|1.04|0.062067131092413144|123398.473244902|-0.0611047340086482|0.0666267211728547|137184.78378780046|-0.05660882818847654|
|male_age40_term25|1.03|0.066891228221474|106342.33343646188|-0.06391016726995723|0.0823362401085792|140239.89971496942|-0.05284158263544448|
|male_age50_term20|1.05|0.07014036152349759|92032.19772703681|-0.06047763741654569|0.07014036152349759|92032.19772703681|-0.06047763741654569|
|female_age30_term35|1.03|0.06293748323816922|128064.70780742128|-0.06102391154743509|0.07216040822364903|155793.68866249718|-0.05198144849506401|
|female_age40_term25|1.01|0.06256397324765525|98176.59830353923|-0.06886143593856732|0.09358926104352822|166519.9125391919|-0.04654655669030882|
|female_age50_term20|1.02|0.06832858565170027|91744.56864855313|-0.06619013159755978|0.10100913397236796|148724.52575525464|-0.04756932306176366|
|female_age60_term10|1.05|0.10458215011014094|49347.9433452091|-0.029557515837741997|0.10458215011014094|49347.9433452091|-0.029557515837741997|

## 支配制約の分析
r_end=1.05時点では全制約が違反0件で、支配制約は発生していない。

|制約|違反件数|最大超過/不足|
|---|---|---|
|irr_hard (>=0.0)|0|0.0|
|nbv_hard (>=0.0)|0|0.0|
|loading_surplus_hard_ratio (>=-0.10)|0|0.0|
|premium_to_maturity_hard_max (<=1.05)|0|0.0|

## 示唆
not foundは0件で、irr_threshold=0.06はr_end=1.05内で達成可能である。今後not foundが出る場合は、r範囲拡張、irr_threshold緩和、前提（費用・利率）の見直し、または免除/監視の適用が選択肢になる。
min_rがr_endに張り付く点は2件（male_age50_term20, female_age60_term10）あるため、解の脆弱性を前提に感度検証を行う必要がある。

## 付加保険料計算式とキャッシュフロー分解
### 付加保険料計算式（最終適用）
- 純保険料率: `net_rate = A / a`
- 総保険料率: `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`
- 年払総保険料: `gross_annual_premium = round(gross_rate * sum_assured, 0)`
- `alpha/beta/gamma` の生成（モデルポイントごと）
  - `alpha = a0 + a_age*(issue_age-30) + a_term*(term_years-10) + a_sex*(sex_indicator)`
  - `beta  = b0 + b_age*(issue_age-30) + b_term*(term_years-10) + b_sex*(sex_indicator)`
  - `gamma = clamp(g0 + g_term*(term_years-10), 0, 0.5)`

最終の loading_parameters（最適化結果）
|係数|値|
|---|---|
|a0|0.001999999999999986|
|a_age|0.0|
|a_term|-0.0012000000000000001|
|a_sex|-0.0005|
|b0|0.005|
|b_age|0.0|
|b_term|0.0|
|b_sex|0.0|
|g0|0.03|
|g_term|0.0|

### モデルポイント別のalpha/beta/gamma計算（途中式）
定義: `age_delta = issue_age - 30`, `term_delta = term_years - 10`, `sex_indicator = 1.0 if female else 0.0`。

- male_age30_term35（age_delta=0, term_delta=25, sex_indicator=0）
  - alpha = 0.002000 + 0.000000*0.0 + (-0.001200)*25.0 + (-0.000500)*0.0 = -0.028000
  - beta  = 0.005000 + 0.000000*0.0 + 0.000000*25.0 + 0.000000*0.0 = 0.005000
  - gamma = clamp(0.030000 + 0.000000*25.0, 0, 0.5) = 0.030000
- male_age40_term25（age_delta=10, term_delta=15, sex_indicator=0）
  - alpha = 0.002000 + 0.000000*10.0 + (-0.001200)*15.0 + (-0.000500)*0.0 = -0.016000
  - beta  = 0.005000 + 0.000000*10.0 + 0.000000*15.0 + 0.000000*0.0 = 0.005000
  - gamma = clamp(0.030000 + 0.000000*15.0, 0, 0.5) = 0.030000
- male_age50_term20（age_delta=20, term_delta=10, sex_indicator=0）
  - alpha = 0.002000 + 0.000000*20.0 + (-0.001200)*10.0 + (-0.000500)*0.0 = -0.010000
  - beta  = 0.005000 + 0.000000*20.0 + 0.000000*10.0 + 0.000000*0.0 = 0.005000
  - gamma = clamp(0.030000 + 0.000000*10.0, 0, 0.5) = 0.030000
- female_age30_term35（age_delta=0, term_delta=25, sex_indicator=1）
  - alpha = 0.002000 + 0.000000*0.0 + (-0.001200)*25.0 + (-0.000500)*1.0 = -0.028500
  - beta  = 0.005000 + 0.000000*0.0 + 0.000000*25.0 + 0.000000*1.0 = 0.005000
  - gamma = clamp(0.030000 + 0.000000*25.0, 0, 0.5) = 0.030000
- female_age40_term25（age_delta=10, term_delta=15, sex_indicator=1）
  - alpha = 0.002000 + 0.000000*10.0 + (-0.001200)*15.0 + (-0.000500)*1.0 = -0.016500
  - beta  = 0.005000 + 0.000000*10.0 + 0.000000*15.0 + 0.000000*1.0 = 0.005000
  - gamma = clamp(0.030000 + 0.000000*15.0, 0, 0.5) = 0.030000
- female_age50_term20（age_delta=20, term_delta=10, sex_indicator=1）
  - alpha = 0.002000 + 0.000000*20.0 + (-0.001200)*10.0 + (-0.000500)*1.0 = -0.010500
  - beta  = 0.005000 + 0.000000*20.0 + 0.000000*10.0 + 0.000000*1.0 = 0.005000
  - gamma = clamp(0.030000 + 0.000000*10.0, 0, 0.5) = 0.030000
- female_age60_term10（age_delta=30, term_delta=0, sex_indicator=1）
  - alpha = 0.002000 + 0.000000*30.0 + (-0.001200)*0.0 + (-0.000500)*1.0 = 0.001500
  - beta  = 0.005000 + 0.000000*30.0 + 0.000000*0.0 + 0.000000*1.0 = 0.005000
  - gamma = clamp(0.030000 + 0.000000*0.0, 0, 0.5) = 0.030000

### キャッシュフロー分解（年次）
- 保険料収入: `premium_income = gross_annual_premium * inforce_begin`（払込期間のみ）
- 純保険料収入: `net_premium_income = net_annual_premium * inforce_begin`
- 付加保険料収入: `loading_income = premium_income - net_premium_income`
- 給付: 死亡給付、解約返戻金、満期給付
- 費用: 獲得費 + 維持費 + 集金費（companyモデルはCSVから推定）
- 準備金増減: `reserve_change = sum_assured * (inforce_end*tV_{t+1} - inforce_begin*tV_t)`
- 運用収益: 期首準備金と収支に対するフォワード収益
- 純キャッシュフロー: `net_cf = premium_income + investment_income - (death + surrender + expenses + reserve_change)`
- 指標: `IRR = irr(net_cf系列)`, `NBV = sum(pv_net_cf)`

## 次の実験案
1) python -m pricing.cli report-feasibility configs/trial-001.yaml --r-start 1.00 --r-end 1.06 --r-step 0.005 --irr-threshold 0.06 --out out/feasibility_deck_cap106_irr06.yaml
2) python -m pricing.cli report-feasibility configs/trial-001.yaml --r-start 1.00 --r-end 1.05 --r-step 0.005 --irr-threshold 0.065 --out out/feasibility_deck_irr065_cap105.yaml
