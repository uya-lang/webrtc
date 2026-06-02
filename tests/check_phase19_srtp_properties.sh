#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_srtp_property_test_main.uya
test -f src/webrtc_srtp_replay_test_main.uya
test -f src/webrtc_srtp_index_test_main.uya
test -f tests/srtp_sequence_replay_tests.py
test -f tests/fixtures/srtp/rfc3711_vectors.json

rg -Fq "SRTP replay/rollover property tests passed" src/webrtc_srtp_property_test_main.uya
rg -Fq "srtp_index_guess" src/webrtc_srtp_property_test_main.uya
rg -Fq "srtp_replay_check" src/webrtc_srtp_property_test_main.uya

../uya/bin/uya run src/webrtc_srtp_property_test_main.uya
../uya/bin/uya run src/webrtc_srtp_index_test_main.uya
../uya/bin/uya run src/webrtc_srtp_replay_test_main.uya
python3 tests/srtp_sequence_replay_tests.py
bash tests/check_phase9_srtp.sh
