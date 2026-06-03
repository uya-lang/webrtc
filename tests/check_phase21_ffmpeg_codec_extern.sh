#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/ffmpeg_codec.uya
test -f src/webrtc_ffmpeg_codec_boundary_test_main.uya

rg -Fq "optional FFmpeg libavcodec boundary" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_encoder_open" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_encode_audio" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_encode_video_i420" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_decode_audio" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_decode_video_i420" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_packet_to_encoded_frame" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_raw_audio_view_make" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_raw_video_i420_view_make" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "FFmpeg codec extern boundary tests passed" src/webrtc_ffmpeg_codec_boundary_test_main.uya

if rg -Fq "captureStream" src/webrtc/media/ffmpeg_codec.uya src/webrtc_ffmpeg_codec_boundary_test_main.uya; then
	printf '%s\n' "FFmpeg codec boundary must not depend on browser captureStream loopback" >&2
	exit 1
fi

../uya/bin/uya run src/webrtc_ffmpeg_codec_boundary_test_main.uya

echo "Phase 21 FFmpeg codec extern boundary checks passed"
