#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/peer_connection.uya
test -f src/webrtc_peer_connection_get_stats_test_main.uya

rg -q "export fn peer_connection_get_stats" src/webrtc/peer_connection.uya
rg -q "sender_count: usize" src/webrtc/peer_connection.uya
rg -q "receiver_count: usize" src/webrtc/peer_connection.uya
! sed -n '/export fn peer_connection_get_stats/,/return;/p' src/webrtc/peer_connection.uya | rg -q "peer_connection_sender_count|peer_connection_receiver_count"

"${UYA:-./uya/bin/uya}" run src/webrtc_peer_connection_get_stats_test_main.uya

echo "Phase 16 get_stats checks passed"
