#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_ice_candidate_limits_test_main.uya
test -f src/webrtc/ice/agent.uya
test -f src/webrtc/ice/candidate.uya

rg -Fq "ICE candidate upper limit tests passed" src/webrtc_ice_candidate_limits_test_main.uya
rg -Fq "ICE_MAX_REMOTE_CANDIDATES" src/webrtc_ice_candidate_limits_test_main.uya
rg -Fq "ICE_MAX_CANDIDATE_PAIRS" src/webrtc_ice_candidate_limits_test_main.uya

../uya/bin/uya run src/webrtc_ice_candidate_limits_test_main.uya
bash tests/check_phase5_ice.sh
