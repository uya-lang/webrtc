# Phase 8 DTLS Fixtures

这些 fixture 用于 Phase 8 的第一批 DTLS record / handshake failing tests。

当前覆盖的失败类别：

- record header 截断
- record epoch / sequence 边界
- fragmented handshake 长度不一致
- fragment overlap / gap，供后续 reassembly failing tests 使用
- OpenSSL 生成的 P-256 自签名 DER 证书样本，供 `Certificate` 消息 parse/write 与后续 fingerprint 测试复用

这些样本当前只用于 fixture 完整性检查和测试占位；真正的 parser / reassembly 实现会在后续任务里消费它们。
