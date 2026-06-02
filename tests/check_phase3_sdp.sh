#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/sdp
test -f tests/fixtures/sdp/chrome_offer.sdp
test -f tests/fixtures/sdp/firefox_offer.sdp
test -f tests/fixtures/sdp/README.md
test -f src/webrtc/sdp/model.uya
test -f src/webrtc/sdp/parse.uya
test -f src/webrtc/sdp/write.uya
test -f src/webrtc/sdp/jsep.uya
test -f benchmarks/bench_sdp_parse.uya
test -f benchmarks/baselines/bench_sdp_parse.jsonl
test -x tests/sdp_fixture_roundtrip.py
test -x tests/sdp_bench_baseline.py

rg -Fq "def run_roundtrip_test" tests/sdp_fixture_roundtrip.py
rg -Fq "def run_error_tests" tests/sdp_fixture_roundtrip.py
rg -Fq 'run_roundtrip_test("chrome_offer.sdp")' tests/sdp_fixture_roundtrip.py
rg -Fq 'run_roundtrip_test("firefox_offer.sdp")' tests/sdp_fixture_roundtrip.py
rg -Fq '"MissingFingerprint"' tests/sdp_fixture_roundtrip.py
rg -Fq '"MissingIcePwd"' tests/sdp_fixture_roundtrip.py
rg -Fq '"MissingIceUfrag"' tests/sdp_fixture_roundtrip.py
rg -Fq '"MissingRtcpMux"' tests/sdp_fixture_roundtrip.py
rg -Fq '"UnsupportedCapability"' tests/sdp_fixture_roundtrip.py
rg -Fq "SUPPORTED_VP8_FMTP" tests/sdp_fixture_roundtrip.py

rg -Fq "export struct SessionDescription" src/webrtc/sdp/model.uya
rg -Fq "export struct MediaSection" src/webrtc/sdp/model.uya
rg -Fq "export struct CodecParameters" src/webrtc/sdp/model.uya
rg -Fq "export struct HeaderExtension" src/webrtc/sdp/model.uya
rg -Fq "export fn sdp_line_scanner_next" src/webrtc/sdp/parse.uya
rg -Fq "export fn sdp_parse_session_description_bytes" src/webrtc/sdp/parse.uya
rg -Fq '"group:BUNDLE "' src/webrtc/sdp/parse.uya
rg -Fq '"rtcp-fb:"' src/webrtc/sdp/parse.uya
rg -Fq "export fn sdp_write_session_description" src/webrtc/sdp/write.uya
rg -Fq "a=sctp-port:" src/webrtc/sdp/write.uya
rg -Fq "export fn sdp_validate_webrtc_session" src/webrtc/sdp/jsep.uya
rg -Fq '"max-fs"' src/webrtc/sdp/jsep.uya
rg -Fq '"max-fr"' src/webrtc/sdp/jsep.uya
rg -Fq '"transport-cc"' src/webrtc/sdp/jsep.uya
rg -Fq "benchmark_main_emit_sdp_parse_jsonl" benchmarks/bench_sdp_parse.uya

python3 tests/sdp_fixture_roundtrip.py
python3 tests/sdp_bench_baseline.py
