# SCTP Parser Fuzz Seeds

这些 seed 面向 SCTP packet / chunk parser 的结构化起步输入，覆盖：

- 最小合法 packet + `COOKIE_ACK` chunk。
- packet 头部截断。
- chunk length 小于最小 header 长度。
- chunk length 越界导致的 packet 截断。

每个 `.hex` 文件都是可直接 `xxd -r -p` 还原的十六进制字节流。

