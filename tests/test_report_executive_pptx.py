from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.report_executive_pptx import report_executive_pptx_from_config


def test_report_executive_pptx_generates_outputs(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    pytest.importorskip("pptx")

    config_path = REPO_ROOT / "configs" / "trial-001.executive.optimized.yaml"
    outputs = report_executive_pptx_from_config(
        config_path=config_path,
        out_path=tmp_path / "executive_pricing_deck.pptx",
        markdown_path=tmp_path / "feasibility_report.md",
        run_summary_path=tmp_path / "run_summary_executive.json",
        deck_out_path=tmp_path / "feasibility_deck_executive.yaml",
        chart_dir=tmp_path / "charts",
        r_start=1.0,
        r_end=1.01,
        r_step=0.01,
        irr_threshold=0.0,
        include_sensitivity=False,
        language="ja",
        chart_language="en",
    )

    assert outputs.pptx_path.exists()
    assert outputs.markdown_path.exists()
    assert outputs.run_summary_path.exists()
    assert outputs.feasibility_deck_path.exists()
    assert outputs.cashflow_chart_path.exists()
    assert outputs.premium_chart_path.exists()

    markdown = outputs.markdown_path.read_text(encoding="utf-8")
    assert "価格提案（モデルポイント別P）" in markdown
    assert "モデルポイント別 alpha/beta/gamma 計算" in markdown
