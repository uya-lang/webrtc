#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/direct_sender.uya
test -f src/webrtc_ffmpeg_direct_sender_test_main.uya
rg -Fq "export struct UyaDirectSender" src/webrtc/media/direct_sender.uya
rg -Fq "export fn rtp_packetize_encoded_frame" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.media.opus_rtp" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.media.vp8_rtp" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.rtp.rtp_packet" src/webrtc/media/direct_sender.uya
rg -Fq "Uya FFmpeg direct sender RTP packetizer tests passed" src/webrtc_ffmpeg_direct_sender_test_main.uya

../uya/bin/uya run src/webrtc_ffmpeg_direct_sender_test_main.uya

echo "Phase 21 Uya FFmpeg direct sender RTP packetizer checks passed"
