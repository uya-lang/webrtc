# SDP fixtures

这些 fixtures 用来驱动 Phase 3 的 parse/write/parse roundtrip 和 validator 回归。

- `chrome_offer.sdp`：基于 Chromium/libwebrtc 的 SDP 参考字符串整理，保留当前 parser 已覆盖的核心字段，并补齐 loopback host candidate 与 DataChannel section。
  - https://chromium.googlesource.com/external/webrtc/+/branch-heads/57/webrtc/api/webrtcsdp_unittest.cc
  - https://chromium.googlesource.com/external/w3c/web-platform-tests/+/merge_pr_8554/webrtc/protocol/bundle.https.html
- `firefox_offer.sdp`：基于 Chromium WebRTC SDP fuzz corpus 中的 Firefox offer 归一化，保留当前阶段需要验证的 JSEP 字段。
  - https://chromium.googlesource.com/chromium/src/+/refs/heads/main/third_party/webrtc/tools_webrtc/ios/PRESUBMIT.py
  - https://webrtc.googlesource.com/src/+/refs/heads/main/test/fuzzers/corpora/sdp-corpus/firefox-2.sdp

归一化原则：

- 只保留本阶段 parser/writer/validator 已支持的字段。
- ICE candidate、fingerprint 和 SCTP 参数使用文档化的示例值，避免把环境相关 IP/ufrag/pwd 当成稳定断言。
- 行顺序已经调整到当前 writer 的规范顺序，因此 `parse -> write -> parse` 要求精确稳定。
