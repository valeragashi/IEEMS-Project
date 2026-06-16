"""Deterministic JSON helpers — all agents must use these for file I/O."""

import json
from pathlib import Path


def read_json(path: Path) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data: dict | list) -> None:
    """Write JSON deterministically: sorted keys, 2-space indent, no trailing spaces."""
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )