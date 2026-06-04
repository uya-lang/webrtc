# Changelog

## v0.1.0 - 2026-06-04

纯 Uya WebRTC transport 里程碑版本。该版本聚焦 Linux 默认平台、浏览器互通、DataChannel、encoded-frame RTP/SRTP 媒体路径，以及显式 reference codec 测试边界。

### 发布能力

- 完成 SDP、STUN/TURN、ICE、DTLS 1.2、SRTP/SRTCP、RTP/RTCP、SCTP DataChannel、PeerConnection、Stats/Trace、拥塞控制和 jitter/reassembly 基础能力。
- Chrome / Firefox / Pion / aiortc 互通脚本已纳入测试入口，GStreamer webrtcbin 因当前 GI runtime 无法形成真实 offer/answer，仍记录为 blocked。
- `make test-ffmpeg-chrome-call` 可显式启用 FFmpeg reference codec，通过 Uya direct sender 将 Opus/VP8 RTP 经 SRTP/UDP 推给 Chrome recvonly peer，并验证 inbound RTP 和 decoded frames。
- `make preview-ffmpeg-chrome-call` 提供手工预览入口，支持默认测试源和指定 MP4 源。
- `build/webrtc-uya version` 输出 `webrtc-uya 0.1.0`。

### 已知阻塞

- 纯 Uya Opus/VP8 codec bridge 的 sibling 对齐仍等待 `../opus` RTP Opus 与 `../vp8` RTP VP8 payload/reassembly 能力落地。
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
