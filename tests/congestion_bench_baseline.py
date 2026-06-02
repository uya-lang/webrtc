#!/usr/bin/env python3
"""Validate phase 15 congestion benchmark rows and scenario metrics."""

from __future__ import annotations

from pathlib import Path

from bench_validate_common import generated_rows, parse_jsonl, require_positive, validate_expected_rows

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "benchmarks" / "baselines" / "bench_congestion.jsonl"
EXPECTED_ROWS = {
    "bench_congestion_bandwidth_drop",
    "bench_congestion_bandwidth_recovery",
    "bench_congestion_queue_delay",
    "bench_congestion_loss",
    "bench_congestion_jitter",
}


def validate_rows(rows: list[dict], source: str) -> None:
    by_name = validate_expected_rows(rows, EXPECTED_ROWS, source)
    for name in sorted(EXPECTED_ROWS):
        row = by_name[name]
        if row.get("suite") != "phase15":
            raise AssertionError(f"{source}:{name}: suite must be phase15")
        if row.get("allocations") != 0:
            raise AssertionError(f"{source}:{name}: allocations must be 0")
        require_positive(row, "value", source)
    require_positive(by_name["bench_congestion_queue_delay"], "high_watermark", source)
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
    validate_rows(parse_jsonl(BASELINE), "bench_congestion.jsonl")
    validate_rows(generated_rows("bench_congestion_"), "benchmarks/run.sh output")
    print("congestion benchmark baseline assertions passed")


if __name__ == "__main__":
    main()
