#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/av1_rtp.uya
test -f src/webrtc_media_av1_rtp_test_main.uya

rg -Fq "export fn av1_rtp_descriptor_parse" src/webrtc/media/av1_rtp.uya
rg -Fq "export fn av1_rtp_descriptor_write" src/webrtc/media/av1_rtp.uya
rg -Fq "export fn av1_rtp_frame_metadata_from_descriptor" src/webrtc/media/av1_rtp.uya
rg -Fq "export fn av1_rtp_frame_metadata_from_packet" src/webrtc/media/av1_rtp.uya
rg -Fq "export fn av1_rtp_packet_is_keyframe" src/webrtc/media/av1_rtp.uya

if rg -n "av1_.*(encode|decode)|AV1.*(Encoder|Decoder)|libaom|dav1d|rav1e|SVT-AV1|svt_av1|aom_codec|dav1d_" src/webrtc tests --glob '!tests/check_phase21_av1_payload_tools.sh'; then
    exit 1
fi

../uya/bin/uya run src/webrtc_media_av1_rtp_test_main.uya
bash tests/check_phase11_media.sh
