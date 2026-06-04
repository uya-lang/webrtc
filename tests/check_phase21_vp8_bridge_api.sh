#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

cleanup_generated_uya_cache() {
    if [ -d uya/lib/libc ] && [ -d uya/lib/std ] && ! git ls-files --error-unmatch uya >/dev/null 2>&1; then
        rm -rf uya
    fi
}

trap cleanup_generated_uya_cache EXIT
cleanup_generated_uya_cache

test -f src/webrtc/media/codec_bridge.uya
test -f src/webrtc/media/model.uya
test -f src/webrtc/media/vp8_codec_bridge.uya
test -f src/webrtc_media_codec_bridge_test_main.uya
test -f src/webrtc_media_vp8_codec_bridge_test_main.uya
test -d ../vp8/src/vp8

rg -Fq "export struct CodecBridgeVp8Yuv420View" src/webrtc/media/codec_bridge.uya
rg -Fq "export struct CodecBridgeVp8FrameView" src/webrtc/media/codec_bridge.uya
rg -Fq "export struct CodecBridgeVp8EncodeRequest" src/webrtc/media/codec_bridge.uya
rg -Fq "export struct CodecBridgeVp8DecodeRequest" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_vp8_yuv420_view_make" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_vp8_frame_view_make" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_vp8_frame_to_encoded_frame" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_vp8_encoded_frame_to_frame" src/webrtc/media/codec_bridge.uya
rg -Fq "CodecBridgeInvalidVp8YuvFrame" src/webrtc/media/codec_bridge.uya
rg -Fq "CodecBridgeInvalidVp8Frame" src/webrtc/media/codec_bridge.uya
rg -Fq "codec_bridge_vp8_frame_to_encoded_frame" src/webrtc_media_codec_bridge_test_main.uya
rg -Fq "codec_bridge_vp8_encoded_frame_to_frame" src/webrtc_media_codec_bridge_test_main.uya
rg -Fq "codec_bridge_vp8_yuv420_view_make" src/webrtc_media_codec_bridge_test_main.uya
rg -Fq "use vp8.api" src/webrtc/media/vp8_codec_bridge.uya
rg -Fq "use vp8.container.rtp_vp8" src/webrtc/media/vp8_codec_bridge.uya
rg -Fq "export fn vp8_codec_bridge_ready" src/webrtc/media/vp8_codec_bridge.uya
rg -Fq "export fn vp8_codec_bridge_encode_i420_to_frame" src/webrtc/media/vp8_codec_bridge.uya
rg -Fq "export fn vp8_codec_bridge_decode_frame_to_i420" src/webrtc/media/vp8_codec_bridge.uya
rg -Fq "export fn vp8_codec_bridge_parse_rtp_payload_descriptor" src/webrtc/media/vp8_codec_bridge.uya
rg -Fq "vp8_codec_bridge_encode_i420_to_frame" src/webrtc_media_vp8_codec_bridge_test_main.uya
rg -Fq "vp8_codec_bridge_rtp_reassemble_packet" src/webrtc_media_vp8_codec_bridge_test_main.uya

../uya/bin/uya run src/webrtc_media_codec_bridge_test_main.uya
tmp_pkg="build/legacy-vp8-bridge-test"
rm -rf "$tmp_pkg"
mkdir -p "$tmp_pkg/src"
cp -R src/. "$tmp_pkg/src/"
mkdir -p "$tmp_pkg/src/vp8"
cp -R ../vp8/src/vp8/. "$tmp_pkg/src/vp8/"
# Keep this as legacy staging until ../vp8 publishes a package-mode manifest that
# passes current Uya package-mode integer-cast checks.
../uya/bin/uya build "$tmp_pkg/src/webrtc_media_vp8_codec_bridge_test_main.uya" -o "$tmp_pkg/webrtc-vp8-bridge-test"
"$tmp_pkg/webrtc-vp8-bridge-test"
bash tests/check_phase21_opus_bridge_api.sh
