#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_dtls_test_main.uya
test -d src/webrtc/dtls
test -f src/webrtc/dtls/handshake.uya
test -f src/webrtc/dtls/model.uya
test -f src/webrtc/dtls/record.uya
test -d tests/fixtures/dtls
test -d tests/fixtures/dtls/certs
test -d tests/fixtures/dtls/fuzz
test -f tests/fixtures/dtls/README.md
test -f tests/fixtures/dtls/certs/openssl_self_signed_p256.der.hex
test -f tests/fixtures/dtls/exporter_reference.json
test -f tests/fixtures/dtls/fuzz/truncated_record_header.hex
test -f tests/fixtures/dtls/fuzz/record_epoch_sequence_edge.hex
test -f tests/fixtures/dtls/fuzz/fragment_length_mismatch.hex
test -f tests/fixtures/dtls/fuzz/reassembly_overlap.hex
test -f tests/fixtures/dtls/fuzz/reassembly_gap.hex
test -x tests/dtls_vectors.py
test -x tests/dtls_exporter_reference.py

rg -Fq "dtls_test_check_record_parser_truncation_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_record_epoch_and_sequence_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_record_writer_roundtrip" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_handshake_fragment_length_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_reassembly_overlap_and_gap_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_reassembly_two_fragment_roundtrip" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_client_hello_roundtrip" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_client_hello_invalid_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_server_hello_roundtrip" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_server_hello_invalid_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_certificate_roundtrip" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_certificate_invalid_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_ecdhe_key_exchange_roundtrip" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_ecdhe_key_exchange_invalid_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_ecdhe_generated_key_share" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_exporter_reference_cases" src/webrtc_dtls_test_main.uya
rg -Fq "export struct DtlsRecordHeader" src/webrtc/dtls/model.uya
rg -Fq "export struct DtlsHandshakeFragment" src/webrtc/dtls/handshake.uya
rg -Fq "export struct DtlsHandshakeReassemblyState" src/webrtc/dtls/handshake.uya
rg -Fq "export struct DtlsClientHello" src/webrtc/dtls/handshake.uya
rg -Fq "export struct DtlsServerHello" src/webrtc/dtls/handshake.uya
rg -Fq "export struct DtlsCertificateEntry" src/webrtc/dtls/handshake.uya
rg -Fq "export struct DtlsCertificateMessage" src/webrtc/dtls/handshake.uya
rg -Fq "export struct DtlsServerKeyExchange" src/webrtc/dtls/handshake.uya
rg -Fq "export struct DtlsClientKeyExchange" src/webrtc/dtls/handshake.uya
rg -Fq "export struct DtlsEcdheKeyShare" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_handshake_fragment_parse" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_handshake_reassembly_absorb" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_handshake_reassembly_take_message" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_client_hello_parse" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_client_hello_write" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_server_hello_parse" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_server_hello_write" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_certificate_parse" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_certificate_write" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_server_key_exchange_parse" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_server_key_exchange_write" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_client_key_exchange_parse" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_client_key_exchange_write" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_ecdhe_p256_key_share_generate" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_ecdhe_p256_shared_secret" src/webrtc/dtls/handshake.uya
rg -Fq "export fn dtls_record_parse" src/webrtc/dtls/record.uya
rg -Fq "export fn dtls_record_write" src/webrtc/dtls/record.uya

xxd -r -p tests/fixtures/dtls/certs/openssl_self_signed_p256.der.hex \
    | openssl x509 -inform DER -noout -text >/dev/null

python3 tests/dtls_vectors.py
python3 tests/dtls_exporter_reference.py
../uya/bin/uya run src/webrtc_dtls_test_main.uya
