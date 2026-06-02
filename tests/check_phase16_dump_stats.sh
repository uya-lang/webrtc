#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_dump_stats_main.uya
test -f Makefile
make build >/dev/null

output_file="$(mktemp)"
trap 'rm -f "$output_file"' EXIT

./build/webrtc-uya dump-stats >"$output_file"

rg -q "peer_connection handle=" "$output_file"
rg -q "data_channel handle=" "$output_file"
rg -q "codec handle=" "$output_file"

echo "Phase 16 dump-stats checks passed"
