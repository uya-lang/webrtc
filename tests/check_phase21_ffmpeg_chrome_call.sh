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
if rg -Fq "captureStream" tests/ffmpeg_chrome_call.py; then
	printf '%s\n' "ffmpeg chrome call must not use browser media captureStream loopback" >&2
	exit 1
fi
if rg -Fq "const pc1 =" tests/ffmpeg_chrome_call.py || rg -Fq "const pc2 =" tests/ffmpeg_chrome_call.py; then
	printf '%s\n' "ffmpeg chrome call must not use browser pc1/pc2 loopback" >&2
	exit 1
fi
rg -Fq "videoFramesDecoded" tests/ffmpeg_chrome_call.py

python3 tests/ffmpeg_chrome_call.py

echo "Phase 21 FFmpeg Chrome call checks passed"
