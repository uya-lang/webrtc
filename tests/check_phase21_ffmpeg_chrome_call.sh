#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -x tests/ffmpeg_chrome_call.py
test -x examples/host_ffmpeg_chrome_call.py
rg -Fq "generate_ffmpeg_media" tests/ffmpeg_chrome_call.py
rg -Fq "libopus" tests/ffmpeg_chrome_call.py
rg -Fq "libvpx" tests/ffmpeg_chrome_call.py
rg -Fq "RTCPeerConnection" tests/ffmpeg_chrome_call.py
rg -Fq "m=audio" tests/ffmpeg_chrome_call.py
rg -Fq "m=video" tests/ffmpeg_chrome_call.py
rg -Fq "UyaDirectSender" tests/ffmpeg_chrome_call.py
rg -Fq "uya_ffmpeg_direct_sender" tests/ffmpeg_chrome_call.py
rg -Fq "rtp_packetize_encoded_frame" tests/ffmpeg_chrome_call.py
rg -Fq "SRTP/SRTCP -> UDP" tests/ffmpeg_chrome_call.py
rg -Fq "start_uya_direct_sender" tests/ffmpeg_chrome_call.py
rg -Fq "wait_for_uya_direct_sender" tests/ffmpeg_chrome_call.py
rg -Fq "ManualPreviewState" tests/ffmpeg_chrome_call.py
rg -Fq "PreviewMediaAssets" tests/ffmpeg_chrome_call.py
rg -Fq "prepare_mp4_raw_preview" tests/ffmpeg_chrome_call.py
rg -Fq -- "--source-mp4" tests/ffmpeg_chrome_call.py
rg -Fq -- "--raw-video-i420" tests/ffmpeg_chrome_call.py
rg -Fq -- "--raw-audio-s16le" tests/ffmpeg_chrome_call.py
rg -Fq -- "--video-width" tests/ffmpeg_chrome_call.py
rg -Fq -- "--video-height" tests/ffmpeg_chrome_call.py
rg -Fq -- "--media-duration-us" tests/ffmpeg_chrome_call.py
rg -Fq "media_duration_us" tests/ffmpeg_chrome_call.py
rg -Fq "stream_display_dimensions" tests/ffmpeg_chrome_call.py
rg -Fq "videoFrameWidth" tests/ffmpeg_chrome_call.py
rg -Fq "preview_manifest.json" tests/ffmpeg_chrome_call.py
rg -Fq "Start Uya Video" tests/ffmpeg_chrome_call.py
rg -Fq "remoteVideo" tests/ffmpeg_chrome_call.py
rg -Fq "/api/start-call" tests/ffmpeg_chrome_call.py
rg -Fq "/api/finish-call" tests/ffmpeg_chrome_call.py
rg -Fq "window.__uyaManualPreviewResult" tests/ffmpeg_chrome_call.py
rg -Fq "subprocess.Popen" tests/ffmpeg_chrome_call.py
if rg -Fq "subprocess.run(" tests/ffmpeg_chrome_call.py; then
	printf '%s\n' "ffmpeg chrome call must keep the Uya sender alive with subprocess.Popen" >&2
	exit 1
fi
if rg -Fq "captureStream" tests/ffmpeg_chrome_call.py; then
	printf '%s\n' "ffmpeg chrome call must not use browser media captureStream loopback" >&2
	exit 1
fi
if rg -Fq "RAW_PREVIEW_MAX_WIDTH" tests/ffmpeg_chrome_call.py || rg -Fq "RAW_PREVIEW_MAX_HEIGHT" tests/ffmpeg_chrome_call.py; then
	printf '%s\n' "mp4 preview must preserve the source dimensions instead of using a fixed preview resolution cap" >&2
	exit 1
fi
if rg -Fq "scale=" tests/ffmpeg_chrome_call.py || rg -Fq "pad=" tests/ffmpeg_chrome_call.py; then
	printf '%s\n' "mp4 preview must not scale or pad the input video before sending it to Chrome" >&2
	exit 1
fi
if rg -Fq -- "-stream_loop" tests/ffmpeg_chrome_call.py; then
	printf '%s\n' "mp4 preview must send the whole source instead of looping a short clipped preview" >&2
	exit 1
fi
if rg -Fq "const pc1 =" tests/ffmpeg_chrome_call.py || rg -Fq "const pc2 =" tests/ffmpeg_chrome_call.py; then
	printf '%s\n' "ffmpeg chrome call must not use browser pc1/pc2 loopback" >&2
	exit 1
fi
rg -Fq "videoFramesDecoded" tests/ffmpeg_chrome_call.py
rg -Fq "sender_srtp_packets" tests/ffmpeg_chrome_call.py
rg -Fq "sender_srtcp_packets" tests/ffmpeg_chrome_call.py
rg -Fq "sender_rtcp_sender_reports" tests/ffmpeg_chrome_call.py
rg -Fq "sender_rtcp_packets_received" tests/ffmpeg_chrome_call.py
rg -Fq "sender_udp_packets" tests/ffmpeg_chrome_call.py
rg -Fq "next_video_us = now_us + (video_frame_duration_us as u64)" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "next_rtcp_us = now_us + CLI_RTCP_REPORT_INTERVAL_US" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "try cli_send_video_frame(" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "host-ffmpeg-chrome-call" Makefile
rg -Fq "HOST_CALL_VIDEO_DEV" Makefile
rg -Fq "HOST_CALL_SENDER_BIN" Makefile
rg -Fq "HOST_CALL_PLAYBACK ?= 0" Makefile
rg -Fq "HOST_CALL_UYA_AUDIO_CAPTURE ?= 0" Makefile
rg -Fq 'host-ffmpeg-chrome-call: $(HOST_CALL_SENDER_BIN)' Makefile
rg -Fq "host-ffmpeg-chrome-call-playback" Makefile
rg -Fq "HOST_CALL_PLAYBACK=1" Makefile
rg -Fq -- "--sender-executable" Makefile
rg -Fq -- "--uya-audio-capture" Makefile
rg -Fq "getUserMedia" examples/host_ffmpeg_chrome_call.py
rg -Fq "sender_executable" examples/host_ffmpeg_chrome_call.py
rg -Fq "normalize_sender_executable" examples/host_ffmpeg_chrome_call.py
rg -Fq "DEFAULT_PLAYBACK = \"0\"" examples/host_ffmpeg_chrome_call.py
rg -Fq "DEFAULT_UYA_AUDIO_CAPTURE = \"0\"" examples/host_ffmpeg_chrome_call.py
rg -Fq "uya_audio_capture" examples/host_ffmpeg_chrome_call.py
rg -Fq "markTiming" examples/host_ffmpeg_chrome_call.py
rg -Fq "first-video-frame" examples/host_ffmpeg_chrome_call.py
rg -Fq "requestVideoFrameCallback" examples/host_ffmpeg_chrome_call.py
rg -Fq "__hostFfmpegChromeCallTiming" examples/host_ffmpeg_chrome_call.py
rg -Fq "start-call-returned" examples/host_ffmpeg_chrome_call.py
rg -Fq "timing," examples/host_ffmpeg_chrome_call.py
rg -Fq "sender_executable" tests/ffmpeg_chrome_call.py
rg -Fq "addTransceiver(audioTrack" examples/host_ffmpeg_chrome_call.py
rg -Fq "addTransceiver(videoTrack" examples/host_ffmpeg_chrome_call.py
rg -Fq "sendrecv" examples/host_ffmpeg_chrome_call.py
rg -Fq "start_ffmpeg_audio_fifo" examples/host_ffmpeg_chrome_call.py
rg -Fq "open_fifo_read_anchors" examples/host_ffmpeg_chrome_call.py
rg -Fq "close_fifo_anchors" examples/host_ffmpeg_chrome_call.py
rg -Fq "stdin=subprocess.DEVNULL" examples/host_ffmpeg_chrome_call.py
rg -Fq "default_route_ipv4" examples/host_ffmpeg_chrome_call.py
if sed -n '/def start_ffplay_playback/,/^def make_host_call_page/p' examples/host_ffmpeg_chrome_call.py | rg -Fq -- "-nostdin"; then
	printf '%s\n' "host ffplay playback must not pass -nostdin; this ffplay build treats the next option as its value" >&2
	exit 1
fi
ffplay_start_fn="$(sed -n '/def start_ffplay_playback/,/^def make_host_call_page/p' examples/host_ffmpeg_chrome_call.py)"
if printf '%s' "$ffplay_start_fn" | rg -Fq "time.sleep"; then
	printf '%s\n' "host ffplay startup must not add fixed sleeps before returning the Uya answer" >&2
	exit 1
fi
printf '%s' "$ffplay_start_fn" | rg -Fq "mux_command"
printf '%s' "$ffplay_start_fn" | rg -Fq "pipe:1"
printf '%s' "$ffplay_start_fn" | rg -Fq "nut"
printf '%s' "$ffplay_start_fn" | rg -Fq "use_wallclock_as_timestamps"
printf '%s' "$ffplay_start_fn" | rg -Fq "sync"
printf '%s' "$ffplay_start_fn" | rg -Fq "audio"
ffplay_refs="$(printf '%s' "$ffplay_start_fn" | rg -F "ffplay," | wc -l | tr -d ' ')"
test "$ffplay_refs" -eq 1
python3 - <<'PY'
import examples.host_ffmpeg_chrome_call as host_call

host_call.default_route_ipv4 = lambda: "192.168.3.8"
offer_sdp = "\r\n".join(
    [
        "v=0",
        "m=audio 53522 UDP/TLS/RTP/SAVPF 111",
        "c=IN IP4 172.19.0.1",
        "a=candidate:1 1 udp 2122260223 172.19.0.1 53522 typ host generation 0",
        "a=candidate:2 1 udp 2122194687 192.168.3.8 41463 typ host generation 0",
    ]
)
assert host_call.select_uya_local_host(offer_sdp, "auto") == "192.168.3.8"
assert host_call.select_uya_local_host(offer_sdp, "10.0.0.5") == "10.0.0.5"
PY
rg -Fq -- "--raw-audio-s16le" tests/ffmpeg_chrome_call.py
rg -Fq -- "--playback-audio-s16le" tests/ffmpeg_chrome_call.py
rg -Fq -- "--playback-video-i420" tests/ffmpeg_chrome_call.py
rg -Fq -- "--playback-smoke-e2e" tests/ffmpeg_chrome_call.py
rg -Fq -- "--v4l2-device" tests/ffmpeg_chrome_call.py
rg -Fq "v4l2_device" tests/ffmpeg_chrome_call.py
rg -Fq "srtpPacketsReceived" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "audioRtpPacketsReceived" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "videoFramesReceived" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "audioFramesDecoded" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "videoFramesDecoded" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "PlaybackPipeCapture" tests/ffmpeg_chrome_call.py

python3 tests/ffmpeg_chrome_call.py --contract-only
python3 tests/ffmpeg_chrome_call.py --playback-smoke-e2e
python3 tests/ffmpeg_chrome_call.py --manual-preview-e2e

mp4_tmp="$(mktemp -d)"
trap 'rm -rf "$mp4_tmp"' EXIT
ffmpeg -hide_banner -loglevel error -y \
	-f lavfi -i testsrc2=size=1920x1080:rate=30:duration=1 \
	-f lavfi -i sine=frequency=660:sample_rate=48000:duration=1 \
	-map 0:v:0 \
	-map 1:a:0 \
	-c:v mpeg4 \
	-q:v 4 \
	-pix_fmt yuv420p \
	-c:a aac \
	-shortest \
	"$mp4_tmp/source.mp4"
python3 tests/ffmpeg_chrome_call.py --manual-preview-e2e --source-mp4 "$mp4_tmp/source.mp4"

python3 tests/ffmpeg_chrome_call.py

echo "Phase 21 FFmpeg Chrome call checks passed"
