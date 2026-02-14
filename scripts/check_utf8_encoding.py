from __future__ import annotations

"""
Scan repository text files and report UTF-8 decode issues / BOM usage.
"""

import argparse
from pathlib import Path
import sys


TARGET_SUFFIXES = {
    ".md",
    ".py",
    ".ps1",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
}

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "build",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check UTF-8 decode and BOM usage.")
    parser.add_argument("--root", type=str, default=".", help="Repository root path.")
    parser.add_argument(
        "--fail-on-bom",
        action="store_true",
        help="Return non-zero when UTF-8 BOM is detected.",
    )
    parser.add_argument(
        "--include-out",
        action="store_true",
        help="Include out/ and reports/ generated artifacts.",
    )
    return parser.parse_args()


def _iter_target_files(root: Path, include_out: bool) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in relative_parts):
            continue
        if not include_out and relative_parts and relative_parts[0] in {"out", "reports"}:
            continue
        if path.suffix.lower() not in TARGET_SUFFIXES:
            continue
        files.append(path)
    return files


def main() -> int:
    args = _parse_args()
    root = Path(args.root).expanduser().resolve()

    decode_errors: list[str] = []
    bom_files: list[str] = []
    checked_count = 0

    for file_path in _iter_target_files(root, include_out=bool(args.include_out)):
        checked_count += 1
        data = file_path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            bom_files.append(str(file_path.relative_to(root).as_posix()))
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            decode_errors.append(
                f"{file_path.relative_to(root).as_posix()}: {exc.reason} at byte {exc.start}"
            )

    print(f"checked_files: {checked_count}")
    if bom_files:
        print("bom_files:")
        for item in bom_files:
            print(f"- {item}")
    if decode_errors:
        print("decode_errors:")
        for item in decode_errors:
            print(f"- {item}")

    if decode_errors:
        return 1
    if args.fail_on_bom and bom_files:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

