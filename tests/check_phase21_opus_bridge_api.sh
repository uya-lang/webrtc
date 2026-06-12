#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/codec_bridge.uya
test -f src/webrtc/media/model.uya
test -f src/webrtc_media_codec_bridge_test_main.uya

rg -Fq "export struct CodecBridgeOpusPcmView" src/webrtc/media/codec_bridge.uya
rg -Fq "export struct CodecBridgeOpusPacketView" src/webrtc/media/codec_bridge.uya
rg -Fq "export struct CodecBridgeOpusEncodeRequest" src/webrtc/media/codec_bridge.uya
rg -Fq "export struct CodecBridgeOpusDecodeRequest" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_opus_pcm_view_make" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_opus_packet_view_make" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_opus_packet_to_encoded_frame" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_opus_encoded_frame_to_packet" src/webrtc/media/codec_bridge.uya
rg -Fq "CodecBridgeInvalidOpusPcm" src/webrtc/media/codec_bridge.uya
rg -Fq "CodecBridgeInvalidOpusPacket" src/webrtc/media/codec_bridge.uya
rg -Fq "CodecBridgeInvalidEncodedFrame" src/webrtc/media/codec_bridge.uya
rg -Fq "codec_bridge_opus_packet_to_encoded_frame" src/webrtc_media_codec_bridge_test_main.uya
rg -Fq "codec_bridge_opus_encoded_frame_to_packet" src/webrtc_media_codec_bridge_test_main.uya
rg -Fq "codec_bridge_opus_pcm_view_make" src/webrtc_media_codec_bridge_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_media_codec_bridge_test_main.uya
bash tests/check_phase21_codec_bridge_feature_gate.sh
