#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f benchmarks/bench_rtp_loopback.uya
test -f benchmarks/baselines/bench_rtp_loopback.jsonl
test -x tests/rtp_loopback_bench_baseline.py

rg -q "export fn benchmark_main_emit_rtp_loopback_jsonl" benchmarks/bench_rtp_loopback.uya

python3 tests/rtp_loopback_bench_baseline.py

echo "Phase 18 RTP loopback benchmark checks passed"
