from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.cli import optimize_from_config, run_from_config
from pricing.optimize import optimize_loading_parameters
from pricing.profit_test import run_profit_test


def test_optimize_generates_config_file(capsys) -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    optimized_path = REPO_ROOT / "configs" / "trial-001.optimized.yaml"

    if optimized_path.exists():
        optimized_path.unlink()

    optimize_from_config(config_path)
    capsys.readouterr()

    assert optimized_path.exists()
    optimized = yaml.safe_load(optimized_path.read_text(encoding="utf-8"))
    assert "loading_parameters" in optimized
    assert "a0" in optimized["loading_parameters"]


def test_run_outputs_loading_parameters(capsys) -> None:
    optimized_path = REPO_ROOT / "configs" / "trial-001.optimized.yaml"
    if not optimized_path.exists():
        optimize_from_config(REPO_ROOT / "configs" / "trial-001.yaml")
        capsys.readouterr()

    run_from_config(optimized_path)
    output = capsys.readouterr().out

    assert "loading_parameters" in output
    assert output.count("status=") == 8
    assert "loading_surplus_threshold=" in output
    assert "loading_surplus_ratio=" in output


def test_optimize_success_matches_run_constraints() -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    result = optimize_loading_parameters(config, base_dir=REPO_ROOT)
    if not result.success:
        pytest.skip("Optimization did not find a feasible solution.")

    optimized = copy.deepcopy(config)
    optimized["loading_parameters"] = {
        "a0": result.params.a0,
        "a_age": result.params.a_age,
        "a_term": result.params.a_term,
        "a_sex": result.params.a_sex,
        "b0": result.params.b0,
        "b_age": result.params.b_age,
        "b_term": result.params.b_term,
        "b_sex": result.params.b_sex,
        "g0": result.params.g0,
        "g_term": result.params.g_term,
    }

    batch = run_profit_test(optimized, base_dir=REPO_ROOT)
    constraints = optimized.get("constraints", {})
    expense_cfg = optimized.get("expense_sufficiency", {})
    irr_min = float(constraints.get("irr_min", 0.08))
    loading_min = float(expense_cfg.get("threshold", 0.0))

    assert all(res.irr >= irr_min for res in batch.results)
    assert all(res.loading_surplus >= loading_min for res in batch.results)
