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
- Uya direct sender：支持通过显式 FFmpeg reference codec 生成 Opus/VP8 encoded frames，再由 Uya 侧完成 RTP、SRTP、SRTCP、UDP 发送给 Chrome recvonly peer。
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
```

手工预览默认测试源：

```sh
make preview-ffmpeg-chrome-call
```

手工预览指定 MP4：

```sh
make preview-ffmpeg-chrome-call MP4=/absolute/path/to/source.mp4
```

## 发布验证

2026-06-04 本地发布验证已通过：

- `make test`
- `make bench`
- `make test-codec-bridge`
- `make test-ffmpeg-chrome-call`

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

## 已知限制

- 纯 Uya Opus/VP8 codec bridge 的完整 sibling 对齐仍未作为默认 runtime 发布；当前发布只承诺 WebRTC 侧 bridge 边界、feature gate 和显式 reference codec 验证。
- FFmpeg 只允许出现在显式测试目标和预览路径中，不能进入默认 runtime 或纯 Uya codec bridge。
- SDP fuzz 真实 parser smoke 仍受 Uya C99 nested byte array field codegen 问题阻塞。
- GStreamer webrtcbin interop 当前 blocked：本机 GI runtime 下 `webrtcbin` 无法形成真实 offer/answer。
- macOS kqueue、Windows IOCP、Android、iOS 和完整平台 CI matrix 仍需要对应 runner、FFI 或 SDK 才能验收。

## 适合验证的场景

- 验证纯 Uya WebRTC transport 能完成浏览器互通和 encoded-frame RTP/SRTP 传输。
- 验证 Uya direct sender 到 Chrome recvonly peer 的真实音视频推送路径。
- 验证 DataChannel、RTP/RTCP、SRTP/SRTCP、Stats、benchmark 和 codec boundary 的当前集成状态。

## 不适合作为承诺的场景

- 不承诺完整跨平台后端可用性。
- 不承诺默认 runtime 内置 FFmpeg/libopus/libvpx。
- 不承诺纯 Uya Opus/VP8 encoder/decoder 已接入生产路径。
- 不把浏览器内部 loopback 当成 Uya 到浏览器推流能力证明；本版本的推流证明来自 `make test-ffmpeg-chrome-call` 的 Uya direct sender 路径。
