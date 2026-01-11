# Pricing実施報告（trial-001）
作成日: 2026-01-11（configs/trial-001.yaml の as_of に準拠）
作成者: pricing-automation 実装・管理

## 1. 実施概要
- 対象商品: 養老保険（endowment）
- 実行コマンド: `python -m pricing.cli run configs/trial-001.yaml`
- 実行環境: `PYTHONPATH=src`

## 2. リポジトリ概観
- `configs/`: 実行設定（YAML）
- `data/`: 入力データ（死亡率・スポット・費用）
- `src/pricing/`: 計算ロジック（保険料・収益性・最適化）
- `out/`: 出力（Excel/CSV/ログ）
- `tests/`: 検証用テスト

## 3. 入力前提（主要項目）
- 予定利率: 1.0%（flat）
- 予定死亡率: `data/mortality_pricing.csv`
- 実績死亡率: `data/mortality_actual.csv`
- 割引曲線: `data/spot_curve_actual.csv`
- 費用モデル: `data/company_expense.csv`（company モード）
- Loading: alpha=0.03, beta=0.007, gamma=0.03

## 4. 指標定義（説明用）
- P（総保険料）: `gross_annual_premium`（年払総保険料）
- 純保険料: `net_annual_premium`
- 付加P: `gross_annual_premium - net_annual_premium`
- PTM: `gross_annual_premium * premium_paying_years / sum_assured`
- IRR / NBV / loading_surplus: `out/result_trial-001.xlsx` の「モデルポイント別サマリー」に準拠

## 5. モデルポイント別サマリー
出典: `out/result_trial-001.xlsx`（モデルポイント別サマリー）

| model_point_id | sex | issue_age | term_years | premium_paying_years | sum_assured | net_annual_premium | gross_annual_premium | loading_premium | irr | nbv | loading_surplus | premium_to_maturity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| male_age30_term35 | male | 30 | 35 | 35 | 3000000 | 74011 | 86633 | 12622 | 0.03066445291335103 | 34054.42442103568 | -244097.3663027328 | 1.010718333333333 |
| male_age40_term25 | male | 40 | 25 | 25 | 3000000 | 109199 | 124032 | 14833 | 0.03927990090253308 | 69868.89333811932 | -208238.9741570005 | 1.0336 |
| male_age50_term20 | male | 50 | 20 | 20 | 3000000 | 142644 | 159323 | 16679 | 0.04315910039586977 | 72941.50072943133 | -184788.784222684 | 1.062153333333333 |
| female_age30_term35 | female | 30 | 35 | 35 | 3000000 | 73117 | 85649 | 12532 | 0.03101273413189971 | 36319.10382608154 | -245794.8619454681 | 0.9992383333333333 |
| female_age40_term25 | female | 40 | 25 | 25 | 3000000 | 107822 | 122510 | 14688 | 0.04012547475246241 | 74273.80969946065 | -210365.4475178259 | 1.020916666666667 |
| female_age50_term20 | female | 50 | 20 | 20 | 3000000 | 139432 | 155896 | 16464 | 0.04692465536252147 | 87185.92611465926 | -187233.5733671275 | 1.039306666666667 |
| female_age60_term10 | female | 60 | 10 | 10 | 3000000 | 289977 | 314739 | 24762 | 0.01578195054331934 | 1757.560522501619 | -126726.4478051465 | 1.04913 |

## 6. 最適化探索の調整（確認方針）
- `premium_to_maturity_soft_min` を 1.005 に微調整し、PTMの余裕を保ったまま min_irr 上積み余地を確認する。
- `bounds` は a0/b0/g0 を据え置き、a_term などに小さな step を追加して局所探索を行う。
- 設定反映先: `configs/trial-001.yaml`

## 7. 留意事項
- premium_to_maturity が 1.0 を超えるモデルポイントが複数あるため、顧客説明・商品設計の観点で上限運用方針の確認が必要。
- loading_surplus が全モデルポイントで負のため、費用負荷設計の見直し余地がある。

## 8. 出力成果物
- `out/result_trial-001.xlsx`
- `out/result_trial-001.log`
- `out/sweep_ptm_all.csv`
