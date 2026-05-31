# Phase 7 Crypto Fixtures

这些 fixture 用于 Phase 7 的 hash / HMAC 标准向量与 Wycheproof 风格负例准备。

来源：

- SHA-1 / SHA-256：NIST FIPS 180-4 Secure Hash Standard
  - https://csrc.nist.gov/pubs/fips/180-4/upd1/final
- HMAC-SHA1：RFC 2202 Test Cases for HMAC-MD5 and HMAC-SHA-1
  - https://www.rfc-editor.org/rfc/rfc2202
- HMAC-SHA256：RFC 4231 Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512
  - https://www.rfc-editor.org/rfc/rfc4231

说明：

- `*_vectors.json` 保存官方正例。
- `wycheproof_like_*.json` 保存仿照 Wycheproof 风格组织的负例。
- 负例刻意覆盖改 tag、改消息、截断 tag 等后续 constant-time / verify 路径必须拒绝的情况。
