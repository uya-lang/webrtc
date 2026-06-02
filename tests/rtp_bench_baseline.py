#!/usr/bin/env python3
"""Validate RTP/RTCP parser benchmark rows and parser hot-path metrics."""

from __future__ import annotations

from pathlib import Path

from bench_validate_common import generated_rows, parse_jsonl, require_positive, validate_expected_rows

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE = REPO_ROOT / "benchmarks" / "baselines" / "bench_rtp_rtcp_parse.jsonl"
EXPECTED_ROWS = {"bench_rtp_parse", "bench_rtp_extension_parse", "bench_rtcp_parse"}


def validate_rows(rows: list[dict], source: str) -> None:
    by_name = validate_expected_rows(rows, EXPECTED_ROWS, source)
    for name in sorted(EXPECTED_ROWS):
        row = by_name[name]
        if row.get("suite") != "phase10":
            raise AssertionError(f"{source}:{name}: suite must be phase10")
        if row.get("unit") != "ns/packet":
            raise AssertionError(f"{source}:{name}: unit must be ns/packet")
        require_positive(row, "value", source)
        require_positive(row, "packets_per_s", source)
        if row.get("allocations") != 0:
            raise AssertionError(f"{source}:{name}: allocations must be 0")
        if row.get("high_watermark") != 0:
            raise AssertionError(f"{source}:{name}: high_watermark must be 0")


def main() -> None:
    if not BASELINE.exists():
        raise AssertionError(f"baseline file not found: {BASELINE}")
    validate_rows(parse_jsonl(BASELINE), "bench_rtp_rtcp_parse.jsonl")
    validate_rows(generated_rows("bench_rtp_"), "benchmarks/run.sh output")
    print("RTP/RTCP benchmark baseline assertions passed")


if __name__ == "__main__":
    main()
