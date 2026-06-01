#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d src/webrtc/media
test -f src/webrtc/media/model.uya
test -f src/webrtc/media/codec_bridge.uya
test -f src/webrtc_media_model_test_main.uya
test -f src/webrtc_media_codec_bridge_test_main.uya

rg -q "export struct EncodedFrame" src/webrtc/media/model.uya
rg -q "export fn encoded_frame_make" src/webrtc/media/model.uya
rg -q "export struct CodecBridgeBoundary" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_boundary_make" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_register_opus_adapter" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_register_vp8_adapter" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_clear" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_require_enabled" src/webrtc/media/codec_bridge.uya
rg -q "export struct CodecCapability" src/webrtc/media/model.uya
rg -q "export struct CodecCapabilitySet" src/webrtc/media/model.uya
rg -q "export struct CodecNegotiationResult" src/webrtc/media/model.uya
rg -q "export fn codec_capability_make" src/webrtc/media/model.uya
rg -q "export fn codec_capability_set_make" src/webrtc/media/model.uya
rg -q "export fn codec_negotiation_result_make" src/webrtc/media/model.uya
rg -q "export const MEDIA_KIND_AUDIO" src/webrtc/media/model.uya
rg -q "export const CODEC_ID_OPUS" src/webrtc/media/model.uya
rg -q "export fn codec_default_clock_rate_hz" src/webrtc/media/model.uya
rg -q "export fn codec_default_payload_type" src/webrtc/media/model.uya
rg -q "export fn codec_id_from_default_payload_type" src/webrtc/media/model.uya

../uya/bin/uya run src/webrtc_media_model_test_main.uya
../uya/bin/uya run src/webrtc_media_codec_bridge_test_main.uya

echo "Phase 11 media model checks passed"
