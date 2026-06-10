#!/bin/sh
set -eu

BIN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

VIDEO_DEV=${VIDEO_DEV:-/dev/video7}
WIDTH=${WIDTH:-320}
HEIGHT=${HEIGHT:-180}
FPS=${FPS:-10}
PIXEL_FORMAT=${PIXEL_FORMAT:-nv12}
DURATION_US=${DURATION_US:-60000000}
FRAME_DURATION_US=${FRAME_DURATION_US:-}
WORKDIR=${WORKDIR:-/tmp/rk1106-webrtc-push}
LOCAL_HOST=${LOCAL_HOST:-192.168.3.165}
SIGNAL_BASE_URL=${SIGNAL_BASE_URL:-}
OFFER_URL_WAS_SET=${OFFER_URL+x}
ANSWER_URL_WAS_SET=${ANSWER_URL+x}
OFFER_URL=${OFFER_URL:-}
ANSWER_URL=${ANSWER_URL:-}
OFFER_POLL_TRIES=${OFFER_POLL_TRIES:-120}
OFFER_POLL_INTERVAL=${OFFER_POLL_INTERVAL:-1}
OFFER_POLL_INTERVAL_MS=${OFFER_POLL_INTERVAL_MS:-}
SENDER_LOG=${SENDER_LOG:-"$WORKDIR/sender.log"}
PRINT_LOGS_ON_EXIT=${PRINT_LOGS_ON_EXIT:-0}

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
if [ -z "$OFFER_URL" ]; then
    OFFER_URL=http://192.168.3.8:8081/offer
fi
if [ -z "$ANSWER_URL" ]; then
    ANSWER_URL=http://192.168.3.8:8081/answer
fi

detect_local_host() {
    if command -v ip >/dev/null 2>&1; then
        ip route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") {print $(i + 1); exit}}'
        return 0
    fi
    if command -v hostname >/dev/null 2>&1; then
        hostname -I 2>/dev/null | awk '{print $1}'
        return 0
    fi
    printf '%s\n' "127.0.0.1"
}

check_offer_target() {
    if [ -z "$OFFER_URL" ]; then
        if [ ! -f "$OFFER_JSON" ]; then
            echo "missing offer JSON: $OFFER_JSON" >&2
            echo "Set OFFER_URL/SIGNAL_BASE_URL for Uya HTTP signaling, or copy host/manual_preview.html offer text to this file first." >&2
            exit 2
        fi
    fi
}

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
    print_log_tail "sender log" "$SENDER_LOG" 120
    print_log_tail "diagnostics" "$DIAGNOSTICS_JSON" 40
}

if [ -z "$LOCAL_HOST" ]; then
    LOCAL_HOST=$(detect_local_host)
fi
if [ -z "$LOCAL_HOST" ]; then
    LOCAL_HOST=127.0.0.1
fi

mkdir -p "$WORKDIR"
rm -f "$ANSWER_JSON" "$DIAGNOSTICS_JSON" "$SENDER_LOG"
check_offer_target

sender_pid=
cleanup() {
    if [ -n "${sender_pid:-}" ]; then
        kill "$sender_pid" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

echo "starting Uya V4L2 VP8 WebRTC sender: $VIDEO_DEV ${WIDTH}x${HEIGHT} $PIXEL_FORMAT ${FPS}fps, local candidate $LOCAL_HOST" >&2
set -- \
    --offer-json "$OFFER_JSON" \
    --answer-json "$ANSWER_JSON" \
    --diagnostics-json "$DIAGNOSTICS_JSON" \
    --codec uya \
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
"$BIN_DIR/uya_vp8_direct_sender" "$@" >"$SENDER_LOG" 2>&1 &
sender_pid=$!

tries=0
answer_seen=0
while [ "$tries" -lt 200 ]; do
    if [ -s "$ANSWER_JSON" ]; then
        answer_seen=1
        echo "answer ready: $ANSWER_JSON" >&2
        if [ -n "$ANSWER_URL" ]; then
            echo "Uya sender posted answer to $ANSWER_URL" >&2
        else
            echo "paste it into host/manual_preview.html to start receiving video" >&2
        fi
        break
    fi
    if ! kill -0 "$sender_pid" 2>/dev/null; then
        sender_status=0
        wait "$sender_pid" || sender_status=$?
        echo "sender exited before writing answer (status=$sender_status)" >&2
        print_runtime_logs
        exit "$sender_status"
    fi
    tries=$((tries + 1))
    sleep 0.1
done

if [ "$answer_seen" -eq 0 ]; then
    echo "answer was not ready after polling window; waiting for sender exit" >&2
fi

sender_status=0
wait "$sender_pid" || sender_status=$?
echo "sender finished (status=$sender_status)" >&2
if [ "$sender_status" -ne 0 ] || [ "$PRINT_LOGS_ON_EXIT" = "1" ]; then
    print_runtime_logs
fi
exit "$sender_status"
