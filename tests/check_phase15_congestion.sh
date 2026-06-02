#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f benchmarks/bench_congestion.uya
test -f benchmarks/baselines/bench_congestion.jsonl
test -x tests/congestion_bench_baseline.py

rg -q "export fn benchmark_main_emit_congestion_bandwidth_drop_jsonl" benchmarks/bench_congestion.uya
rg -q "export fn benchmark_main_emit_congestion_bandwidth_recovery_jsonl" benchmarks/bench_congestion.uya
rg -q "export fn benchmark_main_emit_congestion_queue_delay_jsonl" benchmarks/bench_congestion.uya
rg -q "export fn benchmark_main_emit_congestion_loss_jsonl" benchmarks/bench_congestion.uya
rg -q "export fn benchmark_main_emit_congestion_jitter_jsonl" benchmarks/bench_congestion.uya

python3 tests/congestion_bench_baseline.py

echo "Phase 15 congestion benchmark checks passed"
