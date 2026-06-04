# Changelog

## v0.1.0 - 2026-06-04

纯 Uya WebRTC transport 里程碑版本。该版本聚焦 Linux 默认平台、浏览器互通、DataChannel、encoded-frame RTP/SRTP 媒体路径，以及显式 reference codec 测试边界。

详细版本说明：[docs/release-v0.1.0.md](docs/release-v0.1.0.md)

### 发布能力

- 完成 SDP、STUN/TURN、ICE、DTLS 1.2、SRTP/SRTCP、RTP/RTCP、SCTP DataChannel、PeerConnection、Stats/Trace、拥塞控制和 jitter/reassembly 基础能力。
- Chrome / Firefox / Pion / aiortc 互通脚本已纳入测试入口，GStreamer webrtcbin 因当前 GI runtime 无法形成真实 offer/answer，仍记录为 blocked。
- `make test-ffmpeg-chrome-call` 可显式启用 FFmpeg reference codec，通过 Uya direct sender 将 Opus/VP8 RTP 经 SRTP/UDP 推给 Chrome recvonly peer，并验证 inbound RTP 和 decoded frames。
- `make test-codec-bridge` 已接入纯 Uya `../vp8` sibling 的显式 bridge gate，覆盖 I420 -> VP8 `EncodedFrame` -> I420 roundtrip 以及 RTP VP8 descriptor/reassembly 语义。
- `make preview-ffmpeg-chrome-call` 提供手工预览入口，支持默认测试源和指定 MP4 源。
- `build/webrtc-uya version` 输出 `webrtc-uya 0.1.0`。

### 已知阻塞

- 纯 Uya Opus codec bridge 的完整 sibling encoder/decoder 与 RTP Opus 能力仍未接入生产路径。
- `../vp8` 当前通过 legacy staging 进入显式 bridge gate；切换为 UPM path dependency 还需要 sibling 仓库提供 package-mode manifest 并通过当前 Uya package-mode cast checks。
- SDP fuzz 真实 parser smoke 仍受 Uya C99 nested byte array field codegen 问题阻塞。
- macOS kqueue、Windows IOCP、Android、iOS 和完整平台 CI matrix 需要对应 runner、FFI 或 SDK 才能真实验收。
- FFmpeg 只作为显式 reference codec / Chrome interop 测试边界使用，默认 runtime 不引入 FFmpeg、libopus 或 libvpx。

### 发布验证

2026-06-04 本地已通过：

- `make test`
- `make bench`
- `make test-codec-bridge`
- `make test-ffmpeg-chrome-call`

`make test-ffmpeg-chrome-call` 的 Chrome direct call 统计：`chrome_audio_packets=235`、`chrome_video_packets=141`、`chrome_video_frames=141`、`sender_rtp_packets=481`、`sender_srtp_packets=481`、`sender_srtcp_packets=12`、`sender_udp_packets=493`。1080p MP4 preview 路径也通过，`chrome_video_size=1920x1080`、`chrome_video_frames=23`。
