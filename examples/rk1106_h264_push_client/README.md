# RK1106/RV1103B V4L2 H264 WebRTC push client

This example builds a board-side WebRTC video push client for RK1106/RV1103B.

Pipeline:

```text
V4L2 camera -> Uya I420 conversion -> RK MPP H264 encode -> H264 RTP/SRTP -> browser
```

The WebRTC signaling, ICE-lite/STUN, DTLS/SRTP, RTCP sender report, V4L2 mmap
capture, and H264 RTP packetization live in Uya. The Rockchip-specific H264
encoder is isolated in `src/rk1106_h264_encoder_shim.c`.

The board build links the shim against RK MPP. The `host` build uses the same
Uya WebRTC sender and V4L2 path, but starts the local `ffmpeg` CLI as a fallback
H264 encoder so the browser pipeline can be validated before copying to the
board.

## Build

The Makefile defaults to the RK1106 SDK path used by the other examples:

```sh
make -C examples/rk1106_h264_push_client package
```

The package is written to:

```sh
examples/rk1106_h264_push_client/build/rk1106-h264-push-client
```

For local host validation:

```sh
make -C examples/rk1106_h264_push_client host
```

This requires `ffmpeg` with `libx264` support on `PATH`.

Copy it to the board:

```sh
scp -r examples/rk1106_h264_push_client/build/rk1106-h264-push-client root@BOARD_IP:/userdata/
```

## Run

On the host:

```sh
python3 examples/rk1106_h264_push_client/host/signaling_server.py \
    --host 0.0.0.0 --port 8080
```

Open `http://HOST_IP:8080/manual_preview.html` in Chrome and click
`Auto Signal`. Chrome must include `H264/90000` in the offer.

On the board:

```sh
cd /userdata/rk1106-h264-push-client
./board_run.sh
```

Useful runtime overrides:

```sh
VIDEO_DEV=/dev/video7
PIXEL_FORMAT=nv12
WIDTH=320
HEIGHT=180
FPS=10
BITRATE=1000000
GOP=30
DURATION_US=60000000
LOCAL_HOST=192.168.3.165
SIGNAL_BASE_URL=http://192.168.3.8:8080/api
OFFER_POLL_TRIES=120
OFFER_POLL_INTERVAL_MS=1000
```

You can also run the binary directly:

```sh
./rk1106_h264_sender \
    --offer-url http://192.168.3.8:8080/offer \
    --answer-url http://192.168.3.8:8080/answer \
    --answer-json /tmp/answer.json \
    --diagnostics-json /tmp/diagnostics.json \
    --v4l2-device /dev/video7 \
    --v4l2-format nv12 \
    --video-width 320 \
    --video-height 180 \
    --video-frame-duration-us 100000 \
    --h264-bitrate 1000000 \
    --h264-gop 30 \
    --media-duration-us 60000000 \
    --local-host 192.168.3.165 \
    --codec uya
```

To test only V4L2 capture without browser signaling:

```sh
./rk1106_h264_sender --v4l2-test-frames 10 \
    --v4l2-device /dev/video7 --v4l2-format nv12 \
    --video-width 320 --video-height 180 --video-frame-duration-us 100000
```

Expected sender milestones:

```text
rk1106_h264_sender: answer JSON posted
rk1106_h264_sender: V4L2 capture started
rk1106_h264_sender: received browser STUN
rk1106_h264_sender: DTLS/SRTP ready
rk1106_h264_sender: first H264 frame sent
```

If the sender exits early, `board_run.sh` prints the tail of `sender.log` and
`diagnostics.json`.
