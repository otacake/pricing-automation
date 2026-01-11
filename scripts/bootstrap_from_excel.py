from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_XLSX = REPO_ROOT / "data" / "golden" / "養老保険_収益性_RORC.xlsx"
OUTPUT_DIR = REPO_ROOT / "data"


@dataclass(frozen=True)
class MortalityGroup:
    header_row: int
    age_col: int
    male_col: int
    female_col: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract CSV inputs from the golden Excel file."
    )
    parser.add_argument(
        "--xlsx",
        default=str(DEFAULT_XLSX),
        help="Path to the Excel file (default: data/golden/養老保険_収益性_RORC.xlsx).",
    )
    return parser.parse_args()


def coerce_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text.startswith("="):
            return None
        try:
            return float(text.replace(",", ""))
        except ValueError:
            return None
    return None


def format_int(value: int | float | None) -> str:
    if value is None or isinstance(value, bool):
        return ""
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return ""


def format_float(value: int | float | None) -> str:
    if value is None or isinstance(value, bool):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(number):
        return ""
    text = f"{number:.15f}".rstrip("0").rstrip(".")
    return text if text else "0"


def is_label(value: object, keyword: str) -> bool:
    if not isinstance(value, str):
        return False
    return keyword in value.replace(" ", "")


def find_mortality_groups(ws) -> list[MortalityGroup]:
    groups: list[MortalityGroup] = []
    max_rows = min(50, ws.max_row)
    max_cols = min(50, ws.max_column)
    for row in range(1, max_rows + 1):
        for col in range(1, max_cols + 1):
            if not is_label(ws.cell(row, col).value, "年齢"):
                continue
            if not is_label(ws.cell(row, col + 1).value, "男性"):
                continue
            female_col = None
            if is_label(ws.cell(row, col + 2).value, "女性"):
                female_col = col + 2
            groups.append(
                MortalityGroup(
                    header_row=row,
                    age_col=col,
                    male_col=col + 1,
                    female_col=female_col,
                )
            )
    groups.sort(key=lambda g: g.age_col)
    return groups


def extract_mortality_rows(ws, group: MortalityGroup) -> list[tuple[int, float | None, float | None]]:
    start_row = group.header_row + 1
    rows: list[tuple[int, float | None, float | None]] = []
    started = False
    for row in range(start_row, ws.max_row + 1):
        male_value = coerce_number(ws.cell(row, group.male_col).value)
        female_value = None
        if group.female_col is not None:
            female_value = coerce_number(ws.cell(row, group.female_col).value)
        if male_value is None and female_value is None:
            if started:
                break
            continue
        started = True
        age_value = coerce_number(ws.cell(row, group.age_col).value)
        if age_value is None:
            age_value = row - start_row
        rows.append((int(round(age_value)), male_value, female_value))
    return rows


def extract_spot_curve(ws, spot_col: int = 18) -> list[tuple[int, float]]:
    rows: list[tuple[int, float]] = []
    started = False
    t = 1
    for row in range(1, ws.max_row + 1):
        value = coerce_number(ws.cell(row, spot_col).value)
        if value is None:
            if started:
                break
            continue
        started = True
        rows.append((t, value / 100.0))
        t += 1
    return rows


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows) + 1


def print_preview(path: Path, row_count: int, max_lines: int = 5) -> None:
    display_path = path
    try:
        display_path = path.relative_to(REPO_ROOT)
    except ValueError:
        pass
    print(str(display_path))
    print(f"rows: {row_count}")
    with path.open("r", encoding="utf-8") as handle:
        for _ in range(max_lines):
            line = handle.readline()
            if not line:
                break
            print(line.rstrip("\r\n"))
    print("")


def main() -> int:
    args = parse_args()
    xlsx_path = Path(args.xlsx)
    if not xlsx_path.is_file():
        print(f"File not found: {xlsx_path}", file=sys.stderr)
        return 2

    try:
        workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
        mortality_ws = workbook["死亡率"]
        spot_ws = workbook["収益性検証_基礎率"]
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 3

    try:
        groups = find_mortality_groups(mortality_ws)
        if not groups:
            raise ValueError("Mortality headers not found.")
        pricing_group = groups[0]
        actual_group = groups[1] if len(groups) > 1 else None
        if actual_group is None:
            raise ValueError("Actual mortality headers not found.")

        pricing_rows_raw = extract_mortality_rows(mortality_ws, pricing_group)
        actual_rows_raw = extract_mortality_rows(mortality_ws, actual_group)
        spot_rows_raw = extract_spot_curve(spot_ws)

        pricing_rows = [
            [format_int(age), format_float(male), format_float(female)]
            for age, male, female in pricing_rows_raw
        ]
        actual_rows = [
            [format_int(age), format_float(male), format_float(female)]
            for age, male, female in actual_rows_raw
        ]
        spot_rows = [
            [format_int(t), format_float(rate)] for t, rate in spot_rows_raw
        ]
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 3
    finally:
        try:
            workbook.close()
        except Exception:
            pass

    outputs = [
        (OUTPUT_DIR / "mortality_pricing.csv", ["age", "q_male", "q_female"], pricing_rows),
        (OUTPUT_DIR / "mortality_actual.csv", ["age", "q_male", "q_female"], actual_rows),
        (OUTPUT_DIR / "spot_curve_actual.csv", ["t", "spot_rate"], spot_rows),
    ]

    for path, header, rows in outputs:
        row_count = write_csv(path, header, rows)
        print_preview(path, row_count)

    return 0


if __name__ == "__main__":
    sys.exit(main())
