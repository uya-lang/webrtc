# Changelog

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
