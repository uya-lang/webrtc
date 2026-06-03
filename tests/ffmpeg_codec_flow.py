#!/usr/bin/env python3
"""Verify generic audio/video codec push-pull flow with FFmpeg codecs."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Iterable, TypeVar


FrameT = TypeVar("FrameT")
Encoder = TypeVar("Encoder")
Decoder = TypeVar("Decoder")


class SkipFlow(Exception):
    pass


class PushPullQueue(Generic[FrameT]):
    def __init__(self) -> None:
        self._items: list[FrameT] = []
        self.pushed = 0
        self.pulled = 0
        self.high_watermark = 0

    def push(self, item: FrameT) -> None:
        self._items.append(item)
        self.pushed += 1
        self.high_watermark = max(self.high_watermark, len(self._items))

    def pull(self) -> FrameT:
        if not self._items:
            raise AssertionError("pull from empty queue")
        self.pulled += 1
        return self._items.pop(0)

    def drain(self) -> list[FrameT]:
        out: list[FrameT] = []
        while self._items:
            out.append(self.pull())
        return out

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True)
class AudioRawFrame:
    sequence_id: int
    timestamp: int
    duration_us: int
    sample_rate_hz: int
    channels: int
    samples_per_channel: int
    pcm_s16le: bytes


@dataclass(frozen=True)
class VideoRawFrame:
    sequence_id: int
    timestamp: int
    duration_us: int
    width: int
    height: int
    i420: bytes


@dataclass(frozen=True)
class EncodedPacket:
    media_kind: str
    codec_name: str
    sequence_id: int
    pts_time: float | None
    duration_time: float | None
    size: int
    flags: str


@dataclass(frozen=True)
class EncodedStream:
    media_kind: str
    codec_name: str
    path: Path
    packets: PushPullQueue[EncodedPacket]


@dataclass(frozen=True)
class FFmpegAudioCodec:
    encoder_name: str = "libopus"
    decoder_codec: str = "opus"
    container: str = "ogg"


@dataclass(frozen=True)
class FFmpegVideoCodec:
    encoder_name: str = "libvpx"
    decoder_codec: str = "vp8"
    container: str = "ivf"


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SkipFlow(f"{name} not found")
    return path


def require_ffmpeg_codec(ffmpeg: str, kind: str, codec_name: str) -> None:
    completed = run([ffmpeg, "-hide_banner", f"-{kind}s"])
    if codec_name not in completed.stdout:
        raise SkipFlow(f"ffmpeg {kind} {codec_name} not available")


def parse_time(value: object) -> float | None:
    if value is None:
        return None
    text = str(value)
    if not text or text == "N/A":
        return None
    return float(text)


def probe_packets(ffprobe: str, path: Path, media_kind: str) -> tuple[str, PushPullQueue[EncodedPacket], dict[str, object]]:
    selector = "a:0" if media_kind == "audio" else "v:0"
    completed = run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            selector,
            "-show_streams",
            "-show_packets",
            "-of",
            "json",
            str(path),
        ]
    )
    data = json.loads(completed.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise AssertionError(f"{media_kind}: ffprobe found no stream in {path}")
    stream = streams[0]
    codec_name = str(stream.get("codec_name") or "")
    packets = data.get("packets") or []
    if not packets:
        raise AssertionError(f"{media_kind}: ffprobe found no packets in {path}")

    out: PushPullQueue[EncodedPacket] = PushPullQueue()
    last_pts: float | None = None
    for index, packet in enumerate(packets):
        size = int(packet.get("size") or 0)
        if size <= 0:
            raise AssertionError(f"{media_kind}: packet {index} has invalid size {size}")
        pts_time = parse_time(packet.get("pts_time"))
        if pts_time is not None and last_pts is not None and pts_time < last_pts - 1e-9:
            raise AssertionError(f"{media_kind}: packet pts moved backwards at {index}")
        if pts_time is not None:
            last_pts = pts_time
        duration_time = parse_time(packet.get("duration_time"))
        if duration_time is not None and duration_time <= 0.0:
            raise AssertionError(f"{media_kind}: packet {index} has non-positive duration")
        out.push(
            EncodedPacket(
                media_kind=media_kind,
                codec_name=codec_name,
                sequence_id=index,
                pts_time=pts_time,
                duration_time=duration_time,
                size=size,
                flags=str(packet.get("flags") or ""),
            )
        )
    return codec_name, out, stream


class AudioEncoder(Generic[Encoder]):
    def __init__(self, ffmpeg: str, ffprobe: str, encoder: Encoder) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.encoder = encoder

    def encode(self, frames: PushPullQueue[AudioRawFrame], workdir: Path) -> tuple[EncodedStream, bytes]:
        if not isinstance(self.encoder, FFmpegAudioCodec):
            raise TypeError("AudioEncoder expects FFmpegAudioCodec for this verification")
        raw_path = workdir / "audio_input.s16le"
        encoded_path = workdir / f"audio_encoded.{self.encoder.container}"
        raw_bytes = bytearray()
        expected_sequence = 0
        frame_count = len(frames)
        while len(frames) > 0:
            frame = frames.pull()
            if frame.sequence_id != expected_sequence:
                raise AssertionError("audio raw frame sequence mismatch")
            expected_sequence += 1
            raw_bytes.extend(frame.pcm_s16le)
        raw_path.write_bytes(raw_bytes)

        run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "s16le",
                "-ar",
                "48000",
                "-ac",
                "1",
                "-i",
                str(raw_path),
                "-c:a",
                self.encoder.encoder_name,
                "-b:a",
                "96k",
                "-vbr",
                "off",
                "-frame_duration",
                "20",
                "-application",
                "audio",
                str(encoded_path),
            ]
        )
        codec_name, packets, stream = probe_packets(self.ffprobe, encoded_path, "audio")
        if codec_name != self.encoder.decoder_codec:
            raise AssertionError(f"audio codec mismatch: {codec_name}")
        if int(stream.get("sample_rate") or 0) != 48000:
            raise AssertionError("audio sample rate changed")
        if int(stream.get("channels") or 0) != 1:
            raise AssertionError("audio channel count changed")
        if packets.pushed < max(1, frame_count - 1):
            raise AssertionError("audio encoded fewer packets than expected")
        return EncodedStream("audio", codec_name, encoded_path, packets), bytes(raw_bytes)


class AudioDecoder(Generic[Decoder]):
    def __init__(self, ffmpeg: str, decoder: Decoder) -> None:
        self.ffmpeg = ffmpeg
        self.decoder = decoder

    def decode(self, stream: EncodedStream, workdir: Path) -> bytes:
        if not isinstance(self.decoder, FFmpegAudioCodec):
            raise TypeError("AudioDecoder expects FFmpegAudioCodec for this verification")
        if stream.media_kind != "audio":
            raise AssertionError("audio decoder received non-audio stream")
        packet_count = 0
        while len(stream.packets) > 0:
            packet = stream.packets.pull()
            if packet.media_kind != "audio" or packet.sequence_id != packet_count:
                raise AssertionError("audio encoded packet pull order mismatch")
            packet_count += 1
        decoded_path = workdir / "audio_decoded.s16le"
        run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(stream.path),
                "-f",
                "s16le",
                "-ar",
                "48000",
                "-ac",
                "1",
                str(decoded_path),
            ]
        )
        return decoded_path.read_bytes()


class VideoEncoder(Generic[Encoder]):
    def __init__(self, ffmpeg: str, ffprobe: str, encoder: Encoder) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.encoder = encoder

    def encode(self, frames: PushPullQueue[VideoRawFrame], workdir: Path) -> tuple[EncodedStream, bytes]:
        if not isinstance(self.encoder, FFmpegVideoCodec):
            raise TypeError("VideoEncoder expects FFmpegVideoCodec for this verification")
        raw_path = workdir / "video_input.i420"
        encoded_path = workdir / f"video_encoded.{self.encoder.container}"
        raw_bytes = bytearray()
        expected_sequence = 0
        frame_count = len(frames)
        while len(frames) > 0:
            frame = frames.pull()
            if frame.sequence_id != expected_sequence:
                raise AssertionError("video raw frame sequence mismatch")
            expected_sequence += 1
            raw_bytes.extend(frame.i420)
        raw_path.write_bytes(raw_bytes)

        run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "yuv420p",
                "-s:v",
                "64x48",
                "-r",
                "30",
                "-i",
                str(raw_path),
                "-c:v",
                self.encoder.encoder_name,
                "-b:v",
                "2M",
                "-crf",
                "4",
                "-g",
                "30",
                "-threads",
                "1",
                str(encoded_path),
            ]
        )
        codec_name, packets, stream = probe_packets(self.ffprobe, encoded_path, "video")
        if codec_name != self.encoder.decoder_codec:
            raise AssertionError(f"video codec mismatch: {codec_name}")
        if int(stream.get("width") or 0) != 64 or int(stream.get("height") or 0) != 48:
            raise AssertionError("video dimensions changed")
        if packets.pushed != frame_count:
            raise AssertionError(f"video packet count mismatch: {packets.pushed} != {frame_count}")
        first_packet = packets._items[0]
        if "K" not in first_packet.flags:
            raise AssertionError("video first packet is not marked keyframe")
        return EncodedStream("video", codec_name, encoded_path, packets), bytes(raw_bytes)


class VideoDecoder(Generic[Decoder]):
    def __init__(self, ffmpeg: str, decoder: Decoder) -> None:
        self.ffmpeg = ffmpeg
        self.decoder = decoder

    def decode(self, stream: EncodedStream, workdir: Path) -> bytes:
        if not isinstance(self.decoder, FFmpegVideoCodec):
            raise TypeError("VideoDecoder expects FFmpegVideoCodec for this verification")
        if stream.media_kind != "video":
            raise AssertionError("video decoder received non-video stream")
        packet_count = 0
        while len(stream.packets) > 0:
            packet = stream.packets.pull()
            if packet.media_kind != "video" or packet.sequence_id != packet_count:
                raise AssertionError("video encoded packet pull order mismatch")
            packet_count += 1
        decoded_path = workdir / "video_decoded.i420"
        run(
            [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(stream.path),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "yuv420p",
                str(decoded_path),
            ]
        )
        return decoded_path.read_bytes()


def build_audio_frames(frame_count: int = 50) -> PushPullQueue[AudioRawFrame]:
    sample_rate = 48000
    samples_per_frame = 960
    frames: PushPullQueue[AudioRawFrame] = PushPullQueue()
    for frame_index in range(frame_count):
        pcm = bytearray()
        base_sample = frame_index * samples_per_frame
        for offset in range(samples_per_frame):
            sample_index = base_sample + offset
            t = sample_index / sample_rate
            value = int(10500 * math.sin(2 * math.pi * 440 * t) + 2200 * math.sin(2 * math.pi * 880 * t))
            pcm.extend(struct.pack("<h", max(-32768, min(32767, value))))
        frames.push(
            AudioRawFrame(
                sequence_id=frame_index,
                timestamp=base_sample,
                duration_us=20000,
                sample_rate_hz=sample_rate,
                channels=1,
                samples_per_channel=samples_per_frame,
                pcm_s16le=bytes(pcm),
            )
        )
    return frames


def build_video_frames(frame_count: int = 30) -> PushPullQueue[VideoRawFrame]:
    width = 64
    height = 48
    frames: PushPullQueue[VideoRawFrame] = PushPullQueue()
    for frame_index in range(frame_count):
        y = bytearray()
        for row in range(height):
            for col in range(width):
                y.append((col * 3 + row * 5 + frame_index * 7) & 0xFF)
        u = bytearray()
        v = bytearray()
        for row in range(height // 2):
            for col in range(width // 2):
                u.append((128 + col * 2 - row + frame_index * 3) & 0xFF)
                v.append((64 + col - row * 2 + frame_index * 5) & 0xFF)
        frames.push(
            VideoRawFrame(
                sequence_id=frame_index,
                timestamp=frame_index * 3000,
                duration_us=33333,
                width=width,
                height=height,
                i420=bytes(y + u + v),
            )
        )
    return frames


def pcm_s16le_samples(data: bytes) -> list[int]:
    usable = len(data) - (len(data) % 2)
    return [sample[0] for sample in struct.iter_unpack("<h", data[:usable])]


def snr_db(reference: bytes, decoded: bytes) -> float:
    ref = pcm_s16le_samples(reference)
    got = pcm_s16le_samples(decoded)
    if len(got) < int(len(ref) * 0.98):
        raise AssertionError(f"decoded audio too short: {len(got)} < {len(ref)}")
    best = -999.0
    max_shift = min(960, max(0, len(got) - 1), max(0, len(ref) - 1))
    for shift in range(-max_shift, max_shift + 1, 8):
        if shift >= 0:
            ref_slice = ref[shift:]
            got_slice = got
        else:
            ref_slice = ref
            got_slice = got[-shift:]
        count = min(len(ref_slice), len(got_slice))
        if count <= 0:
            continue
        signal = 0.0
        noise = 0.0
        for lhs, rhs in zip(ref_slice[:count], got_slice[:count]):
            signal += float(lhs * lhs)
            delta = lhs - rhs
            noise += float(delta * delta)
        if noise == 0.0:
            return 99.0
        best = max(best, 10.0 * math.log10(signal / noise))
    return best


def psnr_db(reference: bytes, decoded: bytes) -> float:
    count = min(len(reference), len(decoded))
    if count < int(len(reference) * 0.98):
        raise AssertionError(f"decoded video too short: {count} < {len(reference)}")
    mse = 0.0
    for lhs, rhs in zip(reference[:count], decoded[:count]):
        delta = lhs - rhs
        mse += float(delta * delta)
    mse /= count
    if mse == 0.0:
        return 99.0
    return 10.0 * math.log10((255.0 * 255.0) / mse)


def run_flow(keep_temp: bool) -> str:
    ffmpeg = require_tool("ffmpeg")
    ffprobe = require_tool("ffprobe")
    require_ffmpeg_codec(ffmpeg, "encoder", "libopus")
    require_ffmpeg_codec(ffmpeg, "encoder", "libvpx")
    require_ffmpeg_codec(ffmpeg, "decoder", "opus")
    require_ffmpeg_codec(ffmpeg, "decoder", "vp8")

    with tempfile.TemporaryDirectory(prefix="webrtc-ffmpeg-codec-flow-") as tmp:
        workdir = Path(tmp)
        audio_codec = FFmpegAudioCodec()
        video_codec = FFmpegVideoCodec()

        audio_encoder: AudioEncoder[FFmpegAudioCodec] = AudioEncoder(ffmpeg, ffprobe, audio_codec)
        audio_stream, audio_reference = audio_encoder.encode(build_audio_frames(), workdir)
        audio_decoder: AudioDecoder[FFmpegAudioCodec] = AudioDecoder(ffmpeg, audio_codec)
        audio_decoded = audio_decoder.decode(audio_stream, workdir)
        audio_snr = snr_db(audio_reference, audio_decoded)
        if audio_snr < 15.0:
            raise AssertionError(f"audio SNR too low: {audio_snr:.2f} dB")

        video_encoder: VideoEncoder[FFmpegVideoCodec] = VideoEncoder(ffmpeg, ffprobe, video_codec)
        video_stream, video_reference = video_encoder.encode(build_video_frames(), workdir)
        video_decoder: VideoDecoder[FFmpegVideoCodec] = VideoDecoder(ffmpeg, video_codec)
        video_decoded = video_decoder.decode(video_stream, workdir)
        video_psnr = psnr_db(video_reference, video_decoded)
        if video_psnr < 28.0:
            raise AssertionError(f"video PSNR too low: {video_psnr:.2f} dB")

        if keep_temp:
            kept = Path(tempfile.mkdtemp(prefix="webrtc-ffmpeg-codec-flow-kept-"))
            for path in workdir.iterdir():
                target = kept / path.name
                target.write_bytes(path.read_bytes())
            temp_note = f" kept={kept}"
        else:
            temp_note = ""

        return (
            "ffmpeg codec flow checks passed: "
            f"audio_packets={audio_stream.packets.pulled} "
            f"audio_snr_db={audio_snr:.2f} "
            f"video_packets={video_stream.packets.pulled} "
            f"video_psnr_db={video_psnr:.2f}"
            f"{temp_note}"
        )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-temp", action="store_true", help="copy generated media artifacts to a retained temp directory")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        print(run_flow(args.keep_temp))
    except SkipFlow as exc:
        print(f"ffmpeg codec flow skipped: {exc}")
        return 0
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr)
        return exc.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
