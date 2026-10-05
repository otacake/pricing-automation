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

import pricing.pdca_cycle as cycle_mod
import pricing.profit_test as profit_test_mod
from pricing.endowment import LoadingFunctionParams
from pricing.optimize import OptimizationResult
from pricing.profit_test import ProfitTestBatchResult
from tests.data_paths import apply_fixture_inputs
from pricing.pdca_cycle import run_pdca_cycle


def _make_temp_config(tmp_path: Path) -> Path:
    source = REPO_ROOT / "configs" / "trial-001.synthetic.yaml"
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["model_points"] = config["model_points"][:1]
    apply_fixture_inputs(config)

    out_path = tmp_path / "trial-temp.yaml"
    out_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return out_path


def test_run_pdca_cycle_without_reports(tmp_path: Path) -> None:
    config_path = _make_temp_config(tmp_path)
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "gate": {"max_violation_count": 999},
                "feasibility": {"enabled": False},
                "reporting": {
                    "generate_markdown": False,
                    "generate_executive_pptx": False,
                    "report_language": "ja",
                    "chart_language": "en",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    outputs = run_pdca_cycle(config_path, policy_path=policy_path, skip_tests=True)
    assert outputs.manifest_path.exists()
    assert outputs.baseline_summary_path.exists()
    assert outputs.final_summary_path.exists()
    assert outputs.result_log_path.exists()
    assert outputs.result_excel_path.exists()
    assert outputs.feasibility_deck_path is None
    assert outputs.markdown_report_path is None
    assert outputs.executive_pptx_path is None

    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "success"
    assert "metrics" in manifest
    assert "baseline_violation_count" in manifest["metrics"]
    assert outputs.result_log_path.read_text(encoding="utf-8").startswith("profit_test")
    assert "cycle_status: success" in outputs.result_log_path.read_text(encoding="utf-8")


def _quiet_policy(tmp_path: Path, *, max_violation_count: int) -> Path:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "gate": {"max_violation_count": max_violation_count},
                "feasibility": {"enabled": False},
                "reporting": {
                    "generate_markdown": False,
                    "generate_executive_pptx": False,
                    "report_language": "ja",
                    "chart_language": "en",
                },
                "ledger": {"path": str(tmp_path / "pdca_ledger.jsonl")},
                "loop": {"max_iterations": 2, "random_seed": 11},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return policy_path


def _shift_irr(result: ProfitTestBatchResult, delta: float) -> ProfitTestBatchResult:
    shifted = [replace(item, irr=float(item.irr) + delta) for item in result.results]
    summary = result.summary.copy()
    summary["irr"] = summary["irr"] + delta
    return ProfitTestBatchResult(
        results=shifted,
        summary=summary,
        expense_assumptions=result.expense_assumptions,
    )


def _fake_optimize(config, base_dir=None, *, success: bool = False):
    batch = profit_test_mod.run_profit_test(config, base_dir=base_dir)
    params = LoadingFunctionParams(0.04, 0.0, 0.0, 0.0, 0.01, 0.0, 0.0, 0.0, 0.04, 0.0)
    hypotheses = ()
    if not success:
        hypotheses = (
            {
                "hypothesis_id": "surrender_charge_term_12",
                "change_class": "approval_required",
                "applied": False,
                "changes": [{"path": "profit_test.surrender_charge_term", "value": 12}],
                "reason": "not applied",
            },
        )
    return OptimizationResult(
        params=params,
        batch_result=batch,
        success=success,
        iterations=1,
        failure_details=[] if success else ["stub"],
        exempt_model_points=[],
        exemption_settings=None,
        watch_model_points=[],
        min_irr=float(batch.summary["irr"].min()),
        min_irr_model_point=str(batch.summary["model_point"].iloc[0]),
        approval_hypotheses=hypotheses,
    )


def test_cycle_rejects_regression_and_keeps_incumbent(tmp_path: Path, monkeypatch) -> None:
    config_path = _make_temp_config(tmp_path)
    policy_path = _quiet_policy(tmp_path, max_violation_count=-1)

    def wrapped(config, base_dir=None, loading_params=None):
        result = profit_test_mod.run_profit_test(
            config, base_dir=base_dir, loading_params=loading_params
        )
        if isinstance(config, dict) and "loading_parameters" in config:
            return _shift_irr(result, -1.0)
        return result

    monkeypatch.setattr(cycle_mod, "run_profit_test", wrapped)
    monkeypatch.setattr(
        cycle_mod,
        "optimize_loading_parameters",
        lambda config, base_dir=None: _fake_optimize(config, base_dir, success=False),
    )

    outputs = run_pdca_cycle(config_path, policy_path=policy_path, skip_tests=True)
    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    assert manifest["metrics"]["optimization_attempted"] is True
    assert manifest["metrics"]["optimization_adopted"] is False
    assert manifest["metrics"]["rejection_reason"] in {
        "violation_count_increased",
        "lexicographic_objective_worse",
    }
    assert manifest["metrics"]["final_violation_count"] == manifest["metrics"]["baseline_violation_count"]
    assert outputs.optimized_config_path is None

    evaluated = Path(manifest["outputs"]["evaluated_config_path"])
    written = yaml.safe_load(evaluated.read_text(encoding="utf-8"))
    assert written.get("profit_test", {}).get("surrender_charge_term") is None
    assert "irr_target" not in written.get("optimization", {}) or written["optimization"].get(
        "irr_target"
    ) == yaml.safe_load(config_path.read_text(encoding="utf-8")).get("optimization", {}).get(
        "irr_target"
    )

    rows = [
        json.loads(line)
        for line in (tmp_path / "pdca_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    decisions = {row["decision"] for row in rows}
    assert "rejected" in decisions
    assert "approval_required" in decisions
    assert all(row["applied"] is False for row in rows if row["decision"] == "approval_required")


def test_cycle_adopts_lexicographic_improvement(tmp_path: Path, monkeypatch) -> None:
    config_path = _make_temp_config(tmp_path)
    policy_path = _quiet_policy(tmp_path, max_violation_count=-1)

    def wrapped(config, base_dir=None, loading_params=None):
        result = profit_test_mod.run_profit_test(
            config, base_dir=base_dir, loading_params=loading_params
        )
        if isinstance(config, dict) and "loading_parameters" in config:
            return _shift_irr(result, 0.05)
        return result

    monkeypatch.setattr(cycle_mod, "run_profit_test", wrapped)
    monkeypatch.setattr(
        cycle_mod,
        "optimize_loading_parameters",
        lambda config, base_dir=None: _fake_optimize(config, base_dir, success=True),
    )
    outputs = run_pdca_cycle(config_path, policy_path=policy_path, skip_tests=True)
    manifest = json.loads(outputs.manifest_path.read_text(encoding="utf-8"))
    assert manifest["metrics"]["optimization_adopted"] is True
    assert outputs.optimized_config_path is not None
    rows = [
        json.loads(line)
        for line in (tmp_path / "pdca_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(row["decision"] == "accepted" for row in rows)


def test_failed_quality_gate_still_writes_manifest_and_log(tmp_path: Path, monkeypatch) -> None:
    config_path = _make_temp_config(tmp_path)
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "gate": {"max_violation_count": 999},
                "feasibility": {"enabled": False},
                "reporting": {
                    "generate_markdown": True,
                    "generate_executive_pptx": True,
                    "report_language": "ja",
                    "chart_language": "en",
                },
                "ledger": {"path": str(tmp_path / "pdca_ledger.jsonl")},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    def fail_report(*_args, **_kwargs):
        raise RuntimeError("PptxGenJS quality gate failed. failed_checks=[dual_alternative_integrity]")

    monkeypatch.setattr(cycle_mod, "report_executive_pptx_from_config", fail_report)
    with pytest.raises(RuntimeError, match="quality_gate") as caught:
        run_pdca_cycle(config_path, policy_path=policy_path, skip_tests=True)
    manifest_path = Path(str(caught.value).rsplit("manifest=", 1)[1])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["failure_class"] == "quality_gate"
    log_path = Path(manifest["outputs"]["result_log_path"])
    assert log_path.is_file()
    assert "cycle_status: failed" in log_path.read_text(encoding="utf-8")


def test_data_quality_failure_still_writes_manifest(tmp_path: Path) -> None:
    config = yaml.safe_load((REPO_ROOT / "configs" / "trial-001.synthetic.yaml").read_text(encoding="utf-8"))
    config["model_points"] = config["model_points"][:1]
    config["model_points"][0]["sum_assured"] = 0
    apply_fixture_inputs(config)
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    policy_path = _quiet_policy(tmp_path, max_violation_count=999)
    with pytest.raises(RuntimeError, match="data_missing") as caught:
        run_pdca_cycle(config_path, policy_path=policy_path, skip_tests=True)
    manifest_path = Path(str(caught.value).rsplit("manifest=", 1)[1])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["failure_class"] == "data_missing"
    assert Path(manifest["outputs"]["result_log_path"]).is_file()
