#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/stats/collect.uya
test -f src/webrtc_stats_collect_test_main.uya

rg -q "export fn rtc_ice_candidate_pair_stats_collect" src/webrtc/stats/collect.uya
rg -q "export fn rtc_transport_stats_collect" src/webrtc/stats/collect.uya

../uya/bin/uya run src/webrtc_stats_collect_test_main.uya

echo "Phase 16 stats collect checks passed"
