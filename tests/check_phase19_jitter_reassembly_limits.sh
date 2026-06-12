#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_jitter_reassembly_limits_test_main.uya
test -f src/webrtc/rtp/jitter.uya
test -f src/webrtc/rtp/frame_queue.uya
test -f src/webrtc/receiver.uya

rg -Fq "JitterBuffer/reassembly memory limit tests passed" src/webrtc_jitter_reassembly_limits_test_main.uya
rg -Fq "RTP_JITTER_MAX_PACKETS" src/webrtc_jitter_reassembly_limits_test_main.uya
rg -Fq "RTP_JITTER_MAX_MISSING" src/webrtc_jitter_reassembly_limits_test_main.uya
rg -Fq "RTP_FRAME_OUTPUT_QUEUE_MAX_FRAMES" src/webrtc_jitter_reassembly_limits_test_main.uya
rg -Fq "RECEIVER_MAX_PENDING_FRAMES" src/webrtc_jitter_reassembly_limits_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_jitter_reassembly_limits_test_main.uya
bash tests/check_phase12_rtp.sh
