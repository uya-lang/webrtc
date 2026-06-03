# Phase 21 FFmpeg Extern Codec Ingest Walkthrough

## What Changed

- Added an explicit FFmpeg extern codec path for Uya sender tests.
- `PCM/s16le -> Opus EncodedFrame -> rtp_packetize_encoded_frame` is covered.
- `I420 -> VP8 EncodedFrame -> rtp_packetize_encoded_frame` is covered.
- Added decoder verification helpers for `Opus/VP8 EncodedFrame -> PCM/I420`, so future pure Uya encoder/decoder work can A/B against FFmpeg.
- Kept FFmpeg behind the explicit `test-ffmpeg-codec-extern` gate; the default encoded-frame direct sender test still does not link FFmpeg.

## Main Files

- `src/webrtc/media/ffmpeg_codec.uya`: FFmpeg encoder/decoder session wrappers and raw/encoded frame conversion APIs.
- `src/webrtc/media/ffmpeg_direct_ingest.uya`: sender-facing ingest adapter that encodes raw frames and immediately packetizes the resulting `EncodedFrame`.
- `tests/fixtures/ffmpeg_codec/ffmpeg_codec_shim.c`: explicit libavcodec/libavutil C shim used only by the FFmpeg extern test.
- `src/webrtc_ffmpeg_codec_boundary_test_main.uya`: runtime coverage for Opus ingest, VP8 ingest, and decoder verification.
- `tests/check_phase21_ffmpeg_codec_extern.sh`: prepares local FFmpeg dev headers/linker symlinks without sudo and runs the extern codec gate.

## Validation

- `make test-ffmpeg-codec-extern` passed.
- `bash tests/check_phase21_ffmpeg_direct_sender.sh` passed.
- `bash tests/check_phase21_ffmpeg_direct_sender_cli.sh` passed.

## Remaining Risks

- Full Chrome inbound media push still depends on the following existing TODO items: Chrome host ICE/STUN, DTLS-SRTP exporter, SRTP/SRTCP protect, and UDP send.
- `test-ffmpeg-codec-extern` downloads `libavcodec-dev` and `libavutil-dev` with `apt download` when headers are not installed, then uses the system runtime libraries already present on the machine.
