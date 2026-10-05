from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pricing.optimize as optimize_mod
from pricing.endowment import LoadingFunctionParams
from pricing.profit_test import ProfitTestBatchResult


def _batch() -> ProfitTestBatchResult:
    summary = pd.DataFrame(
        {
            "irr": [0.01],
            "loading_surplus": [10.0],
            "premium_to_maturity_ratio": [1.01],
        }
    )
    return ProfitTestBatchResult(results=[], summary=summary, expense_assumptions=None)


def _result(success: bool) -> optimize_mod.OptimizationResult:
    return optimize_mod.OptimizationResult(
        params=LoadingFunctionParams(
            a0=0.04,
            a_age=0.0,
            a_term=0.0,
            a_sex=0.0,
            b0=0.01,
            b_age=0.0,
            b_term=0.0,
            b_sex=0.0,
            g0=0.04,
            g_term=0.0,
        ),
        batch_result=_batch(),
        success=success,
        iterations=3,
        failure_details=[] if success else ["irr_hard"],
        exempt_model_points=[],
        exemption_settings=None,
        watch_model_points=[],
        min_irr=0.01,
        min_irr_model_point="mp",
    )


def test_failed_search_records_hypotheses_without_applying_them(tmp_path: Path, monkeypatch) -> None:
    calls = {"n": 0}

    def fake_once(config, base_dir):
        calls["n"] += 1
        assert config["profit_test"].get("surrender_charge_term", 10) == 10
        assert config["optimization"]["irr_target"] == 0.08
        return _result(success=False)

    monkeypatch.setattr(optimize_mod, "_optimize_once", fake_once)
    config = {
        "profit_test": {},
        "optimization": {"irr_target": 0.08},
    }
    result = optimize_mod.optimize_loading_parameters(config, base_dir=tmp_path)
    assert calls["n"] == 1
    assert result.proposal is None
    assert result.success is False
    assert result.approval_hypotheses
    assert {item["change_class"] for item in result.approval_hypotheses} == {"approval_required"}
    assert all(item["applied"] is False for item in result.approval_hypotheses)
    paths = {
        change["path"]
        for item in result.approval_hypotheses
        for change in item["changes"]
    }
    assert "profit_test.surrender_charge_term" in paths
    assert "optimization.irr_target" in paths

    output_path = tmp_path / "optimized.yaml"
    optimize_mod.write_optimized_config(config, result, output_path)
    written = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert "surrender_charge_term" not in written.get("profit_test", {})
    assert written["optimization"]["irr_target"] == 0.08
    assert written["loading_parameters"]["a0"] == 0.04


def test_feasible_search_has_no_relaxation_hypothesis(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(optimize_mod, "_optimize_once", lambda config, base_dir: _result(True))
    result = optimize_mod.optimize_loading_parameters({}, base_dir=tmp_path)
    assert result.approval_hypotheses == ()
    assert result.proposal is None
