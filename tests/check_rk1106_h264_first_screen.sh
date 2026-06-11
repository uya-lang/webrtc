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
rg -Fq "freezePer1000=" "$preview"
rg -Fq "videoStats: latestVideoStats" "$preview"
rg -Fq "codec=\${codecText(report, stat)}" "$preview"

rg -Fq 'H264_GOP=${H264_GOP:-15}' "$board_run"
rg -Fq 'H264_BITRATE=${H264_BITRATE:-600000}' "$board_run"
rg -Fq 'FASTBOOT_STARTUP_VENC_CHANNEL=${FASTBOOT_STARTUP_VENC_CHANNEL:-1}' "$board_run"
rg -Fq 'FASTBOOT_VIDEO_WIDTH=${FASTBOOT_VIDEO_WIDTH:-1280}' "$board_run"
rg -Fq 'FASTBOOT_VIDEO_HEIGHT=${FASTBOOT_VIDEO_HEIGHT:-720}' "$board_run"
rg -Fq 'FASTBOOT_STARTUP_VIDEO_WIDTH=${FASTBOOT_STARTUP_VIDEO_WIDTH:-$((FASTBOOT_VIDEO_WIDTH / 2))}' "$board_run"
rg -Fq 'FASTBOOT_STARTUP_VIDEO_HEIGHT=${FASTBOOT_STARTUP_VIDEO_HEIGHT:-$((FASTBOOT_VIDEO_HEIGHT / 2))}' "$board_run"
rg -Fq 'FASTBOOT_H264_START_BITRATE=${FASTBOOT_H264_START_BITRATE:-$((FASTBOOT_H264_BITRATE / 4))}' "$board_run"
rg -Fq 'FASTBOOT_H264_RAMP_FRAMES=${FASTBOOT_H264_RAMP_FRAMES:-$((FASTBOOT_VIDEO_FPS * 3))}' "$board_run"
rg -Fq 'DISABLE_AUDIO=${DISABLE_AUDIO:-0}' "$board_run"
rg -Fq 'HELPER_STDERR_LOG=${HELPER_STDERR_LOG:-/dev/null}' "$board_run"
rg -Fq 'set -- "$@" --prebuffer-h264' "$board_run"
rg -Fq 'export UYA_RK1106_PREBUFFER_H264=1' "$board_run"
rg -Fq 'export UYA_RK1106_DISABLE_AUDIO="$DISABLE_AUDIO"' "$board_run"
rg -Fq 'const CLI_H264_STARTUP_KEYFRAME_BURST_COUNT: u32 = 1u32;' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'const CLI_H264_RESUME_KEYFRAME_MAX_DELAY_US: u64 = 500_000u64;' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'const CLI_H264_LIVE_LAG_DROP_THRESHOLD_US: u64 = CLI_H264_RESUME_KEYFRAME_MAX_DELAY_US;' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'const CLI_H264_VCL_PARSE_WAIT_BYTES: usize = 16usize;' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'var disable_audio: bool = cli_env_flag_enabled("UYA_RK1106_DISABLE_AUDIO\0" as &const byte);' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'audio RTP disabled by UYA_RK1106_DISABLE_AUDIO' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'FASTBOOT_H264_FIFO_BUILD_ID "continuous-fifo-720p-startup-quarter-av' examples/rk1106_h264_push_client/src/fastboot_demo_mirror/fastboot_demo.c
rg -Fq 'FASTBOOT_FIFO_DEFAULT_START_BITRATE (FASTBOOT_FIFO_DEFAULT_BITRATE / 4)' examples/rk1106_h264_push_client/src/fastboot_demo_mirror/fastboot_demo.c
rg -Fq 'startup output switch frame=' examples/rk1106_h264_push_client/src/fastboot_demo_mirror/fastboot_demo.c
rg -Fq 'fastboot_h264_clear_parameter_set_cache' examples/rk1106_h264_push_client/src/fastboot_demo_mirror/fastboot_demo.c
rg -Fq 'H264 live lag drop event=' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'keyframe_available = false;' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'H264 resume requires IDR pending_delay_under_us=' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'H264 startup resume queue_delay_us=' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'media heartbeat h264_live_lag_stale_idrs=' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'media heartbeat h264_last_resume_delay_us=' src/webrtc_rk1106_h264_sender_main.uya
! rg -Fq 'first H264 frame sent from cached keyframe' src/webrtc_rk1106_h264_sender_main.uya
! rg -Fq 'adaptive H264 frame_duration_us' src/webrtc_rk1106_h264_sender_main.uya

rg -Fq 'H264_GOP=15' "$readme"
rg -Fq 'FASTBOOT_H264_GOP=15' "$readme"
rg -Fq 'const CLI_DEFAULT_H264_GOP: u32 = 15u32;' src/webrtc_rk1106_h264_sender_main.uya
rg -Fq 'connectedToFirstFrame' "$readme"
rg -Fq '从当前 FIFO 队头向后扫描' "$readme"
rg -Fq '低于 500ms 的可解码 IDR' "$readme"
rg -Fq 'RTP duration 固定使用配置帧间隔' "$readme"

rg -Fq "find_browser_executable" tests/rk1106_h264_chrome_first_screen.py
rg -Fq "start_host_sender" tests/rk1106_h264_chrome_first_screen.py
rg -Fq "answerToFirstFrame too slow" tests/rk1106_h264_chrome_first_screen.py
rg -Fq "Uya answer did not negotiate H264" tests/rk1106_h264_chrome_first_screen.py
rg -Fq "freezeCount ratio too high" tests/rk1106_h264_chrome_first_screen.py
rg -Fq "Chrome receiver target delay too high" tests/rk1106_h264_chrome_first_screen.py
rg -Fq -- "--steady-min-frames" tests/rk1106_h264_chrome_first_screen.py
rg -Fq -- "--steady-observe-us" tests/rk1106_h264_chrome_first_screen.py
rg -Fq -- "--external-sender" tests/rk1106_h264_chrome_first_screen.py
rg -Fq -- "--max-jitter-target-delay" tests/rk1106_h264_chrome_first_screen.py
