from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pricing.optimize as optimize_mod
from pricing.endowment import EndowmentPremiums, LoadingParameters
from pricing.outputs import write_optimize_log
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


def test_optimize_exemption_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = {
        "optimization": {
            "stages": [{"name": "base", "variables": ["a0"]}],
            "max_iterations_per_stage": 1,
            "exemption": {
                "enabled": True,
                "method": "sweep_ptm",
                "sweep": {"start": 1.0, "end": 1.0, "step": 0.01, "irr_threshold": 0.0},
            },
        }
    }

    def fake_sweep_premium_to_maturity_all(**_kwargs):
        return pd.DataFrame(), {"mp1": 1.0, "mp2": None}

    def fake_run_profit_test(_config, base_dir=None, loading_params=None):
        res1 = _make_result(
            model_point_id="mp1",
            irr=0.1,
            nbv=1.0,
            loading_surplus=100.0,
            premium_to_maturity_ratio=1.0,
        )
        res2 = _make_result(
            model_point_id="mp2",
            irr=-0.5,
            nbv=-1.0,
            loading_surplus=-100.0,
            premium_to_maturity_ratio=2.0,
        )
        summary = pd.DataFrame(
            [
                {
                    "model_point": "mp1",
                    "sum_assured": 1_000_000,
                    "irr": res1.irr,
                    "new_business_value": res1.new_business_value,
                    "loading_surplus": res1.loading_surplus,
                    "premium_to_maturity_ratio": res1.premium_to_maturity_ratio,
                },
                {
                    "model_point": "mp2",
                    "sum_assured": 1_000_000,
                    "irr": res2.irr,
                    "new_business_value": res2.new_business_value,
                    "loading_surplus": res2.loading_surplus,
                    "premium_to_maturity_ratio": res2.premium_to_maturity_ratio,
                },
            ]
        )
        return ProfitTestBatchResult(
            results=[res1, res2],
            summary=summary,
            expense_assumptions=None,
        )

    monkeypatch.setattr(
        optimize_mod, "sweep_premium_to_maturity_all", fake_sweep_premium_to_maturity_all
    )
    monkeypatch.setattr(optimize_mod, "run_profit_test", fake_run_profit_test)

    result = optimize_mod.optimize_loading_parameters(config, base_dir=tmp_path)
    assert result.exempt_model_points == ["mp2"]
    assert result.success is True

    log_path = tmp_path / "optimize.log"
    write_optimize_log(log_path, config, result)
    log_text = log_path.read_text(encoding="utf-8")
    assert "exempt_list: mp2" in log_text
    assert "exempt_detail id=mp2" in log_text
