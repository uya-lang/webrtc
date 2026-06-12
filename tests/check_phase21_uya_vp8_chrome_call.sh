#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/vp8_codec_bridge.uya
test -f src/webrtc_uya_vp8_direct_sender_main.uya
test -x tests/uya_vp8_chrome_call.py
test -d ../vp8/src/vp8

rg -Fq "use vp8.api" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq "use webrtc.peer_connection" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq "vp8_codec_bridge_encode_i420_to_frame" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq "cli_send_uya_vp8_live_frame" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq "run_live_uya_vp8_sender" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq ".setRemoteChromeOffer" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq ".createPassiveAnswer" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq ".initDirectTransport" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq ".directRuntime" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq -- "--raw-video-i420" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq "rawVideoPathSeen" src/webrtc_uya_vp8_direct_sender_main.uya
if rg -Fq "direct_session_parse_chrome_offer_sdp(" src/webrtc_uya_vp8_direct_sender_main.uya || rg -Fq "direct_session_write_passive_answer(" src/webrtc_uya_vp8_direct_sender_main.uya; then
	printf '%s\n' "Uya VP8 Chrome sender must negotiate through PeerConnection methods" >&2
	exit 1
fi
if rg -Fq -- "--encoded-video-vp8" src/webrtc_uya_vp8_direct_sender_main.uya || rg -Fq "generate_uya_vp8_frames" tests/uya_vp8_chrome_call.py; then
	printf '%s\n' "Uya VP8 Chrome path must live-encode from raw I420 instead of reading pre-encoded VP8 frames" >&2
	exit 1
fi
if rg -n "use webrtc.media.ffmpeg_|Ffmpeg|ffmpeg_direct_sender_encode|ffmpeg_codec_encode" src/webrtc_uya_vp8_direct_sender_main.uya; then
	printf '%s\n' "Uya VP8 Chrome sender must not import or call the FFmpeg codec boundary" >&2
	exit 1
fi
rg -Fq "preview-uya-vp8-chrome-call" Makefile
rg -Fq "UYA_VP8_PREVIEW_MAX_WIDTH" Makefile
rg -Fq "UYA_VP8_PREVIEW_MAX_DURATION" Makefile
rg -Fq "UYA_VP8_PREVIEW_FPS" Makefile
rg -Fq "UYA_VP8_FORCE_SCALAR" Makefile
rg -Fq "UYA_VP8_PREVIEW_CFLAGS" Makefile
rg -Fq -- "--source-mp4" tests/uya_vp8_chrome_call.py
rg -Fq -- "--max-video-width" tests/uya_vp8_chrome_call.py
rg -Fq -- "--max-duration-seconds" tests/uya_vp8_chrome_call.py
rg -Fq -- "--preview-fps" tests/uya_vp8_chrome_call.py
rg -Fq -- "--video-frame-duration-us" tests/uya_vp8_chrome_call.py
rg -Fq "make_manual_preview_page" tests/uya_vp8_chrome_call.py
rg -Fq "stage_uya_lib" tests/uya_vp8_chrome_call.py
rg -Fq 'env["UYA_ROOT"]' tests/uya_vp8_chrome_call.py
rg -Fq "vp8_force_scalar_enabled" tests/uya_vp8_chrome_call.py
rg -Fq "force_staged_vp8_scalar_kernels" tests/uya_vp8_chrome_call.py
rg -Fq "build_uya_vp8_sender" tests/uya_vp8_chrome_call.py
rg -Fq "PreviewSenderExecutable" tests/uya_vp8_chrome_call.py
rg -Fq "run_chrome_page(tempdir_path, raw_video_path, sender_executable=sender_executable)" tests/uya_vp8_chrome_call.py
rg -Fq -- "--video-frame-duration-us" src/webrtc_uya_vp8_direct_sender_main.uya
rg -Fq "patch_staged_tls_ec_calls" tests/uya_vp8_chrome_call.py
rg -Fq "codecProviderUsesExtern" tests/uya_vp8_chrome_call.py
rg -Fq "uyaVp8VideoReady" tests/uya_vp8_chrome_call.py
rg -Fq "rawVideoPathSeen" tests/uya_vp8_chrome_call.py
rg -Fq "Chrome decoded no Uya VP8 frames" tests/uya_vp8_chrome_call.py

# Keep the FFmpeg reference boundary covered separately; the Uya VP8 sender below
# must source raw I420 and run the pure Uya VP8 encoder in its live send loop.
bash tests/check_phase21_ffmpeg_codec_extern.sh
python3 tests/uya_vp8_chrome_call.py
