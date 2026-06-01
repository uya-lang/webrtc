# RTP/RTCP Fuzz Corpus Seeds

这些 seed 面向 RTP/RTCP parser 的结构化 fuzz 起步输入，覆盖：

- RTP 最小包、带 CSRC+extension 的合法包。
- RTP extension 截断、padding 越界。
- RTCP SR/RR/NACK/PLI/FIR/Transport-CC 合法包。
- RTCP 头截断、length 越界、Transport-CC status-count 不一致。

每个 `.hex` 文件都是可直接 `xxd -r -p` 还原的十六进制字节流，供后续 fuzz harness 导入为初始语料。
