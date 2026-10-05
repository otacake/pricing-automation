from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tests.data_paths import apply_fixture_inputs
from pricing.diagnostics import build_execution_context
from pricing.reporting.alternatives import build_decision_alternatives


def _small_config() -> dict:
    source = REPO_ROOT / "configs" / "trial-001.synthetic.yaml"
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["model_points"] = config["model_points"][:1]
    apply_fixture_inputs(config)

    optimization = config.setdefault("optimization", {})
    optimization["max_iterations_per_stage"] = 3
    optimization["stages"] = [{"name": "base", "variables": ["a0", "b0", "g0"]}]
    optimization.setdefault("objective", {})["mode"] = "penalty"
    return config


def test_build_decision_alternatives_uses_distinct_objectives() -> None:
    config = _small_config()
    ctx = build_execution_context(
        config=config,
        base_dir=REPO_ROOT,
        config_path=REPO_ROOT / "configs" / "trial-001.yaml",
        command="test",
        argv=[],
    )
    rec, ctr = build_decision_alternatives(
        config=config,
        base_dir=REPO_ROOT,
        execution_context=ctx,
        counter_objective="maximize_min_irr",
        include_sensitivity=False,
        language="ja",
    )
    assert rec.objective_mode == "penalty"
    assert ctr.objective_mode == "maximize_min_irr"
    assert rec.alternative_id == "recommended"
    assert ctr.alternative_id == "counter"
