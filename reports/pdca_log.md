# PDCA Log

## 2026-01-12 16:09

### Plan
- 選択実験: `report-feasibility --r-start 1.00 --r-end 1.05 --r-step 0.005 --irr-threshold 0.07`
- 理由: IRR閾値引き上げがmin_irr改善の目的に直結するため

### Do
- 変更: `optimization.premium_to_maturity_soft_min` を 1.005 → 1.02
- 実行: `pytest -q` → `pricing.cli optimize` → `pricing.cli run`

### Check
- Before: max_premium_to_maturity=1.04913, min_irr=0.015781950543319344, failures=0
- After: max_premium_to_maturity=1.0496766666666666, min_irr=0.017035184400258398, failures=0
- Delta(min_irr): 0.0012532338569390539

### Act
- failures=0（watch除外）を維持しつつmin_irrが改善したため変更を採用

## 2026-01-12 16:33

### Plan
- 選択実験: `report-feasibility --r-start 1.00 --r-end 1.05 --r-step 0.005 --irr-threshold 0.07`
- 理由: IRR閾値を厳しくした場合の必要premium帯を確認する狙いがあり、soft_min引き上げでmin_irr改善を試すため

### Do
- 変更: `optimization.premium_to_maturity_soft_min` を 1.02 → 1.03
- 実行: `pytest -q` → `pricing.cli optimize` → `pricing.cli run`

### Check
- Before: max_premium_to_maturity=1.0496766666666666, min_irr=0.017035184400258398, failures=0
- After: max_premium_to_maturity=1.0496766666666666, min_irr=0.017035184400258398, failures=0
- Delta(min_irr): 0.0

### Act
- min_irrの改善が無かったため変更を破棄し、`premium_to_maturity_soft_min` を 1.02 に戻した

## 2026-01-12 16:52

### Plan
- 選択実験: `report-feasibility --r-start 1.00 --r-end 1.05 --r-step 0.005 --irr-threshold 0.07`
- 理由: IRR閾値引き上げの方向性に合わせ、min_irrの下限を押し上げる効果を検証するため

### Do
- 変更: `optimization.irr_hard` を 0.0 → 0.02
- 実行: `pytest -q` → `pricing.cli optimize` → `pricing.cli run`

### Check
- Before: max_premium_to_maturity=1.0496766666666666, min_irr=0.017035184400258398, failures=0
- After: max_premium_to_maturity=1.0507766666666667, min_irr=0.019556637099602515, failures=1
- Delta(min_irr): 0.002521452699344117

### Act
- failures=0（watch除外）を維持できなかったため変更を破棄し、`irr_hard` を 0.0 に戻した
- 復帰手順: `pytest -q` → `pricing.cli optimize` → `pricing.cli run` で最適化結果を再生成

## 2026-02-14 17:36

### Plan
- Goal: remove exception handling (`watch`) and produce a fully auditable pricing set for all model points.
- Constraint design update: `irr_hard=0.02`, `premium_to_maturity_hard_max=1.056`, `loading_surplus_hard_ratio=-0.10`, `nbv_hard=0.0`.
- Deliverables: `reports/feasibility_report.md` and `reports/executive_pricing_deck.pptx`.

### Do
- Baseline run with `configs/trial-001.yaml`.
- Feasibility scan with `report-feasibility`.
- Optimization experiments:
  - no-watch + `irr_hard=0.02` + cap 1.05 (failed)
  - no-watch + `irr_hard=0.02` + cap 1.056 (success)
- Final run with `configs/trial-001.executive.optimized.yaml`.
- Generated executive artifacts with `report-executive-pptx`.

### Check
- Baseline (`trial-001.yaml`):
  - violation_count=6
  - min_irr=0.0845786734
  - min_nbv=142540.1263
  - max_premium_to_maturity=1.1801533333
- Final (`trial-001.executive.optimized.yaml`):
  - violation_count=0
  - min_irr=0.0341899847
  - min_nbv=23581.1006
  - max_premium_to_maturity=1.0557666667
- Interpretation:
  - Soundness improved materially (PTM cap now satisfied for all points).
  - Profitability floor remains positive with explicit hard floor (`irr_hard=0.02`).

### Act
- Adopted `configs/trial-001.executive.optimized.yaml` as the recommended reproducible pricing configuration.
- Updated `reports/feasibility_report.md` with formulas, coefficients, and model-point intermediate calculations.
- Generated `reports/executive_pricing_deck.pptx` and copied feasibility snapshot to `reports/feasibility_deck.yaml`.
## PDCA Cycle 20260214_162654
- config: `C:/Users/shunsuke/pricing-automation/out/trial-001.autonomous-best_20260214_162546.yaml`
- policy: `C:/Users/shunsuke/pricing-automation/policy/pricing_policy.yaml`
- baseline_violation_count: `0`
- final_violation_count: `0`
- optimization_applied: `false`
- manifest: `C:/Users/shunsuke/pricing-automation/out/run_manifest_20260214_162654.json`
