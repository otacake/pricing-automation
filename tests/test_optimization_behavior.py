from __future__ import annotations

import copy
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.config import load_optimization_settings, loading_surplus_threshold
from pricing.endowment import EndowmentPremiums, LoadingParameters
from pricing.optimize import optimize_loading_parameters
from pricing.profit_test import ModelPoint, ProfitTestBatchResult, ProfitTestResult


def test_optimization_settings_defaults() -> None:
    settings = load_optimization_settings({})
    assert settings.irr_hard == 0.07
    assert settings.irr_target == 0.08
    assert settings.loading_surplus_hard == 0.0
    assert settings.loading_surplus_hard_ratio == -0.10
    assert settings.premium_to_maturity_hard_max == 1.05
    assert settings.premium_to_maturity_target == 1.0
    assert settings.nbv_hard == 0.0


def test_loading_surplus_ratio_threshold() -> None:
    settings = load_optimization_settings({"optimization": {"loading_surplus_hard_ratio": -0.10}})
    assert loading_surplus_threshold(settings, 3000000) == -300000.0


def test_stage_search_base_only() -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = copy.deepcopy(config)
    config["optimization"] = {
        "stages": [{"name": "base", "variables": ["a0", "b0", "g0"]}],
        "max_iterations_per_stage": 10,
    }

    result = optimize_loading_parameters(config, base_dir=REPO_ROOT)
    assert result.batch_result.summary.shape[0] == 8


def test_premium_hard_max_failure() -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config = copy.deepcopy(config)
    config["optimization"] = config.get("optimization", {})
    config["optimization"]["premium_to_maturity_hard_max"] = 0.5
    config["optimization"]["max_iterations_per_stage"] = 10

    result = optimize_loading_parameters(config, base_dir=REPO_ROOT)
    assert result.success is False
    assert any("premium_to_maturity_hard" in item for item in result.failure_details)


def test_nbv_hard_failure(monkeypatch) -> None:
    config = {
        "optimization": {
            "irr_hard": 0.0,
            "irr_target": 0.1,
            "loading_surplus_hard_ratio": -0.1,
            "premium_to_maturity_hard_max": 2.0,
            "premium_to_maturity_target": 1.0,
            "nbv_hard": 0.0,
            "stages": [{"name": "base", "variables": ["a0"]}],
            "bounds": {"a0": {"min": 0.0, "max": 0.2, "step": 0.1}},
            "l2_lambda": 0.0,
            "max_iterations_per_stage": 5,
        }
    }

    def fake_run_profit_test(_config, base_dir=None, loading_params=None):
        point = ModelPoint(
            issue_age=30,
            sex="male",
            term_years=10,
            premium_paying_years=10,
            sum_assured=1000000,
        )
        premiums = EndowmentPremiums(
            A=0.0,
            a=1.0,
            net_rate=0.0,
            gross_rate=0.0,
            net_annual_premium=0,
            gross_annual_premium=0,
            monthly_premium=0,
        )
        result = ProfitTestResult(
            model_point=point,
            loadings=LoadingParameters(alpha=0.0, beta=0.0, gamma=0.0),
            cashflow=pd.DataFrame(),
            irr=0.05,
            new_business_value=-1.0,
            premiums=premiums,
            pv_loading=0.0,
            pv_expense=0.0,
            loading_surplus=0.0,
            premium_total=0.0,
            premium_to_maturity_ratio=1.0,
        )
        summary = pd.DataFrame(
            [
                {
                    "model_point": "dummy",
                    "irr": 0.05,
                    "new_business_value": -1.0,
                    "loading_surplus": 0.0,
                    "premium_to_maturity_ratio": 1.0,
                    "sum_assured": 1000000,
                }
            ]
        )
        return ProfitTestBatchResult(
            results=[result],
            summary=summary,
            expense_assumptions=None,
        )

    monkeypatch.setattr(
        "pricing.optimize.run_profit_test",
        fake_run_profit_test,
    )

    result = optimize_loading_parameters(config, base_dir=REPO_ROOT)
    assert result.success is False
    assert any("nbv_hard" in item for item in result.failure_details)


def test_parameter_can_change_with_stage(monkeypatch) -> None:
    config = {
        "loading_parameters": {
            "a0": 0.0,
            "a_age": 0.0,
            "a_term": 0.0,
            "a_sex": 0.0,
            "b0": 0.0,
            "b_age": 0.0,
            "b_term": 0.0,
            "b_sex": 0.0,
            "g0": 0.0,
            "g_term": 0.0,
        },
        "optimization": {
            "irr_hard": 0.0,
            "irr_target": 0.1,
            "loading_surplus_hard": 0.0,
            "premium_to_maturity_hard_max": 2.0,
            "premium_to_maturity_target": 1.0,
            "stages": [{"name": "base", "variables": ["a0"]}],
            "bounds": {"a0": {"min": 0.0, "max": 0.2, "step": 0.1}},
            "l2_lambda": 0.0,
            "max_iterations_per_stage": 5,
        },
    }

    def fake_run_profit_test(_config, base_dir=None, loading_params=None):
        assert loading_params is not None
        irr = 0.05 + loading_params.a0
        point = ModelPoint(
            issue_age=30,
            sex="male",
            term_years=10,
            premium_paying_years=10,
            sum_assured=1000000,
        )
        premiums = EndowmentPremiums(
            A=0.0,
            a=1.0,
            net_rate=0.0,
            gross_rate=0.0,
            net_annual_premium=0,
            gross_annual_premium=0,
            monthly_premium=0,
        )
        result = ProfitTestResult(
            model_point=point,
            loadings=LoadingParameters(alpha=0.0, beta=0.0, gamma=0.0),
            cashflow=pd.DataFrame(),
            irr=irr,
            new_business_value=0.0,
            premiums=premiums,
            pv_loading=0.0,
            pv_expense=0.0,
            loading_surplus=1.0,
            premium_total=0.0,
            premium_to_maturity_ratio=1.0,
        )
        summary = pd.DataFrame(
            [
                {
                    "model_point": "dummy",
                    "irr": irr,
                    "new_business_value": 0.0,
                    "loading_surplus": 1.0,
                    "premium_to_maturity_ratio": 1.0,
                    "sum_assured": 1000000,
                }
            ]
        )
        return ProfitTestBatchResult(
            results=[result],
            summary=summary,
            expense_assumptions=None,
        )

    monkeypatch.setattr(
        "pricing.optimize.run_profit_test",
        fake_run_profit_test,
    )

    result = optimize_loading_parameters(config, base_dir=REPO_ROOT)
    assert result.params.a0 != 0.0
