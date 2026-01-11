from __future__ import annotations

"""
Sweep premium-to-maturity ratios and evaluate IRR for a model point.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from .commutation import build_mortality_q_by_age
from .endowment import calc_endowment_premiums
from .profit_test import (
    DEFAULT_LAPSE_RATE,
    DEFAULT_VALUATION_INTEREST,
    _forward_rates_from_spot,
    _inforce_series,
    _reserve_factors,
    _resolve_path,
    calc_irr,
    load_mortality_csv,
    load_spot_curve_csv,
)


@dataclass(frozen=True)
class SweepModelPoint:
    """
    Model point definition used in the premium-to-maturity sweep.

    Units
    - issue_age: years
    - term_years / premium_paying_years: years
    - sum_assured: JPY
    - sex: "male" / "female"
    """

    issue_age: int
    sex: str
    term_years: int
    premium_paying_years: int
    sum_assured: int
    model_point_id: str


def model_point_label(issue_age: int, sex: str, term_years: int) -> str:
    """
    Build a model point label used in CLI selection.
    """
    return f"{sex}_age{issue_age}_term{term_years}"


def load_model_points(config: Mapping[str, object]) -> list[SweepModelPoint]:
    """
    Load model points from config for sweep selection.
    """
    product = config.get("product", {}) if isinstance(config, Mapping) else {}
    defaults = {
        "term_years": product.get("term_years"),
        "premium_paying_years": product.get("premium_paying_years"),
        "sum_assured": product.get("sum_assured"),
    }
    points_cfg = config.get("model_points")
    if points_cfg is None:
        points_cfg = [config.get("model_point")]

    points: list[SweepModelPoint] = []
    for entry in points_cfg or []:
        if not isinstance(entry, Mapping):
            continue
        issue_age = int(entry["issue_age"])
        sex = str(entry["sex"])
        term_years = int(entry.get("term_years", defaults["term_years"]))
        premium_paying_years = int(
            entry.get("premium_paying_years", defaults["premium_paying_years"])
        )
        sum_assured = int(entry.get("sum_assured", defaults["sum_assured"]))
        model_point_id = entry.get("id")
        label = (
            str(model_point_id)
            if model_point_id is not None
            else model_point_label(issue_age, sex, term_years)
        )
        points.append(
            SweepModelPoint(
                issue_age=issue_age,
                sex=sex,
                term_years=term_years,
                premium_paying_years=premium_paying_years,
                sum_assured=sum_assured,
                model_point_id=label,
            )
        )
    if not points:
        raise ValueError("Model point definition is missing.")
    return points


def select_model_point(
    points: Iterable[SweepModelPoint],
    label: str,
) -> SweepModelPoint:
    """
    Select a model point by label for sweep.
    """
    points_list = list(points)
    for point in points_list:
        if point.model_point_id == label:
            return point
    raise ValueError(f"Model point not found: {label}")


def _iter_range(start: float, end: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("step must be positive.")
    values: list[float] = []
    current = start
    while current <= end + 1e-12:
        values.append(round(current, 10))
        current += step
    if not values:
        raise ValueError("Sweep range is empty.")
    return values


def _calc_sweep_metrics(
    config: Mapping[str, object],
    base_dir: Path,
    model_point: SweepModelPoint,
    gross_annual_premium: int,
) -> dict[str, float]:
    pricing = config["pricing"]
    loadings = config["loading_alpha_beta_gamma"]
    profit_test_cfg = config.get("profit_test", {})

    interest_cfg = pricing["interest"]
    if interest_cfg.get("type") != "flat":
        raise ValueError("Only flat interest rate is supported.")
    pricing_interest = float(interest_cfg["flat_rate"])
    valuation_interest = float(
        profit_test_cfg.get("valuation_interest_rate", DEFAULT_VALUATION_INTEREST)
    )
    lapse_rate = float(profit_test_cfg.get("lapse_rate", DEFAULT_LAPSE_RATE))

    alpha = float(loadings["alpha"])
    beta = float(loadings["beta"])
    gamma = float(loadings["gamma"])

    pricing_mortality_path = _resolve_path(base_dir, pricing["mortality_path"])
    actual_mortality_path = _resolve_path(
        base_dir, profit_test_cfg["mortality_actual_path"]
    )
    spot_curve_path = _resolve_path(base_dir, profit_test_cfg["discount_curve_path"])

    pricing_rows = load_mortality_csv(pricing_mortality_path)
    actual_rows = load_mortality_csv(actual_mortality_path)
    spot_curve = load_spot_curve_csv(spot_curve_path)
    forward_rates = _forward_rates_from_spot(spot_curve, model_point.term_years)

    premiums = calc_endowment_premiums(
        mortality_rows=pricing_rows,
        sex=model_point.sex,
        issue_age=model_point.issue_age,
        term_years=model_point.term_years,
        premium_paying_years=model_point.premium_paying_years,
        interest_rate=pricing_interest,
        sum_assured=model_point.sum_assured,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
    )

    q_pricing = build_mortality_q_by_age(pricing_rows, model_point.sex)
    q_actual = build_mortality_q_by_age(actual_rows, model_point.sex)

    tV_pricing, tW_pricing, _ = _reserve_factors(
        q_by_age=q_pricing,
        issue_age=model_point.issue_age,
        term_years=model_point.term_years,
        premium_paying_years=model_point.premium_paying_years,
        interest_rate=pricing_interest,
        alpha=alpha,
    )
    tV_valuation, _, _ = _reserve_factors(
        q_by_age=q_pricing,
        issue_age=model_point.issue_age,
        term_years=model_point.term_years,
        premium_paying_years=model_point.premium_paying_years,
        interest_rate=valuation_interest,
        alpha=alpha,
    )

    inforce_begin, inforce_end, death_rates, lapse_rates = _inforce_series(
        q_by_age=q_actual,
        issue_age=model_point.issue_age,
        term_years=model_point.term_years,
        lapse_rate=lapse_rate,
    )

    net_cfs: list[float] = []
    pv_net_cf = 0.0
    pv_loading = 0.0
    pv_expense = 0.0

    for t in range(model_point.term_years):
        if t + 1 not in spot_curve:
            raise ValueError(f"Missing spot rate for t={t + 1}.")
        spot_rate = spot_curve[t + 1]
        forward_rate = forward_rates[t]

        inforce_beg = inforce_begin[t]
        inforce_end_t = inforce_end[t]
        q_t = death_rates[t]
        w_t = lapse_rates[t]

        is_premium_year = t < model_point.premium_paying_years

        premium_income = (
            gross_annual_premium * inforce_beg if is_premium_year else 0.0
        )
        net_premium_income = (
            premiums.net_annual_premium * inforce_beg if is_premium_year else 0.0
        )
        loading_income = premium_income - net_premium_income

        death_benefit = (
            inforce_beg * q_t * model_point.sum_assured if is_premium_year else 0.0
        )
        surrender_benefit = (
            inforce_beg
            * w_t
            * (tW_pricing[t] + tW_pricing[t + 1])
            / 2.0
            * model_point.sum_assured
            if is_premium_year
            else 0.0
        )
        maturity_benefit = (
            inforce_end_t * model_point.sum_assured
            if t == model_point.term_years - 1
            else 0.0
        )

        # Acquisition expense: 0.5 * alpha for actual basis in Excel.
        expenses_acq = (0.5 * alpha * model_point.sum_assured) if t == 0 else 0.0
        expenses_maint = (
            inforce_beg * model_point.sum_assured * beta if is_premium_year else 0.0
        )
        expenses_coll = (
            inforce_beg * gross_annual_premium * gamma if is_premium_year else 0.0
        )
        expenses_total = expenses_acq + expenses_maint + expenses_coll

        reserve_change = (
            model_point.sum_assured
            * (inforce_end_t * tV_valuation[t + 1] - inforce_beg * tV_valuation[t])
            if is_premium_year
            else 0.0
        )

        investment_income = (
            (
                inforce_beg * tV_valuation[t] * model_point.sum_assured
                + premium_income
                - expenses_total
            )
            * forward_rate
            - (death_benefit + surrender_benefit) * ((1.0 + forward_rate) ** 0.5 - 1.0)
            if is_premium_year
            else 0.0
        )

        net_cf = (
            premium_income
            + investment_income
            - (death_benefit + surrender_benefit + expenses_total + reserve_change)
        )
        net_cfs.append(net_cf)

        spot_df = (1.0 / (1.0 + spot_rate)) ** (t + 1)
        pv_net_cf += net_cf * spot_df
        pv_loading += loading_income * spot_df
        pv_expense += expenses_total * spot_df

    irr = calc_irr(net_cfs)
    loading_surplus = pv_loading - pv_expense

    premium_to_maturity = (
        gross_annual_premium * model_point.premium_paying_years / model_point.sum_assured
    )

    return {
        "irr": irr,
        "nbv": pv_net_cf,
        "loading_surplus": loading_surplus,
        "loading_surplus_ratio": loading_surplus / model_point.sum_assured,
        "premium_to_maturity": premium_to_maturity,
    }


def sweep_premium_to_maturity(
    config: Mapping[str, object],
    base_dir: Path,
    model_point_label: str,
    start: float,
    end: float,
    step: float,
    irr_threshold: float,
    out_path: Path,
) -> tuple[pd.DataFrame, float | None]:
    """
    Sweep premium-to-maturity ratios for a model point.

    Units
    - start/end/step: premium_to_maturity ratio
    - irr_threshold: annual rate
    - out_path: CSV output path
    """
    points = load_model_points(config)
    model_point = select_model_point(points, model_point_label)

    rows: list[dict[str, float | int]] = []
    min_r: float | None = None

    for ratio in _iter_range(start, end, step):
        gross_annual_premium = int(
            round(ratio * model_point.sum_assured / model_point.premium_paying_years, 0)
        )
        metrics = _calc_sweep_metrics(
            config=config,
            base_dir=base_dir,
            model_point=model_point,
            gross_annual_premium=gross_annual_premium,
        )
        if min_r is None and metrics["irr"] >= irr_threshold:
            min_r = ratio

        rows.append(
            {
                "model_point_id": model_point.model_point_id,
                "sex": model_point.sex,
                "issue_age": model_point.issue_age,
                "term_years": model_point.term_years,
                "premium_paying_years": model_point.premium_paying_years,
                "sum_assured": model_point.sum_assured,
                "r": ratio,
                "gross_annual_premium": gross_annual_premium,
                "irr": metrics["irr"],
                "nbv": metrics["nbv"],
                "loading_surplus": metrics["loading_surplus"],
                "loading_surplus_ratio": metrics["loading_surplus_ratio"],
                "premium_to_maturity": metrics["premium_to_maturity"],
            }
        )

    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df, min_r


def sweep_premium_to_maturity_all(
    config: Mapping[str, object],
    base_dir: Path,
    start: float,
    end: float,
    step: float,
    irr_threshold: float,
    nbv_threshold: float,
    loading_surplus_ratio_threshold: float,
    premium_to_maturity_hard_max: float,
    out_path: Path,
) -> tuple[pd.DataFrame, dict[str, float | None]]:
    """
    Sweep premium-to-maturity ratios for all model points.

    Units
    - start/end/step: premium_to_maturity ratio
    - irr_threshold: annual rate
    - nbv_threshold: JPY
    - loading_surplus_ratio_threshold: ratio
    - premium_to_maturity_hard_max: ratio
    """
    points = load_model_points(config)
    ratios = _iter_range(start, end, step)

    rows: list[dict[str, float | int | str]] = []
    min_r_by_id: dict[str, float | None] = {
        point.model_point_id: None for point in points
    }

    for ratio in ratios:
        for point in points:
            gross_annual_premium = int(
                round(ratio * point.sum_assured / point.premium_paying_years, 0)
            )
            metrics = _calc_sweep_metrics(
                config=config,
                base_dir=base_dir,
                model_point=point,
                gross_annual_premium=gross_annual_premium,
            )
            if min_r_by_id[point.model_point_id] is None:
                if (
                    metrics["irr"] >= irr_threshold
                    and metrics["nbv"] >= nbv_threshold
                    and metrics["loading_surplus_ratio"]
                    >= loading_surplus_ratio_threshold
                    and metrics["premium_to_maturity"] <= premium_to_maturity_hard_max
                ):
                    min_r_by_id[point.model_point_id] = ratio

            rows.append(
                {
                    "model_point_id": point.model_point_id,
                    "sex": point.sex,
                    "issue_age": point.issue_age,
                    "term_years": point.term_years,
                    "premium_paying_years": point.premium_paying_years,
                    "sum_assured": point.sum_assured,
                    "r": ratio,
                    "gross_annual_premium": gross_annual_premium,
                    "irr": metrics["irr"],
                    "nbv": metrics["nbv"],
                    "loading_surplus": metrics["loading_surplus"],
                    "loading_surplus_ratio": metrics["loading_surplus_ratio"],
                    "premium_to_maturity": metrics["premium_to_maturity"],
                }
            )

    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df, min_r_by_id
