#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/codec_bridge.uya
test -f src/webrtc/media/model.uya
test -f src/webrtc_media_codec_bridge_test_main.uya

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

../uya/bin/uya run src/webrtc_media_codec_bridge_test_main.uya
bash tests/check_phase21_opus_bridge_api.sh
