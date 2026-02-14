from __future__ import annotations

"""Path resolution helpers for reproducible CLI execution."""

from pathlib import Path


def resolve_base_dir_from_config(config_path: Path) -> Path:
    """
    Resolve the base directory used for relative input/output paths.

    The resolver prefers the nearest parent directory that contains
    ``pyproject.toml`` so that CLI execution does not depend on the
    current working directory.
    """
    resolved = config_path.expanduser().resolve()
    search_roots = [resolved.parent, *resolved.parents]
    for root in search_roots:
        if (root / "pyproject.toml").is_file():
            return root
    return resolved.parent
