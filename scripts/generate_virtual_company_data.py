from __future__ import annotations

import argparse
from pathlib import Path

from pricing.virtual_company import VirtualCompanySpec, write_company_expense_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/company_expense.csv")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--years", type=int, default=5)
    args = parser.parse_args()

    spec = VirtualCompanySpec(start_year=args.start_year, years=args.years)
    out_path = write_company_expense_csv(Path(args.out), seed=args.seed, spec=spec)
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
