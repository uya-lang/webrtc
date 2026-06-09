#!/bin/sh
set -eu

EXAMPLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

SENDER_BIN=${SENDER_BIN:-"$EXAMPLE_DIR/build/rk1106_h264_sender_host"}
VIDEO_DEV=${VIDEO_DEV:-/dev/video0}
WIDTH=${WIDTH:-320}
HEIGHT=${HEIGHT:-240}
FPS=${FPS:-15}
PIXEL_FORMAT=${PIXEL_FORMAT:-yuyv}
DURATION_US=${DURATION_US:-60000000}
FRAME_DURATION_US=${FRAME_DURATION_US:-}
WORKDIR=${WORKDIR:-/tmp/rk1106-webrtc-host-push}
MEDIA_PATH=${MEDIA_PATH:-"$WORKDIR/host_testsrc.h264"}
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

if [ ! -x "$SENDER_BIN" ]; then
    echo "missing host sender: $SENDER_BIN" >&2
    echo "Build it first: make -C $EXAMPLE_DIR host" >&2
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

if [ ! -s "$MEDIA_PATH" ]; then
    if ! command -v ffmpeg >/dev/null 2>&1; then
        echo "missing host H264 media: $MEDIA_PATH" >&2
        echo "Set MEDIA_PATH to an Annex-B H264 file, or install ffmpeg for generated test media." >&2
        exit 2
    fi
    duration_seconds=$(((DURATION_US + 999999) / 1000000))
    if [ "$duration_seconds" -lt 1 ]; then
        duration_seconds=1
    fi
    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i "testsrc2=size=${WIDTH}x${HEIGHT}:rate=${FPS}" \
        -t "$duration_seconds" \
        -c:v libx264 -preset ultrafast -tune zerolatency \
        -pix_fmt yuv420p -profile:v baseline \
        -x264-params "keyint=${FPS}:min-keyint=${FPS}:scenecut=0" \
        -f h264 "$MEDIA_PATH"
fi

echo "starting host RK1106 Annex-B H264 WebRTC sender: $MEDIA_PATH ${WIDTH}x${HEIGHT} ${FPS}fps, local candidate $LOCAL_HOST" >&2
set -- \
    --offer-json "$OFFER_JSON" \
    --answer-json "$ANSWER_JSON" \
    --diagnostics-json "$DIAGNOSTICS_JSON" \
    --codec uya \
    --media "$MEDIA_PATH" \
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

"$SENDER_BIN" "$@" >"$SENDER_LOG" 2>&1 || {
    status=$?
    echo "host sender failed (status=$status)" >&2
    print_runtime_logs
    exit "$status"
}

echo "host sender finished" >&2
if [ "$PRINT_LOGS_ON_EXIT" = "1" ]; then
    print_runtime_logs
fi
