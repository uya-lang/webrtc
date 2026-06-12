#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/track.uya
test -f src/webrtc_track_test_main.uya

rg -q "export struct Track" src/webrtc/track.uya
rg -q "export fn track_write_encoded_frame" src/webrtc/track.uya
rg -q "export fn track_read_encoded_frame" src/webrtc/track.uya
rg -q -F "fn main() i32" src/webrtc_track_test_main.uya

"${UYA:-./uya/bin/uya}" run src/webrtc_track_test_main.uya

echo "Phase 14 track checks passed"
