#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/sctp/fuzz
test -f tests/fixtures/sctp/fuzz/README.md
test -f tests/fixtures/sctp/fuzz/sctp_minimal_cookie_ack.hex
test -f tests/fixtures/sctp/fuzz/sctp_truncated_header.hex
test -f tests/fixtures/sctp/fuzz/sctp_bad_chunk_length_too_small.hex
test -f tests/fixtures/sctp/fuzz/sctp_bad_chunk_length_overflow.hex
test -f src/webrtc_sctp_fuzz_test_main.uya

rg -Fq "SCTP fuzz corpus smoke passed" src/webrtc_sctp_fuzz_test_main.uya
rg -Fq "sctp_packet_parse" src/webrtc_sctp_fuzz_test_main.uya
rg -Fq "sctp_cookie_ack_chunk_parse" src/webrtc_sctp_fuzz_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_sctp_fuzz_test_main.uya
bash tests/check_phase13_sctp.sh
