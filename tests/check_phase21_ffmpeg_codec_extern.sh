#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

prepare_ffmpeg_dev_tree() {
	local dev_root=".uyacache/ffmpeg-dev"
	local include_root="$dev_root/usr/include/x86_64-linux-gnu"
	local lib_root="$dev_root/usr/lib/x86_64-linux-gnu"

	if [ -f "$include_root/libavcodec/avcodec.h" ] && [ -e "$lib_root/libavcodec.so" ] && [ -e "$lib_root/libavutil.so" ]; then
		return 0
	fi

	rm -rf "$dev_root"
	mkdir -p "$dev_root/download"
	if ! command -v apt >/dev/null 2>&1 || ! command -v dpkg-deb >/dev/null 2>&1; then
		printf '%s\n' "FFmpeg extern codec test requires apt and dpkg-deb to prepare libavcodec-dev/libavutil-dev without sudo" >&2
		return 1
	fi

	(
		cd "$dev_root/download"
		apt download libavcodec-dev libavutil-dev
	)
	for deb in "$dev_root"/download/*.deb; do
		dpkg-deb -x "$deb" "$dev_root"
	done

	mkdir -p "$lib_root"
	if [ -e /lib/x86_64-linux-gnu/libavcodec.so.60 ]; then
		ln -sf /lib/x86_64-linux-gnu/libavcodec.so.60 "$lib_root/libavcodec.so"
	fi
	if [ -e /lib/x86_64-linux-gnu/libavutil.so.58 ]; then
		ln -sf /lib/x86_64-linux-gnu/libavutil.so.58 "$lib_root/libavutil.so"
	fi

	test -f "$include_root/libavcodec/avcodec.h"
	test -f "$include_root/libavutil/frame.h"
	test -e "$lib_root/libavcodec.so"
	test -e "$lib_root/libavutil.so"
}

prepare_ffmpeg_dev_tree

test -f src/webrtc/media/ffmpeg_codec.uya
test -f src/webrtc/media/ffmpeg_direct_ingest.uya
test -f tests/fixtures/ffmpeg_codec/ffmpeg_codec_shim.c
test -f src/webrtc_ffmpeg_codec_boundary_test_main.uya

rg -Fq "optional FFmpeg libavcodec boundary" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_encoder_open" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_decoder_open" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_encode_audio" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_encode_video_i420" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_decode_audio" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "extern fn uya_ffmpeg_codec_decode_video_i420" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_encode_audio_to_frame" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_encode_video_i420_to_frame" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_decode_audio_frame" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_decode_video_i420_frame" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_packet_to_encoded_frame" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_raw_audio_view_make" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_codec_raw_video_i420_view_make" src/webrtc/media/ffmpeg_codec.uya
rg -Fq "ffmpeg_direct_sender_encode_opus_rtp" src/webrtc/media/ffmpeg_direct_ingest.uya
rg -Fq "ffmpeg_direct_sender_encode_vp8_rtp" src/webrtc/media/ffmpeg_direct_ingest.uya
rg -Fq "ffmpeg_direct_sender_decode_opus_for_verification" src/webrtc/media/ffmpeg_direct_ingest.uya
rg -Fq "ffmpeg_direct_sender_decode_vp8_i420_for_verification" src/webrtc/media/ffmpeg_direct_ingest.uya
rg -Fq "avcodec_find_encoder_by_name" tests/fixtures/ffmpeg_codec/ffmpeg_codec_shim.c
rg -Fq "avcodec_find_decoder" tests/fixtures/ffmpeg_codec/ffmpeg_codec_shim.c
rg -Fq "FFmpeg codec extern boundary tests passed" src/webrtc_ffmpeg_codec_boundary_test_main.uya

if rg -Fq "captureStream" src/webrtc/media/ffmpeg_codec.uya src/webrtc/media/ffmpeg_direct_ingest.uya src/webrtc_ffmpeg_codec_boundary_test_main.uya; then
	printf '%s\n' "FFmpeg codec boundary must not depend on browser captureStream loopback" >&2
	exit 1
fi

../uya/bin/uya run src/webrtc_ffmpeg_codec_boundary_test_main.uya

echo "Phase 21 FFmpeg codec extern boundary checks passed"
