#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/rtp
test -f tests/fixtures/rtp/README.md
test -f tests/fixtures/rtp/parser_cases.json
test -x tests/test_rtp_parser.py
test -f src/webrtc/rtp/rtp_packet.uya
test -f src/webrtc/rtp/rtp_extension.uya
test -f src/webrtc/rtp/rtp_common_extensions.uya
test -f src/webrtc/rtp/rtp_sender.uya
test -f src/webrtc/rtp/rtp_receiver_route.uya
test -f src/webrtc/rtcp/rtcp_packet.uya
test -f src/webrtc_rtp_packet_test_main.uya
test -f src/webrtc_rtp_extension_test_main.uya
test -f src/webrtc_rtp_common_extensions_test_main.uya
test -f src/webrtc_rtp_sender_test_main.uya
test -f src/webrtc_rtp_receiver_route_test_main.uya
test -f src/webrtc_rtcp_packet_test_main.uya
test -f benchmarks/baselines/bench_rtp_rtcp_parse.jsonl
test -x tests/rtp_bench_baseline.py

rg -q '"rtp_valid_packets"' tests/fixtures/rtp/parser_cases.json
rg -q '"rtp_invalid_packets"' tests/fixtures/rtp/parser_cases.json
rg -q '"extension_boundary_cases"' tests/fixtures/rtp/parser_cases.json
rg -q '"rtcp_valid_packets"' tests/fixtures/rtp/parser_cases.json
rg -q '"rtcp_invalid_packets"' tests/fixtures/rtp/parser_cases.json
rg -q "export fn rtp_packet_parse" src/webrtc/rtp/rtp_packet.uya
rg -q "export fn rtp_packet_write" src/webrtc/rtp/rtp_packet.uya
rg -q "export fn rtp_header_size" src/webrtc/rtp/rtp_packet.uya
rg -q "export fn rtp_extension_parse_one_byte" src/webrtc/rtp/rtp_extension.uya
rg -q "export fn rtp_extension_write_one_byte" src/webrtc/rtp/rtp_extension.uya
rg -q "export fn rtp_extension_parse_two_byte" src/webrtc/rtp/rtp_extension.uya
rg -q "export fn rtp_extension_write_two_byte" src/webrtc/rtp/rtp_extension.uya
rg -q "export fn rtp_extension_mid_parse" src/webrtc/rtp/rtp_common_extensions.uya
rg -q "export fn rtp_extension_mid_write" src/webrtc/rtp/rtp_common_extensions.uya
rg -q "export fn rtp_extension_abs_send_time_parse" src/webrtc/rtp/rtp_common_extensions.uya
rg -q "export fn rtp_extension_abs_send_time_write" src/webrtc/rtp/rtp_common_extensions.uya
rg -q "export fn rtp_extension_transport_seq_num_parse" src/webrtc/rtp/rtp_common_extensions.uya
rg -q "export fn rtp_extension_transport_seq_num_write" src/webrtc/rtp/rtp_common_extensions.uya
rg -q "export fn rtp_sender_state_init" src/webrtc/rtp/rtp_sender.uya
rg -q "export fn rtp_sender_stamp_packet" src/webrtc/rtp/rtp_sender.uya
rg -q "export fn rtp_sender_advance_timestamp_by_duration_ns" src/webrtc/rtp/rtp_sender.uya
rg -q "export fn rtp_receiver_route_add" src/webrtc/rtp/rtp_receiver_route.uya
rg -q "export fn rtp_receiver_route_resolve" src/webrtc/rtp/rtp_receiver_route.uya
rg -q "export fn rtcp_sender_report_parse" src/webrtc/rtcp/rtcp_packet.uya
rg -q "export fn rtcp_sender_report_write" src/webrtc/rtcp/rtcp_packet.uya
rg -q "export fn rtcp_receiver_report_parse" src/webrtc/rtcp/rtcp_packet.uya
rg -q "export fn rtcp_receiver_report_write" src/webrtc/rtcp/rtcp_packet.uya
rg -q "export fn rtcp_sdes_parse" src/webrtc/rtcp/rtcp_packet.uya
rg -q "export fn rtcp_sdes_write" src/webrtc/rtcp/rtcp_packet.uya
rg -q "export fn rtcp_bye_parse" src/webrtc/rtcp/rtcp_packet.uya
rg -q "export fn rtcp_bye_write" src/webrtc/rtcp/rtcp_packet.uya
rg -q "export fn rtcp_report_rtt_ms" src/webrtc/rtcp/rtcp_packet.uya
rg -q '"bench_rtp_parse"' benchmarks/baselines/bench_rtp_rtcp_parse.jsonl
rg -q '"bench_rtp_extension_parse"' benchmarks/baselines/bench_rtp_rtcp_parse.jsonl
rg -q '"bench_rtcp_parse"' benchmarks/baselines/bench_rtp_rtcp_parse.jsonl

python3 tests/test_rtp_parser.py
python3 tests/rtp_bench_baseline.py
../uya/bin/uya run src/webrtc_rtp_packet_test_main.uya
../uya/bin/uya run src/webrtc_rtp_extension_test_main.uya
../uya/bin/uya run src/webrtc_rtp_common_extensions_test_main.uya
../uya/bin/uya run src/webrtc_rtp_sender_test_main.uya
../uya/bin/uya run src/webrtc_rtp_receiver_route_test_main.uya
../uya/bin/uya run src/webrtc_rtcp_packet_test_main.uya

echo "Phase 10 RTP/RTCP parser fixture checks passed"
