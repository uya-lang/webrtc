#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

rg -Fq ".PHONY: all build test bench test-codec-bridge test-ffmpeg-codec-flow test-ffmpeg-codec-extern test-ffmpeg-chrome-call preview-ffmpeg-chrome-call clean" Makefile
rg -Fq "test-codec-bridge:" Makefile
rg -Fq "test-ffmpeg-codec-flow:" Makefile
rg -Fq "test-ffmpeg-codec-extern:" Makefile
rg -Fq "test-ffmpeg-chrome-call:" Makefile
rg -Fq "preview-ffmpeg-chrome-call:" Makefile
rg -Fq -- '--source-mp4 "$(MP4)"' Makefile
rg -Fq '$(MAKE) -C ../opus smoke' Makefile
rg -Fq '$(MAKE) -C ../vp8 build check-toolchain' Makefile
rg -Fq "bash tests/check_phase21_fixture_manifest.sh" Makefile
rg -Fq "bash tests/check_phase21_opus_bridge_api.sh" Makefile
rg -Fq "bash tests/check_phase21_vp8_bridge_api.sh" Makefile
rg -Fq "bash tests/check_phase21_ffmpeg_codec_extern.sh" Makefile
rg -Fq "bash tests/check_phase21_ffmpeg_chrome_call.sh" Makefile
