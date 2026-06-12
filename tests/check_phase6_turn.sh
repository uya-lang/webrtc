#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

run_turn_main_with_codegen_fallback() {
    local run_log
    run_log="$(mktemp)"
    if "${UYA:-./uya/bin/uya}" run src/webrtc_turn_test_main.uya >"$run_log" 2>&1; then
        rm -f "$run_log"
        return 0
    fi

    if ! rg -q "AsyncFrameDescriptorTable" "$run_log"; then
        cat "$run_log" >&2
        rm -f "$run_log"
        return 1
    fi

    local tmp_c tmp_bin
    tmp_c="$(mktemp /tmp/webrtc-turn-test-XXXXXX.c)"
    tmp_bin="$(mktemp /tmp/webrtc-turn-test-bin-XXXXXX)"
    trap 'rm -f "$run_log" "$tmp_c" "$tmp_bin"' RETURN

    if ! "${UYA:-./uya/bin/uya}" build src/webrtc_turn_test_main.uya --c99 -o "$tmp_c" >/dev/null 2>&1; then
        cat "$run_log" >&2
        return 1
    fi

    python3 - "$tmp_c" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
source = path.read_text()
marker = "struct AsyncFrameDescriptorTable _uya_async_frame_descriptors = {"

if marker in source and "struct AsyncFrameDescriptorTable {" not in source:
    patch = (
        "struct AsyncFrameDescriptorEntry {\n"
        "    int32_t a;\n"
        "    int32_t b;\n"
        "    void* c;\n"
        "};\n"
        "struct AsyncFrameDescriptorTable {\n"
        "    struct AsyncFrameDescriptorEntry entries[256];\n"
        "};\n"
    )
    source = source.replace(
        "// Async frame descriptors (for unified AsyncFramePool)\n",
        patch + "// Async frame descriptors (for unified AsyncFramePool)\n",
        1,
    )
    path.write_text(source)
PY

    if ! cc -std=c99 -O0 -g -fno-builtin "$tmp_c" -o "$tmp_bin"; then
        cat "$run_log" >&2
        return 1
    fi

    "$tmp_bin"
}

test -f src/webrtc_turn_test_main.uya
test -f src/webrtc_turn_coturn_test_main.uya
test -d src/webrtc/turn
test -f src/webrtc/turn/auth.uya
test -f src/webrtc/turn/allocation.uya
test -f src/webrtc/turn/model.uya
test -f src/webrtc/turn/parse.uya
test -f src/webrtc/turn/write.uya
test -x tests/check_phase6_turn_coturn.sh

rg -Fq "export const TURN_METHOD_ALLOCATE" src/webrtc/turn/model.uya
rg -Fq "export const TURN_ATTRIBUTE_REQUESTED_TRANSPORT" src/webrtc/turn/model.uya
rg -Fq "export const TURN_ERROR_UNAUTHORIZED" src/webrtc/turn/model.uya
rg -Fq "export struct TurnAllocateRequest" src/webrtc/turn/model.uya
rg -Fq "export struct TurnAllocateSuccessResponse" src/webrtc/turn/model.uya
rg -Fq "export struct TurnRefreshRequest" src/webrtc/turn/model.uya
rg -Fq "export struct TurnRefreshSuccessResponse" src/webrtc/turn/model.uya
rg -Fq "export struct TurnCreatePermissionRequest" src/webrtc/turn/model.uya
rg -Fq "export struct TurnCreatePermissionSuccessResponse" src/webrtc/turn/model.uya
rg -Fq "export struct TurnChannelBindRequest" src/webrtc/turn/model.uya
rg -Fq "export struct TurnChannelBindSuccessResponse" src/webrtc/turn/model.uya
rg -Fq "export struct TurnSendIndication" src/webrtc/turn/model.uya
rg -Fq "export struct TurnDataIndication" src/webrtc/turn/model.uya
rg -Fq "export struct TurnAuthenticationChallenge" src/webrtc/turn/model.uya
rg -Fq "export struct TurnLongTermCredentials" src/webrtc/turn/model.uya

rg -Fq "export fn turn_long_term_credentials_init_from_challenge" src/webrtc/turn/auth.uya
rg -Fq "export fn turn_long_term_credentials_apply_stale_nonce" src/webrtc/turn/auth.uya
rg -Fq "export fn turn_long_term_credentials_is_ready" src/webrtc/turn/auth.uya
rg -Fq "export struct TurnAllocationState" src/webrtc/turn/allocation.uya
rg -Fq "export fn turn_allocation_state_make" src/webrtc/turn/allocation.uya
rg -Fq "export fn turn_allocation_state_apply_allocate_success" src/webrtc/turn/allocation.uya
rg -Fq "export fn turn_allocation_state_apply_refresh_success" src/webrtc/turn/allocation.uya
rg -Fq "export fn turn_allocation_state_mark_refresh_sent" src/webrtc/turn/allocation.uya
rg -Fq "export fn turn_allocation_state_mark_refresh_retry" src/webrtc/turn/allocation.uya
rg -Fq "export fn turn_allocation_state_tick" src/webrtc/turn/allocation.uya
rg -Fq "export fn turn_parse_realm" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_parse_nonce" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_send_indication_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_data_indication_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_refresh_request_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_refresh_success_response_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_create_permission_request_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_create_permission_success_response_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_parse_channel_number" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_channel_bind_request_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_channel_bind_success_response_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_parse_requested_transport" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_parse_lifetime" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_allocate_request_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_allocate_success_response_parse" src/webrtc/turn/parse.uya
rg -Fq "export fn turn_authentication_challenge_parse" src/webrtc/turn/parse.uya

rg -Fq "export fn turn_builder_init_refresh_request" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_refresh_success_response" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_refresh_error_response" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_create_permission_request" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_create_permission_success_response" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_create_permission_error_response" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_channel_bind_request" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_channel_bind_success_response" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_channel_bind_error_response" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_send_indication" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_data_indication" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_allocate_request" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_init_allocate_success_response" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_requested_transport_udp" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_channel_number" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_xor_relayed_address_ipv4" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_xor_peer_address_ipv4" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_xor_peer_address_ipv6" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_data" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_realm" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_nonce" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_append_long_term_credentials" src/webrtc/turn/write.uya
rg -Fq "export fn turn_builder_finish" src/webrtc/turn/write.uya

rg -Fq "turn_test_check_allocate_request_roundtrip" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_allocate_success_response_roundtrip" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_allocate_invalid_paths" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_long_term_credentials_roundtrip" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_long_term_challenge_invalid_paths" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_refresh_roundtrip" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_refresh_invalid_paths" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_create_permission_roundtrip" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_create_permission_invalid_paths" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_channel_bind_roundtrip" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_channel_bind_invalid_paths" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_allocation_refresh_timer_schedules_before_expiry" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_allocation_refresh_timer_retry_and_expiry" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_send_data_indication_roundtrip" src/webrtc_turn_test_main.uya
rg -Fq "turn_test_check_send_data_indication_invalid_paths" src/webrtc_turn_test_main.uya
rg -Fq "turn_coturn_test_run" src/webrtc_turn_coturn_test_main.uya

run_turn_main_with_codegen_fallback
bash tests/check_phase6_turn_coturn.sh
