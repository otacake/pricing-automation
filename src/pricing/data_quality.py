from __future__ import annotations

"""Gate A checks for pricing inputs.

Validates model-point identity, sum assured, and the CSV inputs referenced by a
config: required columns, numeric types, unit ranges, and non-negative planned
expense assumptions.
"""

from pathlib import Path
from typing import Mapping

import pandas as pd

from .profit_test import _resolve_path
from .validation import ValidationIssue

MORTALITY_COLUMNS = ("age", "q_male", "q_female")
SPOT_COLUMNS = ("t", "spot_rate")
EXPENSE_COLUMNS = (
    "year",
    "new_policies",
    "inforce_avg",
    "premium_income",
    "acq_var_total",
    "acq_fixed_total",
    "maint_var_total",
    "maint_fixed_total",
    "coll_var_total",
    "overhead_total",
)
EXPENSE_NONNEGATIVE_COLUMNS = (
    "acq_var_total",
    "acq_fixed_total",
    "maint_var_total",
    "maint_fixed_total",
    "coll_var_total",
    "overhead_total",
)
EXPENSE_POSITIVE_COLUMNS = ("new_policies", "inforce_avg", "premium_income")

Q_MIN = 0.0
Q_MAX = 1.0
SPOT_MIN = -0.05
SPOT_MAX = 0.25


class DataQualityError(ValueError):
    """Raised when Gate A rejects the inputs."""


def _issue(code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(level="error", code=code, path=path, message=message)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_float(value: object) -> float | None:
    if _is_missing(value) or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_csv(path: Path, issues: list[ValidationIssue], label: str) -> pd.DataFrame | None:
    if not path.is_file():
        issues.append(
            _issue(
                "missing_input_file",
                label,
                f"Input file not found: {path}",
            )
        )
        return None
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001 - surface a Gate A error, do not crash later
        issues.append(
            _issue(
                "unreadable_input_file",
                label,
                f"Could not read CSV {path}: {exc}",
            )
        )
        return None
    if frame.empty:
        issues.append(_issue("empty_input_file", label, f"Input file is empty: {path}"))
        return None
    return frame


def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    issues: list[ValidationIssue],
    label: str,
) -> bool:
    missing = [name for name in columns if name not in frame.columns]
    if not missing:
        return True
    issues.append(
        _issue(
            "missing_column",
            label,
            f"Missing required columns: {', '.join(missing)}",
        )
    )
    return False


def _validate_model_points(config: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    entries: list[object] = []
    model_points = config.get("model_points")
    model_point = config.get("model_point")
    if model_points is not None:
        if not isinstance(model_points, list):
            issues.append(
                _issue("invalid_model_points_type", "model_points", "model_points must be a list.")
            )
        else:
            entries.extend(model_points)
    if model_point is not None:
        entries.append(model_point)

    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"model_points[{index}]"
        if not isinstance(entry, Mapping):
            issues.append(
                _issue("invalid_model_point_entry", path, "Each model point must be a mapping.")
            )
            continue
        raw_id = entry.get("id")
        if raw_id is None or str(raw_id).strip() == "":
            issues.append(
                _issue(
                    "null_model_point_id",
                    f"{path}.id",
                    "Model point id is null or blank.",
                )
            )
            model_id = ""
        else:
            model_id = str(raw_id).strip()
            if model_id in seen:
                issues.append(
                    _issue(
                        "duplicate_model_point_id",
                        f"{path}.id",
                        f"Duplicate model point id: {model_id}",
                    )
                )
            else:
                seen.add(model_id)
        sum_assured = _as_float(entry.get("sum_assured"))
        if sum_assured is None or sum_assured <= 0.0:
            issues.append(
                _issue(
                    "sum_assured_not_positive",
                    f"{path}.sum_assured",
                    f"sum_assured must be > 0 for model point {model_id or index}.",
                )
            )


def _validate_mortality(frame: pd.DataFrame, issues: list[ValidationIssue], label: str) -> None:
    if not _require_columns(frame, MORTALITY_COLUMNS, issues, label):
        return
    ages: list[int] = []
    for index, row in frame.iterrows():
        row_path = f"{label}[{index}]"
        age_value = _as_float(row["age"])
        if age_value is None or not float(age_value).is_integer() or age_value < 0:
            issues.append(_issue("invalid_age", f"{row_path}.age", "age must be a non-negative integer."))
        else:
            ages.append(int(age_value))
        for column in ("q_male", "q_female"):
            q_value = _as_float(row[column])
            if q_value is None:
                issues.append(
                    _issue(
                        "invalid_mortality_q",
                        f"{row_path}.{column}",
                        f"{column} must be numeric.",
                    )
                )
                continue
            if q_value < Q_MIN or q_value > Q_MAX:
                issues.append(
                    _issue(
                        "mortality_q_out_of_range",
                        f"{row_path}.{column}",
                        f"{column} must be within [{Q_MIN}, {Q_MAX}] (annual rate).",
                    )
                )
    if ages:
        unique = sorted(set(ages))
        if len(unique) != len(ages):
            issues.append(_issue("duplicate_age", label, "Mortality ages must be unique."))
        expected = list(range(unique[0], unique[-1] + 1))
        if unique != expected:
            issues.append(
                _issue(
                    "age_not_contiguous",
                    label,
                    "Mortality ages must be contiguous from min(age) to max(age).",
                )
            )


def _validate_spot(frame: pd.DataFrame, issues: list[ValidationIssue], label: str) -> None:
    if not _require_columns(frame, SPOT_COLUMNS, issues, label):
        return
    terms: list[int] = []
    for index, row in frame.iterrows():
        row_path = f"{label}[{index}]"
        term = _as_float(row["t"])
        if term is None or not float(term).is_integer() or term < 1:
            issues.append(_issue("invalid_spot_tenor", f"{row_path}.t", "t must be an integer >= 1."))
        else:
            terms.append(int(term))
        rate = _as_float(row["spot_rate"])
        if rate is None:
            issues.append(
                _issue("invalid_spot_rate", f"{row_path}.spot_rate", "spot_rate must be numeric.")
            )
            continue
        if rate < SPOT_MIN or rate > SPOT_MAX:
            issues.append(
                _issue(
                    "spot_rate_out_of_range",
                    f"{row_path}.spot_rate",
                    f"spot_rate must be within [{SPOT_MIN}, {SPOT_MAX}] (annual rate).",
                )
            )
    if terms:
        unique = sorted(set(terms))
        if len(unique) != len(terms):
            issues.append(_issue("duplicate_spot_tenor", label, "Spot tenors must be unique."))
        expected = list(range(unique[0], unique[-1] + 1))
        if unique != expected or unique[0] != 1:
            issues.append(
                _issue(
                    "spot_tenor_not_contiguous",
                    label,
                    "Spot tenors must be contiguous integers starting at 1.",
                )
            )


def _validate_expenses(frame: pd.DataFrame, issues: list[ValidationIssue], label: str) -> None:
    if not _require_columns(frame, EXPENSE_COLUMNS, issues, label):
        return
    for index, row in frame.iterrows():
        row_path = f"{label}[{index}]"
        year = _as_float(row["year"])
        if year is None or not float(year).is_integer():
            issues.append(_issue("invalid_expense_year", f"{row_path}.year", "year must be an integer."))
        for column in EXPENSE_POSITIVE_COLUMNS:
            value = _as_float(row[column])
            if value is None or value <= 0.0:
                issues.append(
                    _issue(
                        "non_positive_expense_denominator",
                        f"{row_path}.{column}",
                        f"{column} must be a positive number.",
                    )
                )
        for column in EXPENSE_NONNEGATIVE_COLUMNS:
            value = _as_float(row[column])
            if value is None:
                issues.append(
                    _issue(
                        "invalid_planned_expense",
                        f"{row_path}.{column}",
                        f"{column} must be numeric.",
                    )
                )
                continue
            if value < 0.0:
                issues.append(
                    _issue(
                        "negative_planned_expense",
                        f"{row_path}.{column}",
                        f"Planned expense {column} must be >= 0.",
                    )
                )


def validate_input_data(config: Mapping[str, object], base_dir: Path) -> list[ValidationIssue]:
    """Return Gate A issues for config model points and referenced CSV inputs."""
    issues: list[ValidationIssue] = []
    _validate_model_points(config, issues)

    pricing = config.get("pricing") if isinstance(config.get("pricing"), Mapping) else {}
    profit_test = config.get("profit_test") if isinstance(config.get("profit_test"), Mapping) else {}
    expense_model = (
        profit_test.get("expense_model")
        if isinstance(profit_test.get("expense_model"), Mapping)
        else {}
    )

    mortality_path = pricing.get("mortality_path") if isinstance(pricing, Mapping) else None
    if isinstance(mortality_path, str) and mortality_path:
        frame = _read_csv(_resolve_path(base_dir, mortality_path), issues, "pricing.mortality_path")
        if frame is not None:
            _validate_mortality(frame, issues, "pricing.mortality_path")
    else:
        issues.append(
            _issue(
                "missing_input_file",
                "pricing.mortality_path",
                "pricing.mortality_path is required.",
            )
        )

    actual_path = profit_test.get("mortality_actual_path") if isinstance(profit_test, Mapping) else None
    if isinstance(actual_path, str) and actual_path:
        frame = _read_csv(
            _resolve_path(base_dir, actual_path),
            issues,
            "profit_test.mortality_actual_path",
        )
        if frame is not None:
            _validate_mortality(frame, issues, "profit_test.mortality_actual_path")
    else:
        issues.append(
            _issue(
                "missing_input_file",
                "profit_test.mortality_actual_path",
                "profit_test.mortality_actual_path is required.",
            )
        )

    spot_path = profit_test.get("discount_curve_path") if isinstance(profit_test, Mapping) else None
    if isinstance(spot_path, str) and spot_path:
        frame = _read_csv(
            _resolve_path(base_dir, spot_path),
            issues,
            "profit_test.discount_curve_path",
        )
        if frame is not None:
            _validate_spot(frame, issues, "profit_test.discount_curve_path")
    else:
        issues.append(
            _issue(
                "missing_input_file",
                "profit_test.discount_curve_path",
                "profit_test.discount_curve_path is required.",
            )
        )

    mode = str(expense_model.get("mode", "company")) if isinstance(expense_model, Mapping) else "company"
    if mode == "company":
        expense_path = expense_model.get("company_data_path") if isinstance(expense_model, Mapping) else None
        if isinstance(expense_path, str) and expense_path:
            frame = _read_csv(
                _resolve_path(base_dir, expense_path),
                issues,
                "profit_test.expense_model.company_data_path",
            )
            if frame is not None:
                _validate_expenses(frame, issues, "profit_test.expense_model.company_data_path")
        else:
            issues.append(
                _issue(
                    "missing_input_file",
                    "profit_test.expense_model.company_data_path",
                    "company_data_path is required when expense mode is company.",
                )
            )
    return issues


def raise_if_data_invalid(config: Mapping[str, object], base_dir: Path) -> None:
    issues = validate_input_data(config, base_dir)
    errors = [issue for issue in issues if issue.level == "error"]
    if not errors:
        return
    lines = [
        f"validate_data:error: [{issue.code}] {issue.path} - {issue.message}" for issue in errors
    ]
    raise DataQualityError("\n".join(lines))
