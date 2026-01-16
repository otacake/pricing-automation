from __future__ import annotations

import pandas as pd

from pricing.diagnostics import build_run_summary
from pricing.endowment import EndowmentPremiums, LoadingParameters
from pricing.profit_test import ModelPoint, ProfitTestBatchResult, ProfitTestResult


def _make_result(model_point_id: str, irr: float) -> ProfitTestResult:
    point = ModelPoint(
        model_point_id=model_point_id,
        issue_age=30,
        sex="male",
        term_years=10,
        premium_paying_years=10,
        sum_assured=1_000_000,
    )
    loadings = LoadingParameters(alpha=0.01, beta=0.02, gamma=0.03)
    premiums = EndowmentPremiums(
        A=1.0,
        a=1.0,
        net_rate=0.1,
        gross_rate=0.12,
        net_annual_premium=100,
        gross_annual_premium=120,
        monthly_premium=10,
    )
    cashflow = pd.DataFrame({"spot_df": [1.0], "pv_net_cf": [0.0]})
    return ProfitTestResult(
        model_point=point,
        loadings=loadings,
        cashflow=cashflow,
        irr=irr,
        new_business_value=1.0,
        premiums=premiums,
        pv_loading=1.0,
        pv_expense=0.5,
        loading_surplus=0.5,
        premium_total=1200.0,
        premium_to_maturity_ratio=1.2,
    )


def test_build_run_summary_ok() -> None:
    config = {"optimization": {"irr_hard": 0.0, "premium_to_maturity_hard_max": 2.0}}
    result = _make_result("mp1", irr=0.05)
    summary = pd.DataFrame(
        [
            {
                "model_point": "mp1",
                "sum_assured": 1_000_000,
                "irr": result.irr,
                "new_business_value": result.new_business_value,
                "loading_surplus": result.loading_surplus,
                "premium_to_maturity_ratio": result.premium_to_maturity_ratio,
            }
        ]
    )
    batch = ProfitTestBatchResult(results=[result], summary=summary, expense_assumptions=None)
    output = build_run_summary(config, batch)
    assert output["summary"]["violation_count"] == 0
    assert output["model_points"][0]["status"] == "pass"


def test_build_run_summary_violation() -> None:
    config = {"optimization": {"irr_hard": 0.0, "premium_to_maturity_hard_max": 2.0}}
    result = _make_result("mp1", irr=-0.1)
    summary = pd.DataFrame(
        [
            {
                "model_point": "mp1",
                "sum_assured": 1_000_000,
                "irr": result.irr,
                "new_business_value": result.new_business_value,
                "loading_surplus": result.loading_surplus,
                "premium_to_maturity_ratio": result.premium_to_maturity_ratio,
            }
        ]
    )
    batch = ProfitTestBatchResult(results=[result], summary=summary, expense_assumptions=None)
    output = build_run_summary(config, batch)
    assert output["summary"]["violation_count"] == 1
    assert output["violations"][0]["type"] == "irr_hard"
