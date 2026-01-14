# Feasibility Report (trial-001, irr_threshold=0.06, r_end=1.05)

## 結論
- 拘束条件: premium_to_maturity_hard_max が r_end=1.05 で全モデルポイント余裕度0（拘束）。min_r時点でも male_age50_term20 と female_age60_term10 は余裕度0。
- not found: 0件（7/7でmin_r検出）
- 予定事業費・保険料: data/company_expense.csv を0.90スケールして採用した前提で最適化した loading_parameters を採用。scale=1.00/0.95 は premium_to_maturity_hard_max を満たさず、scale=0.90 で非watch全点が制約内。
- 意思決定: rは一律倍率の診断軸であり、最終料率は alpha/beta/gamma の係数式で固定する。拘束2点は監視対象とし、前提更新時に再計算する。
- alpha>=0 を hard 制約として課し、最小alpha=0.0010（male_age30_term35）。付加保険料は `gross_annual_premium > net_annual_premium` を満たす設計で運用する。

## 意思決定サマリー（1枚）
|項目|内容|
|---|---|
|採用する料率式|`gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`、alpha/beta/gammaは線形式（係数は後述）|
|予定事業費|`data/company_expense.csv`（原本を0.90スケールした値を採用）|
|適用範囲|モデルポイント7件、r_start=1.0, r_end=1.05（rは一律倍率）|
|拘束条件|premium_to_maturity_hard_max の余裕度=0（r_endで全点、min_rで2点）|
|alpha/beta/gamma>=0|hard制約として設定（最小alpha=0.0010）|
|付加保険料正|`gross_annual_premium > net_annual_premium` をhard制約として設定|
|残余リスク|刻み0.01と丸めの段差、利率/解約/費用の感度の追加検証|

## 上位者向け説明（意思決定の根拠）
本レポートの目的は「IRR閾値0.06を満たすために必要な保険料倍率の範囲」を数値で特定し、制約の余裕度まで含めて意思決定に使える形へ整理することである。rは一律倍率（各モデルポイントの基準保険料に共通に乗算）であり、min_rはモデルポイントごとの診断値である。irr_threshold=0.06はmin_rを決めるための目標水準であり、irr_hard=0.0は制約の下限である。

最終料率の採用に際しては、company_expense.csv を0.90スケールした前提で最適化を再実行した。scale=1.00/0.95 は premium_to_maturity_hard_max を満たさず、scale=0.90 で初めて非watch全点が制約内となった。以降の最終料率評価は `configs/trial-001.optimized.yaml` に基づく。

KPIの最悪値（探索格子全体）は min IRR=-0.0986235910327119、min NBV=-70191.17194549802、min loading_surplus_ratio=-0.09098095313360245、max premium_to_maturity=1.05 である。制約余裕度を見ると premium_to_maturity_hard_max の余裕度は r_end=1.05 で全点0となり拘束条件である。一方、他の制約は r_end 時点でも余裕があり、最小余裕度は irr_hard で 0.0666267211728547（male_age30_term35）、loading_surplus_ratio で 0.03952236258345432（male_age50_term20）、nbv_hard で 49347.9433452091（female_age60_term10）である。

付加保険料の最終式は後述の「付加保険料計算式とキャッシュフロー分解」に示すとおりで、最適化係数は a0=0.005999999999999986, a_term=-0.0002, a_sex=0.0005, b0=0.005, g0=0.024999999999999998, g_term=-0.003（他係数は0）に固定されている。alpha>=0 と付加保険料正の hard 制約を課したため、alphaは全モデルポイントで正となる。gammaはtermで変動するが長期側は0にクランプされる。

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

補足:
- irr_threshold は min_r 判定に使う目標水準で、irr_hard は制約の下限（本レポートでは 0.0）。
- r は一律倍率であり、`gross_annual_premium = round(r * sum_assured / premium_paying_years, 0)` を全モデルポイントに適用する。
- 本レポートの sweep は `loading_alpha_beta_gamma` を固定値として用いる。最終の料率式で使う係数は `configs/trial-001.optimized.yaml` の `loading_parameters` として後述する（company_expense 0.90スケール前提）。

## KPIサマリー（集計点別）
単位: IRR/ratioはrate、NBVはJPY。min_r集計は「各モデルポイントのmin_r時点」を集計した値。

|集計点|min IRR（値, model_point_id, r）|min NBV（値, model_point_id, r）|min loading_surplus_ratio（値, model_point_id, r）|max premium_to_maturity（値, model_point_id, r）|
|---|---|---|---|---|
|r=1.00|-0.0986235910327119 (female_age60_term10, r=1.00)|-70191.17194549802 (female_age60_term10, r=1.00)|-0.09098095313360245 (male_age50_term20, r=1.00)|1.0 (female_age40_term25, r=1.00)|
|min_r集計|0.062067131092413144 (male_age30_term35, r=1.04)|49347.9433452091 (female_age60_term10, r=1.05)|-0.06886143593856732 (female_age40_term25, r=1.01)|1.05 (female_age60_term10, r=1.05)|
|r_end=1.05|0.0666267211728547 (male_age30_term35, r=1.05)|49347.9433452091 (female_age60_term10, r=1.05)|-0.06047763741654569 (male_age50_term20, r=1.05)|1.05 (female_age30_term35, r=1.05)|
|探索格子全体|-0.0986235910327119 (female_age60_term10, r=1.00)|-70191.17194549802 (female_age60_term10, r=1.00)|-0.09098095313360245 (male_age50_term20, r=1.00)|1.05 (male_age30_term35, r=1.05)|

## 制約の定義（計算式）
- `premium_to_maturity = (gross_annual_premium * premium_paying_years) / sum_assured`（払込総額/満期保険金。割引は行わない）
- `gross_annual_premium = round(gross_rate * sum_assured, 0)`（円単位、偶数丸め）
- `irr_hard`: `IRR = irr(net_cf系列)` が `>= 0.0`
- `nbv_hard`: `NBV = sum(pv_net_cf)` が `>= 0.0`
- `loading_surplus_ratio`: `(pv_loading - pv_expense) / sum_assured` が `>= -0.10`
- `alpha_non_negative`: `alpha >= 0.0`
- `beta_non_negative`: `beta >= 0.0`
- `gamma_non_negative`: `gamma >= 0.0`
- `loading_positive`: `gross_annual_premium > net_annual_premium`
- `premium_to_maturity_hard_max`: `premium_to_maturity <= 1.05`

premium_to_maturity_hard_max=1.05 の根拠は、本レポートでは `configs/trial-001.yaml` の制約値（学習用の仮定）であり、最終承認時は社内規程・商品仕様・外部制約との対応付けを添付することを前提とする。

## 診断軸 r と最終料率式の接続
feasibility sweep の r は一律倍率であり、`gross_annual_premium = round(r * sum_assured / premium_paying_years, 0)` と定義する。従って `premium_to_maturity = gross_annual_premium * premium_paying_years / sum_assured` となり、丸めの影響を除けば r と premium_to_maturity は同一の診断軸である。

一方、最終料率式は `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)` で計算され、ここから得られる `gross_annual_premium` によって `premium_to_maturity`（= 診断軸のr相当）が決まる。したがって、最終料率の妥当性は「最終係数式から算出した premium_to_maturity が r_end（=1.05）内に収まるか」で評価する。
本レポートでは feasibility sweep は `loading_alpha_beta_gamma` 固定の簡易式で実施し、最終係数式での結果は下表に分離して提示する。

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

注記: min_rはモデルポイント別の診断値であり、rをモデルポイント別に運用する場合は料率表の区分設計（年齢・性別・期間）や再最適化が必要になる。

## 予定事業費・保険料の探索結果
premium_to_maturity_hard_max を満たすため、company_expense.csv をスケールして最適化を再実行した。scale は「元の company_expense.csv」に対する倍率として整理する。

|planned expense scale|optimize success (non-watch)|min premium_to_maturity_slack (non-watch)|備考|
|---|---|---|---|
|1.00|fail|-|premium_to_maturity_hard: male_age30_term35, male_age40_term25, female_age40_term25, female_age50_term20, female_age60_term10 / alpha_non_negative: male_age30_term35, female_age30_term35|
|0.95|fail|-|premium_to_maturity_hard: male_age30_term35, male_age40_term25, female_age30_term35, female_age50_term20, female_age60_term10 / alpha_non_negative: male_age30_term35, male_age40_term25, female_age30_term35, female_age40_term25|
|0.90|pass|0.000243 (female_age60_term10)|watch の male_age50_term20 は premium_to_maturity=1.055553|

採用: scale=0.90 を予定事業費の基準として採用し、最終料率の評価は以下に示す。最適化では alpha/beta/gamma>=0 と付加保険料正（gross_annual_premium > net_annual_premium）を hard 制約として追加した。

## 最終料率式によるモデルポイント別結果（configs/trial-001.optimized.yaml）
最終の alpha/beta/gamma 係数式で算出した年払総保険料を用い、IRR/NBV/制約余裕度を計算した。watch対象の male_age50_term20 は hard 制約評価から除外されるが、数値は参考として掲載する。

|model_point_id|gross_annual_premium|irr|nbv|loading_surplus_ratio|premium_to_maturity|irr_hard_slack|nbv_hard_slack|loading_surplus_ratio_slack|premium_to_maturity_slack|
|---|---|---|---|---|---|---|---|---|---|
|male_age30_term35|89114|0.041539|92082.348397|-0.068788|1.039663|0.041539|92082.348397|0.031212|0.010337|
|male_age40_term25|124616|0.044615|89084.175106|-0.067110|1.038467|0.044615|89084.175106|0.032890|0.011533|
|male_age50_term20|158333|0.042239|68193.882663|-0.065920|1.055553|0.042239|68193.882663|0.034080|-0.005553|
|female_age30_term35|88271|0.042353|97470.303152|-0.068529|1.029828|0.042353|97470.303152|0.031471|0.020172|
|female_age40_term25|123304|0.046344|97168.576151|-0.066812|1.027533|0.046344|97168.576151|0.033188|0.022467|
|female_age50_term20|155193|0.047382|86456.553307|-0.065621|1.034620|0.047382|86456.553307|0.034379|0.015380|
|female_age60_term10|314927|0.020119|6878.861864|-0.041182|1.049757|0.020119|6878.861864|0.058818|0.000243|

補足: male_age50_term20 は watch 対象のため premium_to_maturity_slack が負でも hard 制約判定から除外される。

## 事業費の十分性の整理
事業費の十分性は `loading_surplus` と `loading_surplus_ratio` で評価する。定義は `loading_surplus = pv_loading - pv_expense`、`loading_surplus_ratio = loading_surplus / sum_assured` であり、制約は `loading_surplus_ratio >= -0.10` である。評価は profit_test（company費用モデル）で行うべきで、feasibility sweep の `loading_alpha_beta_gamma` 固定式は事業費の十分性を直接反映しない。

現行の company費用モデルでは `data/company_expense.csv` の先頭行（year=2025）から獲得費単価・維持費単価・集金費率を推定する。`profit_test.expense_model.include_overhead_as` は `overhead_split` として読み替えるよう修正済みであり、`overhead_total` は獲得/維持に配賦される。予定事業費の負値は許容せず、獲得費単価・維持費単価・集金費率が負になる場合はエラーで停止する。現在は company_expense.csv を0.90スケールした値を採用している。

会社費用モデルの改善点として、`allocation_rule`（acquisition/maintenance/collection の配賦基準）は現行コードでは使用していない。配賦基準を厳密に反映する場合は実装対応が必要である。

最終料率式での基準値（planned expense scale 0.90）は以下の通り。
- 最小 loading_surplus_ratio = -0.068788（male_age30_term35）
- 余裕度 = -0.068788 - (-0.10) = 0.031212

費用感度（profit_test, company費用モデル）では、expense_up の最小 loading_surplus_ratio が -0.083836 まで悪化し、余裕度は 0.016164 まで縮小する。現時点では制約内だが、費用前提の上振れに対して余裕が薄いことを示すため、次の運用を推奨する。
- `company_expense.csv` は毎期更新し、過年度実績との乖離が大きい場合は再評価する。
- overhead を事業費に含める方針であれば、`overhead_split` を明示し、感度評価を再実施する。
## 制約余裕度（r_end=1.05）
余裕度は「下限制約: 実現値 - 下限」「上限制約: 上限 - 実現値」と定義し、余裕度=0を拘束条件とみなす。

|model_point_id|irr_hard_slack|nbv_hard_slack|loading_surplus_ratio_slack|premium_to_maturity_slack|
|---|---|---|---|---|
|female_age30_term35|0.072160|155793.688662|0.048019|0.000000|
|female_age40_term25|0.093589|166519.912539|0.053453|0.000000|
|female_age50_term20|0.101009|148724.525755|0.052431|0.000000|
|female_age60_term10|0.104582|49347.943345|0.070442|0.000000|
|male_age30_term35|0.066627|137184.783788|0.043391|0.000000|
|male_age40_term25|0.082336|140239.899715|0.047158|0.000000|
|male_age50_term20|0.070140|92032.197727|0.039522|0.000000|

## 制約余裕度（min_r時点）
|model_point_id|min_r|irr_hard_slack|nbv_hard_slack|loading_surplus_ratio_slack|premium_to_maturity_slack|
|---|---|---|---|---|---|
|female_age30_term35|1.03|0.062937|128064.707807|0.038976|0.019997|
|female_age40_term25|1.01|0.062564|98176.598304|0.031139|0.040000|
|female_age50_term20|1.02|0.068329|91744.568649|0.033810|0.030000|
|female_age60_term10|1.05|0.104582|49347.943345|0.070442|0.000000|
|male_age30_term35|1.04|0.062067|123398.473245|0.038895|0.009998|
|male_age40_term25|1.03|0.066891|106342.333436|0.036090|0.020000|
|male_age50_term20|1.05|0.070140|92032.197727|0.039522|0.000000|

## 最小余裕度（拘束条件の特定）
|制約|min余裕度(r_end)|該当モデルポイント|min余裕度(min_r)|該当モデルポイント|
|---|---|---|---|---|
|irr_hard|0.0666267211728547|male_age30_term35|0.062067131092413144|male_age30_term35|
|nbv_hard|49347.9433452091|female_age60_term10|49347.9433452091|female_age60_term10|
|loading_surplus_hard_ratio|0.03952236258345432|male_age50_term20|0.031138564061432686|female_age40_term25|
|premium_to_maturity_hard_max|0.0|全モデルポイント|0.0|female_age60_term10, male_age50_term20|

## 示唆
not foundは0件で、irr_threshold=0.06はr_end=1.05内で達成可能である。min_rがr_endに張り付く点は2件（male_age50_term20, female_age60_term10）であり、上限制約（premium_to_maturity_hard_max）が拘束している。刻み幅0.01と丸め（`round(..., 0)`）の段差により、min_rの境界には0.01未満の誤差が含まれるため、感度検証はr_stepの細分化（0.005等）と端点拡張で行うべきである。

alpha/beta/gamma>=0 と付加保険料正を hard 制約として課したため、長期側の割引は発生しない。最小alphaは 0.0010（male_age30_term35）であり、負荷ゼロに近い点が境界になるため、前提更新時は premium_to_maturity_slack と併せて監視する。

## alphaが期間で減少する妥当性（費用構造）
alpha は獲得費を中心とした「初期費用の上乗せ」を表す前提である。長期になるほど alpha を小さくする設計が数理的に許容されるのは、以下のように費用構造が説明できる場合に限られる。

- 獲得費が契約初期の固定費に近く、保険期間が長いほど「保険金額あたりの初期費用の比率」が低下する（固定費の分散）。  
- 維持費は beta 側（年次・保有に比例）で回収する前提で、alpha を下げても総費用の回収に矛盾しない。  
- 長期契約の価格競争や販売施策により、初期負荷を抑える合理性がある（ただし alpha>=0 を維持する）。  

上記の説明が成立しない場合は、alpha を期間で減少させず、a_term>=0（もしくは0固定）の制約で再推定することが望ましい。現行の最適化では alpha>=0 を hard 制約としているため、「長期ほど alpha が小さいが負にはならない」範囲で費用構造の整合性を確保している。

## 監視運用（提案）
- 監視指標: premium_to_maturity_slack（r_end）、min_r（モデルポイント別）、min_irr（r_end）
- 監視頻度: 月次、または前提（利率・解約率・費用）更新時
- 再計算トリガー: premium_to_maturity_slack<=0.005、または min_r=r_end のモデルポイント数が2件を超える場合
- 承認者: 数理責任者（pricing lead）

## 感度分析（±10%）
### 利率/解約感度（feasibility sweep）
前提の変更は以下の通り。
- 利率: pricing_interest_rate=0.01 を 0.009/0.011 に変更、valuation_interest_rate=0.0025 を 0.00225/0.00275 に変更
- 解約率: profit_test.lapse_rate=0.03 を 0.027/0.033 に変更

結果サマリー（r_end=1.05, irr_threshold=0.06）
|scenario|max_min_r|min_r=r_end count (ids)|min_irr@r_end (mp)|irr_margin@r_end|not_found|
|---|---|---|---|---|---|
|baseline|1.05|2 (male_age50_term20,female_age60_term10)|0.066627 (male_age30_term35)|0.006627|0|
|interest_down|1.05|2 (male_age50_term20,female_age60_term10)|0.065115 (male_age30_term35)|0.005115|0|
|interest_up|1.04|0 (-)|0.068163 (male_age30_term35)|0.008163|0|
|lapse_down|1.05|1 (female_age60_term10)|0.068047 (male_age30_term35)|0.008047|0|
|lapse_up|1.05|1 (male_age50_term20)|0.065225 (male_age30_term35)|0.005225|0|

補足:
- 利率上振れでは max_min_r が 1.04 まで低下し、r_end拘束から外れる。
- 解約率の上下は min_r=r_end の対象を1件に減らすが、not foundは発生しない。

### 費用感度（profit_test, company費用モデル）
data/company_expense.csv（0.90スケール済み）の費用列（acq_var_total, acq_fixed_total, maint_var_total, maint_fixed_total, coll_var_total, overhead_total）を ±10% スケールし、`configs/trial-001.optimized.yaml` の最終料率式で profit_test を再計算した。

|scenario|min_irr|min_nbv|min_loading_surplus_ratio|max_premium_to_maturity|
|---|---|---|---|---|
|baseline|0.020119|6878.861864|-0.068788|1.055553|
|expense_down|0.050250|39757.628960|-0.053741|1.055553|
|expense_up|-0.006226|-25999.905231|-0.083836|1.055553|

## 付加保険料計算式とキャッシュフロー分解
### 付加保険料計算式（最終適用）
- 純保険料率: `net_rate = A / a`
- 総保険料率: `gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)`
- 年払総保険料: `gross_annual_premium = round(gross_rate * sum_assured, 0)`
- 丸め規則: `round(..., 0)` はPython標準の偶数丸め（0.5は偶数側へ）で円単位に丸める
- `alpha/beta/gamma` の生成（モデルポイントごと）
  - `alpha = a0 + a_age*(issue_age-30) + a_term*(term_years-10) + a_sex*(sex_indicator)`
  - `beta  = b0 + b_age*(issue_age-30) + b_term*(term_years-10) + b_sex*(sex_indicator)`
  - `gamma = clamp(g0 + g_term*(term_years-10), 0, 0.5)`

注記: feasibility sweep は `configs/trial-001.yaml` の `loading_alpha_beta_gamma` を固定値として使う。一方、最終の料率式で使う係数は `configs/trial-001.optimized.yaml` の `loading_parameters` に基づく。

最終の loading_parameters（configs/trial-001.optimized.yaml）
|係数|値|
|---|---|
|a0|0.005999999999999986|
|a_age|0.0|
|a_term|-0.0002|
|a_sex|0.0005|
|b0|0.005|
|b_age|0.0|
|b_term|0.0|
|b_sex|0.0|
|g0|0.024999999999999998|
|g_term|-0.003|

### モデルポイント別のalpha/beta/gamma計算（途中式）
定義: `age_delta = issue_age - 30`, `term_delta = term_years - 10`, `sex_indicator = 1.0 if female else 0.0`。

- male_age30_term35（age_delta=0, term_delta=25, sex_indicator=0）
  - alpha = 0.006000 + 0.000000*0.0 + (-0.000200)*25.0 + 0.000500*0.0 = 0.001000
  - beta  = 0.005000 + 0.000000*0.0 + 0.000000*25.0 + 0.000000*0.0 = 0.005000
  - gamma = clamp(0.025000 + (-0.003000)*25.0, 0, 0.5) = 0.000000
- male_age40_term25（age_delta=10, term_delta=15, sex_indicator=0）
  - alpha = 0.006000 + 0.000000*10.0 + (-0.000200)*15.0 + 0.000500*0.0 = 0.003000
  - beta  = 0.005000 + 0.000000*10.0 + 0.000000*15.0 + 0.000000*0.0 = 0.005000
  - gamma = clamp(0.025000 + (-0.003000)*15.0, 0, 0.5) = 0.000000
- male_age50_term20（age_delta=20, term_delta=10, sex_indicator=0）
  - alpha = 0.006000 + 0.000000*20.0 + (-0.000200)*10.0 + 0.000500*0.0 = 0.004000
  - beta  = 0.005000 + 0.000000*20.0 + 0.000000*10.0 + 0.000000*0.0 = 0.005000
  - gamma = clamp(0.025000 + (-0.003000)*10.0, 0, 0.5) = 0.000000
- female_age30_term35（age_delta=0, term_delta=25, sex_indicator=1）
  - alpha = 0.006000 + 0.000000*0.0 + (-0.000200)*25.0 + 0.000500*1.0 = 0.001500
  - beta  = 0.005000 + 0.000000*0.0 + 0.000000*25.0 + 0.000000*1.0 = 0.005000
  - gamma = clamp(0.025000 + (-0.003000)*25.0, 0, 0.5) = 0.000000
- female_age40_term25（age_delta=10, term_delta=15, sex_indicator=1）
  - alpha = 0.006000 + 0.000000*10.0 + (-0.000200)*15.0 + 0.000500*1.0 = 0.003500
  - beta  = 0.005000 + 0.000000*10.0 + 0.000000*15.0 + 0.000000*1.0 = 0.005000
  - gamma = clamp(0.025000 + (-0.003000)*15.0, 0, 0.5) = 0.000000
- female_age50_term20（age_delta=20, term_delta=10, sex_indicator=1）
  - alpha = 0.006000 + 0.000000*20.0 + (-0.000200)*10.0 + 0.000500*1.0 = 0.004500
  - beta  = 0.005000 + 0.000000*20.0 + 0.000000*10.0 + 0.000000*1.0 = 0.005000
  - gamma = clamp(0.025000 + (-0.003000)*10.0, 0, 0.5) = 0.000000
- female_age60_term10（age_delta=30, term_delta=0, sex_indicator=1）
  - alpha = 0.006000 + 0.000000*30.0 + (-0.000200)*0.0 + 0.000500*1.0 = 0.006500
  - beta  = 0.005000 + 0.000000*30.0 + 0.000000*0.0 + 0.000000*1.0 = 0.005000
  - gamma = clamp(0.025000 + (-0.003000)*0.0, 0, 0.5) = 0.025000

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
