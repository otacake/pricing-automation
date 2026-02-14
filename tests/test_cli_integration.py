from __future__ import annotations

import os
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
    pytest.importorskip("pptx")

    deck_path = tmp_path / "executive.pptx"
    md_path = tmp_path / "feasibility.md"
    run_summary_path = tmp_path / "run_summary.json"
    feasibility_path = tmp_path / "feasibility.yaml"
    chart_dir = tmp_path / "charts"

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
        ]
    )

    assert completed.returncode == 0, completed.stderr
    assert deck_path.exists()
    assert md_path.exists()
    assert run_summary_path.exists()
    assert feasibility_path.exists()
    assert (chart_dir / "cashflow_by_profit_source.png").exists()
    assert (chart_dir / "annual_premium_by_model_point.png").exists()
