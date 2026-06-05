# RK1106/RV1103B V4L2 WebRTC push client

This example builds a board-side video push client for
`/home/winger/rk1106/builder/rv1103b_linux_ipc_sdk`.

It uses:

- `uya_vp8_direct_sender`: the pure Uya VP8 WebRTC direct sender with built-in
  V4L2 mmap capture.
- `board_run.sh`: starts the Uya sender with the board V4L2/signaling defaults.
- `host_run.sh`: starts the same sender flow on the host for local webcam
  browser validation.
- `host_ffmpeg_run.sh`: starts the host-only FFmpeg codec sender with the same
  V4L2/signaling flow.
- `host/signaling_server.py`: a tiny offer/answer relay for bring-up.
- `host/manual_preview.html`: a browser preview page that can auto signal.

## Video device

Use standard V4L2 capture. On this RV1103B/RK1106 SDK board, previous logs map
VI pipe0 channels to these video nodes:

- `/dev/video7`: chn0, `rkisp_mainpath`, default for this example.
- `/dev/video8`: chn1, selfpath candidate.
- `/dev/video9`: chn2, bypasspath candidate.

The Uya sender supports single-plane V4L2 capture and the RKISP-style NV12M
multi-plane path. If `/dev/video7` prints a capability or format error, inspect
the board first:

```sh
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video7 --all
v4l2-ctl -d /dev/video7 --list-formats-ext
media-ctl -p -d /dev/media0
```

Then start WebRTC directly from the V4L2 node:

```sh
./uya_vp8_direct_sender \
    --offer-url http://192.168.3.8:8080/offer \
    --answer-url http://192.168.3.8:8080/answer \
    --answer-json /tmp/answer.json \
    --diagnostics-json /tmp/diagnostics.json \
    --v4l2-device /dev/video7 \
    --v4l2-format nv12 \
    --video-width 320 \
    --video-height 180 \
    --video-frame-duration-us 100000 \
    --media-duration-us 60000000 \
    --local-host 192.168.3.165 \
    --codec uya
```

To test only the Uya V4L2 capture path, without browser signaling:

```sh
./uya_vp8_direct_sender --v4l2-test-frames 10 \
    --v4l2-device /dev/video7 --v4l2-format nv12 \
    --video-width 320 --video-height 180 --video-frame-duration-us 100000
```

Then override the node at runtime:

```sh
VIDEO_DEV=/dev/video8 ./board_run.sh offer.json answer.json
```

## Build on host

The Makefile defaults to the toolchain path you provided:

```sh
make -C examples/rk1106_v4l2_push_client package
```

The package is written to:

```sh
examples/rk1106_v4l2_push_client/build/rk1106-v4l2-push-client
```

Copy it to the board, for example:

```sh
scp -r examples/rk1106_v4l2_push_client/build/rk1106-v4l2-push-client root@BOARD_IP:/userdata/
```

For local x86_64 V4L2 smoke tests, build the host binary explicitly:

```sh
make -C examples/rk1106_v4l2_push_client host
examples/rk1106_v4l2_push_client/build/uya_vp8_direct_sender_host \
    --v4l2-test-frames 2 \
    --v4l2-device /dev/video0 --v4l2-format yuyv \
    --video-width 320 --video-height 240 --video-frame-duration-us 66666
```

Do not use stale files under `.uyacache/src/` for this smoke test; they may be
from an older Uya build and can print the old `--media`-only usage.

## Full host WebRTC validation

Use this before copying the package to the board. It verifies the full path:

```text
host V4L2 camera -> Uya I420 conversion -> Uya VP8 encode -> WebRTC RTP/SRTP -> browser video
```

Terminal 1:

```sh
python3 examples/rk1106_v4l2_push_client/host/signaling_server.py \
    --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080/manual_preview.html` in the browser and click
`Auto Signal`.

Terminal 2:

```sh
make -C examples/rk1106_v4l2_push_client host
examples/rk1106_v4l2_push_client/host_run.sh
```

For the host USB camera detected earlier, the defaults are:

```sh
VIDEO_DEV=/dev/video0
PIXEL_FORMAT=yuyv
WIDTH=320
HEIGHT=240
FPS=15
LOCAL_HOST=127.0.0.1
SIGNAL_BASE_URL=http://127.0.0.1:8080/api
```

Expected sender milestones:

```text
uya_vp8_direct_sender: answer JSON posted
uya_vp8_direct_sender: V4L2 capture started
uya_vp8_direct_sender: received browser STUN
uya_vp8_direct_sender: DTLS/SRTP ready
uya_vp8_direct_sender: first VP8 frame sent
```

To validate the same host webcam path with the FFmpeg VP8 codec bridge instead
of the pure Uya VP8 encoder, keep Terminal 1 and the browser page running, then
run:

```sh
examples/rk1106_v4l2_push_client/host_ffmpeg_run.sh
```

This runs `src/webrtc_ffmpeg_direct_sender_main.uya` directly through `uya run`.
The expected milestones are:

```text
uya_ffmpeg_direct_sender: answer JSON posted
uya_ffmpeg_direct_sender: V4L2 capture started
```

The FFmpeg variant is for host validation. It depends on the repo's host
FFmpeg codec bridge cache and is not included in the RK1106 board package.

## Browser preview with signaling

On the host:

```sh
python3 examples/rk1106_v4l2_push_client/host/signaling_server.py \
    --host 0.0.0.0 --port 8080
```

Open `http://HOST_IP:8080/manual_preview.html` in the browser and click
`Auto Signal`. The page creates an offer, posts it to the server, waits for the
board answer, and sets the answer automatically.

On the board:

```sh
cd /userdata/rk1106-v4l2-push-client
./board_run.sh
```

For each new run, click `Auto Signal` first so the server has a fresh browser
offer, then start or restart `board_run.sh`. If the board answers an old offer
left on the server, the browser will not connect to that answer.

By default the Uya sender uses these board bring-up addresses:

```sh
OFFER_URL=http://192.168.3.8:8080/offer
ANSWER_URL=http://192.168.3.8:8080/answer
LOCAL_HOST=192.168.3.165
```

The board polls `OFFER_URL`, writes `answer.json`, then posts it to
`ANSWER_URL`. The HTTP GET/POST runs inside `uya_vp8_direct_sender`; the board
script does not require `curl` or `wget`.

To use a different server, provide explicit endpoints:

```sh
OFFER_URL=http://SERVER/path/to/offer \
ANSWER_URL=http://SERVER/path/to/answer \
LOCAL_HOST=BOARD_IP ./board_run.sh
```

`GET OFFER_URL` must return the browser offer JSON. `POST ANSWER_URL` receives
the answer JSON body. These requests are sent by the board-side Uya binary.

The old manual file workflow still works:

```sh
./board_run.sh offer.json answer.json
```

Useful runtime overrides:

```sh
VIDEO_DEV=/dev/video7
PIXEL_FORMAT=nv12     # also accepts nv12m/i420/i420m/yv12/yv12m/yuyv/uyvy
WIDTH=320
HEIGHT=180
FPS=10
DURATION_US=60000000
LOCAL_HOST=192.168.1.50
SIGNAL_BASE_URL=http://192.168.1.10:8080/api
OFFER_POLL_TRIES=120  # 0 waits forever
OFFER_POLL_INTERVAL_MS=1000
SENDER_LOG=/tmp/rk1106-webrtc-push/sender.log
```

`LOCAL_HOST` must be the board IP reachable by the browser. It is hardcoded to
`192.168.3.165` for this board bring-up; override it if the board IP changes.
If the sender exits early, `board_run.sh` prints the tail of `sender.log` and
the diagnostics JSON on the console.

Useful sender log milestones:

```text
uya_vp8_direct_sender: received browser STUN
uya_vp8_direct_sender: DTLS/SRTP ready
uya_vp8_direct_sender: V4L2 capture started
uya_vp8_direct_sender: first VP8 frame sent
```

If `received browser STUN` is missing, the browser did not send UDP checks to
the board candidate. Check that the browser applied the latest answer and can
reach `LOCAL_HOST`.

## Notes

- The current sender path is VP8 video. The browser offer still includes both
  audio and video m-lines because the existing direct sender validates Chrome
  recvonly Opus/VP8 offers.
- Keep the first run small, for example `320x180@10fps`. The current VP8 encoder
  path is pure Uya scalar on ARM in this example.
- If the sender reports a V4L2 format error, use `v4l2-ctl --list-formats-ext`
  to pick a supported `WIDTH`, `HEIGHT`, and `PIXEL_FORMAT`, or choose another
  V4L2 node/path.
