#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"

tmp_main="src/_repro_vp8_codegen_crash_main.uya"
trap 'rm -f "$tmp_main"' EXIT

cp src/webrtc_media_vp8_rtp_test_main.uya "$tmp_main"
perl -0777 -i -pe 's/var empty_payload: \[byte: 1\] = \[\];\n    const short_check: !bool = vp8_rtp_payload_is_keyframe\(empty_payload\[0:0\]\);/var short_packet: [byte: 1] = [0x10 as byte];\n    const short_check: !bool = vp8_rtp_packet_is_keyframe(short_packet[0:1]);/s' "$tmp_main"

../uya/bin/uya run "$tmp_main"
