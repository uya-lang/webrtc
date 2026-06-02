#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f benchmarks/bench_rtp_rtcp_parse.uya
test -x tests/rtp_bench_baseline.py

rg -q "export fn benchmark_main_emit_rtp_parse_jsonl" benchmarks/bench_rtp_rtcp_parse.uya
rg -q "export fn benchmark_main_emit_rtp_extension_parse_jsonl" benchmarks/bench_rtp_rtcp_parse.uya
rg -q "export fn benchmark_main_emit_rtcp_parse_jsonl" benchmarks/bench_rtp_rtcp_parse.uya

python3 tests/rtp_bench_baseline.py

echo "Phase 18 RTP/RTCP parser benchmark checks passed"
