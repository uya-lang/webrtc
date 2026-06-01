#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d src/webrtc/media
test -f src/webrtc/media/model.uya
test -f src/webrtc_media_model_test_main.uya

rg -q "export struct EncodedFrame" src/webrtc/media/model.uya
rg -q "export fn encoded_frame_make" src/webrtc/media/model.uya

../uya/bin/uya run src/webrtc_media_model_test_main.uya

echo "Phase 11 media model checks passed"
