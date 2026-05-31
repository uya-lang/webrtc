#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

rg -q "bash tests/check_phase2_udp.sh" Makefile
rg -q "bash tests/check_phase3_sdp.sh" Makefile
