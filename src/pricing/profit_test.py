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
from .config import read_loading_parameters
from .endowment import (
    EndowmentPremiums,
    LoadingFunctionParams,
    LoadingParameters,
    calc_endowment_premiums,
    calc_loading_parameters,
)

DEFAULT_VALUATION_INTEREST = 0.0025
DEFAULT_LAPSE_RATE = 0.03


@dataclass(frozen=True)
class ModelPoint:
    """
    Model point definition.

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


@dataclass(frozen=True)
class ExpenseAssumptions:
    """
    Expense assumptions estimated from company data.

    Units
    - year: calendar year
    - acq_per_policy: JPY per policy
    - maint_per_policy: JPY per policy-year
    - coll_rate: ratio per premium income
    """

    year: int
    acq_per_policy: float
    maint_per_policy: float
    coll_rate: float


@dataclass(frozen=True)
class ProfitTestResult:
    """
    Profit test outputs for one model point.

    Units
    - cashflow: annual cashflow table (JPY)
    - irr: internal rate of return (annual rate)
    - new_business_value: sum of discounted net cashflows (JPY)
    - premiums: endowment premiums and factors
    - pv_loading: discounted loading income (JPY)
    - pv_expense: discounted expense outflows (JPY)
    - loading_surplus: pv_loading - pv_expense (JPY)
    - premium_total: gross annual premium * premium years (JPY)
    - premium_to_maturity_ratio: premium_total / sum_assured
    """

    model_point: ModelPoint
    loadings: LoadingParameters
    cashflow: pd.DataFrame
    irr: float
    new_business_value: float
    premiums: EndowmentPremiums
    pv_loading: float
    pv_expense: float
    loading_surplus: float
    premium_total: float
    premium_to_maturity_ratio: float


@dataclass(frozen=True)
class ProfitTestBatchResult:
    """
    Profit test outputs for multiple model points.

    Units
    - summary: model-point summary table (JPY, rates)
    - expense_assumptions: company expense assumptions (if used)
    """

    results: list[ProfitTestResult]
    summary: pd.DataFrame
    expense_assumptions: ExpenseAssumptions | None


def _resolve_path(base_dir: Path, path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else base_dir / path


def load_company_expense_assumptions(
    path: Path,
    year: int | None,
    overhead_split_acq: float,
    overhead_split_maint: float,
) -> ExpenseAssumptions:
    """
    Estimate expense assumptions from company expense CSV.

    Units
    - acq_per_policy / maint_per_policy: JPY
    - coll_rate: ratio per premium income
    """
    if not path.is_file():
        raise ValueError(f"Company expense file not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError(f"Company expense file is empty: {path}")

    if year is None:
        row = df.iloc[0]
    else:
        matched = df[df["year"] == year]
        if matched.empty:
            raise ValueError(f"Company expense year not found: {year}")
        row = matched.iloc[0]

    new_policies = float(row["new_policies"])
    inforce_avg = float(row["inforce_avg"])
    premium_income = float(row["premium_income"])
    if new_policies <= 0 or inforce_avg <= 0 or premium_income <= 0:
        raise ValueError("Company expense denominators must be positive.")

    acq_per_policy = (
        float(row["acq_var_total"])
        + float(row["acq_fixed_total"])
        + float(row["overhead_total"]) * float(overhead_split_acq)
    ) / new_policies
    maint_per_policy = (
        float(row["maint_var_total"])
        + float(row["maint_fixed_total"])
        + float(row["overhead_total"]) * float(overhead_split_maint)
    ) / inforce_avg
    coll_rate = float(row["coll_var_total"]) / premium_income

    return ExpenseAssumptions(
        year=int(row["year"]),
        acq_per_policy=acq_per_policy,
        maint_per_policy=maint_per_policy,
        coll_rate=coll_rate,
    )


def model_point_label(model_point: ModelPoint) -> str:
    """
    Build a compact label for logs and tables.
    """
    return (
        f"{model_point.sex}_age{model_point.issue_age}"
        f"_term{model_point.term_years}"
    )


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


def _parse_model_points(config: Mapping[str, object]) -> list[ModelPoint]:
    product = config.get("product", {}) if isinstance(config, Mapping) else {}
    defaults = {
        "term_years": product.get("term_years"),
        "premium_paying_years": product.get("premium_paying_years"),
        "sum_assured": product.get("sum_assured"),
    }

    points_cfg = config.get("model_points") if isinstance(config, Mapping) else None
    if points_cfg is None:
        points_cfg = [config.get("model_point")] if isinstance(config, Mapping) else []

    if not points_cfg:
        raise ValueError("Model points are missing.")

    points: list[ModelPoint] = []
    for entry in points_cfg:
        if not isinstance(entry, Mapping):
            continue
        issue_age = int(entry["issue_age"])
        sex = str(entry["sex"])
        term_years = int(entry.get("term_years", defaults["term_years"]))
        premium_paying_years = int(
            entry.get("premium_paying_years", defaults["premium_paying_years"])
        )
        sum_assured = int(entry.get("sum_assured", defaults["sum_assured"]))
        points.append(
            ModelPoint(
                issue_age=issue_age,
                sex=sex,
                term_years=term_years,
                premium_paying_years=premium_paying_years,
                sum_assured=sum_assured,
            )
        )

    if not points:
        raise ValueError("Model points are missing.")
    return points


def _resolve_loading_parameters(
    config: Mapping[str, object],
    model_point: ModelPoint,
    loading_params: LoadingFunctionParams | None,
) -> LoadingParameters:
    if loading_params is not None:
        return calc_loading_parameters(
            loading_params,
            issue_age=model_point.issue_age,
            term_years=model_point.term_years,
            sex=model_point.sex,
        )

    params = read_loading_parameters(config) if isinstance(config, Mapping) else None
    if params is not None:
        return calc_loading_parameters(
            params,
            issue_age=model_point.issue_age,
            term_years=model_point.term_years,
            sex=model_point.sex,
        )

    loadings_cfg = config.get("loading_alpha_beta_gamma", {}) if isinstance(config, Mapping) else {}
    if not isinstance(loadings_cfg, Mapping):
        raise ValueError("loading_alpha_beta_gamma must be a mapping.")
    return LoadingParameters(
        alpha=float(loadings_cfg["alpha"]),
        beta=float(loadings_cfg["beta"]),
        gamma=float(loadings_cfg["gamma"]),
    )


def _load_expense_assumptions(
    config: Mapping[str, object],
    base_dir: Path,
) -> tuple[str, ExpenseAssumptions | None]:
    profit_test_cfg = config.get("profit_test", {}) if isinstance(config, Mapping) else {}
    expense_cfg = profit_test_cfg.get("expense_model", {}) if isinstance(profit_test_cfg, Mapping) else {}
    mode = str(expense_cfg.get("mode", "company"))

    if mode == "loading":
        return mode, None
    if mode != "company":
        raise ValueError(f"Unsupported expense model mode: {mode}")

    if "company_data_path" not in expense_cfg:
        raise ValueError("company_data_path is required for company expense model.")

    overhead_cfg = expense_cfg.get("overhead_split", {}) if isinstance(expense_cfg, Mapping) else {}
    overhead_split_acq = float(overhead_cfg.get("acquisition", 0.0))
    overhead_split_maint = float(overhead_cfg.get("maintenance", 0.0))
    year = expense_cfg.get("year")
    year_value = int(year) if year is not None else None

    expense_path = _resolve_path(base_dir, str(expense_cfg["company_data_path"]))
    assumptions = load_company_expense_assumptions(
        expense_path,
        year=year_value,
        overhead_split_acq=overhead_split_acq,
        overhead_split_maint=overhead_split_maint,
    )
    return mode, assumptions


def _build_summary(results: list[ProfitTestResult]) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for result in results:
        point = result.model_point
        rows.append(
            {
                "model_point": model_point_label(point),
                "sex": point.sex,
                "issue_age": point.issue_age,
                "term_years": point.term_years,
                "premium_paying_years": point.premium_paying_years,
                "sum_assured": point.sum_assured,
                "net_annual_premium": result.premiums.net_annual_premium,
                "gross_annual_premium": result.premiums.gross_annual_premium,
                "monthly_premium": result.premiums.monthly_premium,
                "irr": result.irr,
                "new_business_value": result.new_business_value,
                "pv_loading": result.pv_loading,
                "pv_expense": result.pv_expense,
                "loading_surplus": result.loading_surplus,
                "premium_total": result.premium_total,
                "premium_to_maturity_ratio": result.premium_to_maturity_ratio,
            }
        )
    return pd.DataFrame(rows)


def run_profit_test(
    config: dict,
    base_dir: Path | None = None,
    loading_params: LoadingFunctionParams | None = None,
) -> ProfitTestBatchResult:
    """
    Run profit test using the YAML config structure.

    Units
    - base_dir: root for relative file paths
    - loading_params: overrides loading function coefficients (not a premium scaling factor)
    """
    base_dir = base_dir or Path.cwd()

    product = config["product"]
    pricing = config["pricing"]
    profit_test_cfg = config.get("profit_test", {})

    model_points = _parse_model_points(config)

    interest_cfg = pricing["interest"]
    if interest_cfg.get("type") != "flat":
        raise ValueError("Only flat interest rate is supported.")
    pricing_interest = float(interest_cfg["flat_rate"])
    valuation_interest = float(
        profit_test_cfg.get("valuation_interest_rate", DEFAULT_VALUATION_INTEREST)
    )
    lapse_rate = float(profit_test_cfg.get("lapse_rate", DEFAULT_LAPSE_RATE))

    pricing_mortality_path = _resolve_path(base_dir, pricing["mortality_path"])
    actual_mortality_path = _resolve_path(
        base_dir, profit_test_cfg["mortality_actual_path"]
    )
    spot_curve_path = _resolve_path(base_dir, profit_test_cfg["discount_curve_path"])

    expense_mode, expense_assumptions = _load_expense_assumptions(config, base_dir)

    pricing_rows = load_mortality_csv(pricing_mortality_path)
    actual_rows = load_mortality_csv(actual_mortality_path)
    spot_curve = load_spot_curve_csv(spot_curve_path)
    results: list[ProfitTestResult] = []

    for model_point in model_points:
        loadings = _resolve_loading_parameters(config, model_point, loading_params)
        forward_rates = _forward_rates_from_spot(spot_curve, model_point.term_years)

        premiums = calc_endowment_premiums(
            mortality_rows=pricing_rows,
            sex=model_point.sex,
            issue_age=model_point.issue_age,
            term_years=model_point.term_years,
            premium_paying_years=model_point.premium_paying_years,
            interest_rate=pricing_interest,
            sum_assured=model_point.sum_assured,
            alpha=loadings.alpha,
            beta=loadings.beta,
            gamma=loadings.gamma,
        )

        q_pricing = build_mortality_q_by_age(pricing_rows, model_point.sex)
        q_actual = build_mortality_q_by_age(actual_rows, model_point.sex)

        tV_pricing, tW_pricing, _ = _reserve_factors(
            q_by_age=q_pricing,
            issue_age=model_point.issue_age,
            term_years=model_point.term_years,
            premium_paying_years=model_point.premium_paying_years,
            interest_rate=pricing_interest,
            alpha=loadings.alpha,
        )
        tV_valuation, _, _ = _reserve_factors(
            q_by_age=q_pricing,
            issue_age=model_point.issue_age,
            term_years=model_point.term_years,
            premium_paying_years=model_point.premium_paying_years,
            interest_rate=valuation_interest,
            alpha=loadings.alpha,
        )

        inforce_begin, inforce_end, death_rates, lapse_rates = _inforce_series(
            q_by_age=q_actual,
            issue_age=model_point.issue_age,
            term_years=model_point.term_years,
            lapse_rate=lapse_rate,
        )

        records: list[dict[str, float | int]] = []
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
                premiums.gross_annual_premium * inforce_beg if is_premium_year else 0.0
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

            if expense_mode == "company":
                if expense_assumptions is None:
                    raise ValueError("Expense assumptions are missing.")
                expenses_acq = (
                    expense_assumptions.acq_per_policy * inforce_beg
                    if t == 0
                    else 0.0
                )
                expenses_maint = expense_assumptions.maint_per_policy * inforce_beg
                expenses_coll = expense_assumptions.coll_rate * premium_income
            else:
                expenses_acq = (0.5 * loadings.alpha * model_point.sum_assured) if t == 0 else 0.0
                expenses_maint = (
                    inforce_beg * model_point.sum_assured * loadings.beta if is_premium_year else 0.0
                )
                expenses_coll = (
                    inforce_beg * premiums.gross_annual_premium * loadings.gamma
                    if is_premium_year
                    else 0.0
                )
            expenses_total = expenses_acq + expenses_maint + expenses_coll

            reserve_begin = tV_valuation[t] * model_point.sum_assured
            reserve_end = tV_valuation[t + 1] * model_point.sum_assured
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

            spot_df = (1.0 / (1.0 + spot_rate)) ** (t + 1)
            pv_net_cf = net_cf * spot_df
            pv_loading = loading_income * spot_df  # PV_loading for sufficiency check
            pv_expense = expenses_total * spot_df  # PV_expense for sufficiency check

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
                    "pv_loading": pv_loading,
                    "pv_expense": pv_expense,
                }
            )

        cashflow = pd.DataFrame(records)
        irr = calc_irr(cashflow["net_cf"].tolist())
        new_business_value = float(cashflow["pv_net_cf"].sum())
        pv_loading = float(cashflow["pv_loading"].sum())
        pv_expense = float(cashflow["pv_expense"].sum())
        loading_surplus = pv_loading - pv_expense
        premium_total = float(premiums.gross_annual_premium * model_point.premium_paying_years)
        premium_to_maturity_ratio = premium_total / float(model_point.sum_assured)  # Paid premium vs maturity check

        results.append(
            ProfitTestResult(
                model_point=model_point,
                loadings=loadings,
                cashflow=cashflow,
                irr=irr,
                new_business_value=new_business_value,
                premiums=premiums,
                pv_loading=pv_loading,
                pv_expense=pv_expense,
                loading_surplus=loading_surplus,
                premium_total=premium_total,
                premium_to_maturity_ratio=premium_to_maturity_ratio,
            )
        )

    summary = _build_summary(results)
    return ProfitTestBatchResult(
        results=results,
        summary=summary,
        expense_assumptions=expense_assumptions,
    )
