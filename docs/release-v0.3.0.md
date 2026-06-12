# 纯 Uya WebRTC v0.3.0 版本说明

发布日期：2026-06-12  
版本标签：`v0.3.0`  
发布提交：见 `v0.3.0` 标签指向的提交  
目标平台：Linux x86_64 host + Chrome direct media interop

## 版本定位

`v0.3.0` 是 Chrome direct media PeerConnection 里程碑版本。这个版本保留
`v0.2.0` 的 RK1106 H264/G711 板端直推能力，在通用 PeerConnection 层补齐
Chrome video SDP、transceiver/track 建模、SRTP/VP8 RTP 接收路由和 receiver
统计验证。

本版本重点证明：Uya PeerConnection 不再只停留在 DataChannel-only 的 SDP 和
测试边界，而是可以建立可被 Chrome 理解的 video media section，并把收到的
SRTP/VP8 RTP 包解保护、解析、重组并交给视频 receiver。FFmpeg 仍只作为显式
reference codec / host interop 验证入口，不进入默认 runtime。

## 重点能力

- PeerConnection Chrome video：新增 `addTransceiver`、`addTrack`、video
  `m=` section writer、`processSrtpPacket` 和 `routeVideoFrame` 路径，并通过
  `tests/check_phase14_peer_connection_chrome_video.sh` 纳入 `make test`。
- VP8 RTP 模块：新增 `src/webrtc/media/vp8_rtp.uya`，覆盖 payload descriptor、
  packetize、reassembly 和边界输入测试。
- direct runtime 控制包：`src/webrtc/media/direct_runtime.uya` 补齐 DTLS/STUN/RTCP
  控制 datagram 处理，host/direct sender 共享更完整的运行时统计。
- Chrome call 统计：sender 输出 `srtpPacketsReceived`、`audioRtpPacketsReceived`、
  `videoFramesReceived`、`audioFramesDecoded`、`videoFramesDecoded` 等 receiver
  侧计数，便于区分只发包和真实浏览器媒体闭环。
- host FFmpeg Chrome call：新增 `make host-ffmpeg-chrome-call`，默认先构建
  sender executable，浏览器点击 Start 时直接运行；支持自动选择局域网地址、
  可选 Uya audio capture、本地 ffplay playback 和手工预览 timing 标记。
- 启动提速：host playback 不再在返回 Uya answer 前加入固定 sleep，ffplay
  用 mux pipe 启动，减少 Start 到首帧等待。
- 版本化 CLI：`build/webrtc-uya version` 输出 `webrtc-uya 0.3.0`。

## 使用入口

通用构建和版本确认：

```sh
make build
build/webrtc-uya version
```

PeerConnection/transport 回归：

```sh
make test
```

Chrome direct media / FFmpeg reference codec contract：

```sh
make test-ffmpeg-chrome-call
```

host 侧手工摄像头/麦克风到 Chrome：

```sh
make host-ffmpeg-chrome-call
```

可选本地播放验证：

```sh
make host-ffmpeg-chrome-call-playback
```

## 发布验证

2026-06-12 本地发布验证已通过：

- `git diff --check`
- `make build`
- `build/webrtc-uya version`
- `make test`
- `make test-ffmpeg-chrome-call`
- `timeout 15s make host-ffmpeg-chrome-call HOST_CALL_DURATION_US=3000000 HOST_CALL_PORT=0`
  启动 smoke，确认输出 `host ffmpeg chrome call serving: http://127.0.0.1:.../`

## 已知限制

- PeerConnection Chrome video gate 证明了 SDP 生成、SRTP/VP8 RTP 接收和 receiver
  路由，不等同于完整生产级浏览器 P2P 音视频 API；采集、发送和手工互通仍主要由
  direct sender / host 示例入口承接。
- host FFmpeg Chrome call 是显式 reference codec / 手工验证入口，默认 runtime
  仍不链接 FFmpeg、libopus 或 libvpx。
- 纯 Uya Opus codec bridge 的完整 sibling encoder/decoder 与 RTP Opus 能力仍未
  作为生产路径发布。
- `../vp8` UPM path dependency 仍待 sibling 仓库提供 package-mode manifest，并通过
  当前 Uya package-mode cast checks；纯 Uya VP8 gate 仍使用 legacy staging。
- RK1106 板端真实链路仍依赖 Rockchip SDK、MPI、VENC/AENC、AI 设备和现场网络环境。
- macOS kqueue、Windows IOCP、Android、iOS 和完整平台 CI matrix 仍需要对应
  runner、FFI 或 SDK 才能验收。

## 适合验证的场景

- 验证 PeerConnection 层能生成 Chrome 可接受的视频 SDP。
- 验证 SRTP/VP8 RTP 包可以进入 Uya PeerConnection receiver 路径。
- 验证 host 摄像头/麦克风通过 Uya direct sender 推到 Chrome，并观察首帧 timing。
- 验证 FFmpeg reference codec harness 的 contract、playback smoke 和 manual preview。

## 不适合作为承诺的场景

- 不承诺通用 PeerConnection 已具备完整 transceiver 生命周期和生产级媒体 API。
- 不承诺默认 runtime 内置 FFmpeg/libopus/libvpx。
- 不把 host manual preview 等同于 RK1106 板端全链路验收。
