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

