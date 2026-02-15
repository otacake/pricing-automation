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
    assert contract.frontmatter["narrative"]["mode"] == "conclusion_first"
    assert contract.frontmatter["narrative"]["main_compare_slide_id"] == "decision_statement"


def test_load_style_contract_missing_required_key(tmp_path: Path) -> None:
    source = tmp_path / "style.md"
    source.write_text(
        "---\nversion: '1.0'\nmain_slide_count: 1\nslides:\n  - id: s1\n    title: t\n    message: m\n---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_style_contract(source)


def test_load_style_contract_requires_narrative_contract(tmp_path: Path) -> None:
    source = tmp_path / "style_narrative.md"
    source.write_text(
        "\n".join(
            [
                "---",
                "version: '1.0'",
                "persona: test",
                "visual_signature: test",
                "info_density: test",
                "decoration_level: test",
                "main_slide_count: 1",
                "logo_policy: none",
                "layout:",
                "  slide_size_in: {width: 13.333, height: 7.5}",
                "  margins_in: {left: 0.6, right: 0.6, top: 0.3, bottom: 0.3}",
                "  grid: {columns: 12, gutter: 0.12}",
                "fonts:",
                "  ja_primary: Meiryo UI",
                "  ja_fallback: Meiryo",
                "  en_primary: Calibri",
                "  en_fallback: Arial",
                "typography:",
                "  title_pt: 34",
                "  subtitle_pt: 18",
                "  body_pt: 16",
                "  note_pt: 11",
                "  kpi_pt: 44",
                "colors:",
                "  primary: '#0B5FA5'",
                "  secondary: '#5B6B7A'",
                "  accent: '#F59E0B'",
                "  positive: '#2A9D8F'",
                "  negative: '#D1495B'",
                "  background: '#F8FAFC'",
                "  text: '#111827'",
                "  grid: '#D1D5DB'",
                "slides:",
                "  - id: s1",
                "    title: t",
                "    message: m",
                "---",
                "body",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_style_contract(source)
