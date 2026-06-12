# Changelog

## v0.3.0 - 2026-06-12

Chrome direct media PeerConnection 里程碑版本。该版本在 `v0.2.0` RK1106
板端直推基础上，把通用 PeerConnection 从 DataChannel-only 推进到可生成
Chrome video SDP、接收 SRTP/VP8 RTP 并路由到 receiver 的验证闭环，同时补齐
host FFmpeg Chrome call 的快速手工入口。

详细版本说明：[docs/release-v0.3.0.md](docs/release-v0.3.0.md)

### 发布能力

- PeerConnection 增加 `addTransceiver`、`addTrack`、音视频 SDP writer 和
  Chrome video 收包路径，`make test` 已纳入 Phase 14 Chrome video gate。
- 新增 VP8 RTP payload descriptor / packetizer / reassembly 模块与 Uya 侧测试，
  供 PeerConnection video 接收和 direct sender 共享。
- direct runtime 和 direct sender 补齐控制包处理、RTCP 反馈接收统计与
  receiver-facing 计数，Chrome call 统计能看到 inbound/outbound 两侧状态。
- 新增 `make host-ffmpeg-chrome-call` / `host-ffmpeg-chrome-call-playback`，
  使用预构建 sender executable，支持本机设备、自动选择局域网地址、可选本地播放
  和手工浏览器互通。
- FFmpeg Chrome call harness 增加 contract、playback smoke、manual preview E2E、
  MP4 全尺寸预览和 sender executable 复用验证。
- `build/webrtc-uya version` 输出 `webrtc-uya 0.3.0`。

### 已知限制

- PeerConnection 的 Chrome video gate 已覆盖 SDP 和 SRTP/VP8 接收路由，但通用
  PeerConnection 仍不是完整浏览器 P2P 音视频产品 API；真实采集、渲染和生产级
  transceiver 生命周期仍由 direct sender / 示例入口承接。
- host FFmpeg Chrome call 仍是显式 reference codec / 手工验证入口，不进入默认
  runtime，也不改变默认纯 Uya transport 边界。
- 纯 Uya Opus codec bridge、`../vp8` UPM path dependency、跨平台 CI matrix 等
  限制仍沿用 `v0.1.0` / `v0.2.0` 的记录。
- RK1106 板端真实链路仍需要现场设备和网络环境验收。

### 发布验证

2026-06-12 本地发布验证已通过：

- `./uya/bin/uya --version` 输出 `v0.10.0`
- `git diff --check`
- `make build`
- `build/webrtc-uya version`
- `UYA=./uya/bin/uya make test`
- `UYA=./uya/bin/uya make test-ffmpeg-chrome-call`
- `timeout 15s make host-ffmpeg-chrome-call UYA=./uya/bin/uya HOST_CALL_DURATION_US=3000000 HOST_CALL_PORT=0`
  启动 smoke，确认输出 `host ffmpeg chrome call serving: http://127.0.0.1:.../`

## v0.2.0 - 2026-06-11

RK1106 H264/G711 板端直推里程碑版本。该版本在 `v0.1.0` 纯 Uya WebRTC transport 基座之上，补齐 RK1106 H264 push-client 的板端打包、浏览器手工预览、G711 音频、低延迟 FIFO catch-up、首屏关键帧处理和 720p 启动策略。

详细版本说明：[docs/release-v0.2.0.md](docs/release-v0.2.0.md)

### 发布能力

- 新增 `examples/rk1106_h264_push_client`，支持 RK1106/RV1103B 板端 H264 Annex-B FIFO -> Uya RTP/SRTP -> Chrome recvonly 预览链路。
- 浏览器预览页强制优先 `H264/90000` 与 `PCMU/PCMA`，并展示 `connectedToFirstFrame`、`answerToFirstFrame`、丢帧、freeze、jitter target delay 和 codec stats。
- fastboot helper 支持连续 H264 FIFO 输出、SPS/PPS 缓存、裸 IDR 过滤、G711 helper FIFO 和板端 package 打包。
- sender 在 DTLS/SRTP ready 后从当前 FIFO 队头向后扫描，丢弃旧 P 帧和旧 IDR，直到找到队列剩余估算低于 500ms 的可解码 IDR，再从该 IDR 开始发送并保留更新的 P 帧。
- 板端默认恢复音频，helper 写 `/tmp/fastboot.g711`，sender 发送 G711 RTP；`DISABLE_AUDIO=1` 可回退 video-only。
- 板端默认最终主码流恢复 `1280x720` / `600000` bps，启动阶段使用 `640x360` / `150000` bps，30fps 下约 3 秒后切到 720p 主通道并请求新 IDR。
- `build/webrtc-uya version` 输出 `webrtc-uya 0.2.0`。

### 已知限制

- RK1106 板端链路依赖 Rockchip SDK、MPI、VENC/AENC、AI 设备和实际网络环境；本地发布验证覆盖交叉编译、打包和 Chrome host 回归，真实板端仍需现场跑 `board_run.sh` 验收。
- 启动阶段分辨率切换使用 fastboot helper 的主/子通道输出切换，若产品配置改为非默认通道，需要同时检查 `FASTBOOT_VENC_CHANNEL` 与 `FASTBOOT_STARTUP_VENC_CHANNEL`。
- G711 音频为 8 kHz mono、60ms packet；音视频仍是独立 pacing 路径，复杂现场时钟漂移还需要板端长时间观测。
- `v0.1.0` 中记录的跨平台 CI、纯 Uya Opus 生产路径、UPM path dependency 等限制仍然适用。

### 发布验证

2026-06-11 本地已通过：

- `bash tests/check_rk1106_h264_first_screen.sh`
- `git diff --check`
- `make build`
- `build/webrtc-uya version`
- `make test`
- `make -C examples/rk1106_h264_push_client host`
- `make -C examples/rk1106_h264_push_client fastboot-fifo`
- `make -C examples/rk1106_h264_push_client package`
- `python3 tests/rk1106_h264_chrome_first_screen.py --no-build --duration-us 5000000 --steady-min-frames 1`

Chrome 首屏回归样例统计：`connectedToFirstFrame=22ms`、`answerToFirstFrame=27ms`、`framesDecoded=30`、`framesDropped=0`、`freezeCount=0`、`jitterTargetDelayS=0.011`、`audioRtpPackets=84`、`uyaG711AudioReady=true`。

## v0.1.0 - 2026-06-04

纯 Uya WebRTC transport 里程碑版本。该版本聚焦 Linux 默认平台、浏览器互通、DataChannel、encoded-frame RTP/SRTP 媒体路径，以及显式 reference codec 测试边界。

详细版本说明：[docs/release-v0.1.0.md](docs/release-v0.1.0.md)

### 发布能力

- 完成 SDP、STUN/TURN、ICE、DTLS 1.2、SRTP/SRTCP、RTP/RTCP、SCTP DataChannel、PeerConnection、Stats/Trace、拥塞控制和 jitter/reassembly 基础能力。
- Chrome / Firefox / Pion / aiortc 互通脚本已纳入测试入口，GStreamer webrtcbin 因当前 GI runtime 无法形成真实 offer/answer，仍记录为 blocked。
- `make test-ffmpeg-chrome-call` 可显式启用 FFmpeg reference codec，由 Uya direct sender 在发送循环中将 raw PCM/I420 实时编码为 Opus/VP8，再经 RTP/SRTP/UDP 推给 Chrome recvonly peer，并验证 inbound RTP 和 decoded frames。
- `make test-codec-bridge` 已接入纯 Uya `../vp8` sibling 的显式 bridge gate，覆盖 I420 -> VP8 `EncodedFrame` -> I420 roundtrip 以及 RTP VP8 descriptor/reassembly 语义。
- `make test-uya-vp8-chrome-call` 已接入纯 Uya `../vp8` sibling 的 video-only Chrome E2E：Uya VP8 live sender 在发送循环中调用 `../vp8` bridge 将 raw I420 编码为 VP8 `EncodedFrame`，再完成 RTP/SRTP/UDP 发送，Chrome recvonly peer 验证 inbound RTP 和 decoded VP8 frames。
- `make preview-ffmpeg-chrome-call` 提供手工预览入口，支持默认测试源和指定 MP4 源。
- `make preview-uya-vp8-chrome-call` 提供纯 Uya VP8 video-only 手工预览入口，支持 `MP4=/absolute/path/to/source.mp4`；默认将 MP4 预览缩到 160px 宽并截取 2s，并按宽度自动选择 FPS，可用 `UYA_VP8_PREVIEW_FPS` 覆盖以降低纯 Uya keyframe 编码负载；preview server 先用 `UYA_VP8_PREVIEW_CFLAGS` 预构建 Uya sender，点击 Start 时直接运行 executable；默认保留 VP8 SIMD/asm dispatch，可用 `UYA_VP8_FORCE_SCALAR=1` 复现 scalar 路径；FFmpeg 只用于显式 MP4 -> raw I420 源转换，VP8 编码与 RTP/SRTP/UDP 发送仍走 Uya。
- `build/webrtc-uya version` 输出 `webrtc-uya 0.1.0`。

### 已知阻塞

- 纯 Uya Opus codec bridge 的完整 sibling encoder/decoder 与 RTP Opus 能力仍未接入生产路径。
- `../vp8` 当前通过 legacy staging 进入显式 bridge gate 和 video-only Chrome gate；切换为 UPM path dependency 还需要 sibling 仓库提供 package-mode manifest 并通过当前 Uya package-mode cast checks。
- SDP fuzz 真实 parser smoke 仍受 Uya C99 nested byte array field codegen 问题阻塞。
- macOS kqueue、Windows IOCP、Android、iOS 和完整平台 CI matrix 需要对应 runner、FFI 或 SDK 才能真实验收。
- FFmpeg 只作为显式 reference codec / Chrome interop 测试边界使用，默认 runtime 不引入 FFmpeg、libopus 或 libvpx。

### 发布验证

2026-06-04 本地已通过：

- `make test`
- `make bench`
- `make test-codec-bridge`
- `make test-ffmpeg-chrome-call`
- `make test-uya-vp8-chrome-call`

`make test-ffmpeg-chrome-call` 的 Chrome direct call 统计：`chrome_audio_packets=235`、`chrome_video_packets=141`、`chrome_video_frames=141`、`sender_rtp_packets=481`、`sender_srtp_packets=481`、`sender_srtcp_packets=12`、`sender_udp_packets=493`。1080p MP4 preview 路径也通过，`chrome_video_size=1920x1080`、`chrome_video_frames=23`。

`make test-uya-vp8-chrome-call` 的 Chrome video-only direct call 本地样例统计：`source_video_codec=vp8`、`source_video_size=32x18`、`chrome_video_packets=82`、`chrome_video_frames=81`、`sender_rtp_packets=91`、`sender_srtp_packets=91`、`sender_srtcp_packets=3`、`sender_udp_packets=94`；Chrome decoded frame 计数会随本机调度轻微波动。

`make preview-uya-vp8-chrome-call` 的 MP4 manual preview E2E smoke 统计：`source_kind=mp4`、`preview_size=32x18`、`preview_duration_us=999990`、`chrome_video_packets=31`、`chrome_video_frames=31`、`sender_rtp_packets=31`、`sender_srtp_packets=31`、`sender_udp_packets=32`。
