#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d src/webrtc/rtp
test -f src/webrtc/rtp/jitter.uya
test -f src/webrtc_rtp_jitter_test_main.uya
test -f benchmarks/bench_jitter.uya
test -f benchmarks/baselines/bench_jitter.jsonl
test -x tests/jitter_bench_baseline.py

rg -q "export struct RtpJitterBufferConfig" src/webrtc/rtp/jitter.uya
rg -q "export struct RtpJitterBuffer" src/webrtc/rtp/jitter.uya
rg -q "export struct RtpRetransmissionCache" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_jitter_buffer_config_make" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_jitter_buffer_make" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_jitter_buffer_push_packet" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_jitter_buffer_pop_ready_packet" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_jitter_buffer_build_nack" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_jitter_buffer_fire_nack" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_jitter_buffer_fire_pli" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_rtx_payload_wrap" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_rtx_payload_unwrap" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_retransmission_cache_store" src/webrtc/rtp/jitter.uya
rg -q "export fn rtp_retransmission_cache_lookup" src/webrtc/rtp/jitter.uya

python3 tests/jitter_bench_baseline.py
../uya/bin/uya run src/webrtc_rtp_jitter_test_main.uya

echo "Phase 12 jitter/NACK/PLI/RTX checks passed"
