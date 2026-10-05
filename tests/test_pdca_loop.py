from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pricing.pdca_loop as loop_mod
import pricing.profit_test as profit_test_mod
from pricing.endowment import LoadingFunctionParams
from pricing.optimize import OptimizationResult
from pricing.pdca_loop import run_pdca_loop
from pricing.profit_test import ProfitTestBatchResult
from tests.data_paths import apply_fixture_inputs


def _config_path(tmp_path: Path) -> Path:
    config = yaml.safe_load(
        (REPO_ROOT / "configs" / "trial-001.synthetic.yaml").read_text(encoding="utf-8")
    )
    config["model_points"] = config["model_points"][:1]
    apply_fixture_inputs(config)
    path = tmp_path / "synthetic.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _policy_path(tmp_path: Path) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "loop": {"max_iterations": 3, "random_seed": 20261005},
                "ledger": {"path": str(tmp_path / "pdca_ledger.jsonl")},
                "acceptance": {"objective": "maximize_min_irr", "tie_break": "lower_premium"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _shift_irr(result: ProfitTestBatchResult, delta: float) -> ProfitTestBatchResult:
    shifted = [replace(item, irr=float(item.irr) + delta) for item in result.results]
    summary = result.summary.copy()
    summary["irr"] = summary["irr"] + delta
    return ProfitTestBatchResult(
        results=shifted,
        summary=summary,
        expense_assumptions=result.expense_assumptions,
    )


def _install_fakes(monkeypatch, *, candidate_delta):
    calls = {"n": 0}

    def wrapped(config, base_dir=None, loading_params=None):
        calls["n"] += 1
        result = profit_test_mod.run_profit_test(
            config, base_dir=base_dir, loading_params=loading_params
        )
        delta = candidate_delta(calls["n"])
        if delta == 0.0:
            return result
        return _shift_irr(result, delta)

    def fake_optimize(config, base_dir=None):
        batch = profit_test_mod.run_profit_test(config, base_dir=base_dir)
        return OptimizationResult(
            params=LoadingFunctionParams(0.05, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.04, 0.0),
            batch_result=batch,
            success=False,
            iterations=1,
            failure_details=["stub"],
            exempt_model_points=[],
            exemption_settings=None,
            watch_model_points=[],
            min_irr=float(batch.summary["irr"].min()),
            min_irr_model_point="mp",
            approval_hypotheses=(
                {
                    "hypothesis_id": "irr_target_lower_1pp",
                    "change_class": "approval_required",
                    "applied": False,
                    "changes": [{"path": "optimization.irr_target", "value": 0.07}],
                    "reason": "not applied",
                },
            ),
        )

    monkeypatch.setattr(loop_mod, "run_profit_test", wrapped)
    monkeypatch.setattr(loop_mod, "optimize_loading_parameters", fake_optimize)
    return calls


def _ledger(tmp_path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (tmp_path / "pdca_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_loop_stops_when_candidate_does_not_improve(tmp_path: Path, monkeypatch) -> None:
    def delta(call_n: int) -> float:
        if call_n == 2:
            return 0.04
        return 0.0

    _install_fakes(monkeypatch, candidate_delta=delta)
    outputs = run_pdca_loop(
        _config_path(tmp_path),
        policy_path=_policy_path(tmp_path),
        max_iterations=3,
    )
    assert outputs.status == "success"
    assert outputs.stop_reason == "no_improvement"
    assert outputs.iterations_run == 2
    assert outputs.manifest_path.is_file()
    assert outputs.result_log_path.is_file()
    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    assert manifest["seed"] == 20261005
    assert manifest["config"]["sha256"]
    assert any(step.get("step") == "pdca_loop" for step in manifest["commands"])
    text = outputs.result_log_path.read_text(encoding="utf-8")
    assert "seed:" in text
    assert "stop_reason: no_improvement" in text
    rows = _ledger(tmp_path)
    decisions = [row["decision"] for row in rows]
    assert "accepted" in decisions
    assert "rejected" in decisions
    assert "approval_required" in decisions
    assert all(row["applied"] is False for row in rows if row["decision"] == "approval_required")


def test_loop_stops_at_max_iterations(tmp_path: Path, monkeypatch) -> None:
    _install_fakes(monkeypatch, candidate_delta=lambda call_n: 0.0 if call_n == 1 else 0.01 * call_n)
    outputs = run_pdca_loop(
        _config_path(tmp_path),
        policy_path=_policy_path(tmp_path),
        max_iterations=2,
    )
    assert outputs.stop_reason == "max_iterations"
    assert outputs.iterations_run == 2
    accepted = [row for row in _ledger(tmp_path) if row["decision"] == "accepted"]
    assert len(accepted) == 2


def test_loop_failure_still_writes_manifest_and_log(tmp_path: Path) -> None:
    config = yaml.safe_load(
        (REPO_ROOT / "configs" / "trial-001.synthetic.yaml").read_text(encoding="utf-8")
    )
    config["model_points"][0]["sum_assured"] = 0
    apply_fixture_inputs(config)
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="data_missing") as caught:
        run_pdca_loop(config_path, policy_path=_policy_path(tmp_path), max_iterations=1)
    manifest_path = Path(str(caught.value).rsplit("manifest=", 1)[1])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["failure_class"] == "data_missing"
    assert Path(manifest["outputs"]["result_log_path"]).is_file()
    assert manifest["seed"] == 20261005
