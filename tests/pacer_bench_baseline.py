#!/usr/bin/env python3
"""Validate phase 18 pacer queue benchmark baseline rows."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "benchmarks" / "baselines" / "bench_pacer.jsonl"
RUNNER = REPO_ROOT / "benchmarks" / "run.sh"
EXPECTED_ROWS = {"bench_pacer"}


def parse_jsonl(path: Path) -> list[dict]:
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def validate_rows(rows: list[dict], source: str) -> None:
    by_name = {row["name"]: row for row in rows if isinstance(row, dict) and "name" in row}
    missing = EXPECTED_ROWS.difference(by_name)
    if missing:
        raise AssertionError(f"{source}: missing expected rows: {sorted(missing)}")

    row = by_name["bench_pacer"]
    if row.get("suite") != "phase15":
        raise AssertionError(f"{source}: suite must be phase15")
    if row.get("unit") != "ns/op":
        raise AssertionError(f"{source}: unit must be ns/op")
    if row.get("allocations") != 0:
        raise AssertionError(f"{source}: allocations must be 0")
    if row.get("high_watermark") != 0:
        raise AssertionError(f"{source}: high_watermark must be 0")


def main() -> None:
    if not BASELINE.exists():
        raise AssertionError(f"baseline file not found: {BASELINE}")
    rows = parse_jsonl(BASELINE)
    validate_rows(rows, "bench_pacer.jsonl")

    with tempfile.NamedTemporaryFile(prefix="bench_pacer_", suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run([str(RUNNER), str(tmp_path)], cwd=str(REPO_ROOT), check=True)
        generated = parse_jsonl(tmp_path)
        validate_rows(generated, "benchmarks/run.sh output")
    finally:
        tmp_path.unlink(missing_ok=True)

    print("Pacer benchmark baseline assertions passed")


if __name__ == "__main__":
    main()
