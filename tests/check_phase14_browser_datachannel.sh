#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f tests/browser_datachannel_interop.py
test -f tests/fixtures/dtls/browser_handshake.json
test -d tests/fixtures/dtls

python3 tests/browser_datachannel_interop.py

echo "Phase 14 browser DataChannel interop checks passed"
