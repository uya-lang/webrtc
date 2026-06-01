#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/sctp
test -d tests/fixtures/sctp/fuzz
test -f tests/fixtures/sctp/README.md
test -f tests/fixtures/sctp/fuzz/README.md
test -f tests/fixtures/sctp/parser_cases.json
test -f tests/fixtures/sctp/fuzz/sctp_minimal_cookie_ack.hex
test -f tests/fixtures/sctp/fuzz/sctp_truncated_header.hex
test -f tests/fixtures/sctp/fuzz/sctp_bad_chunk_length_too_small.hex
test -f tests/fixtures/sctp/fuzz/sctp_bad_chunk_length_overflow.hex
test -f src/webrtc/sctp/model.uya
test -f src/webrtc_sctp_packet_test_main.uya
test -f src/webrtc/sctp/dcep.uya
test -f src/webrtc_sctp_dcep_test_main.uya
test -f src/webrtc_sctp_model_test_main.uya
test -f src/webrtc/sctp/tsn.uya
test -f src/webrtc_sctp_tsn_test_main.uya
test -f src/webrtc/sctp/retransmit.uya
test -f src/webrtc_sctp_retransmit_test_main.uya

rg -q "export struct SctpPacket" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_packet_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_packet_write" src/webrtc/sctp/packet.uya
rg -q "export struct SctpInitChunk" src/webrtc/sctp/packet.uya
rg -q "export struct SctpInitAckChunk" src/webrtc/sctp/packet.uya
rg -q "export struct SctpCookieEchoChunk" src/webrtc/sctp/packet.uya
rg -q "export struct SctpCookieAckChunk" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_init_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_init_ack_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_cookie_echo_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_cookie_ack_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_init_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_init_ack_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_cookie_echo_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_cookie_ack_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export struct SctpHeartbeatChunk" src/webrtc/sctp/packet.uya
rg -q "export struct SctpHeartbeatAckChunk" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_heartbeat_chunk_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_heartbeat_ack_chunk_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_heartbeat_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_heartbeat_ack_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_heartbeat_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_heartbeat_ack_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export struct SctpAbortChunk" src/webrtc/sctp/packet.uya
rg -q "export struct SctpShutdownChunk" src/webrtc/sctp/packet.uya
rg -q "export struct SctpShutdownAckChunk" src/webrtc/sctp/packet.uya
rg -q "export struct SctpShutdownCompleteChunk" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_abort_chunk_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_chunk_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_ack_chunk_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_complete_chunk_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_abort_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_ack_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_complete_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_abort_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_ack_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_shutdown_complete_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export const SCTP_DATA_CHUNK_FLAG_UNORDERED" src/webrtc/sctp/packet.uya
rg -q "export const SCTP_SACK_MAX_GAP_ACK_BLOCKS" src/webrtc/sctp/packet.uya
rg -q "export const SCTP_SACK_MAX_DUPLICATE_TSNS" src/webrtc/sctp/packet.uya
rg -q "export struct SctpSackGapAckBlock" src/webrtc/sctp/packet.uya
rg -q "export struct SctpSackChunk" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_sack_gap_ack_block_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_sack_chunk_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_sack_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_sack_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export struct SctpDataChunk" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_data_chunk_make" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_data_chunk_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_data_chunk_write" src/webrtc/sctp/packet.uya
rg -q "export const SCTP_DATA_CHANNEL_DEFAULT_REASSEMBLY_CAP_BYTES" src/webrtc/sctp/model.uya
rg -q "export struct SctpDataChannelInit" src/webrtc/sctp/model.uya
rg -q "export struct SctpDataChannelReassemblyBudget" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_init_make" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_init_reliability_mode" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_reassembly_budget_make" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_reassembly_budget_reserve" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_reassembly_budget_release" src/webrtc/sctp/model.uya
rg -q "export struct SctpTsnOutstandingEntry" src/webrtc/sctp/tsn.uya
rg -q "export struct SctpTsnTracker" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_make" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_reset" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_set_initial_tsn" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_next_send_tsn" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_track_outstanding" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_ack_outstanding_tsn" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_record_received" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_build_sack" src/webrtc/sctp/tsn.uya
rg -q "export fn sctp_tsn_tracker_acknowledge_sack" src/webrtc/sctp/tsn.uya
rg -q "export struct SctpRetransmissionTimer" src/webrtc/sctp/retransmit.uya
rg -q "export fn sctp_retransmission_timer_make" src/webrtc/sctp/retransmit.uya
rg -q "export fn sctp_retransmission_timer_reset" src/webrtc/sctp/retransmit.uya
rg -q "export fn sctp_retransmission_timer_start" src/webrtc/sctp/retransmit.uya
rg -q "export fn sctp_retransmission_timer_stop" src/webrtc/sctp/retransmit.uya
rg -q "export fn sctp_retransmission_timer_should_fire" src/webrtc/sctp/retransmit.uya
rg -q "export fn sctp_retransmission_timer_fire" src/webrtc/sctp/retransmit.uya
rg -q "export struct SctpDcepOpenMessage" src/webrtc/sctp/dcep.uya
rg -q "export struct SctpDcepAckMessage" src/webrtc/sctp/dcep.uya
rg -q "export fn sctp_dcep_open_parse" src/webrtc/sctp/dcep.uya
rg -q "export fn sctp_dcep_open_write" src/webrtc/sctp/dcep.uya
rg -q "export fn sctp_dcep_ack_parse" src/webrtc/sctp/dcep.uya
rg -q "export fn sctp_dcep_ack_write" src/webrtc/sctp/dcep.uya

python3 - <<'PY'
from pathlib import Path
import json

fixture_path = Path("tests/fixtures/sctp/parser_cases.json")
fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
assert fixture["description"].startswith("Phase 13 SCTP"), fixture["description"]
assert fixture["valid_packets"][0]["name"] == "minimal_cookie_ack"
assert fixture["invalid_packets"][0]["error"] == "SctpPacketTooSmall"
PY

../uya/bin/uya run src/webrtc_sctp_packet_test_main.uya
../uya/bin/uya run src/webrtc_sctp_dcep_test_main.uya
../uya/bin/uya run src/webrtc_sctp_model_test_main.uya
../uya/bin/uya run src/webrtc_sctp_tsn_test_main.uya
../uya/bin/uya run src/webrtc_sctp_retransmit_test_main.uya

echo "Phase 13 SCTP parser checks passed"
