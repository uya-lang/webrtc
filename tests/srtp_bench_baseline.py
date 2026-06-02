#!/usr/bin/env python3
"""Validate SRTP benchmark rows and nonzero transport/security metrics."""

from __future__ import annotations

from pathlib import Path

from bench_validate_common import generated_rows, parse_jsonl, require_positive, validate_expected_rows

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "benchmarks" / "baselines" / "bench_srtp.jsonl"
EXPECTED_ROWS = {"bench_srtp_protect", "bench_srtp_unprotect", "bench_srtp_replay_check"}


def validate_rows(rows: list[dict], source: str) -> None:
    by_name = validate_expected_rows(rows, EXPECTED_ROWS, source)
    for name in sorted(EXPECTED_ROWS):
        row = by_name[name]
        if row.get("suite") != "phase9":
            raise AssertionError(f"{source}:{name}: suite must be phase9")
        if row.get("unit") != "ns/op":
            raise AssertionError(f"{source}:{name}: unit must be ns/op")
        if row.get("allocations") != 0:
            raise AssertionError(f"{source}:{name}: allocations must be 0")
        require_positive(row, "value", source)
        require_positive(row, "packets_per_s", source)
        require_positive(row, "p95_ns", source)
        require_positive(row, "p99_ns", source)
        if name != "bench_srtp_replay_check":
            require_positive(row, "throughput_mb_s", source)


def main() -> None:
    if not BASELINE.exists():
        raise AssertionError(f"baseline file not found: {BASELINE}")
    validate_rows(parse_jsonl(BASELINE), "bench_srtp.jsonl")
    validate_rows(generated_rows("bench_srtp_"), "benchmarks/run.sh output")
    print("SRTP benchmark baseline assertions passed")


if __name__ == "__main__":
    main()
