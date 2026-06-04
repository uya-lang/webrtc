#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/media/direct_sender.uya
test -f src/webrtc/media/direct_runtime.uya
test -f src/webrtc_ffmpeg_direct_sender_test_main.uya
test -f src/webrtc_ffmpeg_direct_runtime_test_main.uya
rg -Fq "export struct UyaDirectSender" src/webrtc/media/direct_sender.uya
rg -Fq "export fn rtp_packetize_encoded_frame" src/webrtc/media/direct_sender.uya
rg -Fq "export fn rtp_packetize_encoded_frame_fragment" src/webrtc/media/direct_sender.uya
rg -Fq "export fn direct_sender_vp8_max_fragment_payload_bytes" src/webrtc/media/direct_sender.uya
rg -Fq "export fn direct_sender_protect_rtp_packet" src/webrtc/media/direct_sender.uya
rg -Fq "export fn direct_sender_write_sender_report" src/webrtc/media/direct_sender.uya
rg -Fq "export fn direct_sender_protect_srtcp_packet" src/webrtc/media/direct_sender.uya
rg -Fq "export fn direct_sender_record_rtcp_feedback" src/webrtc/media/direct_sender.uya
rg -Fq "export struct DirectRuntime" src/webrtc/media/direct_runtime.uya
rg -Fq "export fn direct_runtime_write_stun_binding_response" src/webrtc/media/direct_runtime.uya
rg -Fq "export fn direct_runtime_process_dtls_datagram" src/webrtc/media/direct_runtime.uya
rg -Fq "export fn direct_runtime_process_srtcp_feedback" src/webrtc/media/direct_runtime.uya
rg -Fq "webrtc.media.opus_rtp" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.media.vp8_rtp" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.rtp.rtp_packet" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.srtp.protect" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.srtp.srtcp" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.rtcp.rtcp_packet" src/webrtc/media/direct_sender.uya
rg -Fq "webrtc.stun.write" src/webrtc/media/direct_runtime.uya
rg -Fq "webrtc.dtls.server" src/webrtc/media/direct_runtime.uya
rg -Fq "webrtc.srtp.dtls_keys" src/webrtc/media/direct_runtime.uya
rg -Fq "webrtc.srtp.srtcp" src/webrtc/media/direct_runtime.uya
rg -Fq "webrtc.rtcp.rtcp_packet" src/webrtc/media/direct_runtime.uya
rg -Fq "Uya FFmpeg direct sender RTP/SRTCP packetizer tests passed" src/webrtc_ffmpeg_direct_sender_test_main.uya
rg -Fq "Uya FFmpeg direct runtime STUN/DTLS/SRTP/SRTCP tests passed" src/webrtc_ffmpeg_direct_runtime_test_main.uya
rg -Fq "direct_sender_protect_rtp_packet" src/webrtc_ffmpeg_direct_sender_test_main.uya
rg -Fq "check_vp8_frame_fragment_packetize" src/webrtc_ffmpeg_direct_sender_test_main.uya
rg -Fq "direct_sender_write_sender_report" src/webrtc_ffmpeg_direct_sender_test_main.uya
rg -Fq "direct_runtime_process_srtcp_feedback" src/webrtc_ffmpeg_direct_runtime_test_main.uya

if rg -n "@c_import|extern fn|extern \"|export extern" src/webrtc/media/direct_runtime.uya src/webrtc_ffmpeg_direct_runtime_test_main.uya; then
	printf '%s\n' "Direct runtime must stay pure Uya; only the FFmpeg codec boundary may use extern" >&2
	exit 1
fi

../uya/bin/uya run src/webrtc_ffmpeg_direct_sender_test_main.uya
../uya/bin/uya run src/webrtc_ffmpeg_direct_runtime_test_main.uya

echo "Phase 21 Uya FFmpeg direct sender RTP/SRTP packetizer checks passed"
