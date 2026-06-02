#!/usr/bin/env python3
"""Validate pacer queue benchmark rows and queue-depth metrics."""

from __future__ import annotations

from pathlib import Path

from bench_validate_common import generated_rows, parse_jsonl, require_positive, validate_expected_rows

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "benchmarks" / "baselines" / "bench_pacer.jsonl"
EXPECTED_ROWS = {"bench_pacer"}


def validate_rows(rows: list[dict], source: str) -> None:
    by_name = validate_expected_rows(rows, EXPECTED_ROWS, source)
    row = by_name["bench_pacer"]
    if row.get("suite") != "phase15":
        raise AssertionError(f"{source}: suite must be phase15")
    if row.get("unit") != "ns/op":
        raise AssertionError(f"{source}: unit must be ns/op")
    if row.get("allocations") != 0:
        raise AssertionError(f"{source}: allocations must be 0")
    require_positive(row, "value", source)
    require_positive(row, "packets_per_s", source)
    require_positive(row, "high_watermark", source)


def main() -> None:
    if not BASELINE.exists():
        raise AssertionError(f"baseline file not found: {BASELINE}")
    validate_rows(parse_jsonl(BASELINE), "bench_pacer.jsonl")
    validate_rows(generated_rows("bench_pacer_"), "benchmarks/run.sh output")
    print("Pacer benchmark baseline assertions passed")


if __name__ == "__main__":
    main()
