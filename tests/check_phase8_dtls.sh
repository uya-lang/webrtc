#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_dtls_test_main.uya
test -d tests/fixtures/dtls
test -d tests/fixtures/dtls/fuzz
test -f tests/fixtures/dtls/README.md
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
rg -Fq "dtls_test_check_handshake_fragment_length_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_reassembly_overlap_and_gap_cases" src/webrtc_dtls_test_main.uya
rg -Fq "dtls_test_check_exporter_reference_cases" src/webrtc_dtls_test_main.uya

python3 tests/dtls_vectors.py
python3 tests/dtls_exporter_reference.py
