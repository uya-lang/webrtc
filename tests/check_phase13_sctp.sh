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

rg -q "export struct SctpPacket" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_packet_parse" src/webrtc/sctp/packet.uya
rg -q "export fn sctp_packet_write" src/webrtc/sctp/packet.uya
rg -q "export const SCTP_DATA_CHANNEL_DEFAULT_REASSEMBLY_CAP_BYTES" src/webrtc/sctp/model.uya
rg -q "export struct SctpDataChannelInit" src/webrtc/sctp/model.uya
rg -q "export struct SctpDataChannelReassemblyBudget" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_init_make" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_init_reliability_mode" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_reassembly_budget_make" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_reassembly_budget_reserve" src/webrtc/sctp/model.uya
rg -q "export fn sctp_data_channel_reassembly_budget_release" src/webrtc/sctp/model.uya
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

echo "Phase 13 SCTP parser checks passed"
