# 纯 Uya WebRTC 重构详细设计

**版本**：v0.2.0
**状态**：v0.2.0 里程碑发布
**日期**：2026-06-11
**目标平台**：Linux x86_64 first，后续扩展 macOS / Windows / Android / iOS  

## 1. 项目定位

本项目目标是用纯 Uya 语言重构一个可与浏览器和主流 WebRTC 端互通的 Native WebRTC 栈。它不是对 Google libwebrtc 的 C++ 包装，也不是只做一层 API 兼容层，而是把信令模型、SDP、ICE、STUN/TURN、DTLS、SRTP、RTP/RTCP、SCTP DataChannel、拥塞控制、抖动缓冲、统计和测试工具逐步落到 Uya 代码中。

“纯 Uya”在本项目中的含义：

- 核心协议和状态机全部由 Uya 实现，不链接 libwebrtc、libnice、BoringSSL、usrsctp、libsrtp、libvpx、libopus 作为默认运行路径。
- 允许存在极薄 OS FFI 边界：socket、epoll/kqueue/IOCP、clock、pthread 或平台等价线程原语、mmap、sendmmsg/recvmmsg 等系统能力。
- 默认构建路径不依赖 C++ runtime，不复用外部协议库的对象生命周期。
- 性能热点优先使用 Uya `@vector`、固定容量结构、arena、atomic 和编译期边界证明。
- 第一期优先实现 WebRTC 传输和互通能力；纯 Uya Opus / VP8 编解码能力由兄弟仓库 `../opus`、`../vp8` 承担，WebRTC 侧通过 encoded-frame 和可选适配层集成。

第一阶段交付目标：

- 可以与 Chrome / Firefox 建立 P2P 或 server-side PeerConnection。
- 支持 ICE + DTLS + SRTP 的音视频 RTP 传输。
- 支持 SCTP DataChannel。
- 支持基础 SDP offer/answer 和 trickle ICE。
- 支持 Opus / VP8 / H264 / AV1 的 RTP packetize / depacketize 和 encoded-frame API。
- 与 `../opus`、`../vp8` 文档中的 codec API、RTP payload 语义和测试边界保持同步。
- 支持可观测 stats、trace、benchmark 和网络模拟测试。

非目标或延后目标：

- 第一阶段不实现浏览器 DOM / JavaScript WebRTC API。
- 第一阶段不实现摄像头、麦克风、屏幕采集和系统音视频渲染。
- 第一阶段不要求完整实现 Opus、VP8、H264、AV1 编码器/解码器；先传输已编码帧。
- WebRTC 仓库不重复实现 Opus / VP8 codec core；编解码器主体分别放在 `../opus`、`../vp8`。
- 第一阶段不做 MCU/SFU 的完整业务产品，只提供可组合的底层栈和示例。

## 2. 标准基线

设计以以下标准和事实互通需求为边界：

- W3C WebRTC 1.0：PeerConnection、transceiver、sender/receiver、DataChannel 的行为模型。
- W3C WebRTC Statistics：stats 字段语义和采样口径。
- W3C WebRTC Encoded Transform：后续支持端到端加密和 encoded-frame 处理时参考其 frame 边界。
- RFC 8445：ICE。
- RFC 8489：STUN。
- RFC 8656：TURN。
- RFC 8838：Trickle ICE。
- RFC 8829：JSEP offer/answer 行为。
- RFC 3550 / 3551：RTP / RTCP 基础。
- RFC 6716 / RFC 8251：Opus codec 与更新。
- RFC 7587：Opus RTP payload。
- RFC 6386：VP8 bitstream。
- RFC 7741：VP8 RTP payload。
- RFC 5761：RTP / RTCP mux。
- RFC 7983：STUN / DTLS / TURN ChannelData / RTP demux。
- RFC 5764：DTLS-SRTP。
- RFC 3711 / RFC 7714：SRTP 传统 profile 与 AEAD profile。
- RFC 4585 / RFC 4588 / RFC 8285：RTP feedback、RTX、RTP header extension。
- RFC 8831 / RFC 8832：WebRTC DataChannel 和 DCEP。
- RFC 8261：SCTP over DTLS。

浏览器互通的最小闭环：

```text
SDP offer/answer
  -> ICE candidate gathering/checklist/nomination
  -> DTLS handshake and certificate fingerprint verification
  -> DTLS exporter derives SRTP keys
  -> SRTP/SRTCP protects RTP/RTCP
  -> RTP media transport and RTCP feedback
  -> SCTP over DTLS for DataChannel
```

## 3. 成功标准

### 3.1 正确性

- 与 Chrome / Firefox 完成 offer/answer、trickle ICE、DTLS-SRTP、RTP/RTCP、DataChannel 互通。
- 每个协议模块都有 parser/builder roundtrip、错误输入、截断输入、边界长度测试。
- 所有公网输入解析路径返回显式 `!T` 错误，不 panic、不越界、不未定义行为。
- 所有加密、重放窗口、计数器 rollover、序列号 wrap 都有向量测试。

### 3.2 性能

- 建连后 RTP 热路径零堆分配。
- 单 UDP socket 的收发路径支持批量 `recvmmsg` / `sendmmsg`。
- 热路径只传 packet descriptor，不跨线程复制 payload。
- 每个引入热路径的阶段必须同时引入 allocation counter、microbench 或 queue-depth 断言，性能退化不能等到后期统一修。
- 默认每连接内存可预测，避免按 peer、track、SSRC 无上限增长。
- 关键统计包括 P50/P95/P99 延迟、packet loss、jitter、RTT、码率、CPU、内存和队列积压。

### 3.3 可维护性

- 协议核心采用 Sans-I/O 风格：parser、state machine、crypto transform 与 socket I/O 解耦。
- 每个模块可独立 fuzz 和单测。
- 公共 API 不暴露内部 buffer 生命周期。
- 示例和 benchmark 可在无摄像头、无浏览器 UI 的 CI 环境运行。

## 4. 总体架构

建议目录：

```text
src/
  main.uya
  webrtc/
    api.uya             # PeerConnection / DataChannel / track public API
    config.uya          # RtcConfiguration / IceServer / codec capability
    error.uya           # 统一错误定义
    time.uya            # monotonic clock / timer helpers
    arena.uya           # PacketArena / fixed buffer / slab allocator
    ring.uya            # bounded MPSC/SPMC queues
    net/
      udp.uya           # socket, recvmmsg/sendmmsg, nonblocking I/O
      worker.uya        # epoll event loop, timers, pacer tick
      demux.uya         # STUN / DTLS / TURN ChannelData / RTP / RTCP classifier
    sdp/
      model.uya         # SDP AST / media section / attributes
      parse.uya
      write.uya
      jsep.uya          # offer/answer validation and negotiation
    stun/
      types.uya
      parse.uya
      write.uya
      auth.uya
    turn/
      client.uya
      allocation.uya
      channel.uya
    ice/
      candidate.uya
      checklist.uya
      transport.uya
      agent.uya
    crypto/
      hash.uya
      hmac.uya
      aes.uya
      gcm.uya
      ecdsa.uya
      random.uya
    dtls/
      record.uya
      handshake.uya
      cipher.uya
      exporter.uya
      retransmit.uya
    srtp/
      context.uya
      protect.uya
      replay.uya
    rtp/
      packet.uya
      extension.uya
      packetizer.uya
      depacketizer.uya
      sender.uya
      receiver.uya
      jitter.uya
    rtcp/
      packet.uya
      feedback.uya
      scheduler.uya
    sctp/
      packet.uya
      association.uya
      retransmit.uya
      stream.uya
    data/
      channel.uya
      dcep.uya
    media/
      codec.uya
      encoded_frame.uya
      opus_rtp.uya
      vp8_rtp.uya
      h264_rtp.uya
      av1_rtp.uya
      codec_bridge.uya   # optional adapters to ../opus and ../vp8
    congestion/
      pacer.uya
      twcc.uya
      estimator.uya
      bitrate_allocator.uya
    peer/
      connection.uya
      transport.uya
      transceiver.uya
      track.uya
    stats/
      types.uya
      collector.uya
      trace.uya
benchmarks/
examples/
tests/
```

核心依赖方向：

```text
api/peer
  -> sdp, ice, dtls, srtp, rtp, rtcp, sctp, data, media, congestion, stats
ice
  -> stun, turn, net, time
dtls
  -> crypto, time
srtp
  -> crypto, rtp, rtcp
rtp/rtcp
  -> media, congestion, time
sctp/data
  -> dtls, time
net
  -> arena, ring, time
media.codec_bridge
  -> optional sibling package APIs only, not transport internals
```

不允许反向依赖：

- `stun` 不依赖 `ice`。
- `rtp` 不依赖 `peer`。
- `dtls` 不依赖 `ice`。
- `media` payload 格式不依赖 `PeerConnection`。
- `../opus`、`../vp8` 不能为了 WebRTC 适配反向依赖本仓库 transport、peer 或 worker 模块。
- `stats` 可以采样各模块只读快照，但不能驱动业务状态机。

## 5. Uya 编码约束

### 5.1 错误模型

所有公网输入解析和网络状态机函数使用 `!T`：

```uya
error PacketTooShort;
error InvalidPacket;
error UnsupportedProfile;
error ReplayRejected;
error HandshakeFailed;

fn parse_rtp_packet(buf: &[byte]) !RtpPacket {
    if @len(buf) < 12 {
        return error.PacketTooShort;
    }
    ...
}
```

热路径不使用字符串错误；错误码用于 stats 计数和 trace 映射。

### 5.2 内存生命周期

- 网络线程拥有 `PacketArena`。
- packet payload 以 slab + offset + len 表示。
- 协议 parser 返回借用切片，不能逃逸出当前 packet 生命周期。
- 如果 packet 要进入重传缓存、抖动缓冲或跨线程队列，必须优先转移 slab token；确需保留原 owner 时才允许显式 clone 到对应 owner arena。
- 每个允许 clone 的路径必须有预算和统计：clone bytes、clone count、drop count、owner arena high-watermark；超过预算时按模块策略丢弃老包、不完整帧或拒绝大消息。
- RTP 热路径默认只传 `PacketRef`，不得把 payload copy 作为跨线程通信的常规路径；重传缓存、jitter buffer、SCTP reassembly 都要有 cap 下行为测试。
- PeerConnection API 不暴露内部可变切片，用户只看到 `EncodedFrame`、`DataMessage` 等稳定结构。

### 5.3 并发模型

- 使用 bounded ring，避免无界队列导致延迟雪崩。
- 使用 `atomic` 实现队列 head/tail、stats counter、runtime state flag。
- 控制面可加锁，媒体热路径避免全局锁。
- 每个 `TransportWorker` 拥有自己 epoll fd、timer wheel、packet arena 和 pacer。
- Peer 按 ICE transport id 分片到 worker；同一 DTLS/SRTP/SCTP transport 的包由同一 worker 串行处理，减少锁。

### 5.4 SIMD 与常量时间

- RTP/RTCP/STUN parser 不追求 SIMD，优先边界安全和低分支错误路径。
- SRTP auth、AES、GCM、CRC、checksum、音频/视频 payload 扫描可使用 `@vector`。
- crypto 比较必须常量时间；禁止早停 `memcmp` 用于 MAC/tag/cookie/fingerprint 校验。

## 6. 运行时与 I/O 设计

### 6.1 Worker 模型

```text
ApiThread
  -> command queue
TransportWorker[N]
  -> epoll wait
  -> recvmmsg batch
  -> demux
  -> protocol state machine
  -> pacer / sendmmsg
  -> event queue
ApiThread
  <- events: ice state, track frame, data message, stats update
```

第一版可以只实现单 worker，接口保持可扩展到多 worker。

### 6.2 UDP 收包流程

```text
recvmmsg
  -> PacketArena alloc receive slots
  -> classify first byte range
  -> STUN: ice_agent_on_stun
  -> DTLS: dtls_transport_on_record
  -> TURN ChannelData: turn_channel_on_data
  -> RTP/RTCP: srtp_unprotect -> rtp/rtcp receiver
  -> unknown: drop and stats
```

WebRTC UDP mux 按 RFC 7983 做首字节范围分类：

- STUN：`0..3`。
- ZRTP / reserved：`16..19`，首版不支持，计数后丢弃。
- DTLS：`20..63`。
- TURN ChannelData：`64..79`。
- RTP/RTCP：`128..191`。
- 其他范围计为 unknown 并丢弃。

分类器只做最小判定，具体合法性由对应 parser 校验。

### 6.3 发包流程

```text
module produces OutPacket
  -> pacer queue
  -> MTU check
  -> batch sendmmsg
  -> short send / EAGAIN handled by worker
```

所有发包必须经过 pacing 层，例外只有 ICE binding response、DTLS handshake retransmit、RTCP 必要反馈等小包控制流；例外也要有速率保护。

### 6.4 Timer

使用一个 worker 本地 timer wheel 或 min-heap：

- ICE connectivity check pacing。
- ICE transaction retransmit。
- TURN allocation refresh。
- DTLS handshake retransmit。
- SCTP retransmit。
- RTCP periodic sender/receiver report。
- NACK retry / keyframe request backoff。
- Consent freshness。
- Stats sampling。

定时器输入使用 monotonic time，不使用 wall clock。

## 7. 公共 API 设计

公共 API 采用 Native WebRTC 风格，不复制 DOM：

```uya
struct RtcConfiguration {
    ice_servers: &[IceServer],
    bundle_policy: BundlePolicy,
    rtcp_mux_policy: RtcpMuxPolicy,
    worker_count: i32,
}

struct PeerConnection {
    id: u64,
    runtime: &RtcRuntime,
    state: PeerState,
}

interface PeerObserver {
    fn on_ice_candidate(self: &Self, pc: &PeerConnection, cand: &IceCandidate) void;
    fn on_connection_state(self: &Self, pc: &PeerConnection, state: ConnectionState) void;
    fn on_track(self: &Self, pc: &PeerConnection, track: &RemoteTrack) void;
    fn on_data_channel(self: &Self, pc: &PeerConnection, dc: &DataChannel) void;
}
```

关键 API：

- `rtc_runtime_init(config) !RtcRuntime`
- `peer_connection_new(runtime, config, observer) !PeerConnection`
- `pc_add_transceiver(pc, kind, init) !Transceiver`
- `pc_create_offer(pc, opts, out_sdp) !void`
- `pc_create_answer(pc, opts, out_sdp) !void`
- `pc_set_local_description(pc, sdp) !void`
- `pc_set_remote_description(pc, sdp) !void`
- `pc_add_ice_candidate(pc, cand) !void`
- `pc_create_data_channel(pc, label, init) !DataChannel`
- `track_write_encoded_frame(track, frame) !void`
- `receiver_read_encoded_frame(receiver, out) !bool`
- `data_channel_send(dc, msg) !void`
- `peer_connection_get_stats(pc, out) !void`

API 线程和 worker 线程通过 command/event queue 通信。所有跨线程对象使用 id + generation，避免悬垂引用。

## 8. SDP 与 JSEP

### 8.1 数据模型

SDP parser 先生成紧凑 AST：

```text
SessionDescription
  version
  origin
  session_name
  timing
  groups: BUNDLE
  media_sections[]
    kind: audio/video/application
    mid
    direction
    ice_ufrag / ice_pwd
    fingerprint
    setup
    rtcp_mux
    candidates[]
    codecs[]
    header_extensions[]
    ssrcs[]
    ssrc_groups[]
```

parser 保存 span，不在解析期复制大量字符串；进入 negotiation 阶段再归一化到固定结构。

### 8.2 首版支持

- Unified Plan。
- BUNDLE。
- rtcp-mux。
- trickle ICE candidate。
- `a=mid`。
- `a=setup:actpass/active/passive`。
- `a=fingerprint`。
- `a=ice-ufrag` / `a=ice-pwd`。
- audio Opus payload 参数。
- video VP8/H264/AV1 payload 参数。
- DataChannel `m=application ... UDP/DTLS/SCTP webrtc-datachannel`。

### 8.3 校验策略

- SDP parser 只判断语法和长度。
- JSEP validator 判断状态机合法性、bundle 兼容性、payload type 冲突、fingerprint 缺失、rtcp-mux 缺失等。
- 不支持的能力必须返回明确错误，不能静默降级。

## 9. ICE / STUN / TURN

### 9.1 ICE Agent

ICE agent 负责：

- host candidate gathering。
- server reflexive candidate gathering。
- relay candidate gathering。
- remote candidate 注入。
- candidate pair checklist。
- controlling / controlled role。
- regular nomination 和 aggressive nomination 预留。
- role conflict 处理。
- consent freshness。
- selected pair 切换。
- failed / disconnected / connected / completed 状态机。

### 9.2 STUN

STUN 模块实现：

- Binding request / response / error response。
- XOR-MAPPED-ADDRESS。
- USERNAME。
- MESSAGE-INTEGRITY / MESSAGE-INTEGRITY-SHA256。
- FINGERPRINT。
- PRIORITY。
- USE-CANDIDATE。
- ICE-CONTROLLING / ICE-CONTROLLED。
- ERROR-CODE。

parser 使用 TLV 迭代，不复制 attribute value。builder 使用固定 buffer，先写 header，再写 attributes，最后回填 length 和 integrity/fingerprint。

### 9.3 TURN

TURN client 实现：

- Allocate。
- Refresh。
- CreatePermission。
- ChannelBind。
- Send indication / Data indication。
- long-term credential。
- relay candidate 生命周期。

TURN server 不作为第一阶段目标。

### 9.4 性能要点

- ICE transaction table 使用固定容量或 arena + free-list。
- STUN 重传定时器按 RFC RTO/backoff 实现，worker timer 驱动。
- candidate pair 排序在 control path，可使用简单稳定排序；热路径只查 selected pair。
- selected pair 确定后，RTP/RTCP 发包无需再次查 checklist。

## 10. DTLS 与加密

### 10.1 DTLS 范围

首版实现 DTLS 1.2 的 WebRTC 互通子集：

- record layer。
- handshake fragmentation / reassembly。
- HelloVerifyRequest 或 cookie 机制按互通需要实现。
- ClientHello / ServerHello / Certificate / ServerKeyExchange / CertificateRequest 可选 / ServerHelloDone / ClientKeyExchange / CertificateVerify / Finished。
- ECDHE_ECDSA_AES_128_GCM_SHA256 优先。
- SRTP protection profile 协商。
- DTLS exporter 导出 SRTP master key / salt。
- handshake retransmission。
- alert。

后续补充 DTLS 1.3。

### 10.2 证书与 fingerprint

- 默认生成自签名 ECDSA P-256 证书。
- SDP fingerprint 使用 SHA-256。
- `set_remote_description` 后保存远端 fingerprint。
- DTLS handshake 收到证书后做 constant-time fingerprint 比对。
- fingerprint 不匹配立即关闭 transport。

### 10.3 Crypto 原语

纯 Uya crypto 模块需要：

- SHA-1、SHA-256。
- HMAC-SHA1、HMAC-SHA256。
- AES-CTR、AES-GCM。
- GHASH。
- ECDSA P-256。
- ECDHE P-256。
- HKDF / PRF。
- CSPRNG 平台熵源封装。

crypto 是最高风险模块。必须配套官方 test vectors、Wycheproof 风格负例、fuzz 和 constant-time 审计。

## 11. SRTP / SRTCP

首版 SRTP 支持：

- `SRTP_AES128_CM_HMAC_SHA1_80`。
- `SRTP_AES128_CM_HMAC_SHA1_32`。
- SRTCP auth。
- replay protection。
- RTP sequence rollover counter。
- SSRC context。
- key derivation。

第二阶段支持：

- `SRTP_AEAD_AES_128_GCM`。
- `SRTP_AEAD_AES_256_GCM`。
- encrypted header extension。
- E2EE frame transform hook。

SRTP 处理流程：

```text
send RTP
  -> assign seq/timestamp/ssrc
  -> maybe header extension
  -> SRTP protect
  -> pacer

receive UDP
  -> demux RTP/RTCP
  -> SRTP/SRTCP unprotect
  -> replay check
  -> RTP/RTCP parser
```

Replay window 使用固定 64-bit 或 128-bit 滑动窗口，序列号 rollover 逻辑必须有专门测试。

## 12. RTP / RTCP

### 12.1 RTP

RTP 模块负责：

- RTP header parse/write。
- CSRC。
- header extension one-byte/two-byte forms。
- MID、RID、Repaired RID。
- abs-send-time。
- transport-wide sequence number。
- audio level。
- video orientation 预留。
- RTX payload。
- packetizer / depacketizer。

### 12.2 RTCP

RTCP 模块负责：

- Sender Report。
- Receiver Report。
- SDES CNAME。
- BYE。
- NACK。
- PLI。
- FIR。
- REMB 兼容接收和可选发送。
- Transport-CC feedback。
- compound RTCP parse/write。

### 12.3 发送侧

发送侧链路：

```text
EncodedFrame
  -> payload packetizer
  -> RTP sequence/timestamp
  -> retransmission cache
  -> congestion controller
  -> pacer
  -> SRTP
  -> UDP
```

关键策略：

- retransmission cache 按 SSRC + seq 保存 packet descriptor 或 compact clone。
- audio 默认小延迟优先，video 受 pacer 控制。
- 大帧按 MTU 分片，避免 IP fragmentation。
- 发送 timestamp 采用 codec clock rate。

### 12.4 接收侧

接收侧链路：

```text
SRTP packet
  -> RTP parse
  -> SSRC / MID route
  -> jitter buffer
  -> NACK missing packets
  -> depacketizer
  -> EncodedFrame output
  -> stats
```

JitterBuffer 首版目标：

- 支持乱序、重复包、丢包检测。
- 按 frame boundary 输出 encoded frame。
- video keyframe 识别。
- NACK 触发和 PLI backoff。
- 上限内存，超限丢弃老帧或不完整帧。

## 13. Media 与 Codec 边界

第一阶段 media 模块只做 RTP payload 格式和 encoded-frame 边界，不做全量编解码：

- Opus RTP packet parse/write。
- VP8 payload descriptor parse/write。
- H264 STAP-A / FU-A packetize/depacketize。
- AV1 RTP payload descriptor parse/write。
- codec capability negotiation。
- encoded frame metadata：kind、codec、timestamp、duration、keyframe、spatial/temporal id。

兄弟 codec 仓库已经拆分：

- `../opus` 对应 `https://github.com/uya-lang/opus`，负责 RFC 6716 / RFC 8251 的 Opus packet、entropy、SILK、CELT、Hybrid、decoder、encoder、Ogg Opus 和 RTP Opus payload 语义。
- `../vp8` 对应 `https://github.com/uya-lang/vp8`，负责 RFC 6386 的 VP8 bitstream、IVF/WebM、decoder、encoder、SIMD kernel、VP8 RTP payload descriptor 和 frame reassembly 语义。

WebRTC 与 codec 仓库的责任边界：

- WebRTC 拥有 SDP/JSEP codec negotiation、RTP/RTCP、SRTP、jitter buffer、NACK/PLI/RTX、pacer、stats 和 browser interop。
- Opus 仓库拥有 Opus packet 合法性、TOC/frame split、ptime/maxptime/stereo/fec fmtp 映射、decoder/encoder、Ogg Opus。
- VP8 仓库拥有 VP8 bitstream header、keyframe 判断、payload descriptor 字段、partition/frame reassembly 语义、decoder/encoder、IVF/WebM。
- WebRTC `media/opus_rtp.uya` 和 `media/vp8_rtp.uya` 必须与兄弟仓库的 RTP payload 行为保持 roundtrip 等价；实现上可以先内置最小 payload parser，再在 `media/codec_bridge.uya` 中提供可选适配。
- 默认 WebRTC transport 构建不能依赖 codec decoder/encoder；启用 codec bridge 时也只能依赖纯 Uya sibling package，不能引入 libopus、libvpx 或 FFmpeg runtime。
- Encoded-frame API 是稳定边界：codec 仓库可以把 PCM/YUV 编码成 encoded frame，WebRTC 负责 packetize/send；WebRTC 收到 encoded frame 后可以交给 codec bridge decode，也可以直接交给应用、录制或转推。

`EncodedFrame` 建议字段：

```text
EncodedFrame {
  codec: CodecId,
  kind: MediaKind,
  timestamp: u64,
  duration_us: u32,
  payload: PacketRef or borrowed bytes,
  is_keyframe: bool,
  sequence_id: u64,
  spatial_id: i32,
  temporal_id: i32,
  marker: bool,
}
```

Opus 同步点：

- RTP clock rate 固定按 48 kHz。
- payload 可以包含一个或多个 Opus frame，WebRTC 不解码音频内容。
- SDP fmtp 覆盖 `minptime`、`maxptime`、`useinbandfec`、`stereo`、`sprop-stereo`、`usedtx` 等常见参数。
- DTX/空 payload、FEC hint、packet duration 校验与 `../opus/docs/todo.md` 的 RTP Opus 阶段保持一致。

VP8 同步点：

- RTP payload descriptor 支持 X/N/S/PartID、PictureID、TL0PICIDX、TID、KEYIDX。
- keyframe 检测以 payload descriptor + VP8 uncompressed header 为准；完整 bitstream 解析由 `../vp8` 负责。
- jitter buffer 输出完整 VP8 frame，丢包时触发 NACK，长期不可恢复时触发 PLI。
- frame reassembly、RTP malformed 错误和 API examples 与 `../vp8/docs/todo.md` 的 WebM/RTP 与库 API 阶段保持一致。

H264 / AV1 策略不变：

- H264 涉及专利和 profiles，优先只做 RTP payload 与 Annex-B/AVCC 转换。
- AV1 编解码复杂度高，优先 RTP payload 和 OBU 处理。

这一区分很重要：WebRTC 传输栈可以先服务 SFU、录制、转推、AI 实时处理等场景，这些场景经常只需要处理 encoded frames。

## 14. SCTP 与 DataChannel

DataChannel 栈：

```text
DTLS application data
  -> SCTP packet
  -> association
  -> stream
  -> DCEP open/ack
  -> DataChannel message
```

首版 SCTP 支持：

- INIT / INIT_ACK / COOKIE_ECHO / COOKIE_ACK。
- DATA chunk。
- SACK。
- HEARTBEAT。
- ABORT / SHUTDOWN。
- TSN map。
- retransmission timer。
- congestion window 简化实现。
- stream id。
- ordered / unordered。
- reliable / max_retransmits / max_packet_lifetime。
- fragmentation / reassembly。

DCEP 支持：

- OPEN。
- ACK。
- label / protocol。
- negotiated channel。

性能策略：

- 小消息 inline 存储，大消息使用 arena buffer。
- fragment reassembly 有 per-channel memory cap。
- SCTP ack 和 retransmit 走 worker timer。

## 15. 拥塞控制、Pacer 与带宽分配

首版采用 GCC/TWCC 风格设计：

- RTP header extension 写入 transport-wide sequence number。
- 接收端生成 Transport-CC RTCP feedback。
- 发送端根据 send time / arrival time 估算 delay trend。
- loss-based fallback。
- probing。
- pacing rate 和 media target bitrate 解耦。
- audio 最小保护码率，video 按 active layers 分配。

模块边界：

```text
rtp.sender
  -> congestion.on_packet_sent
rtcp.feedback
  -> congestion.on_transport_feedback
congestion.estimator
  -> bitrate_allocator
bitrate_allocator
  -> sender target bitrate event
pacer
  -> paced packet release
```

首版可以先实现保守估算器：

- startup 固定初始码率。
- RTT / loss / queue delay 超阈值降码率。
- 稳定期 additive increase。
- periodic probe。

后续再对齐 libwebrtc GCC 的细节。

## 16. Stats 与可观测性

Stats 结构按 WebRTC Stats API 口径设计，但内部使用紧凑字段：

- `RtcPeerConnectionStats`。
- `RtcTransportStats`。
- `RtcIceCandidatePairStats`。
- `RtcInboundRtpStreamStats`。
- `RtcOutboundRtpStreamStats`。
- `RtcRemoteInboundRtpStreamStats`。
- `RtcDataChannelStats`。
- `RtcCodecStats`。

采样策略：

- 热路径只做 atomic counter 和 timestamp。
- `get_stats` 时聚合快照，不阻塞 worker 太久。
- trace ring 记录关键状态变化：ICE、DTLS、selected pair、SRTP error、NACK、PLI、bitrate change。
- benchmark 输出 JSON lines，方便后续画图。

## 17. 安全设计

安全优先级：

- 所有 packet parser 做长度检查和整数溢出检查。
- SDP/STUN/DTLS/SRTP/SCTP parser 全部 fuzz。
- 加密 tag、fingerprint、MAC 比较使用 constant-time。
- replay window 默认开启，不能被配置关闭。
- ICE consent freshness 默认开启。
- 远端 candidate 数、SSRC 数、DataChannel 数、SCTP stream 数有上限。
- 单 peer 的重传缓存、jitter buffer、reassembly buffer 有内存上限。
- 日志不得输出 ICE password、DTLS private key、SRTP key。

## 18. 测试策略

### 18.1 单元测试

每个 parser/builder：

- golden packet parse。
- write 后 parse 回原结构。
- 截断输入。
- 字段越界。
- 重复 attribute。
- unknown extension。
- 最大长度。

### 18.2 属性测试和 fuzz

重点 fuzz：

- SDP parser。
- STUN parser。
- RTP/RTCP parser。
- DTLS record/handshake parser。
- SCTP chunk parser。
- SRTP unprotect 外层长度处理。

### 18.3 网络模拟

实现 deterministic network simulator：

- loss。
- reorder。
- duplicate。
- delay。
- jitter。
- bandwidth cap。
- burst loss。
- NAT mapping timeout。

所有状态机测试使用虚拟 clock，避免真实 sleep。

### 18.4 互通测试

互通对象：

- Chrome headless。
- Firefox headless。
- Pion WebRTC。
- GStreamer webrtcbin。
- aiortc。

测试场景：

- DataChannel echo。
- one-way audio。
- one-way video。
- sendrecv audio/video。
- trickle ICE。
- TURN relay。
- packet loss + NACK。
- bandwidth drop + bitrate adaptation。

## 19. 性能设计

### 19.1 热路径预算

建连完成后，RTP 收发热路径目标：

- 每 packet 无 malloc/free。
- 每 packet 不做 SDP / ICE checklist 查找。
- 每 packet 只做一次 SSRC/MID route。
- SRTP auth/encrypt/decrypt 使用连续内存。
- packet descriptor 64 字节级别，便于 cache line。

建议 packet descriptor：

```text
PacketRef {
  slab_id: u32,
  offset: u16,
  len: u16,
  five_tuple_id: u32,
  recv_time_us: u64,
  kind: PacketKind,
  flags: u16,
}
```

### 19.2 性能门禁

性能测试不是最后阶段的集中优化项；每个模块第一次进入热路径时必须同时提交对应的基准或断言：

- Phase 0-1：arena/ring allocation counter、high-watermark 和 descriptor size 断言。
- Phase 2：UDP echo benchmark 覆盖 `recvmmsg` / `sendmmsg`、fallback 路径、EAGAIN/EINTR、batch size。
- Parser 阶段：每个公网 parser 有 ns/packet microbench，并保存 JSON lines 基线。
- SRTP/RTP/Jitter/Pacer 阶段：零堆分配断言、queue depth、P95/P99 latency 和 drop reason 统计。
- CI 中性能回归阈值默认 5%；无稳定 CI 性能机时至少保存本地基线和趋势文件，避免无声退化。

### 19.3 内存预算

默认单 peer 初始预算：

- ICE state：几十 KB。
- DTLS state：几十 KB 到数百 KB。
- SRTP contexts：每 SSRC 数 KB。
- RTP retransmission cache：按码率和 RTT 配置，默认视频约 1-4 MB。
- JitterBuffer：按分辨率和帧率配置，默认视频约 2-8 MB。
- DataChannel reassembly：默认总 cap 4 MB。

所有预算必须可配置，并暴露 stats。

### 19.4 基准

benchmarks：

- `bench_packet_parse`：RTP/STUN/RTCP/SCTP parser ns/packet。
- `bench_srtp`：protect/unprotect MB/s 和 packets/s。
- `bench_udp_echo`：recvmmsg/sendmmsg QPS。
- `bench_datachannel`：吞吐和延迟。
- `bench_rtp_loopback`：单 worker 多 peer RTP 转发。
- `bench_jitter`：乱序/丢包场景下 frame 输出延迟。
- `bench_congestion`：虚拟网络下收敛时间和丢包。

验收不要只看平均值，必须看 P95/P99 和最大队列深度。

## 20. 风险与拆解

最高风险：

- DTLS 和 crypto 正确性。
- SCTP 兼容性。
- 浏览器 SDP/JSEP 细节。
- 拥塞控制调参。
- H264/AV1 payload 边界和浏览器差异。
- TURN 长连接和 NAT 边界。

拆解原则：

- 先 data-only，后 RTP media。
- 先 host candidate loopback，后 srflx，再 relay。
- 先 SRTP_AES128_CM_HMAC_SHA1，后 AEAD。
- 先 encoded-frame transport，后接入 `../opus`、`../vp8` 的纯 Uya codec bridge。
- 先单 worker，后多 worker。
- 先固定码率 + NACK/PLI，后 GCC/TWCC。

## 21. 里程碑

M0：项目基座和协议工具  
M1：SDP + STUN parser/builder  
M2：ICE host/srflx 互通  
M3：DTLS-SRTP 建连  
M4：DataChannel echo  
M5：RTP one-way audio/video encoded frame  
M6：RTCP feedback + NACK/PLI + jitter buffer  
M7：TWCC + pacer + 动态码率  
M8：TURN relay  
M9：多 worker 和性能优化  
M10：接入 `../opus` / `../vp8` 纯 Uya codec bridge

## 22. 参考资料

- uya-lang/opus: https://github.com/uya-lang/opus
- uya-lang/vp8: https://github.com/uya-lang/vp8
- W3C WebRTC 1.0: https://www.w3.org/TR/webrtc/
- W3C WebRTC Statistics: https://www.w3.org/TR/webrtc-stats/
- W3C WebRTC Encoded Transform: https://www.w3.org/TR/webrtc-encoded-transform/
- RFC 8445 ICE: https://www.rfc-editor.org/rfc/rfc8445
- RFC 8489 STUN: https://www.rfc-editor.org/rfc/rfc8489
- RFC 8656 TURN: https://www.rfc-editor.org/rfc/rfc8656
- RFC 8838 Trickle ICE: https://www.rfc-editor.org/rfc/rfc8838
- RFC 8829 JSEP: https://www.rfc-editor.org/rfc/rfc8829
- RFC 3550 RTP: https://www.rfc-editor.org/rfc/rfc3550
- RFC 6716 Opus: https://www.rfc-editor.org/rfc/rfc6716
- RFC 8251 Opus Updates: https://www.rfc-editor.org/rfc/rfc8251
- RFC 7587 RTP Payload Format for Opus: https://www.rfc-editor.org/rfc/rfc7587
- RFC 6386 VP8 Data Format: https://www.rfc-editor.org/rfc/rfc6386
- RFC 7741 RTP Payload Format for VP8: https://www.rfc-editor.org/rfc/rfc7741
- RFC 5761 RTP/RTCP mux: https://www.rfc-editor.org/rfc/rfc5761
- RFC 7983 Multiplexing Scheme Updates: https://www.rfc-editor.org/rfc/rfc7983
- RFC 5764 DTLS-SRTP: https://www.rfc-editor.org/rfc/rfc5764
- RFC 3711 SRTP: https://www.rfc-editor.org/rfc/rfc3711
- RFC 7714 SRTP AEAD: https://www.rfc-editor.org/rfc/rfc7714
- RFC 4585 RTP/AVPF feedback: https://www.rfc-editor.org/rfc/rfc4585
- RFC 4588 RTP retransmission: https://www.rfc-editor.org/rfc/rfc4588
- RFC 8285 RTP header extensions: https://www.rfc-editor.org/rfc/rfc8285
- RFC 8831 WebRTC Data Channels: https://www.rfc-editor.org/rfc/rfc8831
- RFC 8832 DCEP: https://www.rfc-editor.org/rfc/rfc8832
- RFC 8261 SCTP over DTLS: https://www.rfc-editor.org/rfc/rfc8261
