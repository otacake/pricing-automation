from __future__ import annotations

"""Append-only PDCA ledger."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Mapping


def stable_config_sha256(config: Mapping[str, object]) -> str:
    payload = json.dumps(config, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_ledger_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path)


def append_ledger_record(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(record)
    body.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    line = json.dumps(body, ensure_ascii=True, sort_keys=True, default=str)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def record_approval_hypotheses(
    path: Path,
    hypotheses: tuple[Mapping[str, object], ...] | list[Mapping[str, object]],
    *,
    loop_id: str,
    source: str,
    iteration: int,
    seed: int | None,
    config_sha256: str | None,
) -> None:
    for hypothesis in hypotheses:
        changes = hypothesis.get("changes", [])
        append_ledger_record(
            path,
            {
                "loop_id": loop_id,
                "source": source,
                "iteration": iteration,
                "candidate_id": str(hypothesis.get("hypothesis_id", "approval_required")),
                "change_class": "approval_required",
                "decision": "approval_required",
                "reason": str(hypothesis.get("reason", "approval_required")),
                "applied": False,
                "seed": seed,
                "config_sha256": config_sha256,
                "changes": changes,
                "incumbent_metrics": None,
                "candidate_metrics": None,
            },
        )
