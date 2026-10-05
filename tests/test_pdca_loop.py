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
from pricing.acceptance import LexMetrics
from pricing.cli import pdca_loop_from_config
from pricing.endowment import LoadingFunctionParams
from pricing.ledger import input_config_sha256, stable_config_sha256
from pricing.optimize import OptimizationResult
from pricing.pdca_loop import record_token, run_pdca_loop
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


def _policy_path(
    tmp_path: Path,
    *,
    max_violation_count: int = 0,
    max_iterations: int = 3,
) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "gate": {"max_violation_count": max_violation_count},
                "loop": {"max_iterations": max_iterations, "random_seed": 20261005},
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


def _outcome(rows: list[dict]) -> dict:
    found = [row for row in rows if row.get("record_type") == "loop_outcome"]
    assert len(found) == 1
    return found[0]


def _script_metrics(monkeypatch, values: list[LexMetrics]) -> None:
    pending = list(values)

    def fake(_summary):
        if not pending:
            raise AssertionError("metrics_from_run_summary was called more times than scripted.")
        return pending.pop(0)

    monkeypatch.setattr(loop_mod, "metrics_from_run_summary", fake)


def _assert_same_stop_reason(outputs, stop_reason: str, tmp_path: Path) -> None:
    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    text = outputs.result_log_path.read_text(encoding="utf-8")
    outcome = _outcome(_ledger(tmp_path))
    assert outputs.stop_reason == stop_reason
    assert manifest["stop_reason"] == stop_reason
    assert outcome["stop_reason"] == stop_reason
    assert f"stop_reason: {stop_reason}" in text


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
    assert outputs.stop_reason == "lexicographic_objective_worse"
    assert outputs.iterations_run == 2
    assert outputs.manifest_path.is_file()
    assert outputs.result_log_path.is_file()
    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    assert manifest["seed"] == 20261005
    assert manifest["config"]["sha256"]
    assert any(step.get("step") == "pdca_loop" for step in manifest["commands"])
    text = outputs.result_log_path.read_text(encoding="utf-8")
    assert "seed:" in text
    assert "success does not mean the gate passed" in text
    assert "stop_reason: lexicographic_objective_worse" in text
    assert outputs.gate_passed is (
        outputs.final_violation_count <= outputs.gate_max_violation_count
    )
    assert manifest["gate_passed"] is outputs.gate_passed
    assert manifest["final_violation_count"] == outputs.final_violation_count
    assert manifest["gate_max_violation_count"] == 0
    assert manifest["status_meaning"] == (
        "status is the execution outcome; success does not mean the gate passed"
    )
    rows = _ledger(tmp_path)
    assert _outcome(rows)["stop_reason"] == "lexicographic_objective_worse"
    rejected = [row for row in rows if row["decision"] == "rejected"]
    assert rejected[-1]["stop_reason"] == "lexicographic_objective_worse"
    assert rejected[-1]["reason"] == "lexicographic_objective_worse"
    assert rejected[-1]["applied"] is False
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
    assert outputs.status == "success"
    _assert_same_stop_reason(outputs, "max_iterations", tmp_path)
    rows = _ledger(tmp_path)
    accepted = [row for row in rows if row["decision"] == "accepted"]
    assert len(accepted) == 2
    assert all(row["stop_reason"] is None for row in accepted)


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
    assert manifest["stop_reason"] == "failed"
    assert manifest["gate_passed"] is None
    assert manifest["final_violation_count"] is None
    assert manifest["gate_max_violation_count"] == 0
    assert manifest["gate_passed"] is not True
    log_text = Path(manifest["outputs"]["result_log_path"]).read_text(encoding="utf-8")
    assert "stop_reason: failed" in log_text
    assert "gate_passed: null" in log_text
    assert "final_violation_count: null" in log_text
    assert "success does not mean the gate passed" in log_text
    assert Path(manifest["outputs"]["result_log_path"]).is_file()
    assert manifest["seed"] == 20261005
    assert _outcome(_ledger(tmp_path))["stop_reason"] == "failed"


@pytest.mark.parametrize(
    ("reason", "incumbent", "candidate"),
    [
        ("no_improvement", LexMetrics(1, 0.03, 100.0), LexMetrics(1, 0.03, 100.0)),
        (
            "lexicographic_objective_worse",
            LexMetrics(1, 0.05, 100.0),
            LexMetrics(1, 0.04, 90.0),
        ),
        (
            "violation_count_increased",
            LexMetrics(0, 0.02, 100.0),
            LexMetrics(2, 0.20, 10.0),
        ),
        (
            "non_finite_metrics",
            LexMetrics(2, 0.05, 100.0),
            LexMetrics(0, float("nan"), 10.0),
        ),
    ],
)
def test_rejection_reason_is_the_stop_reason(
    tmp_path: Path,
    monkeypatch,
    reason: str,
    incumbent: LexMetrics,
    candidate: LexMetrics,
) -> None:
    _install_fakes(monkeypatch, candidate_delta=lambda _call: 0.0)
    _script_metrics(monkeypatch, [incumbent, candidate])
    outputs = run_pdca_loop(
        _config_path(tmp_path),
        policy_path=_policy_path(tmp_path, max_violation_count=0),
        max_iterations=3,
    )
    assert outputs.status == "success"
    assert outputs.iterations_run == 1
    _assert_same_stop_reason(outputs, reason, tmp_path)
    rows = _ledger(tmp_path)
    trial = [row for row in rows if row.get("candidate_id") == "optimize_loading_1"]
    assert trial[0]["decision"] == "rejected"
    assert trial[0]["reason"] == reason
    assert trial[0]["stop_reason"] == reason
    assert trial[0]["applied"] is False
    assert _outcome(rows)["stop_reason"] == reason


def test_gate_passed_when_final_count_meets_threshold(tmp_path: Path, monkeypatch) -> None:
    _install_fakes(monkeypatch, candidate_delta=lambda _call: 0.0)
    _script_metrics(
        monkeypatch,
        [LexMetrics(0, 0.04, 100.0), LexMetrics(0, 0.03, 100.0)],
    )
    outputs = run_pdca_loop(
        _config_path(tmp_path),
        policy_path=_policy_path(tmp_path, max_violation_count=0),
        max_iterations=2,
    )
    assert outputs.status == "success"
    assert outputs.gate_passed is True
    assert outputs.final_violation_count == 0
    assert outputs.gate_max_violation_count == 0
    assert outputs.stop_reason == "lexicographic_objective_worse"
    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    text = outputs.result_log_path.read_text(encoding="utf-8")
    assert manifest["gate_passed"] is True
    assert manifest["final_violation_count"] == 0
    assert "gate_passed: true" in text
    assert "final_violation_count: 0" in text


def test_gate_failure_stays_success_and_keeps_exit_code(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_fakes(monkeypatch, candidate_delta=lambda _call: 0.0)
    _script_metrics(
        monkeypatch,
        [LexMetrics(4, 0.05, 100.0), LexMetrics(4, 0.04, 100.0)],
    )
    config_path = _config_path(tmp_path)
    policy_path = _policy_path(tmp_path, max_violation_count=0)
    code = pdca_loop_from_config(config_path, policy_path=policy_path, max_iterations=3)
    captured = capsys.readouterr().out
    assert code == 0
    assert "status: success" in captured
    assert "success does not mean the gate passed" in captured
    assert "gate_passed: false" in captured
    assert "final_violation_count: 4" in captured
    assert "gate_max_violation_count: 0" in captured
    assert "stop_reason: lexicographic_objective_worse" in captured
    rows = _ledger(tmp_path)
    assert _outcome(rows)["gate_passed"] is False
    assert _outcome(rows)["stop_reason"] == "lexicographic_objective_worse"


def test_passed_gate_does_not_stop_the_search(tmp_path: Path, monkeypatch) -> None:
    _install_fakes(monkeypatch, candidate_delta=lambda _call: 0.0)
    _script_metrics(
        monkeypatch,
        [
            LexMetrics(0, 0.01, 100.0),
            LexMetrics(0, 0.02, 90.0),
            LexMetrics(0, 0.03, 80.0),
        ],
    )
    outputs = run_pdca_loop(
        _config_path(tmp_path),
        policy_path=_policy_path(tmp_path, max_violation_count=0),
        max_iterations=2,
    )
    assert outputs.status == "success"
    assert outputs.gate_passed is True
    assert outputs.iterations_run == 2
    assert outputs.stop_reason == "max_iterations"
    _assert_same_stop_reason(outputs, "max_iterations", tmp_path)


def test_optimizer_exception_stop_reason_is_failed(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("optimizer exploded")

    monkeypatch.setattr(loop_mod, "optimize_loading_parameters", boom)
    with pytest.raises(RuntimeError, match="cycle_error") as caught:
        run_pdca_loop(
            _config_path(tmp_path),
            policy_path=_policy_path(tmp_path, max_violation_count=0),
            max_iterations=2,
        )
    captured = capsys.readouterr().out
    manifest_path = Path(str(caught.value).rsplit("manifest=", 1)[1])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["stop_reason"] == "failed"
    assert isinstance(manifest["gate_passed"], bool)
    assert manifest["final_violation_count"] is not None
    assert "stop_reason: failed" in captured
    assert "success does not mean the gate passed" in captured
    assert _outcome(_ledger(tmp_path))["stop_reason"] == "failed"


def test_data_failure_command_output_keeps_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = yaml.safe_load(
        (REPO_ROOT / "configs" / "trial-001.synthetic.yaml").read_text(encoding="utf-8")
    )
    config["model_points"][0]["sum_assured"] = 0
    apply_fixture_inputs(config)
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    code = pdca_loop_from_config(
        config_path,
        policy_path=_policy_path(tmp_path),
        max_iterations=1,
    )
    captured = capsys.readouterr().out
    assert code == 1
    assert "stop_reason: failed" in captured
    assert "gate_passed: null" in captured
    assert "success does not mean the gate passed" in captured


def _assert_recorded_gate(
    *,
    manifest: dict,
    log_text: str,
    outcome: dict,
    captured: str,
    gate_passed: bool | None,
    final_violation_count: int | None,
    stop_reason: str,
) -> None:
    gate_token = record_token(gate_passed)
    count_token = record_token(final_violation_count)
    assert manifest["status"] == "failed"
    assert manifest["stop_reason"] == stop_reason
    assert manifest["gate_passed"] is gate_passed
    assert manifest["final_violation_count"] is final_violation_count
    assert outcome["stop_reason"] == stop_reason
    assert outcome["gate_passed"] is gate_passed
    assert outcome["final_violation_count"] is final_violation_count
    for text in (log_text, captured):
        assert f"stop_reason: {stop_reason}" in text
        assert f"gate_passed: {gate_token}" in text
        assert f"final_violation_count: {count_token}" in text


@pytest.mark.parametrize(
    ("min_irr", "premium"),
    [
        (float("nan"), 100.0),
        (0.05, float("inf")),
        (float("-inf"), 100.0),
    ],
)
def test_non_finite_initial_incumbent_leaves_gate_unevaluated(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
    min_irr: float,
    premium: float,
) -> None:
    _script_metrics(monkeypatch, [LexMetrics(0, min_irr, premium)])
    code = pdca_loop_from_config(
        _config_path(tmp_path),
        policy_path=_policy_path(tmp_path, max_violation_count=0),
        max_iterations=2,
    )
    captured = capsys.readouterr().out
    assert code == 1
    manifest_path = Path(captured.rsplit("manifest=", 1)[1].strip())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    log_text = Path(manifest["outputs"]["result_log_path"]).read_text(encoding="utf-8")
    _assert_recorded_gate(
        manifest=manifest,
        log_text=log_text,
        outcome=_outcome(_ledger(tmp_path)),
        captured=captured,
        gate_passed=None,
        final_violation_count=None,
        stop_reason="failed",
    )
    assert manifest["failed_stage"] == "incumbent_run"
    assert manifest["champion_metrics"] == {}
    assert manifest["iterations_run"] == 0
    assert manifest["gate_max_violation_count"] == 0


def test_optimize_failure_keeps_valid_incumbent_gate(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("optimizer exploded")

    _script_metrics(monkeypatch, [LexMetrics(0, 0.05, 100.0)])
    monkeypatch.setattr(loop_mod, "optimize_loading_parameters", boom)
    code = pdca_loop_from_config(
        _config_path(tmp_path),
        policy_path=_policy_path(tmp_path, max_violation_count=0),
        max_iterations=2,
    )
    captured = capsys.readouterr().out
    assert code == 1
    manifest_path = Path(captured.rsplit("manifest=", 1)[1].strip())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    log_text = Path(manifest["outputs"]["result_log_path"]).read_text(encoding="utf-8")
    _assert_recorded_gate(
        manifest=manifest,
        log_text=log_text,
        outcome=_outcome(_ledger(tmp_path)),
        captured=captured,
        gate_passed=True,
        final_violation_count=0,
        stop_reason="failed",
    )
    assert manifest["failed_stage"] == "optimize_1"
    assert manifest["champion_metrics"]["violation_count"] == 0
    assert manifest["champion_metrics"]["min_irr"] == 0.05
    assert manifest["champion_metrics"]["premium"] == 100.0
    assert manifest["gate_passed"] is not None


def test_loop_records_separate_input_config_hash(tmp_path: Path, monkeypatch) -> None:
    _install_fakes(monkeypatch, candidate_delta=lambda _call: 0.0)
    _script_metrics(
        monkeypatch,
        [LexMetrics(1, 0.05, 100.0), LexMetrics(1, 0.05, 100.0)],
    )
    outputs = run_pdca_loop(
        _config_path(tmp_path),
        policy_path=_policy_path(tmp_path),
        max_iterations=1,
    )
    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    loop_dir = Path(manifest["outputs"]["loop_dir"])
    candidate = yaml.safe_load((loop_dir / "iter_1" / "candidate.yaml").read_text(encoding="utf-8"))
    incumbent = yaml.safe_load((loop_dir / "champion_initial.yaml").read_text(encoding="utf-8"))
    original_summary = dict(candidate["optimize_summary"])
    rows = _ledger(tmp_path)
    trial = [row for row in rows if row.get("candidate_id") == "optimize_loading_1"][0]
    approval = [row for row in rows if row["decision"] == "approval_required"][0]
    assert trial["config_sha256"] == stable_config_sha256(candidate)
    assert trial["input_config_sha256"] == input_config_sha256(candidate)
    assert trial["incumbent_input_config_sha256"] == input_config_sha256(incumbent)
    assert trial["config_sha256"] != trial["input_config_sha256"]
    assert "optimize_summary" in trial["input_config_sha256_covers"]
    assert approval["config_sha256"] == stable_config_sha256(incumbent)
    assert approval["input_config_sha256"] == input_config_sha256(incumbent)
    assert manifest["config"]["sha256"]
    assert manifest["champion_config_sha256"] == stable_config_sha256(incumbent)
    assert manifest["input_config_sha256"] == input_config_sha256(incumbent)
    assert manifest["input_config_sha256_covers"] == trial["input_config_sha256_covers"]
    assert candidate["optimize_summary"] == original_summary
