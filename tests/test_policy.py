from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.policy import load_auto_cycle_policy


def test_load_auto_cycle_policy_defaults(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        yaml.safe_dump({}, sort_keys=False),
        encoding="utf-8",
    )

    policy = load_auto_cycle_policy(policy_path)
    assert policy.gate.max_violation_count == 0
    assert policy.feasibility.enabled is True
    assert policy.reporting.report_language == "ja"
    assert policy.reporting.chart_language == "en"
    assert policy.reporting.pptx_theme == "consulting-clean-v2"
    assert policy.reporting.style_contract_path == "docs/deck_style_contract.md"
    assert policy.reporting.strict_quality_gate is True
    assert policy.reporting.decision_compare.enabled is True
    assert policy.reporting.decision_compare.counter_objective == "maximize_min_irr"
    assert policy.reporting.explainability.strict_gate is True
    assert policy.reporting.explainability.procon_quant_count == 3
    assert policy.reporting.explainability.procon_qual_count == 3
    assert policy.reporting.explainability.require_causal_bridge is True
    assert policy.reporting.explainability.require_sensitivity_decomp is True


def test_repo_policy_file_is_loadable() -> None:
    policy_path = REPO_ROOT / "policy" / "pricing_policy.yaml"
    policy = load_auto_cycle_policy(policy_path)
    assert policy.reporting.report_language in ("ja", "en")
    assert policy.reporting.chart_language in ("ja", "en")
    assert policy.reporting.pptx_theme == "consulting-clean-v2"
    assert policy.reporting.decision_compare.counter_objective


def test_load_auto_cycle_policy_rejects_legacy_engine(tmp_path: Path) -> None:
    policy_payload = {
        "reporting": {
            "pptx_engine": "legacy",
        }
    }
    policy_path = tmp_path / "policy_legacy.yaml"
    policy_path.write_text(yaml.safe_dump(policy_payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="legacy"):
        load_auto_cycle_policy(policy_path)


def test_load_auto_cycle_policy_accepts_html_hybrid_as_legacy_alias(tmp_path: Path) -> None:
    policy_payload = {
        "reporting": {
            "pptx_engine": "html_hybrid",
            "pptx_theme": "consulting-clean",
        }
    }
    policy_path = tmp_path / "policy_html_hybrid.yaml"
    policy_path.write_text(yaml.safe_dump(policy_payload, sort_keys=False), encoding="utf-8")

    policy = load_auto_cycle_policy(policy_path)
    assert policy.reporting.pptx_theme == "consulting-clean-v2"
