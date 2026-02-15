from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_ROOT) if not existing else f"{SRC_ROOT}{os.pathsep}{existing}"
    return subprocess.run(
        [sys.executable, "-m", "pricing.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _pptxgenjs_ready() -> bool:
    if shutil.which("node") is None:
        return False
    return (REPO_ROOT / "tools" / "exec_deck_hybrid" / "node_modules" / "pptxgenjs").exists()


def test_cli_report_feasibility_writes_output(tmp_path: Path) -> None:
    out_path = tmp_path / "feasibility_cli.yaml"
    completed = _run_cli(
        [
            "report-feasibility",
            "configs/trial-001.yaml",
            "--r-start",
            "1.0",
            "--r-end",
            "1.0",
            "--r-step",
            "0.01",
            "--irr-threshold",
            "0.0",
            "--out",
            str(out_path),
        ]
    )

    assert completed.returncode == 0, completed.stderr
    assert out_path.exists()


def test_cli_report_executive_pptx_writes_outputs(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    if not _pptxgenjs_ready():
        pytest.skip("PptxGenJS backend dependencies are not installed.")

    deck_path = tmp_path / "executive.pptx"
    md_path = tmp_path / "feasibility.md"
    run_summary_path = tmp_path / "run_summary.json"
    feasibility_path = tmp_path / "feasibility.yaml"
    chart_dir = tmp_path / "charts"
    explain_path = tmp_path / "explainability.json"
    compare_path = tmp_path / "decision_compare.json"

    completed = _run_cli(
        [
            "report-executive-pptx",
            "configs/trial-001.executive.optimized.yaml",
            "--out",
            str(deck_path),
            "--md-out",
            str(md_path),
            "--run-summary-out",
            str(run_summary_path),
            "--deck-out",
            str(feasibility_path),
            "--chart-dir",
            str(chart_dir),
            "--r-start",
            "1.0",
            "--r-end",
            "1.0",
            "--r-step",
            "0.01",
            "--irr-threshold",
            "0.0",
            "--lang",
            "ja",
            "--chart-lang",
            "en",
            "--decision-compare",
            "off",
            "--explain-out",
            str(explain_path),
            "--compare-out",
            str(compare_path),
        ]
    )

    assert completed.returncode == 0, completed.stderr
    assert deck_path.exists()
    assert md_path.exists()
    assert run_summary_path.exists()
    assert feasibility_path.exists()
    assert explain_path.exists()
    assert compare_path.exists()
    assert (chart_dir / "cashflow_by_profit_source.png").exists()
    assert (chart_dir / "annual_premium_by_model_point.png").exists()


def test_cli_report_executive_pptx_writes_outputs_with_spec_and_quality(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    if not _pptxgenjs_ready():
        pytest.skip("PptxGenJS dependencies are not installed.")

    deck_path = tmp_path / "executive_hybrid.pptx"
    md_path = tmp_path / "feasibility_hybrid.md"
    run_summary_path = tmp_path / "run_summary_hybrid.json"
    feasibility_path = tmp_path / "feasibility_hybrid.yaml"
    chart_dir = tmp_path / "charts_hybrid"
    spec_path = tmp_path / "spec_hybrid.json"
    preview_path = tmp_path / "preview_hybrid.html"
    quality_path = tmp_path / "quality_hybrid.json"
    explain_path = tmp_path / "explainability_hybrid.json"
    compare_path = tmp_path / "decision_compare_hybrid.json"

    completed = _run_cli(
        [
            "report-executive-pptx",
            "configs/trial-001.executive.optimized.yaml",
            "--out",
            str(deck_path),
            "--md-out",
            str(md_path),
            "--run-summary-out",
            str(run_summary_path),
            "--deck-out",
            str(feasibility_path),
            "--chart-dir",
            str(chart_dir),
            "--spec-out",
            str(spec_path),
            "--preview-html-out",
            str(preview_path),
            "--quality-out",
            str(quality_path),
            "--r-start",
            "1.0",
            "--r-end",
            "1.0",
            "--r-step",
            "0.01",
            "--irr-threshold",
            "0.0",
            "--lang",
            "ja",
            "--chart-lang",
            "en",
            "--decision-compare",
            "off",
            "--explain-out",
            str(explain_path),
            "--compare-out",
            str(compare_path),
        ]
    )

    assert completed.returncode == 0, completed.stderr
    assert deck_path.exists()
    assert md_path.exists()
    assert run_summary_path.exists()
    assert feasibility_path.exists()
    assert spec_path.exists()
    assert preview_path.exists()
    assert quality_path.exists()
    assert explain_path.exists()
    assert compare_path.exists()


def test_cli_report_executive_pptx_rejects_engine_option(tmp_path: Path) -> None:
    completed = _run_cli(
        [
            "report-executive-pptx",
            "configs/trial-001.executive.optimized.yaml",
            "--out",
            str(tmp_path / "deck.pptx"),
            "--engine",
            "pptxgenjs",
        ]
    )

    assert completed.returncode != 0
    assert "unrecognized arguments: --engine" in completed.stderr
