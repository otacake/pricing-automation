from __future__ import annotations

"""
Commutation helpers for survival probabilities.

Notation
- x: issue age (years)
- t: elapsed years
- q_{x+t}: annual mortality rate
- p_{x:t}: survival probability from age x to t years (p_{x:0}=1)
"""

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Protocol


class _RowLike(Protocol):
    def __getitem__(self, key: str) -> object: ...


@dataclass(frozen=True)
class MortalityRow:
    """
    One mortality table row.

    Units
    - age: years
    - q_male / q_female: annual mortality rate (e.g., 0.003)
    """

    age: int
    q_male: float | None
    q_female: float | None


def _get_field(row: object, key: str) -> object:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _coerce_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _coerce_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(round(float(value)))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(round(float(text)))
        except ValueError:
            return None
    return None


def build_mortality_q_by_age(
    mortality_rows: Iterable[MortalityRow | Mapping[str, object]],
    sex: str,
) -> dict[int, float]:
    """
    Build an age-to-q mapping for the given sex.

    Units
    - sex: "male" / "female"
    - q: annual mortality rate
    """
    sex_key = {"male": "q_male", "female": "q_female"}.get(sex)
    if sex_key is None:
        raise ValueError(f"Unsupported sex: {sex}")

    q_by_age: dict[int, float] = {}
    for row in mortality_rows:
        age = _coerce_int(_get_field(row, "age"))
        if age is None:
            continue
        q_value = _coerce_float(_get_field(row, sex_key))
        if q_value is None:
            continue
        q_by_age[age] = q_value
    return q_by_age


def survival_probabilities(
    q_by_age: Mapping[int, float],
    issue_age: int,
    years: int,
) -> list[float]:
    """
    Build survival probabilities p_{x:t}.

    Units
    - issue_age: years
    - years: years
    - q_by_age: annual mortality rate by age
    """
    if years < 0:
        raise ValueError("years must be non-negative.")

    probs = [1.0]
    for t in range(years):
        age = issue_age + t
        if age not in q_by_age:
            raise ValueError(f"Missing mortality rate for age {age}.")
        q_value = q_by_age[age]
        # p_{x:t+1} = p_{x:t} * (1 - q_{x+t})
        probs.append(probs[-1] * (1.0 - q_value))
    return probs
