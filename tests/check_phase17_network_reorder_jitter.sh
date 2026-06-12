#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_network_reorder_jitter_main.uya
test -f src/webrtc/rtp/jitter.uya

rg -q "rtp_jitter_buffer_push_packet" src/webrtc_network_reorder_jitter_main.uya
rg -q "rtp_jitter_buffer_fire_pli" src/webrtc_network_reorder_jitter_main.uya
rg -q "network reorder/duplicate/jitter simulation tests passed" src/webrtc_network_reorder_jitter_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_network_reorder_jitter_main.uya

echo "Phase 17 network reorder/duplicate/jitter simulation checks passed"
