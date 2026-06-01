#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/runtime.uya
test -f src/webrtc/peer_connection.uya
test -f src/webrtc_rtc_runtime_test_main.uya
test -f src/webrtc_peer_connection_lifecycle_test_main.uya

rg -q "export struct PeerConnection" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_make" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_new" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_close" src/webrtc/peer_connection.uya
rg -q "export fn peer_connection_reset" src/webrtc/peer_connection.uya
rg -q -F "fn main() i32" src/webrtc_peer_connection_lifecycle_test_main.uya

../uya/bin/uya run src/webrtc_peer_connection_lifecycle_test_main.uya

echo "Phase 14 PeerConnection lifecycle checks passed"
