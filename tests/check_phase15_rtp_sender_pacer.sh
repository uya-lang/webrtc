#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/rtp/rtp_sender.uya
test -f src/webrtc_rtp_sender_test_main.uya

rg -q "export struct RtpSenderPacedStamp" src/webrtc/rtp/rtp_sender.uya
rg -q "export fn rtp_sender_stamp_paced_packet" src/webrtc/rtp/rtp_sender.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_rtp_sender_test_main.uya

echo "Phase 15 RTP sender pacer checks passed"
