from __future__ import annotations

"""
Profit test for a traditional endowment product.

Cashflow columns are aligned with the Excel sheet "収益性検証":
- net_cf corresponds to column C (収支)
- spot_df corresponds to column S (スポット現価)
- new_business_value corresponds to Excel C3 (sum of net_cf * spot_df)
- irr corresponds to Excel B1 (IRR of net_cf series)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
import pandas as pd

from .commutation import build_mortality_q_by_age, survival_probabilities
from .endowment import EndowmentPremiums, calc_endowment_premiums

DEFAULT_VALUATION_INTEREST = 0.0025
DEFAULT_LAPSE_RATE = 0.03


@dataclass(frozen=True)
class ProfitTestResult:
    """
    Profit test outputs.

    Units
    - cashflow: annual cashflow table (amounts in JPY)
    - irr: internal rate of return (annual rate)
    - new_business_value: sum of discounted net cashflows (JPY)
    - premiums: endowment premiums and factors
    """

    cashflow: pd.DataFrame
    irr: float
    new_business_value: float
    premiums: EndowmentPremiums


def _resolve_path(base_dir: Path, path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else base_dir / path


def load_mortality_csv(path: Path) -> list[dict[str, float | int | None]]:
    """
    Load mortality CSV into a list of dicts with keys: age, q_male, q_female.
    """
    df = pd.read_csv(path)
    return df.to_dict(orient="records")


def load_spot_curve_csv(path: Path) -> dict[int, float]:
    """
    Load spot curve CSV into a dict of {t: spot_rate}.
    """
    df = pd.read_csv(path)
    result: dict[int, float] = {}
    for _, row in df.iterrows():
        t = int(row["t"])
        result[t] = float(row["spot_rate"])
    return result


def _forward_rates_from_spot(spot_curve: Mapping[int, float], term_years: int) -> list[float]:
    """
    Compute one-year forward rates from spot rates.

    forward_t = (1+spot_{t+1})^(t+1) / (1+spot_t)^t - 1
    """
    forward_rates: list[float] = []
    for t in range(term_years):
        spot_next = spot_curve[t + 1]
        if t == 0:
            forward_rates.append(spot_next)
            continue
        spot_prev = spot_curve[t]
        forward = ((1.0 + spot_next) ** (t + 1) / (1.0 + spot_prev) ** t) - 1.0
        forward_rates.append(forward)
    return forward_rates


def _calc_endowment_values(
    q_by_age: Mapping[int, float],
    issue_age: int,
    term_years: int,
    premium_paying_years: int,
    interest_rate: float,
) -> tuple[float, float]:
    """
    Calculate A and a for the given term and premium horizon.

    - A_death = sum v^(t+0.5) * p_{x:t} * q_{x+t}
    - A_maturity = v^n * p_{x:n}
    - a = sum v^t * p_{x:t}
    """
    if term_years < 0 or premium_paying_years < 0:
        raise ValueError("term_years and premium_paying_years must be non-negative.")
    if term_years == 0:
        return 1.0, 0.0

    p = survival_probabilities(q_by_age, issue_age, term_years)
    v = 1.0 / (1.0 + interest_rate)

    # A_death: mid-year death benefit
    death_pv = 0.0
    for t in range(term_years):
        age = issue_age + t
        death_pv += (v ** (t + 0.5)) * p[t] * q_by_age[age]

    # A_maturity: end-of-year maturity benefit
    maturity_pv = (v ** term_years) * p[term_years]
    A = death_pv + maturity_pv

    # a: annuity-due premium factor
    annuity = 0.0
    for t in range(premium_paying_years):
        annuity += (v ** t) * p[t]

    return A, annuity


def _reserve_factors(
    q_by_age: Mapping[int, float],
    issue_age: int,
    term_years: int,
    premium_paying_years: int,
    interest_rate: float,
    alpha: float,
) -> tuple[list[float], list[float], float]:
    """
    Build tV and tW series for t=0..term_years.

    - tV = A(x+t:n-t) - net_rate * a(x+t:n-t)
    - tW = max(tV - ((10 - min(t,10)) / 10) * alpha, 0)
    """
    A0, a0 = _calc_endowment_values(
        q_by_age=q_by_age,
        issue_age=issue_age,
        term_years=term_years,
        premium_paying_years=premium_paying_years,
        interest_rate=interest_rate,
    )
    if a0 <= 0.0:
        raise ValueError("Premium annuity factor must be positive.")
    net_rate = A0 / a0

    tV: list[float] = []
    tW: list[float] = []
    for t in range(term_years + 1):
        remaining_term = term_years - t
        remaining_premium = max(premium_paying_years - t, 0)
        A_t, a_t = _calc_endowment_values(
            q_by_age=q_by_age,
            issue_age=issue_age + t,
            term_years=remaining_term,
            premium_paying_years=remaining_premium,
            interest_rate=interest_rate,
        )
        reserve = A_t - net_rate * a_t
        tV.append(reserve)
        surrender_adj = (10 - min(t, 10)) / 10.0
        tW.append(max(reserve - surrender_adj * alpha, 0.0))

    return tV, tW, net_rate


def _inforce_series(
    q_by_age: Mapping[int, float],
    issue_age: int,
    term_years: int,
    lapse_rate: float,
) -> tuple[list[float], list[float], list[float], list[float]]:
    """
    Build inforce and exit-rate series using the Excel definitions.

    - death_rate = q * (1 - lapse / 2)
    - lapse_rate = lapse * (1 - q / 2)
    - inforce_end = inforce_begin * (1 - death_rate - lapse_rate)
    """
    inforce_begin = [1.0]
    inforce_end: list[float] = []
    death_rates: list[float] = []
    lapse_rates: list[float] = []

    for t in range(term_years):
        age = issue_age + t
        if age not in q_by_age:
            raise ValueError(f"Missing mortality rate for age {age}.")
        q = q_by_age[age]
        death_rate = q * (1.0 - lapse_rate / 2.0)
        lapse_adj = lapse_rate * (1.0 - q / 2.0)
        inforce_next = inforce_begin[-1] * (1.0 - death_rate - lapse_adj)

        death_rates.append(death_rate)
        lapse_rates.append(lapse_adj)
        inforce_end.append(inforce_next)
        inforce_begin.append(inforce_next)

    return inforce_begin[:-1], inforce_end, death_rates, lapse_rates


def calc_irr(
    cashflows: Iterable[float],
    tol: float = 1e-12,
    rate_tol: float = 1e-12,
    max_iter: int = 200,
) -> float:
    """
    Compute IRR for annual cashflows using bisection.
    """
    flows = list(cashflows)
    if not flows:
        raise ValueError("Cashflows must be non-empty.")

    def npv(rate: float) -> float:
        return sum(cf / ((1.0 + rate) ** t) for t, cf in enumerate(flows))

    low = -0.999999
    high = 1.0
    f_low = npv(low)
    f_high = npv(high)
    while f_low * f_high > 0 and high < 1024:
        high *= 2.0
        f_high = npv(high)

    if f_low * f_high > 0:
        raise ValueError("IRR not bracketed.")

    for _ in range(max_iter):
        mid = (low + high) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
        if high - low < rate_tol:
            return (high + low) / 2.0

    raise ValueError("IRR did not converge.")


def run_profit_test(config: dict, base_dir: Path | None = None) -> ProfitTestResult:
    """
    Run profit test using the YAML config structure.
    """
    base_dir = base_dir or Path.cwd()

    product = config["product"]
    model_point = config["model_point"]
    pricing = config["pricing"]
    loadings = config["loading_alpha_beta_gamma"]
    profit_test_cfg = config.get("profit_test", {})

    issue_age = int(model_point["issue_age"])
    sex = str(model_point["sex"])
    term_years = int(product["term_years"])
    premium_paying_years = int(product["premium_paying_years"])
    sum_assured = int(product["sum_assured"])

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
    spot_curve_path = _resolve_path(
        base_dir, profit_test_cfg["discount_curve_path"]
    )

    pricing_rows = load_mortality_csv(pricing_mortality_path)
    actual_rows = load_mortality_csv(actual_mortality_path)
    spot_curve = load_spot_curve_csv(spot_curve_path)
    forward_rates = _forward_rates_from_spot(spot_curve, term_years)

    premiums = calc_endowment_premiums(
        mortality_rows=pricing_rows,
        sex=sex,
        issue_age=issue_age,
        term_years=term_years,
        premium_paying_years=premium_paying_years,
        interest_rate=pricing_interest,
        sum_assured=sum_assured,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
    )

    q_pricing = build_mortality_q_by_age(pricing_rows, sex)
    q_actual = build_mortality_q_by_age(actual_rows, sex)

    tV_pricing, tW_pricing, _ = _reserve_factors(
        q_by_age=q_pricing,
        issue_age=issue_age,
        term_years=term_years,
        premium_paying_years=premium_paying_years,
        interest_rate=pricing_interest,
        alpha=alpha,
    )
    tV_valuation, _, _ = _reserve_factors(
        q_by_age=q_pricing,
        issue_age=issue_age,
        term_years=term_years,
        premium_paying_years=premium_paying_years,
        interest_rate=valuation_interest,
        alpha=alpha,
    )

    inforce_begin, inforce_end, death_rates, lapse_rates = _inforce_series(
        q_by_age=q_actual,
        issue_age=issue_age,
        term_years=term_years,
        lapse_rate=lapse_rate,
    )

    records: list[dict[str, float | int]] = []
    for t in range(term_years):
        if t + 1 not in spot_curve:
            raise ValueError(f"Missing spot rate for t={t + 1}.")
        spot_rate = spot_curve[t + 1]
        forward_rate = forward_rates[t]

        inforce_beg = inforce_begin[t]
        inforce_end_t = inforce_end[t]
        q_t = death_rates[t]
        w_t = lapse_rates[t]

        is_premium_year = t < premium_paying_years

        premium_income = premiums.gross_annual_premium * inforce_beg if is_premium_year else 0.0
        net_premium_income = premiums.net_annual_premium * inforce_beg if is_premium_year else 0.0
        loading_income = premium_income - net_premium_income

        death_benefit = (
            inforce_beg * q_t * sum_assured if is_premium_year else 0.0
        )
        surrender_benefit = (
            inforce_beg
            * w_t
            * (tW_pricing[t] + tW_pricing[t + 1])
            / 2.0
            * sum_assured
            if is_premium_year
            else 0.0
        )
        maturity_benefit = (
            inforce_end_t * sum_assured if t == term_years - 1 else 0.0
        )

        # Acquisition expense: 0.5 * alpha for actual basis in Excel.
        expenses_acq = (0.5 * alpha * sum_assured) if t == 0 else 0.0
        expenses_maint = (
            inforce_beg * sum_assured * beta if is_premium_year else 0.0
        )
        expenses_coll = (
            inforce_beg * premiums.gross_annual_premium * gamma
            if is_premium_year
            else 0.0
        )
        expenses_total = expenses_acq + expenses_maint + expenses_coll

        reserve_begin = tV_valuation[t] * sum_assured
        reserve_end = tV_valuation[t + 1] * sum_assured
        reserve_change = (
            sum_assured
            * (inforce_end_t * tV_valuation[t + 1] - inforce_beg * tV_valuation[t])
            if is_premium_year
            else 0.0
        )

        investment_income = (
            (inforce_beg * tV_valuation[t] * sum_assured + premium_income - expenses_total)
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

        spot_df = (1.0 / (1.0 + spot_rate)) ** (t + 1)
        pv_net_cf = net_cf * spot_df

        records.append(
            {
                "t": t,
                "inforce_begin": inforce_beg,
                "inforce_end": inforce_end_t,
                "q_t": q_t,
                "lapse_t": w_t,
                "premium_income": premium_income,
                "net_premium_income": net_premium_income,
                "loading_income": loading_income,
                "death_benefit": death_benefit,
                "surrender_benefit": surrender_benefit,
                "maturity_benefit": maturity_benefit,
                "expenses_acq": expenses_acq,
                "expenses_maint": expenses_maint,
                "expenses_coll": expenses_coll,
                "expenses_total": expenses_total,
                "reserve_begin": reserve_begin,
                "reserve_end": reserve_end,
                "reserve_change": reserve_change,
                "investment_income": investment_income,
                "net_cf": net_cf,
                "spot_rate": spot_rate,
                "forward_rate": forward_rate,
                "spot_df": spot_df,
                "pv_net_cf": pv_net_cf,
            }
        )

    cashflow = pd.DataFrame(records)
    irr = calc_irr(cashflow["net_cf"].tolist())
    new_business_value = float(cashflow["pv_net_cf"].sum())

    return ProfitTestResult(
        cashflow=cashflow,
        irr=irr,
        new_business_value=new_business_value,
        premiums=premiums,
    )
