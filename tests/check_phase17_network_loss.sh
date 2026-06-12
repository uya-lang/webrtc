#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_network_loss_sim_main.uya
test -f src/webrtc/rtp/jitter.uya

rg -q "export fn rtp_jitter_buffer_should_send_nack" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_jitter_buffer_fire_nack" src/webrtc/rtp/jitter.uya
rg -q "network loss simulation tests passed" src/webrtc_network_loss_sim_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_network_loss_sim_main.uya

echo "Phase 17 network loss simulation checks passed"
