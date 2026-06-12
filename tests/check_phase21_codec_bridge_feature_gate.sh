#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/codec_bridge.uya
test -f src/webrtc_media_codec_bridge_test_main.uya

rg -Fq "export const CODEC_BRIDGE_FEATURE_DEFAULT_ENABLED: bool = false" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_feature_default_enabled" src/webrtc/media/codec_bridge.uya
rg -Fq "export fn codec_bridge_boundary_make_with_feature" src/webrtc/media/codec_bridge.uya
rg -Fq "codec_bridge_feature_default_enabled()" src/webrtc_media_codec_bridge_test_main.uya

transport_imports="$(
    rg -n "webrtc\\.media\\.codec_bridge|\\.\\./opus|\\.\\./vp8|libopus|libvpx|FFmpeg|ffmpeg" \
        src/webrtc/{arena,binary,dtls,ice,net,rtcp,rtp,sctp,sdp,srtp,stun,turn,congestion,stats} \
        src/webrtc/{runtime,peer_connection,receiver,sender,track}.uya \
        2>/dev/null || true
)"
if [[ -n "$transport_imports" ]]; then
    printf '%s\n' "$transport_imports" >&2
    exit 1
fi

"${UYA:-./uya/bin/uya}" run src/webrtc_media_codec_bridge_test_main.uya
bash tests/check_phase11_media.sh
