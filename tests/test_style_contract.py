from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.reporting.style_contract import load_style_contract


def test_load_style_contract_repo_file() -> None:
    contract = load_style_contract(REPO_ROOT / "docs" / "deck_style_contract.md")
    assert contract.frontmatter["main_slide_count"] == 9
    assert contract.frontmatter["fonts"]["ja_primary"] == "Meiryo UI"
    assert len(contract.frontmatter["slides"]) == 9


def test_load_style_contract_missing_required_key(tmp_path: Path) -> None:
    source = tmp_path / "style.md"
    source.write_text(
        "---\nversion: '1.0'\nmain_slide_count: 1\nslides:\n  - id: s1\n    title: t\n    message: m\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_style_contract(source)
