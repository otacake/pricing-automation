from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.sweep_ptm import load_model_points, sweep_premium_to_maturity, sweep_premium_to_maturity_all


def test_sweep_ptm_outputs_rows_and_no_nan(tmp_path: Path) -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    label = "male_age30_term35"
    start = 1.0
    end = 1.02
    step = 0.01

    out_path = tmp_path / "sweep.csv"
    df, _ = sweep_premium_to_maturity(
        config=config,
        base_dir=REPO_ROOT,
        model_point_label=label,
        start=start,
        end=end,
        step=step,
        irr_threshold=0.0,
        out_path=out_path,
    )

    expected_rows = int(round((end - start) / step)) + 1
    assert len(df) == expected_rows
    assert not df.isna().any().any()

    sum_assured = 3000000
    premium_paying_years = 35
    for row in df.itertuples(index=False):
        expected = int(round(row.r * sum_assured / premium_paying_years, 0))
        assert row.gross_annual_premium == expected


def test_sweep_ptm_invalid_model_point() -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    with pytest.raises(ValueError):
        sweep_premium_to_maturity(
            config=config,
            base_dir=REPO_ROOT,
            model_point_label="unknown_point",
            start=1.0,
            end=1.01,
            step=0.01,
            irr_threshold=0.0,
            out_path=REPO_ROOT / "out" / "tmp.csv",
        )


def test_sweep_ptm_all_model_points_rows(tmp_path: Path) -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    points = load_model_points(config)

    out_path = tmp_path / "all.csv"
    df, _ = sweep_premium_to_maturity_all(
        config=config,
        base_dir=REPO_ROOT,
        start=1.0,
        end=1.02,
        step=0.01,
        irr_threshold=0.0,
        nbv_threshold=0.0,
        loading_surplus_ratio_threshold=-1.0,
        premium_to_maturity_hard_max=2.0,
        out_path=out_path,
    )

    expected_rows = len(points) * 3
    assert len(df) == expected_rows


def test_sweep_ptm_all_model_points_not_found(tmp_path: Path) -> None:
    config_path = REPO_ROOT / "configs" / "trial-001.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    out_path = tmp_path / "all.csv"
    _, min_r_by_id = sweep_premium_to_maturity_all(
        config=config,
        base_dir=REPO_ROOT,
        start=1.0,
        end=1.01,
        step=0.01,
        irr_threshold=1.0,
        nbv_threshold=1e12,
        loading_surplus_ratio_threshold=1.0,
        premium_to_maturity_hard_max=1.0,
        out_path=out_path,
    )

    assert all(value is None for value in min_r_by_id.values())
