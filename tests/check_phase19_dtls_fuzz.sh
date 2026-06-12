#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/dtls/fuzz
test -f tests/fixtures/dtls/fuzz/truncated_record_header.hex
test -f tests/fixtures/dtls/fuzz/record_epoch_sequence_edge.hex
test -f tests/fixtures/dtls/fuzz/fragment_length_mismatch.hex
test -f tests/fixtures/dtls/fuzz/reassembly_overlap.hex
test -f tests/fixtures/dtls/fuzz/reassembly_gap.hex
test -f src/webrtc_dtls_fuzz_test_main.uya

rg -Fq "DTLS fuzz corpus smoke passed" src/webrtc_dtls_fuzz_test_main.uya
rg -Fq "dtls_record_parse" src/webrtc_dtls_fuzz_test_main.uya
rg -Fq "dtls_handshake_fragment_parse" src/webrtc_dtls_fuzz_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_dtls_fuzz_test_main.uya
python3 tests/dtls_vectors.py
bash tests/check_phase8_dtls.sh
