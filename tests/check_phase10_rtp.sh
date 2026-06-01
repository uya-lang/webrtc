#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/rtp
test -f tests/fixtures/rtp/README.md
test -f tests/fixtures/rtp/parser_cases.json
test -x tests/test_rtp_parser.py

rg -q '"rtp_valid_packets"' tests/fixtures/rtp/parser_cases.json
rg -q '"rtp_invalid_packets"' tests/fixtures/rtp/parser_cases.json
rg -q '"extension_boundary_cases"' tests/fixtures/rtp/parser_cases.json
rg -q '"rtcp_valid_packets"' tests/fixtures/rtp/parser_cases.json
rg -q '"rtcp_invalid_packets"' tests/fixtures/rtp/parser_cases.json

python3 tests/test_rtp_parser.py

echo "Phase 10 RTP/RTCP parser fixture checks passed"
