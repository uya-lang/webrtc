#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Check SRTP module files exist
test -d src/webrtc/srtp
test -f src/webrtc/srtp/model.uya
test -f src/webrtc/srtp/srtp.uya
test -f src/webrtc/srtp/protect.uya

# Check fixtures
test -f tests/fixtures/srtp/rfc3711_vectors.json
test -x tests/srtp_vectors.py
test -x tests/srtp_sequence_replay_tests.py
test -f benchmarks/baselines/bench_srtp.jsonl
test -x tests/srtp_bench_baseline.py

# Validate vectors
python3 tests/srtp_vectors.py
python3 tests/srtp_sequence_replay_tests.py
python3 tests/srtp_bench_baseline.py

# Check key exports
rg -q "export struct SrtpContext" src/webrtc/srtp/model.uya
rg -q "export struct SrtcpContext" src/webrtc/srtp/model.uya
rg -q "export fn srtp_context_init" src/webrtc/srtp/model.uya
rg -q "export fn srtcp_context_init" src/webrtc/srtp/model.uya
rg -q "export fn srtp_derive_session_keys" src/webrtc/srtp/srtp.uya
rg -q "export fn srtcp_derive_session_keys" src/webrtc/srtp/srtp.uya
rg -q "export fn srtp_index_guess" src/webrtc/srtp/srtp.uya
rg -q "export fn srtp_replay_check" src/webrtc/srtp/srtp.uya
rg -q "export fn srtp_protect" src/webrtc/srtp/protect.uya
rg -q "export fn srtp_unprotect" src/webrtc/srtp/protect.uya

# Check constants
rg -q "SRTP_PROFILE_AES128_CM_HMAC_SHA1_80" src/webrtc/srtp/model.uya
rg -q "SRTP_PROFILE_AES128_CM_HMAC_SHA1_32" src/webrtc/srtp/model.uya
rg -q "SRTP_KEY_BYTES" src/webrtc/srtp/model.uya
rg -q "SRTP_SALT_BYTES" src/webrtc/srtp/model.uya

echo "Phase 9 SRTP checks passed"
