#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/peer_connection.uya
test -f src/webrtc_peer_connection_set_local_description_test_main.uya

rg -q "export fn peer_connection_set_local_description" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_local_description_bytes" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_local_description_len" src/webrtc/peer_connection.uya
rg -q -F "fn main() i32" src/webrtc_peer_connection_set_local_description_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_peer_connection_set_local_description_test_main.uya

echo "Phase 14 PeerConnection set_local_description checks passed"
