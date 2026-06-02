#!/usr/bin/env python3
"""Validate phase 15 congestion benchmark baseline rows and zero-allocation assertions."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "benchmarks" / "baselines" / "bench_congestion.jsonl"
RUNNER = REPO_ROOT / "benchmarks" / "run.sh"
EXPECTED_ROWS = {
    "bench_congestion_bandwidth_drop",
    "bench_congestion_bandwidth_recovery",
    "bench_congestion_queue_delay",
    "bench_congestion_loss",
    "bench_congestion_jitter",
}


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

    for name in sorted(EXPECTED_ROWS):
        row = by_name[name]
        if row.get("suite") != "phase15":
            raise AssertionError(f"{source}:{name}: suite must be phase15")
        if row.get("allocations") != 0:
            raise AssertionError(f"{source}:{name}: allocations must be 0")
        if row.get("high_watermark") != 0:
            raise AssertionError(f"{source}:{name}: high_watermark must be 0")

    if by_name["bench_congestion_bandwidth_drop"].get("unit") != "ms":
        raise AssertionError(f"{source}: bandwidth drop unit must be ms")
    if by_name["bench_congestion_bandwidth_recovery"].get("unit") != "ms":
        raise AssertionError(f"{source}: bandwidth recovery unit must be ms")
    if by_name["bench_congestion_queue_delay"].get("unit") != "ms":
        raise AssertionError(f"{source}: queue delay unit must be ms")
    if by_name["bench_congestion_loss"].get("unit") != "pct":
        raise AssertionError(f"{source}: loss unit must be pct")
    if by_name["bench_congestion_jitter"].get("unit") != "ms":
        raise AssertionError(f"{source}: jitter unit must be ms")


def main() -> None:
    if not BASELINE.exists():
        raise AssertionError(f"baseline file not found: {BASELINE}")
    rows = parse_jsonl(BASELINE)
    validate_rows(rows, "bench_congestion.jsonl")

    with tempfile.NamedTemporaryFile(prefix="bench_congestion_", suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run([str(RUNNER), str(tmp_path)], cwd=str(REPO_ROOT), check=True)
        generated = parse_jsonl(tmp_path)
        validate_rows(generated, "benchmarks/run.sh output")
    finally:
        tmp_path.unlink(missing_ok=True)

    print("congestion benchmark baseline assertions passed")


if __name__ == "__main__":
    main()
