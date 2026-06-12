#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/peer_connection.uya
test -f src/webrtc/api.uya
test -f src/webrtc_peer_connection_data_channel_event_test_main.uya

rg -q "export struct PeerConnectionDataChannelEvent" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_create_data_channel" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_data_channel_event_count" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_pop_data_channel_event" src/webrtc/peer_connection.uya
rg -q -F "fn main() i32" src/webrtc_peer_connection_data_channel_event_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_peer_connection_data_channel_event_test_main.uya

echo "Phase 14 DataChannel event checks passed"
