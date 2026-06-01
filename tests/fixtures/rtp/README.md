# RTP/RTCP Parser Fixtures

`parser_cases.json` 覆盖了 Phase 10 首批 parser 基座：

- RTP 有效包：最小头、CSRC、one-byte extension、two-byte extension、padding。
- RTP 失败包：截断头、版本错误、CSRC 截断、extension header 截断、extension 长度越界、padding 越界。
- Extension 边界：one-byte/two-byte element 截断、reserved id 终止、padding 处理。
- RTCP 有效包：SR/RR 最小包。
- RTCP 失败包：截断头、版本错误、packet type 越界、length 越界。

运行：

```bash
python3 tests/test_rtp_parser.py
```
