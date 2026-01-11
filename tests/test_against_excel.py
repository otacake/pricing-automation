from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_bootstrap_missing_excel() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "bootstrap_from_excel.py"
    missing = repo_root / "data" / "golden" / "__missing__.xlsx"
    result = subprocess.run(
        [sys.executable, str(script), "--xlsx", str(missing)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert f"File not found: {missing}" in result.stderr
