# 纯 Uya WebRTC

本项目目标是用纯 Uya 语言重构一个可与浏览器和主流 WebRTC 端互通的 Native WebRTC 栈。当前发布版本为 `v0.2.0` 里程碑，已经覆盖纯 Uya WebRTC transport、DataChannel、RTP/SRTP、RTCP feedback、Chrome 音视频直推验证、纯 Uya VP8 video-only Chrome gate、显式 FFmpeg codec 测试边界，以及 RK1106 H264/G711 板端直推示例；详细设计见 [docs/design.md](docs/design.md)，任务拆解见 [docs/todo.md](docs/todo.md)。

## 项目目标

- 逐步在 Uya 中实现 SDP、ICE、STUN/TURN、DTLS、SRTP、RTP/RTCP、SCTP DataChannel、拥塞控制、抖动缓冲、统计与测试工具。
- 第一阶段优先完成 WebRTC 传输和互通能力，与 Chrome / Firefox 建立 PeerConnection，并支持 encoded-frame 传输。
- codec 能力与兄弟仓库 `../opus`、`../vp8` 协同推进；本仓库优先解决 WebRTC transport、browser interop 和 RTP/RTCP 语义。

## 纯 Uya 边界

“纯 Uya”在本项目中的含义是：

- 核心协议、parser、state machine 和传输逻辑默认全部由 Uya 实现。
- 默认运行路径不链接 `libwebrtc`、`libnice`、`BoringSSL`、`usrsctp`、`libsrtp`、`libvpx`、`libopus` 等外部协议或编解码库。
- 允许存在极薄的 OS FFI 边界，只覆盖 socket、epoll/kqueue/IOCP、clock、线程原语、`mmap`、`sendmmsg`/`recvmmsg` 等系统能力。
- 默认构建路径不依赖 C++ runtime，也不复用外部协议库的对象生命周期。
- 编解码与传输边界通过 encoded-frame API 隔离；显式启用 codec bridge 时只能依赖纯 Uya 的兄弟仓库实现，而不是引入 `libopus`、`libvpx` 或 FFmpeg runtime。

## 构建方式

当前仓库以 `Makefile` 作为统一入口，默认 runtime 仍保持纯 Uya transport 边界；FFmpeg 只在显式 codec / Chrome interop 测试目标中作为 reference codec 使用，不进入默认运行路径。

项目已经约定当前统一的构建入口，以以下命令作为标准接口：

```sh
make build
make test
make bench
```

对应目标如下：

- `make build`：生成里程碑 CLI wrapper `build/webrtc-uya`，当前支持 `--help`、`version` 与 `dump-stats`。
- `make test`：运行 transport、parser、crypto、DTLS/SRTP、RTP/RTCP、SCTP、PeerConnection、统计和 benchmark 入口检查。
- `make bench`：输出 benchmark 基线到 `build/benchmarks/baseline.jsonl`。
- `make test-codec-bridge`：显式运行 codec bridge gate；当前会 legacy-staging `../vp8` 纯 Uya sibling，验证 I420 -> VP8 `EncodedFrame` -> I420 以及 RTP VP8 descriptor/reassembly 语义。
- `make test-ffmpeg-chrome-call`：显式启用 FFmpeg reference codec，Uya direct sender 在发送循环中将 raw PCM/I420 实时编码成 Opus/VP8 后推给 Chrome recvonly peer。
- `make test-uya-vp8-chrome-call`：显式 legacy-staging `../vp8` 纯 Uya sibling，Uya sender 在发送循环中将 raw I420 实时编码为 VP8 `EncodedFrame`，再通过 RTP/SRTP/UDP 推给 Chrome recvonly peer；当前验证 video-only，Opus 音频 bridge 仍未接入。
- `make preview-uya-vp8-chrome-call MP4=/absolute/path/to/source.mp4`：显式将 MP4 转成 raw I420 源，再由 Uya VP8 live sender 调用 `../vp8` 纯 Uya bridge 实时编码并推给浏览器预览；默认预览会缩到 160px 宽、截取 2s，并按宽度自动选择 FPS（640px 走 10fps，320px 走 15fps，小尺寸走 30fps），可用 `UYA_VP8_PREVIEW_MAX_WIDTH=320 UYA_VP8_PREVIEW_MAX_DURATION=3 UYA_VP8_PREVIEW_FPS=15` 调整；preview server 会先用 `UYA_VP8_PREVIEW_CFLAGS`（默认 `-std=c99 -O3 -g -fno-builtin`）构建 sender，点击 Start 时直接运行该 executable；默认保留 VP8 SIMD/asm dispatch，必要时可用 `UYA_VP8_FORCE_SCALAR=1` 复现 scalar 路径；该路径 video-only，不启用 Opus。

发布记录见 [CHANGELOG.md](CHANGELOG.md)。
