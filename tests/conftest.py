from __future__ import annotations

from pathlib import Path

import pytest

REAL_DATA_FILES = (
    Path(__file__).resolve().parents[1] / "data" / "mortality_pricing.csv",
    Path(__file__).resolve().parents[1] / "data" / "mortality_actual.csv",
    Path(__file__).resolve().parents[1] / "data" / "spot_curve_actual.csv",
    Path(__file__).resolve().parents[1] / "data" / "company_expense.csv",
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_data: requires gitignored data/*.csv or the golden workbook",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if all(path.is_file() for path in REAL_DATA_FILES):
        return
    skip = pytest.mark.skip(reason="real data/*.csv is absent")
    for item in items:
        if item.get_closest_marker("real_data") is not None:
            item.add_marker(skip)
