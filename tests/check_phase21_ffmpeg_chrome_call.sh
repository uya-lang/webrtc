#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -x tests/ffmpeg_chrome_call.py
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

python3 tests/ffmpeg_chrome_call.py --contract-only
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
