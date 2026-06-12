#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/runtime.uya
test -f src/webrtc_rtc_runtime_test_main.uya

rg -q "export struct IceServer" src/webrtc/runtime.uya
rg -q "export struct RtcConfiguration" src/webrtc/runtime.uya
rg -q "export struct RtcRuntime" src/webrtc/runtime.uya
rg -q "export fn rtc_configuration_make" src/webrtc/runtime.uya
rg -q "export fn rtc_configuration_validate" src/webrtc/runtime.uya
rg -q "export fn rtc_runtime_init" src/webrtc/runtime.uya
rg -q "export fn rtc_runtime_register_peer_connection" src/webrtc/runtime.uya
rg -q "export fn rtc_runtime_unregister_peer_connection" src/webrtc/runtime.uya
rg -q -F "fn main() i32" src/webrtc_rtc_runtime_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_rtc_runtime_test_main.uya

echo "Phase 14 RtcRuntime checks passed"
