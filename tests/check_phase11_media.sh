#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d src/webrtc/media
test -f src/webrtc/media/model.uya
test -f src/webrtc/media/codec.uya
test -f src/webrtc/media/codec_bridge.uya
test -f src/webrtc/media/opus_rtp.uya
test -f src/webrtc/media/vp8_rtp.uya
test -f src/webrtc/media/h264_rtp.uya
test -f src/webrtc_media_model_test_main.uya
test -f src/webrtc_media_codec_test_main.uya
test -f src/webrtc_media_codec_bridge_test_main.uya
test -f src/webrtc_media_opus_rtp_test_main.uya
test -f src/webrtc_media_opus_rtp_golden_test_main.uya
test -f src/webrtc_media_vp8_rtp_test_main.uya
test -f src/webrtc_media_av1_rtp_test_main.uya
test -f src/webrtc_media_h264_rtp_test_main.uya

rg -q "export struct EncodedFrame" src/webrtc/media/model.uya
rg -q "export fn encoded_frame_make" src/webrtc/media/model.uya
rg -Fq "export struct VideoEncoder<Encoder>" src/webrtc/media/codec.uya
rg -Fq "export struct VideoDecoder<Decoder>" src/webrtc/media/codec.uya
rg -Fq "export struct AudioEncoder<Encoder>" src/webrtc/media/codec.uya
rg -Fq "export struct AudioDecoder<Decoder>" src/webrtc/media/codec.uya
rg -Fq "export struct CodecFrameQueue<Frame>" src/webrtc/media/codec.uya
rg -q "export fn raw_audio_frame_make" src/webrtc/media/codec.uya
rg -q "export fn raw_video_i420_frame_make" src/webrtc/media/codec.uya
rg -q "export fn codec_frame_queue_push" src/webrtc/media/codec.uya
rg -q "export fn codec_frame_queue_pull" src/webrtc/media/codec.uya
rg -q "export struct CodecBridgeBoundary" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_boundary_make" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_register_opus_adapter" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_register_vp8_adapter" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_clear" src/webrtc/media/codec_bridge.uya
rg -q "export fn codec_bridge_require_enabled" src/webrtc/media/codec_bridge.uya
rg -q "export struct OpusRtpPacketizeConfig" src/webrtc/media/opus_rtp.uya
rg -q "export struct OpusRtpSemantics" src/webrtc/media/opus_rtp.uya
rg -q "export fn opus_rtp_packetize" src/webrtc/media/opus_rtp.uya
rg -q "export fn opus_rtp_depacketize" src/webrtc/media/opus_rtp.uya
rg -q "export fn opus_rtp_validate_clock_rate_hz" src/webrtc/media/opus_rtp.uya
rg -q "export fn opus_rtp_semantics_apply_fmtp_param" src/webrtc/media/opus_rtp.uya
rg -q "export fn opus_rtp_duration_ms_from_samples" src/webrtc/media/opus_rtp.uya
rg -q "export fn opus_rtp_validate_packet_duration_ms" src/webrtc/media/opus_rtp.uya
rg -q "export struct Vp8RtpDescriptor" src/webrtc/media/vp8_rtp.uya
rg -q "export fn vp8_rtp_descriptor_parse" src/webrtc/media/vp8_rtp.uya
rg -q "export fn vp8_rtp_descriptor_write" src/webrtc/media/vp8_rtp.uya
rg -q "export struct Av1RtpDescriptor" src/webrtc/media/av1_rtp.uya
rg -q "export struct Av1RtpFrameMetadata" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_descriptor_make" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_frame_metadata_make" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_descriptor_parse" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_descriptor_write" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_descriptor_is_frame_start" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_descriptor_is_frame_end" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_descriptor_is_keyframe" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_frame_metadata_from_descriptor" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_frame_metadata_from_packet" src/webrtc/media/av1_rtp.uya
rg -q "export fn av1_rtp_packet_is_keyframe" src/webrtc/media/av1_rtp.uya
rg -q "export struct H264RtpStapAPacket" src/webrtc/media/h264_rtp.uya
rg -q "export fn h264_rtp_stap_a_parse" src/webrtc/media/h264_rtp.uya
rg -q "export fn h264_rtp_stap_a_write" src/webrtc/media/h264_rtp.uya
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

"${UYA:-./uya/bin/uya}" run src/webrtc_media_model_test_main.uya
"${UYA:-./uya/bin/uya}" run src/webrtc_media_codec_test_main.uya
"${UYA:-./uya/bin/uya}" run src/webrtc_media_codec_bridge_test_main.uya
"${UYA:-./uya/bin/uya}" run src/webrtc_media_opus_rtp_test_main.uya
"${UYA:-./uya/bin/uya}" run src/webrtc_media_opus_rtp_golden_test_main.uya
"${UYA:-./uya/bin/uya}" run src/webrtc_media_vp8_rtp_test_main.uya
"${UYA:-./uya/bin/uya}" run src/webrtc_media_av1_rtp_test_main.uya
"${UYA:-./uya/bin/uya}" run src/webrtc_media_h264_rtp_test_main.uya

echo "Phase 11 media model checks passed"
