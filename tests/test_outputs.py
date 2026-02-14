from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.endowment import EndowmentPremiums, LoadingParameters
from pricing.outputs import write_profit_test_excel, write_profit_test_log
from pricing.profit_test import ModelPoint, ProfitTestBatchResult, ProfitTestResult


def _make_batch(premium_ratio_override: float = 1.04) -> ProfitTestBatchResult:
    cashflow = pd.DataFrame(
        [
            {"t": 0, "net_cf": 100.0, "spot_df": 1.0},
            {"t": 1, "net_cf": 110.0, "spot_df": 0.98},
        ]
    )
    point1 = ModelPoint(
        model_point_id="mp_a",
        issue_age=30,
        sex="male",
        term_years=20,
        premium_paying_years=20,
        sum_assured=1_000_000,
    )
    point2 = ModelPoint(
        model_point_id="mp_b",
        issue_age=40,
        sex="female",
        term_years=25,
        premium_paying_years=25,
        sum_assured=1_500_000,
    )
    loadings = LoadingParameters(alpha=0.01, beta=0.005, gamma=0.01)
    premiums = EndowmentPremiums(
        A=0.8,
        a=10.0,
        net_rate=0.08,
        gross_rate=0.09,
        net_annual_premium=80_000,
        gross_annual_premium=90_000,
        monthly_premium=7_500,
    )
    result1 = ProfitTestResult(
        model_point=point1,
        loadings=loadings,
        cashflow=cashflow,
        irr=0.03,
        new_business_value=10_000.0,
        premiums=premiums,
        pv_loading=1_000.0,
        pv_expense=800.0,
        loading_surplus=200.0,
        premium_total=float(premiums.gross_annual_premium * point1.premium_paying_years),
        premium_to_maturity_ratio=premium_ratio_override,
        profit_breakdown={"pv_net_cf": 200.0},
    )
    result2 = ProfitTestResult(
        model_point=point2,
        loadings=loadings,
        cashflow=cashflow,
        irr=0.04,
        new_business_value=12_000.0,
        premiums=premiums,
        pv_loading=1_500.0,
        pv_expense=1_200.0,
        loading_surplus=300.0,
        premium_total=float(premiums.gross_annual_premium * point2.premium_paying_years),
        premium_to_maturity_ratio=1.03,
        profit_breakdown={"pv_net_cf": 250.0},
    )
    summary = pd.DataFrame(
        [
            {
                "model_point": "mp_a",
                "sex": "male",
                "issue_age": 30,
                "term_years": 20,
                "premium_paying_years": 20,
                "sum_assured": 1_000_000,
                "net_annual_premium": 80_000,
                "gross_annual_premium": 90_000,
                "monthly_premium": 7_500,
                "irr": 0.03,
                "new_business_value": 10_000.0,
                "pv_loading": 1_000.0,
                "pv_expense": 800.0,
                "loading_surplus": 200.0,
                "premium_total": 1_800_000.0,
                "premium_to_maturity_ratio": premium_ratio_override,
            },
            {
                "model_point": "mp_b",
                "sex": "female",
                "issue_age": 40,
                "term_years": 25,
                "premium_paying_years": 25,
                "sum_assured": 1_500_000,
                "net_annual_premium": 80_000,
                "gross_annual_premium": 90_000,
                "monthly_premium": 7_500,
                "irr": 0.04,
                "new_business_value": 12_000.0,
                "pv_loading": 1_500.0,
                "pv_expense": 1_200.0,
                "loading_surplus": 300.0,
                "premium_total": 2_250_000.0,
                "premium_to_maturity_ratio": 1.03,
            },
        ]
    )
    return ProfitTestBatchResult(
        results=[result1, result2],
        summary=summary,
        expense_assumptions=None,
    )


def test_write_profit_test_excel_creates_model_point_cashflow_sheets(tmp_path: Path) -> None:
    batch = _make_batch()
    out_path = tmp_path / "result.xlsx"
    write_profit_test_excel(out_path, batch)

    wb = openpyxl.load_workbook(out_path, read_only=True)
    try:
        names = wb.sheetnames
    finally:
        wb.close()

    assert "profit_test" in names
    assert "model_point_summary" in names
    assert any(name.startswith("cashflow_") for name in names)
    assert any("mp_a" in name for name in names)
    assert any("mp_b" in name for name in names)


def test_write_profit_test_log_warns_only_above_hard_cap(tmp_path: Path) -> None:
    config = {
        "product": {"type": "endowment"},
        "pricing": {"interest": {"flat_rate": 0.01}},
        "profit_test": {},
        "optimization": {"premium_to_maturity_hard_max": 1.056},
    }

    safe_batch = _make_batch(premium_ratio_override=1.055)
    safe_log = tmp_path / "safe.log"
    write_profit_test_log(safe_log, config, safe_batch)
    assert "premium_total_exceeds_hard_max" not in safe_log.read_text(encoding="utf-8")

    breached_batch = _make_batch(premium_ratio_override=1.07)
    breached_log = tmp_path / "breached.log"
    write_profit_test_log(breached_log, config, breached_batch)
    assert "premium_total_exceeds_hard_max mp_a" in breached_log.read_text(encoding="utf-8")
