# 纯 Uya WebRTC v0.1.0 版本说明

发布日期：2026-06-04  
版本标签：`v0.1.0`  
发布提交：`5ae76f0 release: 发布 v0.1.0 里程碑`  
目标平台：Linux x86_64 first

## 版本定位

`v0.1.0` 是纯 Uya WebRTC transport 的首个里程碑版本。这个版本证明了默认运行路径可以在不引入 `libwebrtc`、`BoringSSL`、`usrsctp`、`libsrtp`、`libopus`、`libvpx` 或 FFmpeg runtime 的前提下，完成 WebRTC transport、DataChannel、RTP/SRTP 媒体传输、RTCP feedback、统计诊断和 Chrome 音视频直推验证。

FFmpeg 只作为显式 reference codec / Chrome interop 测试边界使用，用来验证 WebRTC 侧 encoded-frame、RTP packetizer、SRTP、UDP 和浏览器解码路径。默认 runtime 不依赖 FFmpeg。

## 重点能力

- WebRTC transport 基座：SDP、STUN/TURN、ICE、DTLS 1.2、SRTP/SRTCP、RTP/RTCP、SCTP DataChannel、PeerConnection 生命周期、Stats/Trace、拥塞控制、jitter/reassembly。
- 浏览器与生态互通：Chrome、Firefox、Pion、aiortc 相关脚本已纳入测试入口；GStreamer webrtcbin 仍因当前 GI runtime 无法形成真实 offer/answer 而记录为 blocked。
- Uya direct sender：支持在发送循环中通过显式 FFmpeg reference codec 将 raw PCM/I420 实时编码为 Opus/VP8 encoded frames，再由 Uya 侧完成 RTP、SRTP、SRTCP、UDP 发送给 Chrome recvonly peer。
- 纯 Uya VP8 bridge：显式 codec bridge gate 已 legacy-staging `../vp8` sibling，覆盖 I420 -> VP8 `EncodedFrame` -> I420 roundtrip 以及 RTP VP8 descriptor/reassembly 语义。
- 纯 Uya VP8 Chrome gate：`make test-uya-vp8-chrome-call` 显式 legacy-staging `../vp8` sibling，Uya sender 在发送循环中将 raw I420 编码为 VP8 `EncodedFrame` 后推给 Chrome recvonly peer，并验证 video-only inbound RTP 与 decoded frames。
- 纯 Uya VP8 手工预览：`make preview-uya-vp8-chrome-call MP4=/absolute/path/to/source.mp4` 支持 MP4 源 video-only 预览；默认将 MP4 预览缩到 160px 宽并截取 2s，避免当前纯 Uya VP8 scalar encoder 在 live send loop 中长时间占满 CPU；FFmpeg 只用于显式 MP4 -> raw I420 源转换，VP8 编码、RTP/SRTP/UDP 发送与 Chrome 解码验证走 Uya direct sender。
- 手工预览：`make preview-ffmpeg-chrome-call` 可启动本地预览页，播放 Chrome remote `<video>`，并显示 Chrome inbound stats 与 Uya sender diagnostics。
- MP4 源预览：预览命令支持指定 MP4，按源视频实际尺寸和 duration 转换为 raw I420 + mono s16le 后推给 Chrome。
- 版本化 CLI：`build/webrtc-uya version` 输出 `webrtc-uya 0.1.0`。

## 使用入口

```sh
make build
build/webrtc-uya version

make test
make bench
make test-codec-bridge
make test-ffmpeg-chrome-call
make test-uya-vp8-chrome-call
```

手工预览默认测试源：

```sh
make preview-ffmpeg-chrome-call
```

手工预览指定 MP4：

```sh
make preview-ffmpeg-chrome-call MP4=/absolute/path/to/source.mp4
make preview-uya-vp8-chrome-call MP4=/absolute/path/to/source.mp4
make preview-uya-vp8-chrome-call MP4=/absolute/path/to/source.mp4 UYA_VP8_PREVIEW_MAX_WIDTH=320 UYA_VP8_PREVIEW_MAX_DURATION=3
```

## 发布验证

2026-06-04 本地发布验证已通过：

- `make test`
- `make bench`
- `make test-codec-bridge`
- `make test-ffmpeg-chrome-call`
- `make test-uya-vp8-chrome-call`

Chrome direct call 验证统计：

- `source_audio_codec=opus`
- `source_audio_packets=201`
- `source_video_codec=vp8`
- `source_video_packets=120`
- `chrome_audio_packets=235`
- `chrome_video_packets=141`
- `chrome_video_frames=141`
- `sender_ffmpeg_frames=481`
- `sender_rtp_packets=481`
- `sender_srtp_packets=481`
- `sender_srtcp_packets=12`
- `sender_rtcp_sender_reports=12`
- `sender_srtcp_packets_received=6`
- `sender_rtcp_receiver_reports=6`
- `sender_udp_packets=493`

Synthetic manual preview 验证统计：

- `source_kind=synthetic`
- `preview_size=32x18`
- `preview_duration_us=6000000`
- `chrome_video_size=32x18`
- `chrome_audio_packets=250`
- `chrome_video_packets=150`
- `chrome_video_frames=150`
- `sender_rtp_packets=481`
- `sender_srtp_packets=481`
- `sender_srtcp_packets=12`
- `sender_udp_packets=493`

1080p MP4 manual preview 验证统计：

- `source_kind=mp4`
- `preview_size=1920x1080`
- `preview_duration_us=1000000`
- `chrome_video_size=1920x1080`
- `chrome_audio_packets=23`
- `chrome_video_packets=342`
- `chrome_video_frames=23`
- `sender_rtp_packets=365`
- `sender_srtp_packets=365`
- `sender_srtcp_packets=2`
- `sender_udp_packets=367`

纯 Uya VP8 Chrome video-only 本地样例验证统计：

- `source_video_codec=vp8`
- `source_video_size=32x18`
- `chrome_video_packets=82`
- `chrome_video_frames=81`
- `sender_rtp_packets=91`
- `sender_srtp_packets=91`
- `sender_srtcp_packets=3`
- `sender_rtcp_sender_reports=3`
- `sender_udp_packets=94`

Chrome decoded frame 计数会随本机调度轻微波动，验证以 inbound RTP、decoded frames 非零和 sender RTP/SRTP 计数为准。

纯 Uya VP8 MP4 manual preview E2E smoke 验证统计：

- `source_kind=mp4`
- `preview_size=32x18`
- `preview_duration_us=999990`
- `chrome_video_size=32x18`
- `chrome_video_packets=31`
- `chrome_video_frames=31`
- `sender_rtp_packets=31`
- `sender_srtp_packets=31`
- `sender_srtcp_packets=1`
- `sender_udp_packets=32`

## 已知限制

- 纯 Uya VP8 codec bridge 只在显式 bridge gate 和 video-only Chrome gate 中接入 `../vp8` sibling；默认 runtime 不依赖该 sibling，完整音视频 Chrome 直推证明仍来自显式 FFmpeg reference codec 路径。
- 纯 Uya Opus codec bridge 的完整 sibling encoder/decoder 与 RTP Opus 能力仍未作为生产路径发布。
- `../vp8` UPM path dependency 仍待 sibling 仓库提供 package-mode manifest，并通过当前 Uya package-mode cast checks；本版本测试使用 legacy staging 验证源码级接入。
- FFmpeg 只允许出现在显式测试目标和预览路径中，不能进入默认 runtime 或纯 Uya codec bridge；纯 Uya VP8 MP4 预览中 FFmpeg 只承担 MP4 source decode / raw I420 转换。
- 纯 Uya VP8 MP4 预览默认是降采样短预览，不承诺当前 scalar encoder 可实时或快速处理完整 1080p/长视频。
- SDP fuzz 真实 parser smoke 仍受 Uya C99 nested byte array field codegen 问题阻塞。
- GStreamer webrtcbin interop 当前 blocked：本机 GI runtime 下 `webrtcbin` 无法形成真实 offer/answer。
- macOS kqueue、Windows IOCP、Android、iOS 和完整平台 CI matrix 仍需要对应 runner、FFI 或 SDK 才能验收。

## 适合验证的场景

- 验证纯 Uya WebRTC transport 能完成浏览器互通和 encoded-frame RTP/SRTP 传输。
- 验证 Uya direct sender 到 Chrome recvonly peer 的真实音视频推送路径。
- 验证显式纯 Uya VP8 codec bridge 与 `../vp8` sibling 源码级接入，以及 video-only Chrome 解码路径。
- 验证 DataChannel、RTP/RTCP、SRTP/SRTCP、Stats、benchmark 和 codec boundary 的当前集成状态。

## 不适合作为承诺的场景

- 不承诺完整跨平台后端可用性。
- 不承诺默认 runtime 内置 FFmpeg/libopus/libvpx。
- 不承诺纯 Uya Opus encoder/decoder 或纯 Uya VP8 video-only Chrome gate 已接入生产路径。
- 不把浏览器内部 loopback 当成 Uya 到浏览器推流能力证明；本版本的音视频推流证明来自 `make test-ffmpeg-chrome-call`，纯 Uya VP8 视频证明来自 `make test-uya-vp8-chrome-call`。
