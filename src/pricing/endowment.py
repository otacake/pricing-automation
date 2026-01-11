from __future__ import annotations

"""
Endowment present value and premium calculations.

Notation
- x: issue age (years)
- n: term years
- m: premium paying years
- i: annual interest rate
- v = 1 / (1 + i)
- q_{x+t}: annual mortality rate
- p_{x:t}: survival probability from age x to t years (p_{x:0} = 1)

Formulas
- A_death = sum v^(t+0.5) * p_{x:t} * q_{x+t}
- A_maturity = v^n * p_{x:n}
- A = A_death + A_maturity
- a = sum v^t * p_{x:t} (annuity due)
- net_rate = A / a
- gross_rate = (net_rate + alpha / a + beta) / (1 - gamma)
"""

from dataclasses import dataclass

from .commutation import build_mortality_q_by_age, survival_probabilities


@dataclass(frozen=True)
class EndowmentPremiums:
    """
    Endowment calculation results.

    Units
    - A, a: present value factors per unit sum assured
    - net_rate / gross_rate: annual premium rate
    - net_annual_premium / gross_annual_premium / monthly_premium: JPY
    """

    A: float
    a: float
    net_rate: float
    gross_rate: float
    net_annual_premium: int
    gross_annual_premium: int
    monthly_premium: int


def calc_endowment_factors(
    q_by_age: dict[int, float],
    issue_age: int,
    term_years: int,
    premium_paying_years: int,
    interest_rate: float,
) -> tuple[float, float]:
    """
    Calculate A and a for an endowment product.

    Units
    - interest_rate: annual rate (e.g., 0.01 for 1%)
    - term_years / premium_paying_years: years
    """
    if term_years <= 0:
        raise ValueError("term_years must be positive.")
    if premium_paying_years <= 0:
        raise ValueError("premium_paying_years must be positive.")

    horizon = max(term_years, premium_paying_years)
    p = survival_probabilities(q_by_age, issue_age, horizon)
    v = 1.0 / (1.0 + interest_rate)

    death_pv = 0.0
    for t in range(term_years):
        age = issue_age + t
        # A_death: mid-year death benefit
        death_pv += (v ** (t + 0.5)) * p[t] * q_by_age[age]

    # A_maturity: end-of-year maturity benefit
    maturity_pv = (v ** term_years) * p[term_years]
    A = death_pv + maturity_pv

    annuity = 0.0
    for t in range(premium_paying_years):
        # a: annuity-due premium factor
        annuity += (v ** t) * p[t]

    return A, annuity


def calc_endowment_premiums(
    mortality_rows,
    sex: str,
    issue_age: int,
    term_years: int,
    premium_paying_years: int,
    interest_rate: float,
    sum_assured: int,
    alpha: float,
    beta: float,
    gamma: float,
) -> EndowmentPremiums:
    """
    Calculate endowment premium rates and rounded premiums.

    Units
    - sum_assured: JPY
    - alpha / beta / gamma: annual loading coefficients
    - sex: "male" / "female"
    """
    q_by_age = build_mortality_q_by_age(mortality_rows, sex)
    A, annuity = calc_endowment_factors(
        q_by_age=q_by_age,
        issue_age=issue_age,
        term_years=term_years,
        premium_paying_years=premium_paying_years,
        interest_rate=interest_rate,
    )
    if annuity <= 0.0:
        raise ValueError("Premium annuity factor must be positive.")

    # net_rate = A / a
    net_rate = A / annuity
    # gross_rate = (net_rate + alpha/a + beta) / (1 - gamma)
    gross_rate = (net_rate + alpha / annuity + beta) / (1.0 - gamma)

    net_annual = int(round(net_rate * sum_assured, 0))
    gross_annual = int(round(gross_rate * sum_assured, 0))
    monthly = int(round(gross_annual / 12.0, 0))

    return EndowmentPremiums(
        A=A,
        a=annuity,
        net_rate=net_rate,
        gross_rate=gross_rate,
        net_annual_premium=net_annual,
        gross_annual_premium=gross_annual,
        monthly_premium=monthly,
    )
