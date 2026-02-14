from __future__ import annotations

import sys
from pathlib import Path

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


def test_repo_policy_file_is_loadable() -> None:
    policy_path = REPO_ROOT / "policy" / "pricing_policy.yaml"
    policy = load_auto_cycle_policy(policy_path)
    assert policy.reporting.report_language in ("ja", "en")
    assert policy.reporting.chart_language in ("ja", "en")
