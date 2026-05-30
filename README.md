# 纯 Uya WebRTC

本项目目标是用纯 Uya 语言重构一个可与浏览器和主流 WebRTC 端互通的 Native WebRTC 栈。当前仓库仍处于设计和项目基座阶段，详细设计见 [docs/design.md](docs/design.md)，任务拆解见 [docs/todo.md](docs/todo.md)。

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

当前仓库已经落地 Phase 0 的 `Makefile` 构建入口，但 `src/` 目录和 Uya 源码实现仍未开始，因此现阶段提供的是可运行的占位构建与验证流程。

项目已经约定当前统一的构建入口，以以下命令作为标准接口：

```sh
make build
make test
make bench
```

对应目标如下：

- `make build`：生成占位可执行文件 `build/webrtc-uya`，当前支持 `--help` 与 `version`。
- `make test`：运行当前基座级 smoke test，验证占位 CLI 可执行。
- `make bench`：输出占位 benchmark 基线到 `build/benchmarks/baseline.jsonl`。

随着 `src/main.uya` 等源码落地，上述入口会切换到真实的 Uya build/test/bench 流程。
