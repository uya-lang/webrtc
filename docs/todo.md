# 纯 Uya WebRTC 重构 TODO

**状态**：启动阶段  
**日期**：2026-05-31  
**设计参考**：[design.md](design.md)

实现纪律：

- 先写测试，再写实现，再跑回归。
- 所有公网输入 parser 必须覆盖截断、坏长度、未知字段、最大长度。
- 每个阶段都要有可运行示例和 benchmark 占位。
- 每个阶段的第一批提交应优先加入 failing tests、fixtures、vectors、fuzz corpus 或 benchmark 基线，再补实现让它们通过。
- 热路径功能进入阶段验收前必须有 allocation counter、queue-depth 或 microbench 门禁，性能退化不能留到 Phase 18 才发现。
- 核心协议默认纯 Uya，不引入 libwebrtc/BoringSSL/usrsctp/libsrtp 等外部实现作为运行依赖。
- 若某阶段临时加入 reference oracle，只能用于测试对照，不能进入默认 runtime。
- Media payload 与 codec bridge 必须跟本地 `../opus`、`../vp8` 文档保持同步；WebRTC transport 首版仍可只处理 encoded frames。

## Phase 0：项目基座

- [x] 创建 `docs/design.md`。
- [x] 创建 `docs/todo.md`。
- [x] 根据本地 `../opus`、`../vp8` 同步 WebRTC / codec 边界文档。
- [x] 创建 `README.md`，说明项目目标、纯 Uya 边界、构建方式。
- [x] 创建 `Makefile` 或 `uyabuild` 配置。
- [x] 创建 `src/main.uya`，提供 CLI 占位：`--help`、`version`。
- [x] 创建 `src/webrtc/error.uya`，定义统一错误。
- [x] 创建 `src/webrtc/time.uya`，封装 monotonic clock。
- [x] 创建 `src/webrtc/arena.uya`，实现固定 slab packet arena。
- [x] 创建 `src/webrtc/ring.uya`，实现 bounded ring queue。
- [x] 创建 `tests/` 基础测试入口。
- [x] 创建 `benchmarks/` 基础 benchmark 入口。
- [x] 创建 allocation counter / high-watermark 测试辅助。
- [x] 创建 benchmark JSON lines 输出 helper。

验收标准：

- `make build` 生成可执行文件。
- `make test` 至少跑通空测试和基础 arena/ring 测试。
- `make bench` 至少输出空基线 JSON lines。
- `build/webrtc-uya --help` 可运行。
- 文档中明确不复用外部 WebRTC 协议库。

## Phase 1：基础二进制、buffer 与 packet 工具

- [x] 先增加 binary/buffer/arena failing tests：截断、越界、重复 free、cap 超限、clone 预算。
- [x] 先增加 `PacketRef` size / alignment 断言。
- [x] 先增加 arena/ring allocation counter 和 high-watermark tests。
- [x] 实现 big-endian / little-endian 读写 helpers。
- [x] 实现 checked integer add/mul/align helpers。
- [x] 实现 `ByteReader`，支持 cursor、remaining、read_u8/u16/u32/u64、read_slice。
- [x] 实现 `ByteWriter`，支持固定 buffer、回填 length、写 slice。
- [x] 实现 `PacketRef` 和 `PacketArena`。
- [x] 实现 arena free-list 和 reset。
- [x] 实现 slab token transfer。
- [x] 实现受预算约束的 packet clone 到 owner arena。
- [x] 实现常量时间 byte compare。
- [x] 增加 `bench_arena_ring`。

验收标准：

- 所有读写越界返回 `!T` 错误。
- arena 重复 alloc/free 不泄漏、不重复释放。
- `PacketRef` 不直接持有裸跨线程切片。
- `PacketRef` 保持 64 字节级别，arena/ring 基础路径无堆分配。
- clone bytes/count/drop/high-watermark 可观测，超预算路径有测试。

## Phase 2：UDP I/O 与事件循环

- [x] 先增加 UDP classifier 首字节矩阵测试。
- [x] 先增加短包、unknown、reserved/ZRTP、TURN ChannelData 边界测试。
- [x] 先增加 EAGAIN/EINTR/短写 failing tests。
- [x] 先建立 `bench_udp_echo` JSON lines 基线。
- [x] 实现 Linux UDP socket 创建、bind、connect 可选、nonblocking。
- [x] 实现 epoll worker。
- [x] 实现 monotonic timer wheel 或 min-heap。
- [x] 实现 `recvmmsg` 批量收包路径。
- [x] 实现 `sendmmsg` 批量发包路径。
- [x] 实现 fallback `recvfrom/sendto`。
- [x] 实现 UDP packet classifier：STUN / DTLS / TURN ChannelData / RTP / RTCP / reserved / unknown。
- [x] 实现 worker command queue 和 event queue。
- [x] 增加 loopback UDP echo 测试。

验收标准：

- 单 worker 能收发 UDP echo。
- EAGAIN/EINTR/短写路径测试通过。
- classifier 对 RFC 7983 首字节范围和短包不崩溃。
- `recvmmsg` / `sendmmsg` 与 fallback 路径都有 benchmark 基线。

## Phase 3：SDP parser/writer 与 JSEP 模型

- [x] 先收集 Chrome/Firefox SDP fixtures。
- [x] 先增加 SDP parse/write/parse roundtrip failing tests。
- [x] 先增加缺失 fingerprint、ice-pwd、rtcp-mux、不支持能力的错误测试。
- [x] 定义 `SessionDescription`、`MediaSection`、`CodecParameters`、`HeaderExtension`。
- [x] 实现 SDP 行扫描和字段 parser。
- [x] 支持 `v/o/s/t` 基础字段。
- [x] 支持 `m=` audio/video/application。
- [x] 支持 `a=group:BUNDLE`。
- [x] 支持 `a=mid`。
- [x] 支持 `a=ice-ufrag` / `a=ice-pwd`。
- [x] 支持 `a=fingerprint`。
- [x] 支持 `a=setup`。
- [x] 支持 `a=rtcp-mux`。
- [x] 支持 `a=candidate`。
- [x] 支持 `a=rtpmap` / `a=fmtp` / `a=rtcp-fb`。
- [x] 支持 `a=extmap`。
- [x] 支持 Opus SDP 参数：`minptime`、`maxptime`、`useinbandfec`、`stereo`、`sprop-stereo`、`usedtx`。
- [x] 支持 VP8 SDP 能力和反馈：`rtcp-fb` NACK、PLI、FIR、Transport-CC。
- [x] 支持 DataChannel application section。
- [x] 实现 SDP writer。
- [x] 实现 JSEP validator：bundle、rtcp-mux、fingerprint、payload type、direction。
- [x] 增加 `bench_sdp_parse`。

验收标准：

- Chrome/Firefox 常见 offer 能 parse -> write -> parse。
- 缺失 fingerprint、ice-pwd、rtcp-mux 时返回明确错误。
- 不支持能力不会静默忽略。
- SDP parser 对最大长度和长行输入有 microbench 基线。

## Phase 4：STUN

- [x] 先增加 RFC test vectors。
- [x] 先增加截断 header、坏 length、坏 padding、重复/未知 attribute failing tests。
- [x] 先建立 STUN parser fuzz corpus 和 `bench_stun_parse` 基线。
- [x] 定义 STUN message / attribute 类型。
- [x] 实现 STUN header parser。
- [x] 实现 TLV attribute iterator。
- [x] 实现 Binding request/response/error response builder。
- [x] 实现 XOR-MAPPED-ADDRESS。
- [x] 实现 USERNAME。
- [x] 实现 PRIORITY。
- [x] 实现 USE-CANDIDATE。
- [x] 实现 ICE-CONTROLLING / ICE-CONTROLLED。
- [x] 实现 MESSAGE-INTEGRITY。
- [x] 实现 MESSAGE-INTEGRITY-SHA256。
- [x] 实现 FINGERPRINT。
- [x] 实现 ERROR-CODE。

验收标准：

- binding request/response 与标准向量一致。
- integrity/fingerprint 错误能被拒绝。
- 任意截断 attribute 不越界。
- STUN parser benchmark 输出 ns/packet 和 allocation count。

## Phase 5：ICE host/srflx

- [x] 定义 `IceCandidate`、`CandidatePair`、`IceAgent`。
- [x] 实现 host candidate gathering。
- [x] 实现 STUN server reflexive candidate gathering。
- [x] 实现 remote candidate 添加。
- [x] 实现 candidate priority 计算。
- [x] 实现 checklist。
- [x] 实现 connectivity check transaction。
- [x] 实现 controlling / controlled role。
- [x] 实现 nomination。
- [x] 实现 role conflict。
- [x] 实现 selected pair。
- [x] 实现 consent freshness。
- [x] 实现 trickle ICE 状态。
- [x] 实现 ICE state change event。
- [x] 增加 loopback 双 agent 测试。
- [x] 增加 Chrome/Firefox trickle interop 测试。

验收标准：

- 两个本地 Uya ICE agent 可完成 selected pair。
- 与浏览器 host candidate loopback 场景可连接。
- consent 失败后状态进入 disconnected/failed。

## Phase 6：TURN client

- [x] 实现 TURN Allocate。
- [x] 实现 long-term credential。
- [x] 实现 Refresh。
- [x] 实现 CreatePermission。
- [x] 实现 Send/Data indication。
- [x] 实现 ChannelBind。
- [x] 实现 relay candidate 注入 ICE。
- [x] 实现 allocation refresh timer。
- [x] 增加 coturn interop 测试。

验收标准：

- 通过 coturn 获得 relay candidate。
- relay candidate 可以完成 ICE selected pair。
- allocation 过期前自动 refresh。

## Phase 7：Crypto 基础

- [x] 先收集官方 vectors 和 Wycheproof 风格负例。
- [x] 先增加 constant-time 比较测试和随机源失败测试。
- [x] 先建立 AES/GHASH/HMAC microbench 基线。
- [x] 实现 SHA-1。
- [x] 实现 SHA-256。
- [x] 实现 HMAC-SHA1。
- [x] 实现 HMAC-SHA256。
- [x] 实现 AES-CTR。
- [x] 实现 AES-GCM。
- [x] 实现 GHASH。
- [x] 实现 HKDF / TLS PRF 所需函数。
- [x] 实现 P-256 field arithmetic。
- [x] 实现 ECDHE P-256。
- [x] 实现 ECDSA P-256 sign/verify。
- [x] 实现 CSPRNG 平台熵源封装。

验收标准：

- 所有 crypto primitives 通过标准向量。
- tag/MAC/fingerprint 比较不使用早停逻辑。
- 随机源失败返回明确错误。
- crypto benchmark 记录 MB/s、ns/op 和是否启用 `@vector` 路径。

## Phase 8：DTLS 1.2 WebRTC 子集

- [x] 先增加 DTLS record parser 截断、epoch/sequence、fragment/reassembly failing tests。
- [x] 先增加 exporter reference 对照测试。
- [x] 先准备 OpenSSL/浏览器握手 fixtures。
- [x] 实现 DTLS record parser/writer。
- [x] 实现 handshake message fragmentation/reassembly。
- [x] 实现 ClientHello / ServerHello。
- [x] 实现 certificate 解析和生成。
- [x] 实现 ECDHE key exchange。
- [x] 实现 Finished 校验。
- [x] 实现 SRTP protection profile negotiation。
- [x] 实现 DTLS exporter。
- [x] 实现 handshake retransmission timer。
- [x] 实现 alert。
- [x] 实现 certificate fingerprint 校验。
- [x] 集成 ICE selected pair。
- [x] 增加 OpenSSL/浏览器互通测试脚本。

验收标准：

- Uya client/server 可以完成 DTLS handshake。
- 浏览器可与 Uya 端完成 DTLS handshake。
- fingerprint 错误必须拒绝连接。
- exporter 输出与 reference 对照一致。

## Phase 9：SRTP / SRTCP

- [x] 先增加 RFC 3711 vectors。
- [x] 先增加 sequence wrap、ROC、replay window failing tests。
- [x] 先建立 `bench_srtp` 基线和零堆分配断言。
- [x] 定义 SRTP context。
- [x] 实现 key derivation。
- [x] 实现 RTP sequence rollover counter。
- [x] 实现 replay window。
- [x] 实现 `SRTP_AES128_CM_HMAC_SHA1_80`。
- [x] 实现 `SRTP_AES128_CM_HMAC_SHA1_32`。
- [x] 实现 SRTCP protect/unprotect。
- [x] 集成 DTLS exporter keys。
- [x] 集成 RTP/RTCP demux。

验收标准：

- protect/unprotect roundtrip。
- replay packet 被拒绝。
- sequence rollover 后仍能正确解密。
- 与浏览器收发 SRTP packet 成功。
- protect/unprotect 热路径无堆分配，benchmark 输出 MB/s、packets/s、P95/P99。

## Phase 10：RTP / RTCP 基础

- [x] 先增加 RTP/RTCP parser fixtures、截断包、extension 边界 failing tests。
- [x] 先建立 RTP/RTCP parser microbench 和 allocation count 基线。
- [x] 实现 RTP header parser/writer。
- [x] 实现 one-byte/two-byte RTP header extension。
- [x] 实现 MID extension。
- [x] 实现 abs-send-time extension。
- [x] 实现 transport-wide sequence number extension。
- [x] 实现 RTP sender sequence/timestamp。
- [x] 实现 RTP receiver SSRC/MID route。
- [x] 实现 RTCP SR/RR。
- [x] 实现 RTCP SDES CNAME。
- [x] 实现 RTCP BYE。
- [x] 实现 RTCP NACK。
- [x] 实现 RTCP PLI。
- [x] 实现 RTCP FIR。
- [x] 实现 RTCP Transport-CC feedback。
- [x] 增加 RTP/RTCP fuzz corpus。

验收标准：

- RTP/RTCP parser 对截断包稳定返回错误。
- SR/RR 能计算基本 RTT。
- NACK/PLI 能从 receiver 触发到 sender。
- RTP/RTCP parser 热路径无堆分配。

## Phase 11：Media RTP payload

- [x] 定义 `EncodedFrame`。
- [x] 定义 codec capability 和 negotiation 数据结构。
- [x] 定义 `CodecId` / `MediaKind` / clock-rate / payload-type 映射。
- [x] 定义 optional `media/codec_bridge.uya` 边界，默认 transport build 不依赖 decoder/encoder。
- [x] 实现 Opus RTP packetize/depacketize。
- [x] 对齐 `../opus` 的 RTP Opus 语义：48 kHz clock、ptime/maxptime、stereo/sprop-stereo、useinbandfec、usedtx。
- [x] 增加 Opus single-packet、多 frame、DTX/空 payload、maxptime 超限 golden tests。
- [x] 实现 VP8 RTP payload descriptor。
- [x] 支持 VP8 X/N/S/PartID、PictureID、TL0PICIDX、TID、KEYIDX 字段。
- [x] 实现 VP8 frame reassembly。
- [x] 对齐 `../vp8` 的 VP8 RTP malformed 错误、keyframe 检测和 frame boundary 语义。
- [x] 增加 VP8 keyframe、inter frame、partition start、picture id wrap、丢包重组失败 golden tests。
- [x] 实现 H264 STAP-A。
- [x] 实现 H264 FU-A。
- [x] 实现 Annex-B / AVCC 转换 helper。
- [x] 实现 AV1 RTP payload descriptor。
- [x] 实现 keyframe 检测。
- [x] 实现 frame metadata。
- [x] 增加 payload format golden tests。

验收标准：

- 输入 encoded frame 可分片成 RTP，再重组为等价 frame。
- MTU 限制下不产生超大 UDP payload。
- keyframe metadata 正确。
- Opus / VP8 payload tests 与 `../opus`、`../vp8` 对应 fixtures 或语义说明一致。
- WebRTC transport 在不构建 codec bridge 时仍可跑 encoded-frame RTP 测试。

## Phase 12：JitterBuffer、NACK、PLI、RTX

- [x] 先增加网络模拟测试：loss/reorder/duplicate/delay。
- [x] 先增加 jitter/retransmission cap、clone budget、drop policy failing tests。
- [x] 先建立 `bench_jitter` 和 retransmission cache benchmark 基线。
- [x] 实现按 SSRC 的 packet reorder buffer。
- [x] 实现 missing sequence 检测。
- [x] 实现 NACK 生成和 backoff。
- [x] 实现 sender retransmission cache。
- [x] 实现 RTX payload 支持。
- [x] 实现 incomplete frame timeout。
- [x] 实现 PLI 触发和限频。
- [x] 实现 video frame 输出队列。
- [x] 实现 audio 小抖动缓冲。

验收标准：

- 乱序包能恢复顺序。
- 丢包触发 NACK，重传后可输出完整帧。
- 长时间无法恢复时请求关键帧且不无限占内存。
- 超过 cap 时 clone/drop/high-watermark stats 正确更新。

## Phase 13：DataChannel / SCTP

- [x] 先增加 SCTP packet/chunk parser fixtures、截断、坏 length failing tests。
- [x] 先增加 DCEP OPEN / ACK golden tests。
- [x] 先增加大消息 fragment/reassembly cap 和 unordered/reliable 行为测试。
- [x] 先建立 `bench_datachannel` 的 Sans-I/O 基线。
- [x] 实现 SCTP packet/chunk parser。
- [x] 实现 INIT / INIT_ACK / COOKIE_ECHO / COOKIE_ACK。
- [x] 实现 DATA chunk。
- [x] 实现 SACK。
- [x] 实现 HEARTBEAT。
- [x] 实现 ABORT / SHUTDOWN。
- [x] 实现 TSN tracking。
- [x] 实现 retransmission timer。
- [x] 实现 ordered / unordered delivery。
- [x] 实现 reliable / max_retransmits / max_packet_lifetime。
- [x] 实现 stream reset。
- [x] 实现 DCEP OPEN / ACK。
- [x] 实现 DataChannel public API。
- [x] 增加 Uya loopback DataChannel echo 示例。

验收标准：

- Uya loopback DataChannel 能 open、send、receive、close。
- 大消息 fragment/reassembly 正确。
- 不可靠/无序模式行为符合配置。
- reassembly 超过 cap 时拒绝或丢弃并更新 stats。

## Phase 14：PeerConnection 集成

- [x] 实现 `RtcRuntime`。
- [x] 实现 `PeerConnection` 生命周期。
- [x] 实现 `set_local_description`。
- [x] 实现 `set_remote_description`。
- [x] 实现 `create_offer`。
- [x] 实现 `create_answer`。
- [x] 实现 `add_ice_candidate`。
- [x] 实现 transceiver。
- [x] 实现 sender/receiver。
- [x] 实现 track。
- [x] 实现 DataChannel 事件。
- [x] 实现 connection state 聚合。
- [x] 实现 graceful close。
- [x] 增加 end-to-end loopback 示例。
- [x] 增加浏览器 DataChannel interop 测试。

验收标准：

- Uya to Uya 建立 PeerConnection。
- 浏览器 to Uya 建立 PeerConnection。
- 浏览器 DataChannel 能 open、send、receive、close。
- 关闭连接后 worker 无泄漏、无悬挂 timer。

## Phase 15：拥塞控制与 Pacer

- [x] 先增加虚拟网络 benchmark：带宽下降/恢复、queue delay、loss、jitter。
- [x] 先增加 pacer queue cap、drop/backpressure、P95/P99 delay failing tests。
- [x] 实现 pacer queue。
- [x] 实现 transport-wide seq 分配。
- [x] 实现 send-time 记录。
- [x] 实现 Transport-CC feedback parser。
- [x] 实现 delay-based estimator。
- [x] 实现 loss-based fallback。
- [x] 实现 probing。
- [x] 实现 bitrate allocator。
- [x] 实现 audio/video priority。
- [x] 将 RTP sender 接入 pacer。

验收标准：

- 带宽下降时码率下降且队列不无限增长。
- 带宽恢复时可逐步探测上升。
- P95/P99 queue delay 在目标阈值内。

## Phase 16：Stats、Trace 与诊断

- [x] 定义 stats 类型。
- [x] 实现 transport stats。
- [x] 实现 ICE candidate pair stats。
- [x] 实现 inbound RTP stats。
- [x] 实现 outbound RTP stats。
- [x] 实现 remote inbound RTP stats。
- [x] 实现 data channel stats。
- [x] 实现 codec stats。
- [x] 实现 trace ring。
- [x] 实现 `get_stats` API。
- [x] 实现 CLI `dump-stats` 示例。

验收标准：

- stats 与浏览器关键字段口径接近。
- get_stats 不长时间阻塞 worker。
- trace 能定位 ICE/DTLS/SRTP/RTP 主要状态变化。

## Phase 17：互通测试矩阵

- [x] Chrome headless DataChannel echo。
- [x] Chrome headless one-way audio。
- [x] Chrome headless one-way video VP8。
- [x] Chrome headless H264 payload。
- [x] Chrome headless trickle ICE。
- [x] Chrome headless TURN relay。
- [x] Firefox headless DataChannel echo。
- [x] Firefox headless one-way audio/video。
- [x] Pion WebRTC interop。
- [x] aiortc interop。
- [~] GStreamer webrtcbin interop。
  - blocked: 本机需通过 `/tmp` 解压 GStreamer tools/GIR 才能加载 `webrtcbin`；`GstWebRTC` 可 import 且 transceiver 可创建，但当前 GI runtime 下 `webrtcbin` request sink pad 返回空、`create-offer` 返回空 offer，尚不能形成真实 offer/answer 或连接验证。
- [x] 网络模拟：1%/5%/10% loss。
- [x] 网络模拟：reorder/duplicate/jitter。

验收标准：

- 每个 interop case 有自动化脚本。
- 失败日志包含 SDP、ICE state、DTLS state、selected pair、最近 SRTP/RTCP 错误摘要。

## Phase 18：性能优化

- [x] 汇总前序阶段已有 benchmark 基线。
- [x] 补齐遗漏的 RTP/RTCP parser microbench。
- [x] 补齐遗漏的 STUN parser microbench。
- [x] 补齐遗漏的 SRTP protect/unprotect microbench。
- [x] 补齐遗漏的 UDP recvmmsg/sendmmsg benchmark。
- [x] 补齐遗漏的 DataChannel throughput benchmark。
- [x] 补齐遗漏的 RTP loopback multi-peer benchmark。
- [x] 补齐遗漏的 JitterBuffer benchmark。
- [x] 补齐遗漏的 Pacer queue benchmark。
- [x] 用 `@vector` 优化 AES/GHASH/CRC 可行路径。
- [x] 优化 packet descriptor cache locality。
- [x] 优化 retransmission cache。
- [x] 优化 stats snapshot。

验收标准：

- benchmark 输出 JSON lines。
- 所有优化版有 reference 对照。
- 性能回归超过 5% 时 CI 报警。

## Phase 19：安全加固

- [~] SDP fuzz。
  - blocked: 直接编译真实 Uya SDP parser fuzz smoke 时，Uya C99 后端会把 `[[byte: 32]: N]` 结构字段生成为非法 C（见 `.agent/toolchain-bugs/20260602223335-nested-byte-array-field.md`）；在工具链修复前无法用真实 parser 入口完成 SDP fuzz 验证。
- [x] STUN fuzz。
- [x] DTLS record/handshake fuzz。
- [x] RTP/RTCP fuzz。
- [x] SCTP fuzz。
- [x] SRTP replay/rollover property tests。
- [x] ICE candidate 上限测试。
- [x] SSRC/track/datachannel 上限测试。
- [x] JitterBuffer/reassembly 内存上限测试。
- [x] Secret logging audit。
- [x] constant-time audit。

验收标准：

- fuzz corpus 持续运行不崩溃。
- 所有公网输入长度字段都有测试覆盖。
- 日志不泄漏 key/password。

## Phase 20：多平台

- [x] 抽象 net backend。
- [x] Linux epoll backend 完成。
- [~] macOS kqueue backend。
  - blocked: 当前运行环境是 Linux，`../uya/lib` 和本仓库没有 kqueue/kevent FFI 或 macOS runner，无法在本机实现并验证真实 macOS kqueue backend 或 DataChannel echo。
- [~] Windows IOCP backend。
  - blocked: 当前运行环境是 Linux，`../uya/lib` 和本仓库没有 Win32 IOCP/OVERLAPPED FFI、Windows runner 或 MinGW cross compiler，无法在本机实现并验证真实 Windows IOCP backend 或 DataChannel echo。
- [~] Android socket/thread/time 适配。
  - blocked: 当前运行环境是 Linux，未提供 Android NDK、`adb`、Android runner 或 Android 专用 socket/thread/time FFI，无法在本机实现并验证真实 Android socket/thread/time 适配。
- [~] iOS socket/thread/time 适配。
  - blocked: 当前运行环境是 Linux，未提供 iOS SDK、`xcrun`、iOS runner、Darwin/iOS socket/thread/time FFI 或 kqueue 支撑，无法在本机实现并验证真实 iOS socket/thread/time 适配。
- [~] 平台 CI matrix。
  - blocked: 该任务验收要求 macOS/Windows 至少跑通 DataChannel echo，但 macOS kqueue 与 Windows IOCP 后端当前均缺少真实 FFI/runner 验证；在后端阻塞解除前只能建立不完整或 allow-failure 矩阵，不能作为完成提交。

验收标准：

- Linux 为默认稳定平台。
- macOS/Windows 至少跑通 DataChannel echo。
- 平台差异只在 `net` / `time` / `random` 等边界模块。

## Phase 21：Codec 兄弟仓库同步与集成

该阶段不阻塞 WebRTC 传输栈首版。`../opus` 和 `../vp8` 已经作为独立纯 Uya codec 仓库存在，本仓库只维护 WebRTC 侧的边界、适配和互通测试。
FFmpeg 只作为显式 reference codec / 浏览器互通测试目标使用，不能进入默认 runtime 或纯 Uya codec bridge。

- [x] 确认 `../opus` 已有 `docs/design.md` 和 `docs/todo.md`。
- [x] 确认 `../vp8` 已有 `docs/design.md` 和 `docs/todo.md`。
- [x] 在 WebRTC 设计文档中同步 `../opus` / `../vp8` 的职责边界。
- [x] 建立 codec bridge feature gate，默认关闭。
- [x] 定义泛型 codec 抽象：`VideoEncoder<Encoder>`、`VideoDecoder<Decoder>`、`AudioEncoder<Encoder>`、`AudioDecoder<Decoder>`。
- [x] 定义 Opus bridge：PCM/Opus packet 与 WebRTC `EncodedFrame` 的转换 API。
- [x] 定义 VP8 bridge：YUV/VP8 frame 与 WebRTC `EncodedFrame` 的转换 API。
- [~] 对齐 Opus RTP payload tests 与 `../opus` 的 `container/rtp_opus.uya` 计划。
  - blocked: `../opus` 的 Phase 19 RTP Opus 任务仍未实现，`../opus/src/opus/container/` 只有 `.gitkeep`，暂无 `container/rtp_opus.uya`、payload fixtures 或 sibling 测试可供本仓库真实对齐。
- [~] 对齐 VP8 RTP payload tests 与 `../vp8` 的 RTP payload descriptor / frame reassembly 计划。
  - blocked: `../vp8` 的 Phase 16 RTP VP8 payload descriptor parser 与 RTP packet reassembly 仍未实现，当前 sibling 仓库只有 IVF/raw container 模块，没有 RTP 模块、fixtures 或 reassembly 测试可供本仓库真实对齐。
- [x] 建立跨仓库 fixture manifest，记录样本来源、hash、授权和适用阶段。
- [x] 增加 `make test-codec-bridge`，仅在 sibling codec 可构建时运行。
- [x] 增加 `make test-ffmpeg-codec-flow`，用 FFmpeg `libopus` / `libvpx` 验证泛型 codec 推拉流准确性。
- [x] 增加 `make test-ffmpeg-chrome-call`，用 FFmpeg 生成 VP8/Opus WebM，Chrome recvonly `RTCPeerConnection` + Uya direct sender 验证 audio/video 通话、SDP media line、Opus/VP8 negotiation、inbound packets 和 decoded frames。
- [~] 增加浏览器 one-way audio 示例，可选择直接发送 encoded Opus 或通过 Opus bridge 编码。
  - blocked: 现有 Phase 17 audio interop 使用浏览器 WebAudio/内部 Opus 发送，不能作为本仓库直接发送 encoded Opus 或通过 Opus bridge 编码的示例；`../opus` encoder 与 RTP Opus bridge 仍未实现，暂无真实 bridge encode 路径可验证。
- [~] 增加浏览器 one-way VP8 示例，可选择直接发送 encoded VP8 或通过 VP8 bridge 编码。
  - blocked: 现有 Phase 17 video interop 使用浏览器 canvas/内部 VP8 发送，不能作为本仓库直接发送 encoded VP8 或通过 VP8 bridge 编码的示例；`../vp8` encoder、library API 与 RTP reassembly 仍未实现，暂无真实 bridge encode 路径可验证。
- [x] 打通 Uya 进程直连 Chrome 的 FFmpeg codec 音视频通话：FFmpeg raw/encoded frame -> WebRTC RTP payload packetizer -> SRTP -> UDP -> Chrome inbound RTP，且不经浏览器内部 `pc1`/`pc2` loopback。
  - [x] 建立 `test-ffmpeg-chrome-call` 的 Uya direct sender 验收壳：Chrome 只做 recvonly inbound peer，测试禁止 `captureStream`、浏览器内部 `pc1`/`pc2` loopback 和 Pion/aiortc/wrtc 等外部 WebRTC sender。
  - [x] 增加 Uya sender CLI 入口 `uya_ffmpeg_direct_sender`，dry-run 可读取 Chrome offer / media 参数并输出诊断 JSON；非 dry-run 在 DTLS-SRTP 未接通前拒绝写假 SDP answer。
  - [x] 在 Uya sender 中实现 `EncodedFrame` -> Opus/VP8 RTP payload packetizer，并覆盖 timestamp、payload type、SSRC、marker、单包 MTU guard。
  - [x] 在 Uya sender 中实现 FFmpeg libavcodec/libavutil extern codec ingest：PCM/I420 raw frame -> Opus/VP8 `EncodedFrame`，并保留 decoder path 供后续验证 Uya 自研 encoder/decoder。
    - [x] 定义 FFmpeg codec extern ABI、raw audio/video view、encoded packet -> `EncodedFrame` 适配和显式门禁 `test-ffmpeg-codec-extern`。
    - [x] 接入 FFmpeg Opus encoder：PCM/s16le -> Opus packet -> `EncodedFrame`，并进入 `rtp_packetize_encoded_frame`。
    - [x] 接入 FFmpeg VP8 encoder：I420 -> VP8 frame -> `EncodedFrame`，并进入 `rtp_packetize_encoded_frame`。
    - [x] 接入 FFmpeg decoder 验证路径：Opus/VP8 `EncodedFrame` -> decoded PCM/I420，用于后续 Uya 自研 encoder/decoder A/B 验证。
  - [x] 建立 FFmpeg/Uya codec provider 可切换入口：direct sender CLI 支持 `--codec ffmpeg|uya`，FFmpeg provider 继续走已验证的 extern codec ingest，Uya provider 通过纯 `codec_bridge` ready 位保留切换入口；当前 Uya sibling encoder/decoder 尚未接入时 dry-run 诊断明确报告 `codecProviderReady=false`。
    - verified 2026-06-04: `bash tests/check_phase11_media.sh`、`bash tests/check_phase21_ffmpeg_codec_extern.sh`、`bash tests/check_phase21_ffmpeg_direct_sender_cli.sh`、`bash tests/check_phase21_ffmpeg_direct_sender.sh`、`bash tests/check_phase21_ffmpeg_chrome_call.sh` 通过；Chrome E2E 使用 `--codec ffmpeg`，`chrome_audio_packets=235`、`chrome_video_packets=141`、`chrome_video_frames=141`、`sender_ffmpeg_frames=481`、`sender_rtp_packets=481`、`sender_srtp_packets=481`、`sender_srtcp_packets=10`、`sender_rtcp_sender_reports=10`、`sender_srtcp_packets_received=6`、`sender_rtcp_receiver_reports=6`、`sender_udp_packets=491`。
  - [x] 在 Uya sender 中接通 Chrome host ICE/STUN 和 DTLS-SRTP exporter，生成真实 SRTP/SRTCP key。
    - [x] 约束 direct sender 新增 session / DTLS identity 路径保持纯 Uya；FFmpeg codec 是唯一允许的 extern codec 边界。
    - [x] 解析 Chrome recvonly Opus/VP8 offer，并生成带纯 Uya 静态 P-256 identity fingerprint 的 `setup:passive` SDP answer。
    - [x] 嵌入 DTLS identity 证书 DER，验证 fingerprint、私钥派生公钥和 ECDSA sign/verify。
    - [x] 实现纯 Uya DTLS server first flight：解析 ClientHello，协商 `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` / `SRTP_AES128_CM_SHA1_80`，写出 ServerHello / Certificate / ServerKeyExchange / ServerHelloDone。
    - [x] 实现纯 Uya ClientKeyExchange -> ECDH premaster -> TLS master secret -> DTLS-SRTP exporter key material，并验证 server-role SRTP context 方向。
    - [x] 实现纯 Uya DTLS AES-128-GCM record key expansion、nonce/AAD 组装和 encrypted Finished 解密/verify_data 校验 roundtrip。
    - [x] 实现纯 Uya DTLS server handshake，协商 `SRTP_AES128_CM_SHA1_80` 并通过 exporter 生成 SRTP/SRTCP key。
  - [x] 在 Uya sender 中将 RTP 经 SRTP protect 后通过 UDP 发给 Chrome selected pair。
    - [x] 将 `rtp_packetize_encoded_frame` 输出接入 SRTP protect，并用 unprotect roundtrip 验证 protected RTP 包可还原。
    - [x] 将 protected SRTP 包通过 UDP 发给 Chrome selected pair。
    - [x] 补齐 SRTCP Sender Report/Receiver feedback 发送与统计；当前不阻塞 Chrome inbound RTP/VP8 解码验收。
      - verified 2026-06-04: `bash tests/check_phase21_ffmpeg_chrome_call.sh` 通过，Uya sender 发送 `sender_srtcp_packets=10`、`sender_rtcp_sender_reports=10`，并解析 Chrome 回传 `sender_srtcp_packets_received=5`、`sender_rtcp_packets_received=5`、`sender_rtcp_receiver_reports=5`。
  - [x] 通过 Chrome inbound-rtp stats 和 decoded audio/video frames 验证观看成功，并记录 FFmpeg packet、RTP packet、SRTP packet、UDP packet 计数。
    - verified 2026-06-03: `python3 tests/ffmpeg_chrome_call.py --keep-temp` 通过，`source_audio_packets=201`、`source_video_packets=120`、`chrome_audio_packets=10`、`chrome_video_packets=6`、`chrome_video_frames=6`、`sender_ffmpegFrames=321`、`sender_rtpPackets=321`、`sender_srtpPackets=321`、`sender_udpPackets=321`。
    - verified 2026-06-04: `bash tests/check_phase21_ffmpeg_chrome_call.sh` 通过，`source_audio_packets=201`、`source_video_packets=120`、`chrome_audio_packets=238`、`chrome_video_packets=143`、`chrome_video_frames=143`、`sender_ffmpeg_frames=481`、`sender_rtp_packets=481`、`sender_srtp_packets=481`、`sender_srtcp_packets=10`、`sender_rtcp_sender_reports=10`、`sender_srtcp_packets_received=5`、`sender_rtcp_packets_received=5`、`sender_rtcp_receiver_reports=5`、`sender_udp_packets=491`。
  - [x] 增加 `make preview-ffmpeg-chrome-call` 一键手工预览：Chrome 打开本地页后点击 `Start Uya Video`，页面通过本地 JSON API 启动 `uya_ffmpeg_direct_sender`、交换 SDP、播放 remote `<video>` 并显示 Chrome inbound stats / Uya sender diagnostics。
    - verified 2026-06-04: `python3 tests/ffmpeg_chrome_call.py --manual-preview-e2e --keep-temp` 通过，`chrome_audio_packets=237`、`chrome_video_packets=142`、`chrome_video_frames=142`、`sender_ffmpeg_frames=481`、`sender_rtp_packets=481`、`sender_srtp_packets=481`、`sender_srtcp_packets=10`、`sender_rtcp_sender_reports=10`、`sender_srtcp_packets_received=10`、`sender_rtcp_packets_received=10`、`sender_rtcp_receiver_reports=10`、`sender_udp_packets=491`。
    - verified 2026-06-04: `bash tests/check_phase21_ffmpeg_chrome_call.sh` 通过（含 `--manual-preview-e2e`），manual preview `chrome_audio_packets=234`、`chrome_video_packets=141`、`chrome_video_frames=141`、`sender_rtp_packets=481`、`sender_srtcp_packets=10`、`sender_rtcp_receiver_reports=8`、`sender_udp_packets=491`。
    - verified 2026-06-04: `make test-ffmpeg-chrome-call` 通过，manual preview `chrome_audio_packets=234`、`chrome_video_packets=140`、`chrome_video_frames=140`、`sender_rtp_packets=481`、`sender_srtcp_packets=10`、`sender_rtcp_receiver_reports=9`、`sender_udp_packets=491`。
- [x] H264 仅保留 payload/Annex-B/AVCC 工具，编解码另行评估。
- [x] AV1 仅保留 OBU/RTP 工具，编解码另行评估。

验收标准：

- codec bridge 不污染 WebRTC transport 核心。
- transport 可在无 codec 编解码器时处理 encoded frames。
- 启用 bridge 时只依赖纯 Uya sibling package，不引入 libopus、libvpx、FFmpeg runtime。
- FFmpeg 相关能力只通过显式测试目标启用，并输出 Chrome inbound audio/video 统计。
- Opus / VP8 bridge 的错误边界清楚区分 payload 错误、codec bitstream 错误和 WebRTC transport 错误。

## 第一条推荐执行线

最短可见成果路线：

1. Phase 0 - Phase 2：项目可构建，UDP worker 可收发。
2. Phase 3 - Phase 5：SDP/STUN/ICE host/srflx，先跑本地 ICE。
3. Phase 7 - Phase 9：Crypto/DTLS/SRTP，打通浏览器握手。
4. Phase 13：SCTP/DCEP Sans-I/O 与 Uya loopback DataChannel。
5. Phase 14：PeerConnection 集成后跑浏览器 DataChannel echo。
6. Phase 10 - Phase 12：RTP/RTCP/media payload，打通 encoded audio/video。
7. Phase 15 - Phase 18：拥塞控制和性能优化。
