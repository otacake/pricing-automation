from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pricing.reporting.procon_rules import build_procon_bundle, validate_procon_cardinality


def test_build_procon_bundle_has_fixed_cardinality() -> None:
    bundle = build_procon_bundle(
        alternative_id="recommended",
        objective_mode="maximize_min_irr",
        metrics={
            "min_irr": 0.03,
            "min_nbv": 120000.0,
            "min_loading_surplus_ratio": -0.02,
            "max_premium_to_maturity": 1.03,
            "violation_count": 0,
        },
        peer_metrics={
            "min_irr": 0.028,
            "min_nbv": 100000.0,
            "min_loading_surplus_ratio": -0.04,
            "max_premium_to_maturity": 1.04,
            "violation_count": 1,
        },
        quant_count=3,
        qual_count=3,
        language="ja",
    )
    assert len(bundle["pros"]["quant"]) == 3
    assert len(bundle["cons"]["quant"]) == 3
    assert len(bundle["pros"]["qual"]) == 3
    assert len(bundle["cons"]["qual"]) == 3


def test_validate_procon_cardinality() -> None:
    payload = {
        "recommended": {
            "pros": {"quant": [1, 2, 3], "qual": [1, 2, 3]},
            "cons": {"quant": [1, 2, 3], "qual": [1, 2, 3]},
        }
    }
    assert validate_procon_cardinality(procon_map=payload, quant_count=3, qual_count=3) is True
    broken = {
        "recommended": {
            "pros": {"quant": [1], "qual": [1, 2, 3]},
            "cons": {"quant": [1, 2, 3], "qual": [1, 2, 3]},
        }
    }
    assert validate_procon_cardinality(procon_map=broken, quant_count=3, qual_count=3) is False
