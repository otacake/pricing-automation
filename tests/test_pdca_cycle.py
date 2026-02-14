from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.pdca_cycle import run_pdca_cycle


def _make_temp_config(tmp_path: Path) -> Path:
    source = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["model_points"] = config["model_points"][:1]

    config["pricing"]["mortality_path"] = str((REPO_ROOT / "data" / "mortality_pricing.csv").resolve())
    config["profit_test"]["mortality_actual_path"] = str(
        (REPO_ROOT / "data" / "mortality_actual.csv").resolve()
    )
    config["profit_test"]["discount_curve_path"] = str(
        (REPO_ROOT / "data" / "spot_curve_actual.csv").resolve()
    )
    expense_cfg = config.get("profit_test", {}).get("expense_model", {})
    if isinstance(expense_cfg, dict) and "company_data_path" in expense_cfg:
        expense_cfg["company_data_path"] = str((REPO_ROOT / "data" / "company_expense.csv").resolve())

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
    assert "metrics" in manifest
    assert "baseline_violation_count" in manifest["metrics"]
