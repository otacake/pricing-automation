from __future__ import annotations

import shutil
import sys
from pathlib import Path
import json

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.report_executive_pptx import report_executive_pptx_from_config
import pricing.report_executive_pptx as executive_pptx


def _pptxgenjs_ready() -> bool:
    if shutil.which("node") is None:
        return False
    return (REPO_ROOT / "tools" / "exec_deck_hybrid" / "node_modules" / "pptxgenjs").exists()


def test_require_node_runtime_reports_backend_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executive_pptx.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="PptxGenJS backend"):
        executive_pptx._require_node_runtime()


def test_report_executive_pptx_generates_outputs_with_pptxgenjs_backend(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    if not _pptxgenjs_ready():
        pytest.skip("PptxGenJS dependencies are not installed.")

    config_path = REPO_ROOT / "configs" / "trial-001.executive.optimized.yaml"
    outputs = report_executive_pptx_from_config(
        config_path=config_path,
        out_path=tmp_path / "executive_pricing_deck_hybrid.pptx",
        markdown_path=tmp_path / "feasibility_report_hybrid.md",
        run_summary_path=tmp_path / "run_summary_executive_hybrid.json",
        deck_out_path=tmp_path / "feasibility_deck_executive_hybrid.yaml",
        chart_dir=tmp_path / "charts_hybrid",
        spec_out_path=tmp_path / "executive_deck_spec.json",
        preview_html_path=tmp_path / "executive_preview.html",
        quality_out_path=tmp_path / "executive_quality.json",
        r_start=1.0,
        r_end=1.01,
        r_step=0.01,
        irr_threshold=0.0,
        include_sensitivity=False,
        language="ja",
        chart_language="en",
        strict_quality=True,
        decision_compare="off",
    )

    assert outputs.pptx_path.exists()
    assert outputs.markdown_path.exists()
    assert outputs.run_summary_path.exists()
    assert outputs.feasibility_deck_path.exists()
    assert outputs.cashflow_chart_path.exists()
    assert outputs.premium_chart_path.exists()
    assert outputs.spec_path is not None and outputs.spec_path.exists()
    assert outputs.preview_html_path is not None and outputs.preview_html_path.exists()
    assert outputs.quality_path is not None and outputs.quality_path.exists()
    assert outputs.explainability_path is not None and outputs.explainability_path.exists()
    assert outputs.decision_compare_path is not None and outputs.decision_compare_path.exists()

    spec = json.loads(outputs.spec_path.read_text(encoding="utf-8"))
    assert "management_narrative" in spec
    assert "main_slide_checks" in spec
    assert spec["main_slide_checks"]["coverage"] >= 1.0

    quality = json.loads(outputs.quality_path.read_text(encoding="utf-8"))
    assert "main_compare_present" in quality
    assert "main_narrative_coverage" in quality
    assert "main_narrative_density_ok" in quality
    assert "decision_style_ok" in quality
