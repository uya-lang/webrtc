#!/usr/bin/env bash
set -euo pipefail

test -f src/webrtc_peer_connection_chrome_video_test_main.uya
rg -Fq "fn addTransceiver(self: &Self" src/webrtc/peer_connection.uya
rg -Fq "fn addTrack(self: &Self" src/webrtc/peer_connection.uya
rg -Fq "fn createOffer(self: &Self" src/webrtc/peer_connection.uya
rg -Fq "fn processSrtpPacket(self: &Self" src/webrtc/peer_connection.uya
rg -Fq "fn routeVideoFrame(self: &Self" src/webrtc/peer_connection.uya
rg -Fq "export fn peer_connection_add_track" src/webrtc/peer_connection.uya
rg -Fq "export fn peer_connection_process_srtp_packet" src/webrtc/peer_connection.uya
rg -Fq "pc.createOffer" src/webrtc_peer_connection_chrome_video_test_main.uya
rg -Fq "pc.addTransceiver" src/webrtc_peer_connection_chrome_video_test_main.uya
rg -Fq "pc.processSrtpPacket" src/webrtc_peer_connection_chrome_video_test_main.uya
rg -Fq "m=video 9 UDP/TLS/RTP/SAVPF" src/webrtc/peer_connection.uya
rg -q -F "fn main() i32" src/webrtc_peer_connection_chrome_video_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_peer_connection_chrome_video_test_main.uya

echo "Phase 14 PeerConnection Chrome video checks passed"
