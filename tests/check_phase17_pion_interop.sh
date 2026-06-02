#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -x tests/pion_interop.py
go version >/dev/null

python3 tests/pion_interop.py

echo "Phase 17 Pion WebRTC interop checks passed"
