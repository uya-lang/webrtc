#!/bin/sh
set -eu

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FIFO_PATH=${FIFO_PATH:-/tmp/fastboot.h264}
MEDIA_PATH=${MEDIA_PATH:-}
SIGNAL_BASE_URL=${SIGNAL_BASE_URL:-http://192.168.3.8:8080/api}
OFFER_URL_WAS_SET=${OFFER_URL+x}
ANSWER_URL_WAS_SET=${ANSWER_URL+x}
OFFER_URL=${OFFER_URL:-}
ANSWER_URL=${ANSWER_URL:-}
LOCAL_HOST=${LOCAL_HOST:-192.168.3.166}
MEDIA_DURATION_US=${MEDIA_DURATION_US:-6000000}
VIDEO_FRAME_DURATION_US=${VIDEO_FRAME_DURATION_US:-33333}
H264_BITRATE=${H264_BITRATE:-1000000}
H264_GOP=${H264_GOP:-30}
DIAG_PATH=${DIAG_PATH:-/tmp/rk1106_h264_sender_diagnostics.json}
BOOT_TRACE_LOG=${BOOT_TRACE_LOG:-/tmp/rk1106_h264_sender_boot.log}
SENDER_STDOUT_LOG=${SENDER_STDOUT_LOG:-/tmp/rk1106_h264_sender.stdout.log}
SENDER_STDERR_LOG=${SENDER_STDERR_LOG:-/tmp/rk1106_h264_sender.stderr.log}
SENDER_HELP_STDOUT_LOG=${SENDER_HELP_STDOUT_LOG:-/tmp/rk1106_h264_sender_help.stdout.log}
SENDER_HELP_STDERR_LOG=${SENDER_HELP_STDERR_LOG:-/tmp/rk1106_h264_sender_help.stderr.log}
HELPER_STDOUT_LOG=${HELPER_STDOUT_LOG:-/tmp/fastboot_h264_fifo.stdout.log}
HELPER_STDERR_LOG=${HELPER_STDERR_LOG:-/tmp/fastboot_h264_fifo.stderr.log}
PRINT_LOGS_ON_SUCCESS=${PRINT_LOGS_ON_SUCCESS:-1}
LIVE_LOGS=${LIVE_LOGS:-1}

if [ -n "$SIGNAL_BASE_URL" ]; then
    SIGNAL_BASE_URL=${SIGNAL_BASE_URL%/}
    if [ -z "$OFFER_URL_WAS_SET" ]; then
        OFFER_URL="$SIGNAL_BASE_URL/offer"
    fi
    if [ -z "$ANSWER_URL_WAS_SET" ]; then
        ANSWER_URL="$SIGNAL_BASE_URL/answer"
    fi
fi

is_ipv4_address() {
    saved_ifs=$IFS
    IFS=.
    set -- $1
    IFS=$saved_ifs
    if [ "$#" -ne 4 ]; then
        return 1
    fi
    for octet in "$@"; do
        case "$octet" in
            ''|*[!0-9]*)
                return 1
                ;;
        esac
        if [ "$octet" -lt 0 ] || [ "$octet" -gt 255 ]; then
            return 1
        fi
    done
    return 0
}

local_ipv4_present() {
    target=$1
    checked=0
    if command -v ip >/dev/null 2>&1; then
        checked=1
        if ip -4 addr show 2>/dev/null | grep -q "[[:space:]]$target/"; then
            return 0
        fi
    fi
    if command -v ifconfig >/dev/null 2>&1; then
        checked=1
        if ifconfig 2>/dev/null | grep -q "inet addr:$target"; then
            return 0
        fi
        if ifconfig 2>/dev/null | grep -q "inet $target"; then
            return 0
        fi
    fi
    if [ "$checked" -eq 1 ]; then
        return 1
    fi
    return 2
}

print_local_ipv4s() {
    if command -v ip >/dev/null 2>&1; then
        ip -4 addr show 2>/dev/null >&2 || true
        return
    fi
    if command -v ifconfig >/dev/null 2>&1; then
        ifconfig 2>/dev/null >&2 || true
    fi
}

print_tail() {
    label=$1
    path=$2
    lines=${3:-80}
    if [ -f "$path" ]; then
        echo "---- $label: $path ----" >&2
        tail -n "$lines" "$path" >&2 || true
    else
        echo "---- $label: $path (missing) ----" >&2
    fi
}

start_live_logs() {
    if [ "$LIVE_LOGS" != "1" ]; then
        return
    fi
    if ! command -v tail >/dev/null 2>&1; then
        echo "board_run: warning: tail not found, live logs disabled" >&2
        return
    fi
    echo "board_run: live logs enabled (sender/helper stderr)" >&2
    tail -n 20 -f "$SENDER_STDERR_LOG" "$HELPER_STDERR_LOG" >&2 &
    TAIL_PID=$!
}

stop_live_logs() {
    if [ -n "${TAIL_PID:-}" ]; then
        kill "$TAIL_PID" 2>/dev/null || true
        wait "$TAIL_PID" 2>/dev/null || true
        TAIL_PID=
    fi
}

cleanup() {
    status=$?
    stop_live_logs
    if [ -n "${SENDER_PID:-}" ]; then
        kill "$SENDER_PID" 2>/dev/null || true
        wait "$SENDER_PID" 2>/dev/null || true
    fi
    if [ -n "${FASTBOOT_PID:-}" ]; then
        kill "$FASTBOOT_PID" 2>/dev/null || true
        wait "$FASTBOOT_PID" 2>/dev/null || true
    fi
    echo "board_run: exit_status=$status" >&2
    if [ "$status" -ne 0 ] || [ "$PRINT_LOGS_ON_SUCCESS" = "1" ]; then
        print_tail "sender help stderr" "$SENDER_HELP_STDERR_LOG" 80
        print_tail "sender help stdout" "$SENDER_HELP_STDOUT_LOG" 80
        print_tail "sender stderr" "$SENDER_STDERR_LOG" 120
        print_tail "sender stdout" "$SENDER_STDOUT_LOG" 60
        print_tail "sender boot trace" "$BOOT_TRACE_LOG" 120
        print_tail "helper stderr" "$HELPER_STDERR_LOG" 120
        print_tail "helper stdout" "$HELPER_STDOUT_LOG" 60
        print_tail "diagnostics" "$DIAG_PATH" 40
        if [ -n "$MEDIA_PATH" ]; then
            echo "---- media file stat ----" >&2
            ls -l "$MEDIA_PATH" >&2 || true
        else
            if [ -p "$FIFO_PATH" ] || [ -e "$FIFO_PATH" ]; then
                echo "---- fifo stat ----" >&2
                ls -l "$FIFO_PATH" >&2 || true
            fi
        fi
    fi
    if [ -z "$MEDIA_PATH" ]; then
        rm -f "$FIFO_PATH"
    fi
    exit "$status"
}
trap cleanup EXIT INT TERM

rm -f "$FIFO_PATH" "$DIAG_PATH" \
    "$BOOT_TRACE_LOG" \
    "$SENDER_STDOUT_LOG" "$SENDER_STDERR_LOG" \
    "$SENDER_HELP_STDOUT_LOG" "$SENDER_HELP_STDERR_LOG" \
    "$HELPER_STDOUT_LOG" "$HELPER_STDERR_LOG"
: >"$SENDER_STDERR_LOG"
: >"$HELPER_STDERR_LOG"
start_live_logs
if [ -n "$MEDIA_PATH" ]; then
    if [ ! -r "$MEDIA_PATH" ]; then
        echo "board_run: MEDIA_PATH is not readable: $MEDIA_PATH" >&2
        exit 14
    fi
    MEDIA_INPUT_PATH=$MEDIA_PATH
else
    mkfifo "$FIFO_PATH"
    MEDIA_INPUT_PATH=$FIFO_PATH
fi

echo "board_run: pwd=$(pwd)" >&2
echo "board_run: dir=$DIR" >&2
if [ -n "$MEDIA_PATH" ]; then
    echo "board_run: media_file=$MEDIA_PATH" >&2
else
    echo "board_run: fifo=$FIFO_PATH" >&2
fi
echo "board_run: offer=$OFFER_URL answer=$ANSWER_URL local_host=$LOCAL_HOST" >&2
if ! is_ipv4_address "$LOCAL_HOST"; then
    echo "board_run: LOCAL_HOST must be the board IPv4 address, got '$LOCAL_HOST' (example: 192.168.3.195)" >&2
    exit 12
fi
if local_ipv4_present "$LOCAL_HOST"; then
    :
else
    local_host_status=$?
    if [ "$local_host_status" -eq 1 ]; then
        echo "board_run: LOCAL_HOST=$LOCAL_HOST is not assigned on this board" >&2
        echo "board_run: LOCAL_HOST only writes the SDP candidate; it does not change the board IP" >&2
        echo "board_run: configure the board to $LOCAL_HOST first, or run with LOCAL_HOST=<actual board IPv4>" >&2
        echo "---- board IPv4 addresses ----" >&2
        print_local_ipv4s
        exit 13
    fi
    echo "board_run: warning: unable to verify LOCAL_HOST on local interfaces" >&2
fi
echo "board_run: sender_bin=$DIR/rk1106_h264_sender" >&2
if [ -z "$MEDIA_PATH" ]; then
    echo "board_run: helper_bin=$DIR/fastboot_h264_fifo" >&2
fi
ls -l "$DIR/rk1106_h264_sender" "$DIR/fastboot_h264_fifo" >&2 || true

echo "board_run: preflight sender --help" >&2
"$DIR/rk1106_h264_sender" --help >"$SENDER_HELP_STDOUT_LOG" 2>"$SENDER_HELP_STDERR_LOG" || true
if grep -q "rk1106_h264_sender" "$SENDER_HELP_STDERR_LOG" "$SENDER_HELP_STDOUT_LOG" 2>/dev/null; then
    echo "board_run: sender --help usable" >&2
else
    echo "board_run: sender --help unusable" >&2
    exit 11
fi

if [ -z "$MEDIA_PATH" ]; then
    FASTBOOT_H264_OUT="$FIFO_PATH" FASTBOOT_VENC0_PATH="$FIFO_PATH" "$DIR/fastboot_h264_fifo" >"$HELPER_STDOUT_LOG" 2>"$HELPER_STDERR_LOG" &
    FASTBOOT_PID=$!
    echo "board_run: helper_pid=$FASTBOOT_PID" >&2
    sleep 1
    if ! kill -0 "$FASTBOOT_PID" 2>/dev/null; then
        echo "board_run: helper exited before sender start" >&2
        exit 10
    fi
else
    echo "board_run: file-only media mode; fastboot helper disabled" >&2
fi

set -- \
    --media "$MEDIA_INPUT_PATH" \
    --offer-url "$OFFER_URL" \
    --answer-url "$ANSWER_URL" \
    --diagnostics-json "$DIAG_PATH" \
    --local-host "$LOCAL_HOST" \
    --media-duration-us "$MEDIA_DURATION_US" \
    --video-frame-duration-us "$VIDEO_FRAME_DURATION_US" \
    --h264-bitrate "$H264_BITRATE" \
    --h264-gop "$H264_GOP"

echo "board_run: sender args: $*" >&2
set +e
("$DIR/rk1106_h264_sender" "$@" >"$SENDER_STDOUT_LOG" 2>"$SENDER_STDERR_LOG") &
SENDER_PID=$!
wait "$SENDER_PID"
SENDER_STATUS=$?
SENDER_PID=
set -e
stop_live_logs
echo "board_run: sender_status=$SENDER_STATUS" >&2
exit "$SENDER_STATUS"
