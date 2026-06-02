#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_peer_connection_loopback_main.uya

rg -q "export fn peer_connection_graceful_close" src/webrtc/peer_connection.uya
rg -q "export fn track_write_encoded_frame" src/webrtc/track.uya
rg -q "export fn sender_send_encoded_frame" src/webrtc/sender.uya
rg -q "export fn receiver_deliver_encoded_frame" src/webrtc/receiver.uya
rg -q -F "fn main() i32" src/webrtc_peer_connection_loopback_main.uya

/media/winger/_dde_home/winger/uya/uya/bin/uya run src/webrtc_peer_connection_loopback_main.uya

echo "Phase 14 peer connection loopback checks passed"
