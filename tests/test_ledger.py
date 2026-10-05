from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.ledger import input_config_sha256, stable_config_sha256


def _base_config() -> dict:
    return {
        "loading_parameters": {"a0": 0.03, "b0": 0.007, "g0": 0.03},
        "pricing": {"interest": {"type": "flat", "flat_rate": 0.01}},
        "optimization": {"irr_target": 0.08},
        "product": {"sum_assured": 1000000},
    }


def test_input_config_sha256_ignores_only_optimize_summary() -> None:
    base = _base_config()
    with_summary = copy.deepcopy(base)
    with_summary["optimize_summary"] = {"min_irr": 0.02, "success": False}
    reordered = {
        "product": {"sum_assured": 1000000},
        "optimization": {"irr_target": 0.08},
        "pricing": {"interest": {"flat_rate": 0.01, "type": "flat"}},
        "loading_parameters": {"g0": 0.03, "a0": 0.03, "b0": 0.007},
        "optimize_summary": {"success": True, "min_irr": 9.0},
    }
    digest = input_config_sha256(base)
    assert input_config_sha256(with_summary) == digest
    assert input_config_sha256(reordered) == digest
    assert with_summary["optimize_summary"] == {"min_irr": 0.02, "success": False}
    assert stable_config_sha256(with_summary) != stable_config_sha256(base)
    assert stable_config_sha256(with_summary) != digest


def test_input_config_sha256_changes_with_pricing_inputs() -> None:
    base = _base_config()
    digest = input_config_sha256(base)

    changed_loading = copy.deepcopy(base)
    changed_loading["loading_parameters"]["a0"] = 0.05
    assert input_config_sha256(changed_loading) != digest

    changed_interest = copy.deepcopy(base)
    changed_interest["pricing"]["interest"]["flat_rate"] = 0.02
    assert input_config_sha256(changed_interest) != digest

    changed_constraint = copy.deepcopy(base)
    changed_constraint["optimization"]["irr_target"] = 0.07
    assert input_config_sha256(changed_constraint) != digest

    changed_product = copy.deepcopy(base)
    changed_product["product"]["sum_assured"] = 2000000
    assert input_config_sha256(changed_product) != digest
    assert base["loading_parameters"]["a0"] == 0.03
