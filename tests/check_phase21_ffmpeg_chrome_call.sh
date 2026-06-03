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
rg -Fq "videoFramesDecoded" tests/ffmpeg_chrome_call.py

python3 tests/ffmpeg_chrome_call.py

echo "Phase 21 FFmpeg Chrome call checks passed"
