from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.cli import _format_run_output
from pricing.endowment import EndowmentPremiums, LoadingParameters
from pricing.optimize import optimize_loading_parameters
from pricing.profit_test import ModelPoint, ProfitTestBatchResult, ProfitTestResult


def _make_result(
    model_point_id: str,
    irr: float,
    nbv: float,
    loading_surplus: float,
    premium_to_maturity_ratio: float,
) -> ProfitTestResult:
    point = ModelPoint(
        model_point_id=model_point_id,
        issue_age=30,
        sex="male",
        term_years=10,
        premium_paying_years=10,
        sum_assured=1_000_000,
    )
    loadings = LoadingParameters(alpha=0.0, beta=0.0, gamma=0.0)
    premiums = EndowmentPremiums(
        A=1.0,
        a=1.0,
        net_rate=0.1,
        gross_rate=0.1,
        net_annual_premium=100,
        gross_annual_premium=100,
        monthly_premium=10,
    )
    cashflow = pd.DataFrame({"net_cf": [0.0]})
    return ProfitTestResult(
        model_point=point,
        loadings=loadings,
        cashflow=cashflow,
        irr=irr,
        new_business_value=nbv,
        premiums=premiums,
        pv_loading=0.0,
        pv_expense=0.0,
        loading_surplus=loading_surplus,
        premium_total=1000.0,
        premium_to_maturity_ratio=premium_to_maturity_ratio,
    )


def test_watch_model_point_excluded_from_success(monkeypatch, tmp_path: Path) -> None:
    config = {
        "optimization": {
            "stages": [{"name": "base", "variables": ["a0"]}],
            "max_iterations_per_stage": 1,
            "watch_model_point_ids": ["watch_me"],
        }
    }

    def fake_run_profit_test(_config, base_dir=None, loading_params=None):
        res_ok = _make_result(
            model_point_id="ok",
            irr=0.1,
            nbv=1.0,
            loading_surplus=100.0,
            premium_to_maturity_ratio=1.0,
        )
        res_watch = _make_result(
            model_point_id="watch_me",
            irr=-0.5,
            nbv=-1.0,
            loading_surplus=-100.0,
            premium_to_maturity_ratio=2.0,
        )
        summary = pd.DataFrame(
            [
                {
                    "model_point": "ok",
                    "sum_assured": 1_000_000,
                    "irr": res_ok.irr,
                    "new_business_value": res_ok.new_business_value,
                    "loading_surplus": res_ok.loading_surplus,
                    "premium_to_maturity_ratio": res_ok.premium_to_maturity_ratio,
                },
                {
                    "model_point": "watch_me",
                    "sum_assured": 1_000_000,
                    "irr": res_watch.irr,
                    "new_business_value": res_watch.new_business_value,
                    "loading_surplus": res_watch.loading_surplus,
                    "premium_to_maturity_ratio": res_watch.premium_to_maturity_ratio,
                },
            ]
        )
        return ProfitTestBatchResult(
            results=[res_ok, res_watch],
            summary=summary,
            expense_assumptions=None,
        )

    monkeypatch.setattr("pricing.optimize.run_profit_test", fake_run_profit_test)

    result = optimize_loading_parameters(config, base_dir=tmp_path)
    assert result.success is True
    assert result.watch_model_points == ["watch_me"]


def test_run_output_marks_watch() -> None:
    config = {
        "optimization": {"watch_model_point_ids": ["watch_me"]},
    }

    res_ok = _make_result(
        model_point_id="ok",
        irr=0.1,
        nbv=1.0,
        loading_surplus=100.0,
        premium_to_maturity_ratio=1.0,
    )
    res_watch = _make_result(
        model_point_id="watch_me",
        irr=-0.5,
        nbv=-1.0,
        loading_surplus=-100.0,
        premium_to_maturity_ratio=2.0,
    )
    summary = pd.DataFrame(
        [
            {
                "model_point": "ok",
                "sum_assured": 1_000_000,
                "irr": res_ok.irr,
                "new_business_value": res_ok.new_business_value,
                "loading_surplus": res_ok.loading_surplus,
                "premium_to_maturity_ratio": res_ok.premium_to_maturity_ratio,
            },
            {
                "model_point": "watch_me",
                "sum_assured": 1_000_000,
                "irr": res_watch.irr,
                "new_business_value": res_watch.new_business_value,
                "loading_surplus": res_watch.loading_surplus,
                "premium_to_maturity_ratio": res_watch.premium_to_maturity_ratio,
            },
        ]
    )
    batch = ProfitTestBatchResult(
        results=[res_ok, res_watch],
        summary=summary,
        expense_assumptions=None,
    )

    output = _format_run_output(config, batch)
    assert "watch_me" in output
    assert "status=watch" in output
