#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/congestion/pacer.uya
test -f src/webrtc_congestion_pacer_test_main.uya

rg -q "export struct PacerQueueConfig" src/webrtc/congestion/pacer.uya
rg -q "export struct PacerPacket" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_queue_make" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_queue_push" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_queue_pop_ready_packet" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_queue_p95_delay_us" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_queue_p99_delay_us" src/webrtc/congestion/pacer.uya
rg -q "export struct PacerTransportWideSeqAllocator" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_transport_wide_seq_allocator_make" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_transport_wide_seq_allocator_init" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_transport_wide_seq_allocator_next" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_packet_record_send_time" src/webrtc/congestion/pacer.uya
rg -q "export struct PacerTransportCcFeedback" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_transport_cc_feedback_parse" src/webrtc/congestion/pacer.uya
rg -q "export struct PacerDelayBasedEstimator" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_delay_based_estimator_make" src/webrtc/congestion/pacer.uya
rg -q "export fn pacer_delay_based_estimator_update" src/webrtc/congestion/pacer.uya

../uya/bin/uya run src/webrtc_congestion_pacer_test_main.uya

echo "Phase 15 pacer queue checks passed"
