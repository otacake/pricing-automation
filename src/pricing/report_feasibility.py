from __future__ import annotations

"""Generate a feasibility report deck from a pricing config."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import yaml

from .config import load_optimization_settings, loading_surplus_threshold, read_loading_parameters
from .paths import resolve_base_dir_from_config
from .profit_test import (
    DEFAULT_LAPSE_RATE,
    DEFAULT_VALUATION_INTEREST,
    model_point_label,
    run_profit_test,
)
from .sweep_ptm import _calc_sweep_metrics, _iter_range, load_model_points


def _assumption_snapshot(config: Mapping[str, object]) -> dict[str, object]:
    pricing = config["pricing"]
    interest_cfg = pricing["interest"]
    if interest_cfg.get("type") != "flat":
        raise ValueError("Only flat interest rate is supported.")
    pricing_interest_rate = float(interest_cfg["flat_rate"])

    profit_test_cfg = config.get("profit_test", {})
    valuation_interest_rate = float(
        profit_test_cfg.get("valuation_interest_rate", DEFAULT_VALUATION_INTEREST)
    )
    lapse_rate = float(profit_test_cfg.get("lapse_rate", DEFAULT_LAPSE_RATE))

    loading_snapshot: dict[str, object]
    loading_params = read_loading_parameters(config)
    if loading_params is not None:
        loading_snapshot = {
            "mode": "loading_parameters",
            "loading_parameters": {
                "a0": float(loading_params.a0),
                "a_age": float(loading_params.a_age),
                "a_term": float(loading_params.a_term),
                "a_sex": float(loading_params.a_sex),
                "b0": float(loading_params.b0),
                "b_age": float(loading_params.b_age),
                "b_term": float(loading_params.b_term),
                "b_sex": float(loading_params.b_sex),
                "g0": float(loading_params.g0),
                "g_term": float(loading_params.g_term),
            },
        }
    else:
        loadings_cfg = config.get("loading_alpha_beta_gamma", {})
        if not isinstance(loadings_cfg, Mapping):
            raise ValueError(
                "Either loading_parameters/loading_function or loading_alpha_beta_gamma is required."
            )
        loading_snapshot = {
            "mode": "loading_alpha_beta_gamma",
            "loading_alpha_beta_gamma": {
                "alpha": float(loadings_cfg["alpha"]),
                "beta": float(loadings_cfg["beta"]),
                "gamma": float(loadings_cfg["gamma"]),
            },
        }

    return {
        "pricing_interest_rate": pricing_interest_rate,
        "valuation_interest_rate": valuation_interest_rate,
        "lapse_rate": lapse_rate,
        "loading": loading_snapshot,
    }


def _build_kpi_summary(
    sweep_rows: list[dict[str, object]],
    min_r_by_id: dict[str, float | None],
) -> dict[str, object]:
    irr_values = [float(row["irr"]) for row in sweep_rows]
    nbv_values = [float(row["nbv"]) for row in sweep_rows]
    loading_ratio_values = [float(row["loading_surplus_ratio"]) for row in sweep_rows]
    ptm_values = [float(row["premium_to_maturity"]) for row in sweep_rows]

    found_count = sum(value is not None for value in min_r_by_id.values())
    not_found_count = len(min_r_by_id) - found_count

    return {
        "model_point_count": len(min_r_by_id),
        "sweep_row_count": len(sweep_rows),
        "min_r_found": found_count,
        "min_r_not_found": not_found_count,
        "min_irr": min(irr_values),
        "max_irr": max(irr_values),
        "min_nbv": min(nbv_values),
        "max_nbv": max(nbv_values),
        "min_loading_surplus_ratio": min(loading_ratio_values),
        "max_loading_surplus_ratio": max(loading_ratio_values),
        "min_premium_to_maturity": min(ptm_values),
        "max_premium_to_maturity": max(ptm_values),
    }


def _build_constraint_breakdown(
    config: Mapping[str, object],
    base_dir: Path,
    fixed_r: float,
    base_gross_premium_by_id: Mapping[str, int],
) -> list[dict[str, object]]:
    settings = load_optimization_settings(config)
    points = load_model_points(config)

    rows: list[dict[str, object]] = []
    for point in points:
        base_premium = int(base_gross_premium_by_id[point.model_point_id])
        gross_annual_premium = int(round(base_premium * fixed_r, 0))
        if gross_annual_premium <= 0:
            raise ValueError(
                f"Scaled premium must remain positive: {point.model_point_id}, r={fixed_r}"
            )
        metrics = _calc_sweep_metrics(
            config=config,
            base_dir=base_dir,
            model_point=point,
            gross_annual_premium=gross_annual_premium,
        )

        violations: list[str] = []
        if metrics["irr"] < settings.irr_hard:
            violations.append("irr_hard")
        threshold = loading_surplus_threshold(settings, point.sum_assured)
        if metrics["loading_surplus"] < threshold:
            violations.append("loading_surplus_hard")
        if metrics["premium_to_maturity"] > settings.premium_to_maturity_hard_max:
            violations.append("premium_to_maturity_hard_max")
        if metrics["nbv"] < settings.nbv_hard:
            violations.append("nbv_hard")
        if settings.loading_surplus_hard_ratio is not None and (
            metrics["loading_surplus_ratio"] < settings.loading_surplus_hard_ratio
        ):
            violations.append("loading_surplus_ratio_hard")
        if metrics["alpha"] < 0.0:
            violations.append("alpha_non_negative")
        if metrics["beta"] < 0.0:
            violations.append("beta_non_negative")
        if metrics["gamma"] < 0.0:
            violations.append("gamma_non_negative")
        if metrics["loading_positive"] <= 0.0:
            violations.append("loading_positive")

        rows.append(
            {
                "model_point_id": point.model_point_id,
                "r": fixed_r,
                "irr": metrics["irr"],
                "nbv": metrics["nbv"],
                "loading_surplus_ratio": metrics["loading_surplus_ratio"],
                "premium_to_maturity": metrics["premium_to_maturity"],
                "violations": violations,
                "status": "pass" if not violations else "fail",
            }
        )

    return rows


def _base_gross_premium_by_id(
    config: Mapping[str, object],
    base_dir: Path,
) -> dict[str, int]:
    """
    Build model-point base premiums from the actual pricing logic.

    r in sweep is interpreted as a multiplier on these base premiums.
    """
    result = run_profit_test(dict(config), base_dir=base_dir)
    by_id: dict[str, int] = {}
    for res in result.results:
        label = model_point_label(res.model_point)
        by_id[label] = int(res.premiums.gross_annual_premium)
    return by_id


def build_feasibility_report(
    config: Mapping[str, object],
    base_dir: Path,
    r_start: float = 1.0,
    r_end: float = 1.05,
    r_step: float = 0.01,
    irr_threshold: float = 0.04,
    fixed_r: float | None = None,
    config_path: Path | None = None,
) -> dict[str, object]:
    points = load_model_points(config)
    r_values = _iter_range(r_start, r_end, r_step)
    fixed_r_value = float(r_end if fixed_r is None else fixed_r)
    base_gross_by_id = _base_gross_premium_by_id(config, base_dir)

    sweep_rows: list[dict[str, object]] = []
    min_r_by_id: dict[str, float | None] = {
        point.model_point_id: None for point in points
    }

    for r_value in r_values:
        for point in points:
            base_premium = int(base_gross_by_id[point.model_point_id])
            gross_annual_premium = int(round(base_premium * r_value, 0))
            if gross_annual_premium <= 0:
                raise ValueError(
                    f"Scaled premium must remain positive: {point.model_point_id}, r={r_value}"
                )
            metrics = _calc_sweep_metrics(
                config=config,
                base_dir=base_dir,
                model_point=point,
                gross_annual_premium=gross_annual_premium,
            )

            if (
                min_r_by_id[point.model_point_id] is None
                and metrics["irr"] >= irr_threshold
            ):
                min_r_by_id[point.model_point_id] = r_value

            sweep_rows.append(
                {
                    "model_point_id": point.model_point_id,
                    "r": r_value,
                    "base_gross_annual_premium": base_premium,
                    "gross_annual_premium": gross_annual_premium,
                    "irr": metrics["irr"],
                    "nbv": metrics["nbv"],
                    "loading_surplus_ratio": metrics["loading_surplus_ratio"],
                    "premium_to_maturity": metrics["premium_to_maturity"],
                }
            )

    min_r_rows = [
        {
            "model_point_id": point.model_point_id,
            "min_r": min_r_by_id[point.model_point_id],
            "found": min_r_by_id[point.model_point_id] is not None,
        }
        for point in points
    ]

    kpi_summary = _build_kpi_summary(sweep_rows, min_r_by_id)
    constraints_table = _build_constraint_breakdown(
        config=config,
        base_dir=base_dir,
        fixed_r=fixed_r_value,
        base_gross_premium_by_id=base_gross_by_id,
    )

    settings = load_optimization_settings(config)
    deck: dict[str, object] = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "config_path": str(config_path) if config_path is not None else "in-memory",
            "scan": {
                "r_start": float(r_start),
                "r_end": float(r_end),
                "r_step": float(r_step),
                "irr_threshold": float(irr_threshold),
                "r_count": len(r_values),
                "r_definition": "multiplier_on_model_point_base_gross_annual_premium",
            },
            "assumptions": _assumption_snapshot(config),
            "constraints": {
                "irr_hard": settings.irr_hard,
                "nbv_hard": settings.nbv_hard,
                "loading_surplus_hard": settings.loading_surplus_hard,
                "loading_surplus_hard_ratio": settings.loading_surplus_hard_ratio,
                "premium_to_maturity_hard_max": settings.premium_to_maturity_hard_max,
            },
            "model_points": {
                "count": len(points),
                "ids": [point.model_point_id for point in points],
                "base_gross_annual_premium_by_id": {
                    point.model_point_id: int(base_gross_by_id[point.model_point_id])
                    for point in points
                },
            },
            "fixed_point": {
                "r": fixed_r_value,
            },
        },
        "kpi_summary": kpi_summary,
        "slides": [
            {
                "title": "Conclusion",
                "kind": "kpi_summary",
                "table": kpi_summary,
            },
            {
                "title": "Min r by Model Point",
                "kind": "min_r_table",
                "table": min_r_rows,
            },
            {
                "title": f"Constraint Violations at r={fixed_r_value}",
                "kind": "constraint_breakdown",
                "r": fixed_r_value,
                "table": constraints_table,
            },
        ],
        "tables": {
            "sweep": sweep_rows,
        },
    }

    return deck


def report_feasibility_from_config(
    config_path: Path,
    r_start: float = 1.0,
    r_end: float = 1.05,
    r_step: float = 0.01,
    irr_threshold: float = 0.04,
    out_path: Path | None = None,
) -> Path:
    config_path = config_path.expanduser().resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    base_dir = resolve_base_dir_from_config(config_path)
    if out_path is None:
        output_path = base_dir / "out/feasibility_deck.yaml"
    else:
        output_path = out_path if out_path.is_absolute() else (base_dir / out_path)

    deck = build_feasibility_report(
        config=config,
        base_dir=base_dir,
        r_start=r_start,
        r_end=r_end,
        r_step=r_step,
        irr_threshold=irr_threshold,
        config_path=config_path,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(deck, sort_keys=False),
        encoding="utf-8",
    )
    return output_path
