from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.report_feasibility import build_feasibility_report, report_feasibility_from_config


def test_report_feasibility_writes_yaml(tmp_path: Path) -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    out_path = tmp_path / "feasibility_deck.yaml"

    result_path = report_feasibility_from_config(
        config_path=config_path,
        r_start=1.0,
        r_end=1.02,
        r_step=0.01,
        irr_threshold=0.0,
        out_path=out_path,
    )

    assert result_path == out_path
    assert out_path.exists()

    raw = out_path.read_text(encoding="utf-8")
    assert "{{" not in raw
    assert "TODO" not in raw
    assert "TBD" not in raw

    deck = yaml.safe_load(raw)
    assert "meta" in deck
    assert "kpi_summary" in deck
    assert "slides" in deck
    assert isinstance(deck["kpi_summary"]["min_irr"], (int, float))
    assert isinstance(deck["kpi_summary"]["max_premium_to_maturity"], (int, float))
    assert len(deck["slides"]) >= 3


def test_report_feasibility_sweep_row_count() -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["model_points"] = config["model_points"][:2]

    deck = build_feasibility_report(
        config=config,
        base_dir=REPO_ROOT,
        r_start=1.0,
        r_end=1.02,
        r_step=0.01,
        irr_threshold=0.0,
        config_path=config_path,
    )

    sweep_rows = deck["tables"]["sweep"]
    assert len(sweep_rows) == 6


def test_report_feasibility_supports_loading_parameters_only() -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.optimized.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config.pop("loading_alpha_beta_gamma", None)
    config["model_points"] = config["model_points"][:2]

    deck = build_feasibility_report(
        config=config,
        base_dir=REPO_ROOT,
        r_start=1.0,
        r_end=1.0,
        r_step=0.01,
        irr_threshold=0.0,
        config_path=config_path,
    )

    assert deck["meta"]["assumptions"]["loading"]["mode"] == "loading_parameters"
    assert len(deck["tables"]["sweep"]) == 2
