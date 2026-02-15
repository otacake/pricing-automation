from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


REQUIRED_COLOR_KEYS = (
    "primary",
    "secondary",
    "accent",
    "positive",
    "negative",
    "background",
    "text",
    "grid",
)
REQUIRED_NARRATIVE_SECTIONS = ("conclusion", "rationale", "risk", "decision_ask")
ALLOWED_NOTES_MODE = {"auto_from_narrative", "none"}
ALLOWED_COMPARISON_LAYOUT = {"dedicated_main_slide"}
ALLOWED_NARRATIVE_MODE = {"conclusion_first"}


@dataclass(frozen=True)
class DeckStyleContract:
    path: Path
    frontmatter: dict[str, Any]
    body: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.path.as_posix(),
            **self.frontmatter,
        }


def _split_frontmatter(markdown_text: str) -> tuple[str, str]:
    normalized = markdown_text.lstrip("\ufeff").replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError("Style contract must start with YAML frontmatter ('---').")
    end_marker = "\n---\n"
    end_index = normalized.find(end_marker, 4)
    if end_index < 0:
        raise ValueError("Style contract frontmatter is not closed with '---'.")
    frontmatter = normalized[4:end_index]
    body = normalized[end_index + len(end_marker) :]
    return frontmatter, body


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"Style contract requires mapping key: {key}")
    return value


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Style contract requires string key: {key}")
    return value.strip()


def _require_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        raise ValueError(f"Style contract key '{key}' must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Style contract key '{key}' must be an integer.") from exc


def _require_float(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool):
        raise ValueError(f"Style contract key '{key}' must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Style contract key '{key}' must be a number.") from exc


def _require_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Style contract key '{key}' must be a boolean.")
    return value


def _require_str_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Style contract requires list key: {key}")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"Style contract key '{key}' must contain non-empty strings.")
        normalized.append(item.strip())
    return normalized


def _validate_frontmatter(frontmatter: Mapping[str, Any]) -> dict[str, Any]:
    contract = dict(frontmatter)

    _require_str(contract, "version")
    _require_str(contract, "persona")
    _require_str(contract, "visual_signature")
    _require_str(contract, "info_density")
    _require_str(contract, "decoration_level")
    _require_str(contract, "logo_policy")

    main_slide_count = _require_int(contract, "main_slide_count")
    if main_slide_count <= 0:
        raise ValueError("Style contract key 'main_slide_count' must be greater than zero.")
    contract["main_slide_count"] = main_slide_count

    visual = dict(_require_mapping(contract, "visual"))
    visual["icon_style"] = _require_str(visual, "icon_style")
    contract["visual"] = visual

    layout = dict(_require_mapping(contract, "layout"))
    layout["master_variant"] = _require_str(layout, "master_variant")
    slide_size = dict(_require_mapping(layout, "slide_size_in"))
    margins = dict(_require_mapping(layout, "margins_in"))
    grid = dict(_require_mapping(layout, "grid"))
    for key in ("width", "height"):
        if key not in slide_size:
            raise ValueError(f"Style contract requires layout.slide_size_in.{key}")
    for key in ("left", "right", "top", "bottom"):
        if key not in margins:
            raise ValueError(f"Style contract requires layout.margins_in.{key}")
    if "columns" not in grid or "gutter" not in grid:
        raise ValueError("Style contract requires layout.grid.columns and layout.grid.gutter")
    contract["layout"] = {
        "master_variant": layout["master_variant"],
        "slide_size_in": {k: float(slide_size[k]) for k in ("width", "height")},
        "margins_in": {k: float(margins[k]) for k in ("left", "right", "top", "bottom")},
        "grid": {
            "columns": int(grid["columns"]),
            "gutter": float(grid["gutter"]),
        },
    }

    fonts = dict(_require_mapping(contract, "fonts"))
    _require_str(fonts, "ja_primary")
    _require_str(fonts, "ja_fallback")
    _require_str(fonts, "en_primary")
    _require_str(fonts, "en_fallback")
    contract["fonts"] = fonts

    typography = dict(_require_mapping(contract, "typography"))
    for key in ("title_pt", "subtitle_pt", "body_pt", "note_pt", "kpi_pt"):
        if key not in typography:
            raise ValueError(f"Style contract requires typography.{key}")
    contract["typography"] = {k: float(typography[k]) for k in typography}

    colors = dict(_require_mapping(contract, "colors"))
    missing_colors = [key for key in REQUIRED_COLOR_KEYS if key not in colors]
    if missing_colors:
        raise ValueError(f"Style contract missing colors: {', '.join(missing_colors)}")
    contract["colors"] = colors

    tables = dict(_require_mapping(contract, "tables"))
    contract["tables"] = {
        "auto_page_default": _require_bool(tables, "auto_page_default"),
        "auto_page_repeat_header": _require_bool(tables, "auto_page_repeat_header"),
        "auto_page_header_rows": _require_int(tables, "auto_page_header_rows"),
        "auto_page_slide_start_y": _require_float(tables, "auto_page_slide_start_y"),
        "overflow_policy": _require_str(tables, "overflow_policy"),
    }

    charts = dict(_require_mapping(contract, "charts"))
    contract["charts"] = {
        "value_label_default": _require_bool(charts, "value_label_default"),
        "value_label_format_code": _require_str(charts, "value_label_format_code"),
        "line_value_label_format_code": _require_str(charts, "line_value_label_format_code"),
    }

    accessibility = dict(_require_mapping(contract, "accessibility"))
    contract["accessibility"] = {
        "require_unique_titles": _require_bool(accessibility, "require_unique_titles"),
        "require_alt_text": _require_bool(accessibility, "require_alt_text"),
    }

    slides = contract.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("Style contract requires a non-empty slides list.")
    if len(slides) != main_slide_count:
        raise ValueError(
            "Style contract main_slide_count does not match the number of slide definitions."
        )
    normalized_slides: list[dict[str, str]] = []
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, Mapping):
            raise ValueError(f"Slide definition at index {index} must be a mapping.")
        slide_id = _require_str(slide, "id")
        title = _require_str(slide, "title")
        message = _require_str(slide, "message")
        normalized_slides.append({"id": slide_id, "title": title, "message": message})
    contract["slides"] = normalized_slides

    narrative = dict(_require_mapping(contract, "narrative"))
    mode = _require_str(narrative, "mode")
    if mode not in ALLOWED_NARRATIVE_MODE:
        raise ValueError("Style contract narrative.mode must be 'conclusion_first'.")
    comparison_layout = _require_str(narrative, "comparison_layout")
    if comparison_layout not in ALLOWED_COMPARISON_LAYOUT:
        raise ValueError(
            "Style contract narrative.comparison_layout must be 'dedicated_main_slide'."
        )
    text_density = _require_str(narrative, "text_density")
    min_lines = _require_int(narrative, "min_lines_per_main_slide")
    if min_lines <= 0:
        raise ValueError("Style contract narrative.min_lines_per_main_slide must be greater than zero.")
    required_sections = _require_str_list(narrative, "required_sections")
    if required_sections != list(REQUIRED_NARRATIVE_SECTIONS):
        raise ValueError(
            "Style contract narrative.required_sections must be exactly "
            "['conclusion', 'rationale', 'risk', 'decision_ask']."
        )
    compare_slide_id = _require_str(narrative, "main_compare_slide_id")
    if compare_slide_id not in {slide["id"] for slide in normalized_slides}:
        raise ValueError(
            "Style contract narrative.main_compare_slide_id must match one of slides[].id."
        )
    notes_mode = _require_str(narrative, "notes_mode")
    if notes_mode not in ALLOWED_NOTES_MODE:
        raise ValueError("Style contract narrative.notes_mode must be one of: auto_from_narrative, none")
    contract["narrative"] = {
        "mode": mode,
        "comparison_layout": comparison_layout,
        "text_density": text_density,
        "min_lines_per_main_slide": min_lines,
        "required_sections": required_sections,
        "main_compare_slide_id": compare_slide_id,
        "notes_mode": notes_mode,
    }

    return contract


def load_style_contract(path: Path) -> DeckStyleContract:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Style contract not found: {source}")
    raw = source.read_text(encoding="utf-8")
    frontmatter_text, body = _split_frontmatter(raw)
    payload = yaml.safe_load(frontmatter_text)
    if not isinstance(payload, Mapping):
        raise ValueError("Style contract frontmatter must be a YAML mapping.")
    validated = _validate_frontmatter(payload)
    return DeckStyleContract(path=source, frontmatter=validated, body=body)
