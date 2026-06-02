#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f benchmarks/bench_pacer.uya
test -f benchmarks/baselines/bench_pacer.jsonl
test -x tests/pacer_bench_baseline.py

rg -q "export fn benchmark_main_emit_pacer_jsonl" benchmarks/bench_pacer.uya

python3 tests/pacer_bench_baseline.py

echo "Phase 18 pacer queue benchmark checks passed"
