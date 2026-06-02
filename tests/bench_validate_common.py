#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "benchmarks" / "run.sh"


def parse_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or not line.startswith("{"):
            continue
        rows.append(json.loads(line))
    return rows


def validate_expected_rows(rows: list[dict], expected: set[str], source: str) -> dict[str, dict]:
    by_name = {row["name"]: row for row in rows if isinstance(row, dict) and "name" in row}
    missing = expected.difference(by_name)
    if missing:
        raise AssertionError(f"{source}: missing expected rows: {sorted(missing)}")
    return by_name


def require_positive(row: dict, key: str, source: str) -> None:
    value = row.get(key)
    if not isinstance(value, int) or value <= 0:
        raise AssertionError(f"{source}:{row.get('name')}: {key} must be > 0")


def generated_rows(prefix: str) -> list[dict]:
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        subprocess.run([str(RUNNER), str(tmp_path)], cwd=str(REPO_ROOT), check=True)
        return parse_jsonl(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
