#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/stun/fuzz
test -f tests/fixtures/stun/fuzz/truncated_header.hex
test -f tests/fixtures/stun/fuzz/bad_length.hex
test -f tests/fixtures/stun/fuzz/bad_padding.hex
test -f tests/fixtures/stun/fuzz/duplicate_username.hex
test -f tests/fixtures/stun/fuzz/unknown_required.hex
test -f src/webrtc_stun_fuzz_test_main.uya

rg -Fq "run_fuzz_corpus_smoke" tests/stun_vectors.py
rg -Fq "STUN fuzz corpus smoke passed" src/webrtc_stun_fuzz_test_main.uya
rg -Fq "stun_binding_request_validate_attribute" src/webrtc_stun_fuzz_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_stun_fuzz_test_main.uya
python3 tests/stun_vectors.py
bash tests/check_phase4_stun.sh
