from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .style_contract import DeckStyleContract


def _as_float(value: object) -> float:
    return float(value)


def _as_int(value: object) -> int:
    return int(value)


def _summary_claims(
    run_summary: Mapping[str, Any],
    *,
    language: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    summary = run_summary["summary"]
    labels = {
        "ja": {
            "min_irr": "最小IRR",
            "min_nbv": "最小NBV",
            "max_premium_to_maturity": "最大PTM",
            "violation_count": "違反件数",
        },
        "en": {
            "min_irr": "Minimum IRR",
            "min_nbv": "Minimum NBV",
            "max_premium_to_maturity": "Maximum PTM",
            "violation_count": "Violation Count",
        },
    }["ja" if language == "ja" else "en"]

    formatter = {
        "min_irr": "pct",
        "min_nbv": "currency_jpy",
        "max_premium_to_maturity": "ratio",
        "violation_count": "integer",
    }
    claims: list[dict[str, Any]] = []
    trace_map: list[dict[str, str]] = []
    for key in ("min_irr", "min_nbv", "max_premium_to_maturity", "violation_count"):
        claims.append(
            {
                "id": key,
                "label": labels[key],
                "value": _as_float(summary[key]) if key != "violation_count" else _as_int(summary[key]),
                "format": formatter[key],
            }
        )
        trace_map.append(
            {
                "claim_id": key,
                "source_file": "out/run_summary_executive.json",
                "source_path": f"$.summary.{key}",
            }
        )
    return claims, trace_map


def _pricing_rows(summary_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordered = summary_df.sort_values("model_point")
    for row in ordered.itertuples(index=False):
        rows.append(
            {
                "model_point": str(row.model_point),
                "gross_annual_premium": int(row.gross_annual_premium),
                "monthly_premium": float(row.gross_annual_premium) / 12.0,
                "irr": float(row.irr),
                "nbv": float(row.new_business_value),
                "premium_to_maturity": float(row.premium_to_maturity_ratio),
                "loading_surplus_ratio": float(getattr(row, "loading_surplus_ratio", 0.0)),
            }
        )
    return rows


def _constraint_rows(
    constraint_rows: list[dict[str, object]],
    *,
    language: str,
) -> list[dict[str, Any]]:
    labels = {
        "ja": {
            "irr_hard": "IRR下限",
            "nbv_hard": "NBV下限",
            "loading_surplus_hard": "Loading surplus下限",
            "loading_surplus_ratio_hard": "Loading surplus比率下限",
            "premium_to_maturity_hard_max": "PTM上限",
        },
        "en": {},
    }["ja" if language == "ja" else "en"]

    normalized: list[dict[str, Any]] = []
    for row in constraint_rows:
        key = str(row["constraint"])
        normalized.append(
            {
                "constraint": key,
                "label": labels.get(key, key),
                "threshold": float(row["threshold"]),
                "min_gap": float(row["min_gap"]),
                "worst_model_point": str(row["worst_model_point"]),
                "all_ok": bool(row["all_ok"]),
            }
        )
    return normalized


def _cashflow_rows(cashflow_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in cashflow_df.itertuples(index=False):
        rows.append(
            {
                "year": int(row.year),
                "premium_income": float(row.premium_income),
                "investment_income": float(row.investment_income),
                "benefit_outgo": float(row.benefit_outgo),
                "expense_outgo": float(row.expense_outgo),
                "reserve_change_outgo": float(row.reserve_change_outgo),
                "net_cf": float(row.net_cf),
            }
        )
    return rows


def _sensitivity_rows(rows: list[dict[str, object]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "scenario": str(row["scenario"]),
                "min_irr": float(row["min_irr"]),
                "min_nbv": float(row["min_nbv"]),
                "min_loading_surplus_ratio": float(row["min_loading_surplus_ratio"]),
                "max_premium_to_maturity": float(row["max_premium_to_maturity"]),
                "violation_count": int(row["violation_count"]),
            }
        )
    return normalized


def build_executive_deck_spec(
    *,
    config_path: Path,
    run_summary: Mapping[str, Any],
    summary_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
    constraint_rows: list[dict[str, object]],
    sensitivity_rows: list[dict[str, object]],
    style_contract: DeckStyleContract,
    language: str,
    chart_language: str,
    theme: str,
) -> dict[str, Any]:
    claims, trace_map = _summary_claims(run_summary, language=language)
    pricing_rows = _pricing_rows(summary_df)
    constraint_status = _constraint_rows(constraint_rows, language=language)
    cashflow_rows = _cashflow_rows(cashflow_df)
    sensitivity = _sensitivity_rows(sensitivity_rows)
    is_ja = language == "ja"

    decision_asks = (
        [
            "スライド3のモデルポイント別価格Pを承認してください。",
            "制約閾値と監視条件をロックし、前提変更時は再実行してください。",
            "min_irr < 2.0% または max PTM > 1.056 の場合は即時レビューを起動してください。",
        ]
        if is_ja
        else [
            "Approve the model-point pricing table P shown in Slide 3.",
            "Lock thresholds and rerun the package whenever assumptions change.",
            "Trigger immediate review if min_irr < 2.0% or max PTM > 1.056.",
        ]
    )

    headline = (
        "十分性・収益性・健全性を同時充足する価格案"
        if is_ja
        else "Pricing recommendation balancing adequacy, profitability, and soundness"
    )

    return {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "config_path": config_path.as_posix(),
            "language": language,
            "chart_language": chart_language,
            "theme": theme,
            "style_contract_path": style_contract.path.as_posix(),
        },
        "style": style_contract.to_dict(),
        "slides": style_contract.frontmatter["slides"],
        "headline": headline,
        "summary_claims": claims,
        "pricing_table": pricing_rows,
        "constraint_status": constraint_status,
        "cashflow_by_source": cashflow_rows,
        "sensitivity": sensitivity,
        "decision_asks": decision_asks,
        "trace_map": trace_map,
    }
