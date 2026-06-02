#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/sender.uya
test -f src/webrtc/receiver.uya
test -f src/webrtc_sender_receiver_test_main.uya

rg -q "export struct Sender" src/webrtc/sender.uya
rg -q "export fn sender_send_encoded_frame" src/webrtc/sender.uya
rg -q "export fn sender_pop_pending_frame" src/webrtc/sender.uya
rg -q "export struct Receiver" src/webrtc/receiver.uya
rg -q "export fn receiver_deliver_encoded_frame" src/webrtc/receiver.uya
rg -q "export fn receiver_read_encoded_frame" src/webrtc/receiver.uya
rg -q -F "fn main() i32" src/webrtc_sender_receiver_test_main.uya

../uya/bin/uya run src/webrtc_sender_receiver_test_main.uya

echo "Phase 14 sender/receiver checks passed"
