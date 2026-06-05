#!/bin/sh
set -eu

EXAMPLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$EXAMPLE_DIR/../.." && pwd)

UYA=${UYA:-"$REPO_ROOT/../uya/bin/uya"}
SENDER_MAIN=${SENDER_MAIN:-"$REPO_ROOT/src/webrtc_ffmpeg_direct_sender_main.uya"}
VIDEO_DEV=${VIDEO_DEV:-/dev/video0}
WIDTH=${WIDTH:-320}
HEIGHT=${HEIGHT:-240}
FPS=${FPS:-15}
PIXEL_FORMAT=${PIXEL_FORMAT:-yuyv}
DURATION_US=${DURATION_US:-60000000}
FRAME_DURATION_US=${FRAME_DURATION_US:-}
WORKDIR=${WORKDIR:-/tmp/rk1106-webrtc-host-ffmpeg-push}
LOCAL_HOST=${LOCAL_HOST:-127.0.0.1}
SIGNAL_BASE_URL=${SIGNAL_BASE_URL:-http://127.0.0.1:8080/api}
OFFER_URL_WAS_SET=${OFFER_URL+x}
ANSWER_URL_WAS_SET=${ANSWER_URL+x}
OFFER_URL=${OFFER_URL:-}
ANSWER_URL=${ANSWER_URL:-}
OFFER_POLL_TRIES=${OFFER_POLL_TRIES:-120}
OFFER_POLL_INTERVAL=${OFFER_POLL_INTERVAL:-1}
OFFER_POLL_INTERVAL_MS=${OFFER_POLL_INTERVAL_MS:-}
SENDER_LOG=${SENDER_LOG:-"$WORKDIR/sender.log"}
PRINT_LOGS_ON_EXIT=${PRINT_LOGS_ON_EXIT:-1}

OFFER_JSON=${1:-"$WORKDIR/offer.json"}
ANSWER_JSON=${2:-"$WORKDIR/answer.json"}
DIAGNOSTICS_JSON=${3:-"$WORKDIR/diagnostics.json"}

if [ -z "$FRAME_DURATION_US" ]; then
    FRAME_DURATION_US=$((1000000 / FPS))
fi
if [ -z "$OFFER_POLL_INTERVAL_MS" ]; then
    OFFER_POLL_INTERVAL_MS=$((OFFER_POLL_INTERVAL * 1000))
fi

if [ -n "$SIGNAL_BASE_URL" ]; then
    SIGNAL_BASE_URL=${SIGNAL_BASE_URL%/}
    if [ -z "$OFFER_URL_WAS_SET" ]; then
        OFFER_URL="$SIGNAL_BASE_URL/offer"
    fi
    if [ -z "$ANSWER_URL_WAS_SET" ]; then
        ANSWER_URL="$SIGNAL_BASE_URL/answer"
    fi
fi

if [ ! -x "$UYA" ]; then
    echo "missing Uya compiler/runtime: $UYA" >&2
    exit 2
fi
if [ ! -f "$SENDER_MAIN" ]; then
    echo "missing FFmpeg sender main: $SENDER_MAIN" >&2
    exit 2
fi

print_log_tail() {
    label=$1
    path=$2
    lines=$3
    if [ -f "$path" ]; then
        echo "---- $label: $path ----" >&2
        tail -n "$lines" "$path" >&2 || true
    fi
}

print_runtime_logs() {
    print_log_tail "sender log" "$SENDER_LOG" 160
    print_log_tail "diagnostics" "$DIAGNOSTICS_JSON" 60
}

mkdir -p "$WORKDIR"
rm -f "$ANSWER_JSON" "$DIAGNOSTICS_JSON" "$SENDER_LOG"

echo "starting host FFmpeg V4L2 WebRTC sender: $VIDEO_DEV ${WIDTH}x${HEIGHT} $PIXEL_FORMAT ${FPS}fps, local candidate $LOCAL_HOST" >&2
set -- \
    --offer-json "$OFFER_JSON" \
    --answer-json "$ANSWER_JSON" \
    --diagnostics-json "$DIAGNOSTICS_JSON" \
    --codec ffmpeg \
    --v4l2-device "$VIDEO_DEV" \
    --v4l2-format "$PIXEL_FORMAT" \
    --video-width "$WIDTH" \
    --video-height "$HEIGHT" \
    --media-duration-us "$DURATION_US" \
    --video-frame-duration-us "$FRAME_DURATION_US" \
    --local-host "$LOCAL_HOST"
if [ -n "$OFFER_URL" ]; then
    set -- "$@" --offer-url "$OFFER_URL" \
        --offer-poll-tries "$OFFER_POLL_TRIES" \
        --offer-poll-interval-ms "$OFFER_POLL_INTERVAL_MS"
fi
if [ -n "$ANSWER_URL" ]; then
    set -- "$@" --answer-url "$ANSWER_URL"
fi

(cd "$REPO_ROOT" && "$UYA" run "$SENDER_MAIN" -- "$@") >"$SENDER_LOG" 2>&1 || {
    status=$?
    echo "host FFmpeg sender failed (status=$status)" >&2
    print_runtime_logs
    exit "$status"
}

echo "host FFmpeg sender finished" >&2
if [ "$PRINT_LOGS_ON_EXIT" = "1" ]; then
    print_runtime_logs
fi
