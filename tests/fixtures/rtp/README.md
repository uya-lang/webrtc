# RTP/RTCP Parser Fixtures

`parser_cases.json` 覆盖了 Phase 10 首批 parser 基座：

- RTP 有效包：最小头、CSRC、one-byte extension、two-byte extension、padding。
- RTP 失败包：截断头、版本错误、CSRC 截断、extension header 截断、extension 长度越界、padding 越界。
- Extension 边界：one-byte/two-byte element 截断、reserved id 终止、padding 处理。
- RTCP 有效包：SR/RR 最小包。
- RTCP 失败包：截断头、版本错误、packet type 越界、length 越界。

`fuzz/` 目录提供结构化 seed corpus，覆盖：

- RTP：最小合法包、CSRC+extension 合法包、extension 截断、padding 越界。
- RTCP：SR/RR/NACK/PLI/FIR/Transport-CC 合法包。
- RTCP 失败包：截断头、length 越界、Transport-CC status-count 不一致。

运行：

```bash
python3 tests/test_rtp_parser.py
```
