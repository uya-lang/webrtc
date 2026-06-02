#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

rg -Fq ".PHONY: all build test bench test-codec-bridge clean" Makefile
rg -Fq "test-codec-bridge:" Makefile
rg -Fq '$(MAKE) -C ../opus smoke' Makefile
rg -Fq '$(MAKE) -C ../vp8 build check-toolchain' Makefile
rg -Fq "bash tests/check_phase21_fixture_manifest.sh" Makefile
rg -Fq "bash tests/check_phase21_opus_bridge_api.sh" Makefile
rg -Fq "bash tests/check_phase21_vp8_bridge_api.sh" Makefile
