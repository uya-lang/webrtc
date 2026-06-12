#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_file="${1:-$repo_root/build/benchmarks/baseline.jsonl}"

mkdir -p "$(dirname "$out_file")"
: > "$out_file"

run_bench() {
    local source_file="$1"
    (
        cd "$repo_root"
        "${UYA:-./uya/bin/uya}" run "$source_file"
    ) | rg '^\{' >> "$out_file"
}

run_bench src/webrtc_crypto_bench_main.uya
run_bench src/webrtc_srtp_bench_main.uya
run_bench src/webrtc_bench_runner_main.uya
(
    cd "$repo_root"
    python3 tests/bench_external_runner.py
) >> "$out_file"
