# 纯 Uya WebRTC

本项目目标是用纯 Uya 语言重构一个可与浏览器和主流 WebRTC 端互通的 Native WebRTC 栈。当前发布版本为 `v0.1.0` 里程碑，已经覆盖纯 Uya WebRTC transport、DataChannel、RTP/SRTP、RTCP feedback、Chrome 音视频直推验证和显式 FFmpeg codec 测试边界；详细设计见 [docs/design.md](docs/design.md)，任务拆解见 [docs/todo.md](docs/todo.md)。

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
- 编解码与传输边界通过 encoded-frame API 隔离；后续如启用 codec bridge，也只能依赖纯 Uya 的兄弟仓库实现，而不是引入 `libopus`、`libvpx` 或 FFmpeg runtime。

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
- `make test-ffmpeg-chrome-call`：显式启用 FFmpeg reference codec，验证 Uya direct sender 向 Chrome recvonly peer 推送音视频。

发布记录见 [CHANGELOG.md](CHANGELOG.md)。
