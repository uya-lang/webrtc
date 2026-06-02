#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f tests/browser_datachannel_interop.py

python3 tests/browser_datachannel_interop.py h264

echo "Phase 17 browser H264 interop checks passed"
