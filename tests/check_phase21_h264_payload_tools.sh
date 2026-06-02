#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/h264_rtp.uya
test -f src/webrtc_media_h264_rtp_test_main.uya

rg -Fq "export fn h264_rtp_stap_a_parse" src/webrtc/media/h264_rtp.uya
rg -Fq "export fn h264_rtp_stap_a_write" src/webrtc/media/h264_rtp.uya
rg -Fq "export fn h264_rtp_fu_a_parse" src/webrtc/media/h264_rtp.uya
rg -Fq "export fn h264_rtp_fu_a_write" src/webrtc/media/h264_rtp.uya
rg -Fq "export fn h264_rtp_fu_a_reassembly_absorb" src/webrtc/media/h264_rtp.uya
rg -Fq "export fn h264_annexb_to_avcc" src/webrtc/media/h264_rtp.uya
rg -Fq "export fn h264_avcc_to_annexb" src/webrtc/media/h264_rtp.uya

if rg -n "h264_.*(encode|decode)|H264.*(Encoder|Decoder)|libx264|openh264" src/webrtc tests --glob '!tests/check_phase21_h264_payload_tools.sh'; then
    exit 1
fi

../uya/bin/uya run src/webrtc_media_h264_rtp_test_main.uya
bash tests/check_phase11_media.sh
