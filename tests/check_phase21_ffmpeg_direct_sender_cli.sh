#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "uya_ffmpeg_direct_sender" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "rtp_packetize_encoded_frame" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "dtlsSrtpReady" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "refusing to write a fake SDP answer" src/webrtc_ffmpeg_direct_sender_main.uya

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

cat >"$tmpdir/offer.json" <<'JSON'
{
  "type": "offer",
  "sdp": "v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=rtpmap:111 opus/48000/2\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=rtpmap:96 VP8/90000\r\n"
}
JSON
printf '%s\n' 'ffmpeg encoded media placeholder' >"$tmpdir/media.webm"

../uya/bin/uya run src/webrtc_ffmpeg_direct_sender_main.uya -- \
	--offer-json "$tmpdir/offer.json" \
	--media "$tmpdir/media.webm" \
	--answer-json "$tmpdir/answer.json" \
	--diagnostics-json "$tmpdir/diagnostics.json" \
	--dry-run

test -f "$tmpdir/diagnostics.json"
rg -Fq '"sender":"uya_ffmpeg_direct_sender"' "$tmpdir/diagnostics.json"
rg -Fq '"offerParsed":true' "$tmpdir/diagnostics.json"
rg -Fq '"audioMLine":true' "$tmpdir/diagnostics.json"
rg -Fq '"videoMLine":true' "$tmpdir/diagnostics.json"
rg -Fq '"rtpPacketizer":"rtp_packetize_encoded_frame"' "$tmpdir/diagnostics.json"
rg -Fq '"dtlsSrtpReady":false' "$tmpdir/diagnostics.json"
test ! -f "$tmpdir/answer.json"

echo "Phase 21 Uya FFmpeg direct sender CLI checks passed"
