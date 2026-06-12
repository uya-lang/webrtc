#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/stats/types.uya
test -f src/webrtc_stats_types_test_main.uya

rg -q "export struct RtcPeerConnectionStats" src/webrtc/stats/types.uya
rg -q "export fn rtc_peer_connection_stats_make" src/webrtc/stats/types.uya
rg -q "export struct RtcTransportStats" src/webrtc/stats/types.uya
rg -q "export struct RtcDataChannelStats" src/webrtc/stats/types.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_stats_types_test_main.uya

echo "Phase 16 stats type checks passed"
