# 纯 Uya WebRTC v0.2.0 版本说明

发布日期：2026-06-11  
版本标签：`v0.2.0`  
发布提交：见 `v0.2.0` 标签指向的提交  
目标平台：Linux x86_64 host + RK1106/RV1103B board example

## 版本定位

`v0.2.0` 是 RK1106 H264/G711 板端直推里程碑版本。这个版本保留
`v0.1.0` 的纯 Uya WebRTC transport 边界，在此基础上把 RK1106 板端
H264 push-client 推到可打包、可预览、可低延迟恢复的状态。

本版本重点证明：RK1106/RV1103B 板端可以由 fastboot helper 产生 H264
Annex-B FIFO 和 G711 FIFO，再由 Uya sender 完成 DTLS/SRTP、RTP packetize、
SRTCP/RTCP、ICE/STUN 控制和 Chrome recvonly 预览。FFmpeg 仍只作为 host
测试和 reference codec 边界，不进入板端默认 runtime。

## 重点能力

- RK1106 H264 push-client：新增并持续完善 `examples/rk1106_h264_push_client`，
  支持板端 package、host signaling、Chrome manual preview 和自动首屏回归。
- 浏览器预览：`host/manual_preview.html` 强制优先 H264 与 RK1106 G711
  `PCMU/PCMA`，并展示首帧、丢帧、freeze、jitter target delay 与 codec stats。
- 低延迟 FIFO catch-up：DTLS/SRTP ready 后不再发送旧缓存 IDR，而是从当前
  FIFO 队头向后扫描，丢弃旧 P 帧和旧 IDR，直到找到队列剩余估算低于
  500ms 的可解码 IDR，再从该 IDR 开始发送。
- 首屏可解码性：helper 与 sender 都缓存 SPS/PPS，过滤裸 IDR，避免 Chrome
  已 connected 但解码器继续等待参数集。
- 恢复音频：板端默认开启 G711 音频，helper 写 `/tmp/fastboot.g711`，
  sender 发送 G711 RTP；协商到非 G711 时仍自动关闭音频并保持视频/ICE。
- 720p 启动策略：默认最终主码流为 `1280x720` / `600000` bps；启动阶段
  使用 `640x360` / `150000` bps，30fps 下约 3 秒后切到 720p 主通道并请求
  新 IDR。
- 版本化 CLI：`build/webrtc-uya version` 输出 `webrtc-uya 0.2.0`。

## 使用入口

通用构建和版本确认：

```sh
make build
build/webrtc-uya version
```

RK1106 H264 push-client host/board 打包：

```sh
make -C examples/rk1106_h264_push_client host
make -C examples/rk1106_h264_push_client package
```

host 侧启动 signaling/manual preview：

```sh
cd examples/rk1106_h264_push_client
python3 host/signaling_server.py --host 0.0.0.0 --port 8081
```

板端默认运行：

```sh
cd /userdata/rk1106-h264-push-client
./board_run.sh
```

常用板端覆盖项：

```sh
FASTBOOT_VIDEO_WIDTH=1280
FASTBOOT_VIDEO_HEIGHT=720
FASTBOOT_STARTUP_VIDEO_WIDTH=640
FASTBOOT_STARTUP_VIDEO_HEIGHT=360
FASTBOOT_H264_BITRATE=600000
FASTBOOT_H264_START_BITRATE=150000
FASTBOOT_H264_RAMP_FRAMES=90
DISABLE_AUDIO=0
```

## 发布验证

2026-06-11 本地发布验证已通过：

- `bash tests/check_rk1106_h264_first_screen.sh`
- `git diff --check`
- `make build`
- `build/webrtc-uya version`
- `make test`
- `make -C examples/rk1106_h264_push_client host`
- `make -C examples/rk1106_h264_push_client fastboot-fifo`
- `make -C examples/rk1106_h264_push_client package`
- `python3 tests/rk1106_h264_chrome_first_screen.py --no-build --duration-us 5000000 --steady-min-frames 1`

Chrome 首屏回归样例统计：

- `connectedToFirstFrame=22ms`
- `answerToFirstFrame=27ms`
- `framesDecoded=30`
- `framesDropped=0`
- `freezeCount=0`
- `jitterTargetDelayS=0.011`
- `audioRtpPackets=84`
- `uyaG711AudioReady=true`

## 已知限制

- RK1106 板端链路依赖 Rockchip SDK、MPI、VENC/AENC、AI 设备和实际网络环境；
  本地发布验证覆盖交叉编译、打包和 Chrome host 回归，真实板端仍需要现场跑
  `board_run.sh` 验收。
- 启动阶段分辨率切换使用 fastboot helper 的主/子通道输出切换；如果产品配置
  改成非默认通道，需要同时检查 `FASTBOOT_VENC_CHANNEL` 和
  `FASTBOOT_STARTUP_VENC_CHANNEL`。
- G711 音频为 8 kHz mono、60ms packet；音视频仍是独立 pacing 路径，复杂现场
  时钟漂移需要继续板端长时间观测。
- 纯 Uya Opus codec bridge 的完整 sibling encoder/decoder 与 RTP Opus 能力仍未
  作为生产路径发布。
- `../vp8` UPM path dependency 仍待 sibling 仓库提供 package-mode manifest，并通过
  当前 Uya package-mode cast checks；纯 Uya VP8 gate 仍使用 legacy staging。
- macOS kqueue、Windows IOCP、Android、iOS 和完整平台 CI matrix 仍需要对应
  runner、FFI 或 SDK 才能验收。

## 适合验证的场景

- 验证纯 Uya WebRTC transport 在 RK1106/RV1103B 板端 H264/G711 直推中的可用性。
- 验证板端 H264 FIFO 堆积后通过 IDR catch-up 回到低延迟播放。
- 验证 RK1106 G711 音频协商、FIFO 读取和 RTP 发送路径。
- 验证 Chrome 手工预览页的首帧、丢帧、freeze 和 codec stats 观测能力。

## 不适合作为承诺的场景

- 不承诺所有 RK1106 固件、sensor、VENC/AENC 参数组合都无需现场调参。
- 不承诺音视频共享同一硬件时钟或长时间绝对同步。
- 不承诺默认 runtime 内置 FFmpeg/libopus/libvpx。
- 不把 host fallback sender 的 Chrome 首屏回归等同于真实板端全链路验收。
