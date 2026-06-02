#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/rtp/fuzz
test -f tests/fixtures/rtp/fuzz/rtp_minimal_valid.hex
test -f tests/fixtures/rtp/fuzz/rtp_csrc_extension_valid.hex
test -f tests/fixtures/rtp/fuzz/rtp_extension_truncated.hex
test -f tests/fixtures/rtp/fuzz/rtp_padding_overflow.hex
test -f tests/fixtures/rtp/fuzz/rtcp_sr_valid.hex
test -f tests/fixtures/rtp/fuzz/rtcp_rr_valid.hex
test -f tests/fixtures/rtp/fuzz/rtcp_nack_valid.hex
test -f tests/fixtures/rtp/fuzz/rtcp_pli_valid.hex
test -f tests/fixtures/rtp/fuzz/rtcp_length_overflow.hex
test -f tests/fixtures/rtp/fuzz/rtcp_truncated_header.hex
test -f src/webrtc_rtp_rtcp_fuzz_test_main.uya

rg -Fq "RTP/RTCP fuzz corpus smoke passed" src/webrtc_rtp_rtcp_fuzz_test_main.uya
rg -Fq "rtp_packet_parse" src/webrtc_rtp_rtcp_fuzz_test_main.uya
rg -Fq "rtcp_sender_report_parse" src/webrtc_rtp_rtcp_fuzz_test_main.uya

../uya/bin/uya run src/webrtc_rtp_rtcp_fuzz_test_main.uya
python3 tests/test_rtp_parser.py
bash tests/check_phase10_rtp.sh
