#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/stats/trace.uya
test -f src/webrtc_stats_trace_test_main.uya

rg -q "export struct RtcTraceEvent" src/webrtc/stats/trace.uya
rg -q "export fn rtc_trace_ring_push" src/webrtc/stats/trace.uya
rg -q "export fn rtc_trace_ring_pop" src/webrtc/stats/trace.uya

../uya/bin/uya run src/webrtc_stats_trace_test_main.uya

echo "Phase 16 trace ring checks passed"
