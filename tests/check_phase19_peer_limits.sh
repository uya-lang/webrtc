#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_peer_limits_test_main.uya
test -f src/webrtc/rtp/rtp_receiver_route.uya
test -f src/webrtc/track.uya
test -f src/webrtc/api.uya

rg -Fq "Peer SSRC/track/datachannel limit tests passed" src/webrtc_peer_limits_test_main.uya
rg -Fq "RTP_RECEIVER_ROUTE_MAX_ENTRIES" src/webrtc_peer_limits_test_main.uya
rg -Fq "TRACK_MAX_PENDING_FRAMES" src/webrtc_peer_limits_test_main.uya
rg -Fq "DATA_CHANNEL_MAX_BUFFERED_MESSAGES" src/webrtc_peer_limits_test_main.uya

../uya/bin/uya run src/webrtc_peer_limits_test_main.uya
../uya/bin/uya run src/webrtc_rtp_receiver_route_test_main.uya
../uya/bin/uya run src/webrtc_track_test_main.uya
../uya/bin/uya run src/webrtc_sctp_api_test_main.uya
