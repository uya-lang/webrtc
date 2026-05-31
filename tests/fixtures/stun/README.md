# STUN Fixtures

这些 fixtures 用于 Phase 4 的 RFC 向量验证、负例回归和后续 fuzz corpus 扩展。

- `rfc5769_binding_request.hex`：RFC 5769 sample Binding request。
- `rfc5769_binding_response_ipv4.hex`：RFC 5769 IPv4 Binding success response。
- `rfc5769_binding_response_ipv6.hex`：RFC 5769 IPv6 Binding success response。
- `fuzz/`：手工挑选的最小 corpus，覆盖截断 header、坏 length、坏 padding、重复 attribute、未知 comprehension-required attribute。
