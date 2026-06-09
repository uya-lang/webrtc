# RK1106/RV1103B V4L2 H264 WebRTC push client

This example builds a board-side WebRTC video push client for RK1106/RV1103B.

Pipeline:

```text
V4L2 camera -> Uya I420 conversion -> RK MPP H264 encode -> H264 RTP/SRTP -> browser
```

The WebRTC signaling, ICE-lite/STUN, DTLS/SRTP, RTCP sender report, V4L2 mmap
capture, and H264 RTP packetization live in Uya. The Rockchip-specific H264
encoder is isolated in `src/rk1106_h264_encoder_shim.c`.

The board build now uses a Rockchip MPI/rockit-backed VI + VENC path closer to `fastboot_demo`, while keeping the existing Uya WebRTC sender above it. The `host` build still uses the same Uya WebRTC sender and starts the local `ffmpeg` CLI as a fallback H264 encoder so the browser pipeline can be validated before copying to the board.

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

Copy the whole directory, not only `rk1106_h264_sender`; `board_run.sh` and the host helper files are part of the packaged workflow. The sender now follows the SDK-style direct MPP link path instead of runtime `dlopen` fallback logic.

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
FPS=30
BITRATE=1000000
GOP=60
DURATION_US=60000000
LOCAL_HOST=192.168.3.165
SIGNAL_BASE_URL=http://192.168.3.8:8080/api
OFFER_POLL_TRIES=120
OFFER_POLL_INTERVAL_MS=1000
FASTBOOT_VENC_CHANNEL=0
FASTBOOT_VIDEO_WIDTH=1280
FASTBOOT_VIDEO_HEIGHT=720
FASTBOOT_VIDEO_FPS=30
FASTBOOT_H264_BITRATE=600000
FASTBOOT_H264_START_BITRATE=300000
FASTBOOT_H264_RAMP_FRAMES=60
```

You can also run the binary directly:

```sh
./rk1106_h264_sender \
    --offer-url http://192.168.3.8:8080/offer \
    --answer-url http://192.168.3.8:8080/answer \
    --answer-json /userdata/webrtc/answer.json \
    --diagnostics-json /userdata/webrtc/diagnostics.json \
    --v4l2-device /dev/video7 \
    --v4l2-format nv12 \
    --video-width 320 \
    --video-height 180 \
    --video-frame-duration-us 33333 \
    --h264-bitrate 1000000 \
    --h264-gop 60 \
    --media-duration-us 60000000 \
    --local-host 192.168.3.165 \
    --codec uya
```

To test only V4L2 capture without browser signaling:

```sh
./rk1106_h264_sender --v4l2-test-frames 10 \
    --v4l2-device /dev/video7 --v4l2-format nv12 \
    --video-width 320 --video-height 180 --video-frame-duration-us 33333
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


## FIFO 方式

推荐使用 FIFO/文件输出，避免日志污染 H264 码流。

板端示例：

```sh
mkfifo /tmp/fastboot.h264
FASTBOOT_H264_OUT=/tmp/fastboot.h264 ./fastboot_h264_fifo &
./rk1106_h264_sender --media /tmp/fastboot.h264
```

如果只想验证 WebRTC/H264 协议链路，可以先复制一个 Annex-B `.h264`
文件到板子，跳过 fastboot/VI/VENC：

```sh
cd /userdata/rk1106-h264-push-client
MEDIA_PATH=/userdata/sample.h264 MEDIA_DURATION_US=6000000 ./board_run.sh
```

这个模式不会启动 `fastboot_h264_fifo`，只验证：

```text
H264 file -> H264 RTP/SRTP -> Chrome
```


## 一键板端运行

打包目录里可直接执行：

```sh
./board_run.sh
```

可选环境变量：

- `FIFO_PATH`
- `MEDIA_PATH`
- `OFFER_URL`
- `ANSWER_URL`
- `LOCAL_HOST`
- `MEDIA_DURATION_US`
- `VIDEO_FRAME_DURATION_US`
- `H264_BITRATE`
- `H264_GOP`
- `FASTBOOT_VENC_CHANNEL`
- `FASTBOOT_VIDEO_WIDTH`
- `FASTBOOT_VIDEO_HEIGHT`
- `FASTBOOT_VIDEO_FPS`
- `FASTBOOT_H264_BITRATE`
- `FASTBOOT_H264_START_BITRATE`
- `FASTBOOT_H264_RAMP_FRAMES`
- `SUPPRESS_KERNEL_LOGS`

默认 fastboot helper 使用 720p 主码流，`FASTBOOT_VIDEO_FPS=30`，
`FASTBOOT_H264_BITRATE=600000`。启动阶段默认先用
`FASTBOOT_H264_START_BITRATE=300000`，写出 `FASTBOOT_H264_RAMP_FRAMES=60`
帧后恢复到目标码率，减轻首帧/启动缓存冲击。码率参数使用 bps；
helper 写入 Rockchip VENC 时会转换为 SDK 要求的 kbps。设置
`FASTBOOT_H264_RAMP_FRAMES=0` 可以关闭启动码率爬升。
`SUPPRESS_KERNEL_LOGS=1` 默认临时压低内核串口日志，避免 WiFi flow-control
日志刷屏；调试内核/驱动时可用 `SUPPRESS_KERNEL_LOGS=0 ./board_run.sh`。
如果 Chrome 统计里 `framesDropped`、`freezeCount`、`pliCount` 或 `nackCount`
持续增长，可以先试更低码率：

```sh
FASTBOOT_H264_BITRATE=400000 ./board_run.sh
```

如果要切回 1080p：

```sh
FASTBOOT_VIDEO_WIDTH=1920 FASTBOOT_VIDEO_HEIGHT=1080 FASTBOOT_VIDEO_FPS=10 FASTBOOT_H264_BITRATE=1000000 ./board_run.sh
```


## 失败诊断

`board_run.sh` 失败时会自动打印：

- sender stderr/stdout
- helper stderr/stdout
- diagnostics 文件
- FIFO 路径状态

可选环境变量：

- `DIAG_PATH`
- `SENDER_STDOUT_LOG`
- `SENDER_STDERR_LOG`
- `HELPER_STDOUT_LOG`
- `HELPER_STDERR_LOG`
- `PRINT_LOGS_ON_SUCCESS=1`
