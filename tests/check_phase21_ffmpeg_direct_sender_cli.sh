#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_ffmpeg_direct_sender_main.uya
test -f src/webrtc/media/direct_session.uya
test -f src/webrtc/media/direct_runtime.uya
test -f src/webrtc/dtls/identity.uya
test -f src/webrtc/dtls/server.uya
test -f src/webrtc_ffmpeg_direct_sender_session_test_main.uya
test -f src/webrtc_dtls_identity_test_main.uya
test -f src/webrtc_dtls_server_test_main.uya
test ! -e src/webrtc/media/direct_transport.uya
test ! -e tests/fixtures/direct_transport/direct_transport_shim.c
rg -Fq "uya_ffmpeg_direct_sender" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "rtp_packetize_encoded_frame" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "dtlsSrtpReady" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "use webrtc.peer_connection" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "pc.setRemoteChromeOffer" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "pc.createPassiveAnswer" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "pc.initDirectTransport" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "pc.directRuntime" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "pc.processSrtpPacket" src/webrtc_ffmpeg_direct_sender_main.uya
if rg -Fq "direct_session_parse_chrome_offer_sdp(" src/webrtc_ffmpeg_direct_sender_main.uya || rg -Fq "direct_session_write_passive_answer(" src/webrtc_ffmpeg_direct_sender_main.uya; then
	printf '%s\n' "FFmpeg Chrome sender must negotiate through PeerConnection methods" >&2
	exit 1
fi
rg -Fq "dtls_identity_fingerprint_sha256_text" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "run_live_sender" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_runtime_process_dtls_datagram" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_runtime_write_stun_binding_response" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_runtime_process_srtcp_feedback" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_sender_write_sender_report" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_sender_write_picture_loss_indication" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_sender_protect_srtcp_packet" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_sender_record_rtcp_feedback" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_sender_record_srtp_packet_received" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_sender_record_inbound_video_frame" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "Vp8RtpReorderBuffer" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "vp8_rtp_reorder_buffer_push" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "vp8_rtp_reorder_buffer_pop_ready" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "CLI_VIDEO_REORDER_MAX_WAIT_US" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "video_reorder_gap_wait_start_us" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "cli_maybe_send_video_pli" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "ffmpeg_direct_sender_encode_opus_rtp" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "ffmpeg_codec_encode_video_i420_to_frame" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "cli_http_request" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "read_offer_json" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "post_answer_json" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "cli_v4l2_capture_read_i420" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--raw-video-i420" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--raw-audio-s16le" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--offer-url" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--answer-url" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--local-host" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--v4l2-device" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--v4l2-format" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--v4l2-test-frames" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--video-width" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--video-height" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--media-duration-us" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--video-frame-duration-us" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "read_exact_looping" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "open_optional_read_fd" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "rtp_packetize_encoded_frame_fragment" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "direct_sender_vp8_max_fragment_payload_bytes" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "encoded_bytes" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "media_duration_us" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq -- "--codec ffmpeg|uya" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "codec_provider_ffmpeg_make" src/webrtc_ffmpeg_direct_sender_main.uya
rg -Fq "codec_provider_uya_make" src/webrtc_ffmpeg_direct_sender_main.uya
if rg -Fq "CLI_MAX_VIDEO_WIDTH" src/webrtc_ffmpeg_direct_sender_main.uya || rg -Fq "CLI_MAX_VIDEO_HEIGHT" src/webrtc_ffmpeg_direct_sender_main.uya; then
	printf '%s\n' "direct sender must size raw preview video from the input MP4 dimensions instead of a fixed 1080p cap" >&2
	exit 1
fi
if rg -n "@c_import|extern fn uya_ffmpeg_codec_|extern \"libav|libavcodec|libavutil" src/webrtc_ffmpeg_direct_sender_main.uya; then
	printf '%s\n' "direct sender must import FFmpeg only through webrtc.media.ffmpeg_codec" >&2
	exit 1
fi
rg -Fq "direct_session_parse_chrome_offer_sdp" src/webrtc/media/direct_session.uya
rg -Fq "direct_session_write_passive_answer" src/webrtc/media/direct_session.uya
rg -Fq "direct_runtime_process_dtls_datagram" src/webrtc/media/direct_runtime.uya
rg -Fq "direct_runtime_write_stun_binding_response" src/webrtc/media/direct_runtime.uya
rg -Fq "direct_runtime_process_srtcp_feedback" src/webrtc/media/direct_runtime.uya
rg -Fq "dtls_identity_certificate_der" src/webrtc/dtls/identity.uya
rg -Fq "dtls_server_write_first_flight" src/webrtc/dtls/server.uya
rg -Fq "dtls_certificate_fingerprint_verify" src/webrtc_dtls_identity_test_main.uya
rg -Fq "crypto_p256_ecdsa_sign_with_k" src/webrtc_dtls_identity_test_main.uya
rg -Fq "Uya DTLS server first-flight/key-material/record-crypto tests passed" src/webrtc_dtls_server_test_main.uya
rg -Fq "Uya FFmpeg direct runtime STUN/DTLS/SRTP/SRTCP tests passed" src/webrtc_ffmpeg_direct_runtime_test_main.uya
rg -Fq "dtls_server_derive_srtp_key_material" src/webrtc/dtls/server.uya
rg -Fq "dtls_server_decrypt_aes_gcm_record" src/webrtc/dtls/server.uya

if rg -n "@c_import|extern fn|extern \"|export extern" src/webrtc/media/direct_session.uya src/webrtc/media/direct_runtime.uya src/webrtc/dtls/identity.uya src/webrtc/dtls/server.uya src/webrtc_ffmpeg_direct_sender_session_test_main.uya src/webrtc_ffmpeg_direct_runtime_test_main.uya src/webrtc_dtls_identity_test_main.uya src/webrtc_dtls_server_test_main.uya; then
	printf '%s\n' "direct sender session/DTLS identity path must stay pure Uya; extern is only allowed at the FFmpeg codec boundary" >&2
	exit 1
fi

../uya/bin/uya run src/webrtc_dtls_identity_test_main.uya
../uya/bin/uya run src/webrtc_dtls_server_test_main.uya
../uya/bin/uya run src/webrtc_ffmpeg_direct_sender_session_test_main.uya
../uya/bin/uya run src/webrtc_ffmpeg_direct_runtime_test_main.uya

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

cat >"$tmpdir/offer.json" <<'JSON'
{
  "type": "offer",
  "sdp": "v=0\r\no=- 548391 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=group:BUNDLE 0 1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\nc=IN IP4 0.0.0.0\r\na=mid:0\r\na=recvonly\r\na=ice-ufrag:chromeUfrag\r\na=ice-pwd:chromePwd012345678901234567\r\na=fingerprint:sha-256 00:11:22\r\na=setup:actpass\r\na=rtcp-mux\r\na=rtpmap:111 opus/48000/2\r\na=candidate:1 1 udp 2122260223 127.0.0.1 43123 typ host generation 0 ufrag chromeUfrag network-id 1\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\nc=IN IP4 0.0.0.0\r\na=mid:1\r\na=recvonly\r\na=ice-ufrag:chromeUfrag\r\na=ice-pwd:chromePwd012345678901234567\r\na=fingerprint:sha-256 00:11:22\r\na=setup:actpass\r\na=rtcp-mux\r\na=rtpmap:96 VP8/90000\r\na=candidate:2 1 UDP 2122260223 127.0.0.1 43124 typ host generation 0 ufrag chromeUfrag network-id 1\r\n"
}
JSON
printf '%s\n' 'ffmpeg encoded media placeholder' >"$tmpdir/media.webm"

../uya/bin/uya run src/webrtc_ffmpeg_direct_sender_main.uya -- \
	--offer-json "$tmpdir/offer.json" \
	--media "$tmpdir/media.webm" \
	--answer-json "$tmpdir/answer.json" \
	--diagnostics-json "$tmpdir/diagnostics.json" \
	--media-duration-us 1000000 \
	--video-frame-duration-us 66666 \
	--local-host 127.0.0.1 \
	--v4l2-device /dev/video0 \
	--v4l2-format yuyv \
	--codec ffmpeg \
	--dry-run

test -f "$tmpdir/diagnostics.json"
rg -Fq '"sender":"uya_ffmpeg_direct_sender"' "$tmpdir/diagnostics.json"
rg -Fq '"offerParsed":true' "$tmpdir/diagnostics.json"
rg -Fq '"audioMLine":true' "$tmpdir/diagnostics.json"
rg -Fq '"videoMLine":true' "$tmpdir/diagnostics.json"
rg -Fq '"codecProvider":"ffmpeg"' "$tmpdir/diagnostics.json"
rg -Fq '"codecProviderSwitchable":true' "$tmpdir/diagnostics.json"
rg -Fq '"codecProviderReady":true' "$tmpdir/diagnostics.json"
rg -Fq '"codecProviderUsesExtern":true' "$tmpdir/diagnostics.json"
rg -Fq '"codecBridgeRequired":false' "$tmpdir/diagnostics.json"
rg -Fq '"ffmpegMediaPathSeen":true' "$tmpdir/diagnostics.json"
rg -Fq '"uyaCodecPathReady":false' "$tmpdir/diagnostics.json"
rg -Fq '"uyaVp8VideoReady":false' "$tmpdir/diagnostics.json"
rg -Fq '"encodedVideoPathSeen":false' "$tmpdir/diagnostics.json"
rg -Fq '"rtpPacketizer":"rtp_packetize_encoded_frame"' "$tmpdir/diagnostics.json"
rg -Fq '"dtlsIdentityReady":true' "$tmpdir/diagnostics.json"
rg -Fq '"dtlsSrtpReady":false' "$tmpdir/diagnostics.json"
rg -Fq '"answerReady":true' "$tmpdir/diagnostics.json"
rg -Fq '"srtcpPackets":0' "$tmpdir/diagnostics.json"
rg -Fq '"rtcpSenderReports":0' "$tmpdir/diagnostics.json"
rg -Fq '"srtpPacketsReceived":0' "$tmpdir/diagnostics.json"
rg -Fq '"rtpPacketsReceived":0' "$tmpdir/diagnostics.json"
rg -Fq '"audioRtpPacketsReceived":0' "$tmpdir/diagnostics.json"
rg -Fq '"videoRtpPacketsReceived":0' "$tmpdir/diagnostics.json"
rg -Fq '"videoFramesReceived":0' "$tmpdir/diagnostics.json"
rg -Fq '"srtcpPacketsReceived":0' "$tmpdir/diagnostics.json"
rg -Fq '"rtcpPacketsReceived":0' "$tmpdir/diagnostics.json"
test -f "$tmpdir/answer.json"
rg -Fq '"type":"answer"' "$tmpdir/answer.json"
rg -Fq 'm=audio 9 UDP/TLS/RTP/SAVPF 111' "$tmpdir/answer.json"
rg -Fq 'm=video 9 UDP/TLS/RTP/SAVPF 96' "$tmpdir/answer.json"
rg -Fq 'a=ice-lite' "$tmpdir/answer.json"
rg -Fq 'a=setup:passive' "$tmpdir/answer.json"
rg -Fq 'a=fingerprint:sha-256 31:48:5F:0F:03:87:1A:59:FA:D4:1E:90:E6:47:E4:30:88:68:E8:38:F6:7C:15:9F:3D:61:01:A1:51:8D:BE:29' "$tmpdir/answer.json"

../uya/bin/uya run src/webrtc_ffmpeg_direct_sender_main.uya -- \
	--offer-json "$tmpdir/offer.json" \
	--media "$tmpdir/media.webm" \
	--answer-json "$tmpdir/uya_answer.json" \
	--diagnostics-json "$tmpdir/uya_diagnostics.json" \
	--media-duration-us 1000000 \
	--codec uya \
	--dry-run

test -f "$tmpdir/uya_diagnostics.json"
rg -Fq '"codecProvider":"uya"' "$tmpdir/uya_diagnostics.json"
rg -Fq '"codecProviderSwitchable":true' "$tmpdir/uya_diagnostics.json"
rg -Fq '"codecProviderReady":false' "$tmpdir/uya_diagnostics.json"
rg -Fq '"codecProviderUsesExtern":false' "$tmpdir/uya_diagnostics.json"
rg -Fq '"codecBridgeRequired":true' "$tmpdir/uya_diagnostics.json"
rg -Fq '"ffmpegMediaPathSeen":false' "$tmpdir/uya_diagnostics.json"
rg -Fq '"uyaCodecPathReady":false' "$tmpdir/uya_diagnostics.json"
rg -Fq '"uyaVp8VideoReady":false' "$tmpdir/uya_diagnostics.json"
rg -Fq '"encodedVideoPathSeen":false' "$tmpdir/uya_diagnostics.json"
test -f "$tmpdir/uya_answer.json"
rg -Fq '"type":"answer"' "$tmpdir/uya_answer.json"

echo "Phase 21 Uya FFmpeg direct sender CLI checks passed"
