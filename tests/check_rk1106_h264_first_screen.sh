#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

preview="examples/rk1106_h264_push_client/host/manual_preview.html"
board_run="examples/rk1106_h264_push_client/board_run.sh"
readme="examples/rk1106_h264_push_client/README.md"

test -f "$preview"
test -f "$board_run"
test -f "$readme"
test -x tests/rk1106_h264_chrome_first_screen.py

rg -Fq "applyH264VideoPreference(videoTransceiver)" "$preview"
rg -Fq "packetization-mode=1" "$preview"
rg -Fq "window.__rk1106PreviewState" "$preview"
rg -Fq "answerToFirstFrame" "$preview"
rg -Fq "connectedToFirstFrame" "$preview"
rg -Fq "framesDropped=" "$preview"
rg -Fq "freeze=" "$preview"
rg -Fq "codec=\${codecText(report, stat)}" "$preview"

rg -Fq 'H264_GOP=${H264_GOP:-30}' "$board_run"
rg -Fq 'set -- "$@" --prebuffer-h264' "$board_run"
rg -Fq 'export UYA_RK1106_PREBUFFER_H264=1' "$board_run"

rg -Fq 'H264_GOP=30' "$readme"
rg -Fq 'FASTBOOT_H264_GOP=30' "$readme"
rg -Fq 'connectedToFirstFrame' "$readme"

rg -Fq "find_browser_executable" tests/rk1106_h264_chrome_first_screen.py
rg -Fq "start_host_sender" tests/rk1106_h264_chrome_first_screen.py
rg -Fq "answerToFirstFrame too slow" tests/rk1106_h264_chrome_first_screen.py
rg -Fq "Uya answer did not negotiate H264" tests/rk1106_h264_chrome_first_screen.py
