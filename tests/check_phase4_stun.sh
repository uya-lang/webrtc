#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/stun
test -d tests/fixtures/stun/fuzz
test -f tests/fixtures/stun/README.md
test -f tests/fixtures/stun/rfc5769_binding_request.hex
test -f tests/fixtures/stun/rfc5769_binding_response_ipv4.hex
test -f tests/fixtures/stun/rfc5769_binding_response_ipv6.hex
test -f tests/fixtures/stun/fuzz/truncated_header.hex
test -f tests/fixtures/stun/fuzz/bad_length.hex
test -f tests/fixtures/stun/fuzz/bad_padding.hex
test -f tests/fixtures/stun/fuzz/duplicate_username.hex
test -f tests/fixtures/stun/fuzz/unknown_required.hex
test -f src/webrtc_stun_test.uya
test -f src/webrtc/stun/model.uya
test -f src/webrtc/stun/parse.uya
test -f src/webrtc/stun/write.uya
test -f benchmarks/bench_stun_parse.uya
test -f benchmarks/baselines/bench_stun_parse.jsonl
test -x tests/stun_vectors.py

rg -Fq 'test "stun fixtures cover RFC 5769 request and binding responses"' src/webrtc_stun_test.uya
rg -Fq 'test "stun header parser rejects truncated header and invalid message length"' src/webrtc_stun_test.uya
rg -Fq 'test "stun attribute iterator rejects truncated tlv and bad padding"' src/webrtc_stun_test.uya
rg -Fq 'test "binding request parser rejects duplicate username and unknown comprehension-required attribute"' src/webrtc_stun_test.uya
rg -Fq 'test "binding builders encode request success response and error response"' src/webrtc_stun_test.uya
rg -Fq 'test "xor mapped address username priority use-candidate and ice role attributes roundtrip"' src/webrtc_stun_test.uya
rg -Fq 'test "error code parser and builder roundtrip"' src/webrtc_stun_test.uya
rg -Fq 'test "message integrity parser builder and verifier roundtrip"' src/webrtc_stun_test.uya
rg -Fq 'test "message integrity sha256 parser builder and verifier roundtrip"' src/webrtc_stun_test.uya
rg -Fq 'test "fingerprint parser builder and verifier roundtrip"' src/webrtc_stun_test.uya

rg -Fq "export struct StunMessageHeader" src/webrtc/stun/model.uya
rg -Fq "export struct StunAttribute" src/webrtc/stun/model.uya
rg -Fq "export struct StunAttributeIterator" src/webrtc/stun/model.uya
rg -Fq "export struct StunXorMappedAddress" src/webrtc/stun/model.uya
rg -Fq "export struct StunErrorCodeAttribute" src/webrtc/stun/model.uya
rg -Fq "export fn stun_message_type_encode" src/webrtc/stun/model.uya
rg -Fq "export fn stun_header_parse" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_attribute_iterator_init" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_attribute_iterator_next" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_attribute_is_comprehension_required" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_binding_request_validate_attribute" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_xor_mapped_address" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_username" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_priority" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_use_candidate" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_ice_role_tiebreaker" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_message_integrity" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_message_integrity_compute" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_verify_message_integrity" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_message_integrity_sha256" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_message_integrity_sha256_compute" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_verify_message_integrity_sha256" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_fingerprint" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_fingerprint_compute" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_verify_fingerprint" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_parse_error_code" src/webrtc/stun/parse.uya
rg -Fq "export fn stun_builder_init_binding_request" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_init_binding_success_response" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_init_binding_error_response" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_username" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_priority" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_use_candidate" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_ice_controlled" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_ice_controlling" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_xor_mapped_address_ipv4" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_xor_mapped_address_ipv6" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_message_integrity" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_message_integrity_sha256" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_fingerprint" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_append_error_code" src/webrtc/stun/write.uya
rg -Fq "export fn stun_builder_finish" src/webrtc/stun/write.uya
rg -Fq "benchmark_main_emit_stun_parse_jsonl" benchmarks/bench_stun_parse.uya
rg -Fq '"name":"bench_stun_parse"' benchmarks/baselines/bench_stun_parse.jsonl

python3 tests/stun_vectors.py
