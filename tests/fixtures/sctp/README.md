# SCTP Parser Fixtures

这些 fixtures 用于 Phase 13 的 SCTP packet / chunk parser 首批回归。

当前覆盖的输入类别：

- 最小合法 SCTP packet，包含一个 `COOKIE_ACK` chunk。
- 头部截断 packet。
- chunk length 小于 4 的坏长度 packet。
- chunk length 超过剩余字节的坏长度 packet。

`fuzz/` 目录下的 `.hex` 文件都是可直接用 `xxd -r -p` 还原的十六进制字节流，后续会接入 fuzz corpus 和 parser 回归脚本。

