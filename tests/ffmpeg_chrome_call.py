#!/usr/bin/env python3
"""Validate Chrome inbound media from a Uya-owned FFmpeg direct sender.

This is the Phase 21 end-to-end harness for:

    FFmpeg encoded frames -> UyaDirectSender -> rtp_packetize_encoded_frame
    -> SRTP/SRTCP -> UDP -> Chrome inbound RTP

FFmpeg is only the explicit reference codec source. Chrome is only the WebRTC
receiver. The WebRTC sender must be the Uya process named
``uya_ffmpeg_direct_sender``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import textwrap
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from browser_datachannel_interop import (
    CDPClient,
    DEFAULT_TIMEOUT_SECONDS,
    InteropError,
    find_browser_executable,
    find_free_port,
    require,
    start_http_server,
)
from ffmpeg_codec_flow import SkipFlow, probe_packets, require_ffmpeg_codec, require_tool, run


REPO_ROOT = Path(__file__).resolve().parent.parent
UYA_DIRECT_SENDER_MAIN = REPO_ROOT / "src" / "webrtc_ffmpeg_direct_sender_main.uya"
UYA_BIN = REPO_ROOT.parent / "uya" / "bin" / "uya"
RAW_PREVIEW_WIDTH = 32
RAW_PREVIEW_HEIGHT = 18
RAW_PREVIEW_FPS = 30
RAW_PREVIEW_DURATION_SECONDS = 6


@dataclass
class UyaDirectSenderHandle:
    proc: subprocess.Popen[str]
    answer_sdp: str
    diagnostics_path: Path
    stdout_path: Path
    stderr_path: Path


@dataclass
class ManualPreviewSession:
    session_id: str
    handle: UyaDirectSenderHandle
    workdir: Path


@dataclass
class PreviewMediaAssets:
    media_path: Path
    ffmpeg_stats: dict[str, int | str]
    raw_video_path: Path | None = None
    raw_audio_path: Path | None = None


def generate_ffmpeg_media(workdir: Path) -> tuple[Path, dict[str, int | str]]:
    ffmpeg = require_tool("ffmpeg")
    ffprobe = require_tool("ffprobe")
    require_ffmpeg_codec(ffmpeg, "encoder", "libopus")
    require_ffmpeg_codec(ffmpeg, "encoder", "libvpx")
    require_ffmpeg_codec(ffmpeg, "decoder", "opus")
    require_ffmpeg_codec(ffmpeg, "decoder", "vp8")

    media_path = workdir / "ffmpeg_chrome_direct.webm"
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30:duration=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=4",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libvpx",
            "-b:v",
            "600k",
            "-crf",
            "8",
            "-g",
            "30",
            "-threads",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "libopus",
            "-b:a",
            "80k",
            "-vbr",
            "off",
            "-application",
            "audio",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-shortest",
            str(media_path),
        ]
    )

    video_codec, video_packets, video_stream = probe_packets(ffprobe, media_path, "video")
    audio_codec, audio_packets, audio_stream = probe_packets(ffprobe, media_path, "audio")
    if video_codec != "vp8":
        raise AssertionError(f"ffmpeg video codec mismatch: {video_codec}")
    if audio_codec != "opus":
        raise AssertionError(f"ffmpeg audio codec mismatch: {audio_codec}")
    if video_packets.pushed < 60:
        raise AssertionError(f"ffmpeg produced too few video packets: {video_packets.pushed}")
    if audio_packets.pushed < 50:
        raise AssertionError(f"ffmpeg produced too few audio packets: {audio_packets.pushed}")

    return media_path, {
        "audio_codec": audio_codec,
        "audio_packets": audio_packets.pushed,
        "sample_rate": int(audio_stream.get("sample_rate") or 0),
        "video_codec": video_codec,
        "video_packets": video_packets.pushed,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
    }


def probe_streams(media_path: Path) -> dict[str, Any]:
    ffprobe = require_tool("ffprobe")
    output = run(
        [
            ffprobe,
            "-hide_banner",
            "-loglevel",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(media_path),
        ]
    )
    parsed = json.loads(output.stdout)
    if not isinstance(parsed, dict):
        raise AssertionError(f"ffprobe returned invalid JSON for {media_path}")
    return parsed


def source_has_audio(probe: dict[str, Any]) -> bool:
    streams = probe.get("streams")
    if not isinstance(streams, list):
        return False
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == "audio":
            return True
    return False


def first_video_stream(probe: dict[str, Any]) -> dict[str, Any]:
    streams = probe.get("streams")
    if not isinstance(streams, list):
        raise AssertionError("MP4 probe contains no streams")
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == "video":
            return stream
    raise AssertionError("MP4 source contains no video stream")


def prepare_mp4_raw_preview(source_mp4: Path, workdir: Path) -> PreviewMediaAssets:
    source_mp4 = source_mp4.expanduser().resolve()
    if not source_mp4.exists():
        raise AssertionError(f"MP4 source does not exist: {source_mp4}")
    if not source_mp4.is_file():
        raise AssertionError(f"MP4 source is not a file: {source_mp4}")

    ffmpeg = require_tool("ffmpeg")
    require_ffmpeg_codec(ffmpeg, "encoder", "libopus")
    require_ffmpeg_codec(ffmpeg, "encoder", "libvpx")
    require_ffmpeg_codec(ffmpeg, "decoder", "opus")
    require_ffmpeg_codec(ffmpeg, "decoder", "vp8")
    probe = probe_streams(source_mp4)
    video_stream = first_video_stream(probe)

    raw_dir = workdir / "mp4-raw-preview"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_video_path = raw_dir / "video_32x18_i420.raw"
    raw_audio_path = raw_dir / "audio_48000_mono_s16le.raw"

    vf = (
        f"scale={RAW_PREVIEW_WIDTH}:{RAW_PREVIEW_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={RAW_PREVIEW_WIDTH}:{RAW_PREVIEW_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        "format=yuv420p"
    )
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-stream_loop",
            "-1",
            "-t",
            str(RAW_PREVIEW_DURATION_SECONDS),
            "-i",
            str(source_mp4),
            "-map",
            "0:v:0",
            "-vf",
            vf,
            "-r",
            str(RAW_PREVIEW_FPS),
            "-an",
            "-f",
            "rawvideo",
            str(raw_video_path),
        ]
    )

    if source_has_audio(probe):
        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-stream_loop",
                "-1",
                "-t",
                str(RAW_PREVIEW_DURATION_SECONDS),
                "-i",
                str(source_mp4),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-f",
                "s16le",
                str(raw_audio_path),
            ]
        )
        audio_source = "mp4"
    else:
        run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=mono:sample_rate=48000",
                "-t",
                str(RAW_PREVIEW_DURATION_SECONDS),
                "-f",
                "s16le",
                str(raw_audio_path),
            ]
        )
        audio_source = "silence"

    min_video_bytes = RAW_PREVIEW_WIDTH * RAW_PREVIEW_HEIGHT * 3 // 2
    min_audio_bytes = 960 * 2
    if raw_video_path.stat().st_size < min_video_bytes:
        raise AssertionError(f"raw video preview is too short: {raw_video_path.stat().st_size} < {min_video_bytes}")
    if raw_audio_path.stat().st_size < min_audio_bytes:
        raise AssertionError(f"raw audio preview is too short: {raw_audio_path.stat().st_size} < {min_audio_bytes}")

    format_info = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    return PreviewMediaAssets(
        media_path=source_mp4,
        raw_video_path=raw_video_path,
        raw_audio_path=raw_audio_path,
        ffmpeg_stats={
            "source_kind": "mp4",
            "source_path": str(source_mp4),
            "source_duration": str(format_info.get("duration", "")),
            "source_video_codec": str(video_stream.get("codec_name", "")),
            "source_width": int(video_stream.get("width") or 0),
            "source_height": int(video_stream.get("height") or 0),
            "preview_width": RAW_PREVIEW_WIDTH,
            "preview_height": RAW_PREVIEW_HEIGHT,
            "preview_fps": RAW_PREVIEW_FPS,
            "preview_duration_seconds": RAW_PREVIEW_DURATION_SECONDS,
            "preview_video_bytes": raw_video_path.stat().st_size,
            "preview_audio_bytes": raw_audio_path.stat().st_size,
            "preview_audio_source": audio_source,
        },
    )


def prepare_preview_media(workdir: Path, source_mp4: Path | None = None) -> PreviewMediaAssets:
    if source_mp4 is not None:
        return prepare_mp4_raw_preview(source_mp4, workdir)
    media_path, ffmpeg_stats = generate_ffmpeg_media(workdir)
    ffmpeg_stats = dict(ffmpeg_stats)
    ffmpeg_stats["source_kind"] = "synthetic"
    return PreviewMediaAssets(media_path=media_path, ffmpeg_stats=ffmpeg_stats)


def make_call_page() -> str:
    return textwrap.dedent(
        """
        <!doctype html>
        <meta charset="utf-8">
        <title>Uya FFmpeg Direct Chrome Receiver</title>
        <script>
        window.__uyaDirectOffer = null;
        window.__uyaDirectPeer = null;
        window.__ffmpegChromeCallResult = null;
        window.__ffmpegChromeCallProgress = [];

        function mark(step) {
          window.__ffmpegChromeCallProgress.push(step);
        }

        function fail(message, error) {
          const detail = [];
          if (error) {
            if (error.name) detail.push(String(error.name));
            if (error.message) detail.push(String(error.message));
            detail.push(error.stack ? String(error.stack) : String(error));
          }
          window.__ffmpegChromeCallResult = {
            ok: false,
            error: message,
            detail: detail.join("\\n"),
            progress: window.__ffmpegChromeCallProgress.slice()
          };
        }

        function delay(ms) {
          return new Promise(resolve => setTimeout(resolve, ms));
        }

        function waitForEvent(target, name, predicate) {
          return new Promise((resolve, reject) => {
            const handler = event => {
              try {
                if (!predicate || predicate(event)) {
                  target.removeEventListener(name, handler);
                  resolve(event);
                }
              } catch (error) {
                target.removeEventListener(name, handler);
                reject(error);
              }
            };
            target.addEventListener(name, handler);
          });
        }

        async function waitForGatheringComplete(peer) {
          if (peer.iceGatheringState === 'complete') {
            return;
          }
          await waitForEvent(peer, 'icegatheringstatechange', () => peer.iceGatheringState === 'complete');
        }

        function preferredCodecs(kind, mimeType) {
          const capabilities = RTCRtpReceiver.getCapabilities(kind);
          if (!capabilities || !capabilities.codecs) {
            return [];
          }
          const wanted = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase() === mimeType);
          const helpers = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase().indexOf('rtx') >= 0);
          return wanted.concat(helpers);
        }

        async function waitForInbound(kind, receiver) {
          const deadline = Date.now() + 10000;
          while (Date.now() < deadline) {
            const stats = await receiver.getStats();
            for (const stat of stats.values()) {
              if (stat.type !== 'inbound-rtp') continue;
              if (stat.kind !== kind && stat.mediaType !== kind) continue;
              const packets = stat.packetsReceived || 0;
              const frames = stat.framesDecoded || stat.framesReceived || 0;
              let codecMimeType = '';
              if (stat.codecId) {
                const codec = stats.get(stat.codecId);
                if (codec && codec.mimeType) codecMimeType = String(codec.mimeType);
              }
              if (kind === 'audio' && packets > 0) {
                return {packetsReceived: packets, framesDecoded: frames, codecMimeType};
              }
              if (kind === 'video' && packets > 0 && frames > 0) {
                return {packetsReceived: packets, framesDecoded: frames, codecMimeType};
              }
            }
            await delay(100);
          }
          return {packetsReceived: 0, framesDecoded: 0, codecMimeType: ''};
        }

        async function runReceiver() {
          mark('start');
          const receiver = new RTCPeerConnection({iceServers: []});
          window.__uyaDirectPeer = receiver;
          const states = [];
          const tracks = [];
          receiver.addEventListener('connectionstatechange', () => {
            states.push('receiver:' + receiver.connectionState);
          });
          receiver.addEventListener('iceconnectionstatechange', () => {
            states.push('ice:' + receiver.iceConnectionState);
          });
          receiver.addEventListener('track', event => {
            tracks.push(event.track.kind);
          });

          const audioTransceiver = receiver.addTransceiver('audio', {direction: 'recvonly'});
          const opus = preferredCodecs('audio', 'audio/opus');
          if (opus.length > 0) {
            audioTransceiver.setCodecPreferences(opus);
          }
          const videoTransceiver = receiver.addTransceiver('video', {direction: 'recvonly'});
          const vp8 = preferredCodecs('video', 'video/vp8');
          if (vp8.length > 0) {
            videoTransceiver.setCodecPreferences(vp8);
          }
          mark('recvonly-transceivers');

          const offer = await receiver.createOffer();
          await receiver.setLocalDescription(offer);
          await waitForGatheringComplete(receiver);
          window.__uyaDirectOffer = {
            type: receiver.localDescription.type,
            sdp: receiver.localDescription.sdp
          };
          mark('offer-ready');

          window.__uyaDirectApplyAnswer = async answer => {
            await receiver.setRemoteDescription({
              type: 'answer',
              sdp: typeof answer === 'string' ? answer : String(answer.sdp || '')
            });
            mark('answer-applied');

            const audio = receiver.getReceivers().find(item => item.track && item.track.kind === 'audio');
            const video = receiver.getReceivers().find(item => item.track && item.track.kind === 'video');
            if (!audio || !video) {
              throw new Error('Chrome receiver lookup failed');
            }
            const audioStats = await waitForInbound('audio', audio);
            const videoStats = await waitForInbound('video', video);
            if (audioStats.packetsReceived <= 0) {
              throw new Error('Chrome received no Uya-originated audio RTP packets');
            }
            if (videoStats.packetsReceived <= 0 || videoStats.framesDecoded <= 0) {
              throw new Error('Chrome decoded no Uya-originated VP8 frames');
            }
            mark('media-received');
            await delay(4500);
            mark('rtcp-feedback-window');
            const finalAudioStats = await waitForInbound('audio', audio);
            const finalVideoStats = await waitForInbound('video', video);
            receiver.close();
            await delay(25);
            window.__ffmpegChromeCallResult = {
              ok: true,
              browser: navigator.userAgent,
              states,
              tracks,
              receiverConnectionState: receiver.connectionState,
              audioPacketsReceived: finalAudioStats.packetsReceived,
              audioCodecMimeType: finalAudioStats.codecMimeType,
              videoPacketsReceived: finalVideoStats.packetsReceived,
              videoFramesDecoded: finalVideoStats.framesDecoded,
              videoCodecMimeType: finalVideoStats.codecMimeType,
              offerSdp: window.__uyaDirectOffer.sdp,
              answerSdp: typeof answer === 'string' ? answer : String(answer.sdp || ''),
              progress: window.__ffmpegChromeCallProgress.slice()
            };
          };
        }

        runReceiver().catch(error => fail('Chrome recvonly setup failed', error));
        </script>
        """
    ).strip()


def make_preview_page(ffmpeg_stats: dict[str, int | str]) -> str:
    stats_json = json.dumps(ffmpeg_stats, sort_keys=True)
    return textwrap.dedent(
        """
        <!doctype html>
        <meta charset="utf-8">
        <title>Uya FFmpeg Direct Chrome Preview</title>
        <style>
          :root {
            color-scheme: light;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f5f7fa;
            color: #1f2937;
          }
          body { margin: 0; min-height: 100vh; }
          main { max-width: 1180px; margin: 0 auto; padding: 20px; }
          header {
            align-items: center;
            display: flex;
            gap: 12px;
            justify-content: space-between;
            margin-bottom: 12px;
          }
          h1 { margin: 0; font-size: 22px; }
          .actions { display: flex; gap: 8px; }
          button {
            border: 0;
            border-radius: 6px;
            background: #155e75;
            color: white;
            cursor: pointer;
            font: inherit;
            font-weight: 700;
            min-height: 40px;
            padding: 0 16px;
          }
          button.secondary { background: #475569; }
          button:disabled { cursor: default; opacity: 0.55; }
          .stage {
            background: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            overflow: hidden;
          }
          video {
            aspect-ratio: 16 / 9;
            background: #020617;
            display: block;
            image-rendering: pixelated;
            min-height: 280px;
            object-fit: contain;
            width: 100%;
          }
          .status {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 8px;
            margin: 16px 0;
          }
          .metric {
            background: white;
            border: 1px solid #d9dee8;
            border-radius: 8px;
            padding: 10px 12px;
          }
          .label { color: #64748b; display: block; font-size: 12px; margin-bottom: 4px; }
          .value { font-size: 18px; font-weight: 700; }
          pre {
            background: #111827;
            border-radius: 8px;
            color: #e5e7eb;
            font-size: 12px;
            min-height: 180px;
            overflow: auto;
            padding: 12px;
            white-space: pre-wrap;
          }
          @media (max-width: 760px) {
            main { padding: 16px; }
            header { align-items: stretch; flex-direction: column; }
            .actions { width: 100%; }
            button { flex: 1; }
            .status { grid-template-columns: 1fr; }
            video { min-height: 200px; }
          }
        </style>
        <main>
          <header>
            <h1>Uya FFmpeg Direct Chrome Preview</h1>
            <div class="actions">
              <button id="start">Start Uya Video</button>
              <button class="secondary" id="stop" disabled>Stop</button>
            </div>
          </header>
          <section class="stage">
            <video id="remoteVideo" autoplay playsinline controls muted></video>
          </section>
          <section class="status">
            <div class="metric"><span class="label">State</span><span class="value" id="state">idle</span></div>
            <div class="metric"><span class="label">Audio Packets</span><span class="value" id="audioPackets">0</span></div>
            <div class="metric"><span class="label">Video Frames</span><span class="value" id="videoFrames">0</span></div>
            <div class="metric"><span class="label">Sender RTP</span><span class="value" id="senderRtp">0</span></div>
          </section>
          <pre id="log"></pre>
        </main>
        <script>
        const sourceStats = __SOURCE_STATS__;
        const start = document.getElementById('start');
        const stop = document.getElementById('stop');
        const state = document.getElementById('state');
        const remoteVideo = document.getElementById('remoteVideo');
        const audioPackets = document.getElementById('audioPackets');
        const videoFrames = document.getElementById('videoFrames');
        const senderRtp = document.getElementById('senderRtp');
        const log = document.getElementById('log');
        const remoteStream = new MediaStream();
        remoteVideo.srcObject = remoteStream;
        let receiver = null;
        let sessionId = '';
        let finished = false;
        window.__uyaManualPreviewProgress = [];
        window.__uyaManualPreviewResult = null;

        function writeLog(line) {
          log.textContent += line + '\\n';
          log.scrollTop = log.scrollHeight;
        }

        function setState(value) {
          state.textContent = value;
          window.__uyaManualPreviewProgress.push(value);
        }

        function delay(ms) {
          return new Promise(resolve => setTimeout(resolve, ms));
        }

        function fail(message, error) {
          const detail = [];
          if (error) {
            if (error.name) detail.push(String(error.name));
            if (error.message) detail.push(String(error.message));
            detail.push(error.stack ? String(error.stack) : String(error));
          }
          setState('error');
          const detailText = detail.join('\\n');
          writeLog(message + (detailText ? '\\n' + detailText : ''));
          window.__uyaManualPreviewResult = {
            ok: false,
            error: message,
            detail: detailText,
            progress: window.__uyaManualPreviewProgress.slice()
          };
        }

        async function postJson(path, body) {
          const response = await fetch(path, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
          });
          let data = null;
          try {
            data = await response.json();
          } catch (error) {
            throw new Error(path + ' returned non-JSON status ' + response.status);
          }
          if (!response.ok || !data || data.ok !== true) {
            throw new Error((data && data.error) || (path + ' failed with status ' + response.status));
          }
          return data;
        }

        function waitForEvent(target, name, predicate) {
          return new Promise((resolve, reject) => {
            const handler = event => {
              try {
                if (!predicate || predicate(event)) {
                  target.removeEventListener(name, handler);
                  resolve(event);
                }
              } catch (error) {
                target.removeEventListener(name, handler);
                reject(error);
              }
            };
            target.addEventListener(name, handler);
          });
        }

        async function waitForGatheringComplete(peer) {
          if (peer.iceGatheringState === 'complete') {
            return;
          }
          await waitForEvent(peer, 'icegatheringstatechange', () => peer.iceGatheringState === 'complete');
        }

        function preferredCodecs(kind, mimeType) {
          const capabilities = RTCRtpReceiver.getCapabilities(kind);
          if (!capabilities || !capabilities.codecs) {
            return [];
          }
          const wanted = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase() === mimeType);
          const helpers = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase().indexOf('rtx') >= 0);
          return wanted.concat(helpers);
        }

        async function readInbound(kind, rtpReceiver) {
          const stats = await rtpReceiver.getStats();
          for (const stat of stats.values()) {
            if (stat.type !== 'inbound-rtp') continue;
            if (stat.kind !== kind && stat.mediaType !== kind) continue;
            let codecMimeType = '';
            if (stat.codecId) {
              const codec = stats.get(stat.codecId);
              if (codec && codec.mimeType) codecMimeType = String(codec.mimeType);
            }
            return {
              packetsReceived: stat.packetsReceived || 0,
              framesDecoded: stat.framesDecoded || stat.framesReceived || 0,
              codecMimeType
            };
          }
          return {packetsReceived: 0, framesDecoded: 0, codecMimeType: ''};
        }

        async function waitForMedia(audioReceiver, videoReceiver) {
          const deadline = Date.now() + 12000;
          while (Date.now() < deadline) {
            const audioStats = await readInbound('audio', audioReceiver);
            const videoStats = await readInbound('video', videoReceiver);
            audioPackets.textContent = String(audioStats.packetsReceived);
            videoFrames.textContent = String(videoStats.framesDecoded);
            if (audioStats.packetsReceived > 0 && videoStats.packetsReceived > 0 && videoStats.framesDecoded > 0) {
              return {audioStats, videoStats};
            }
            await delay(150);
          }
          throw new Error('Chrome did not decode Uya-originated Opus/VP8 media before timeout');
        }

        async function stopSession() {
          if (sessionId) {
            const id = sessionId;
            sessionId = '';
            await postJson('/api/stop-call', {sessionId: id}).catch(error => writeLog(String(error.message || error)));
          }
          if (receiver) {
            receiver.close();
          }
          stop.disabled = true;
          start.disabled = false;
        }

        async function runOneClickPreview() {
          const states = [];
          const tracks = [];
          setState('offer');
          writeLog('ffmpeg=' + JSON.stringify(sourceStats));
          receiver = new RTCPeerConnection({iceServers: []});
          window.__uyaManualPreviewPeer = receiver;
          receiver.addEventListener('connectionstatechange', () => {
            states.push('receiver:' + receiver.connectionState);
            writeLog('connection=' + receiver.connectionState);
          });
          receiver.addEventListener('iceconnectionstatechange', () => {
            states.push('ice:' + receiver.iceConnectionState);
          });
          receiver.addEventListener('track', event => {
            tracks.push(event.track.kind);
            remoteStream.addTrack(event.track);
            remoteVideo.play().catch(error => writeLog('video.play: ' + String(error.message || error)));
          });

          const audioTransceiver = receiver.addTransceiver('audio', {direction: 'recvonly'});
          const opus = preferredCodecs('audio', 'audio/opus');
          if (opus.length > 0) {
            audioTransceiver.setCodecPreferences(opus);
          }
          const videoTransceiver = receiver.addTransceiver('video', {direction: 'recvonly'});
          const vp8 = preferredCodecs('video', 'video/vp8');
          if (vp8.length > 0) {
            videoTransceiver.setCodecPreferences(vp8);
          }

          const offer = await receiver.createOffer();
          await receiver.setLocalDescription(offer);
          await waitForGatheringComplete(receiver);
          setState('sender');
          const started = await postJson('/api/start-call', {
            offer: {
              type: receiver.localDescription.type,
              sdp: receiver.localDescription.sdp
            }
          });
          sessionId = String(started.sessionId || '');
          if (!sessionId || !started.answer || !started.answer.sdp) {
            throw new Error('preview server did not return a Uya SDP answer');
          }
          writeLog('uya_session=' + sessionId);
          await receiver.setRemoteDescription({
            type: 'answer',
            sdp: String(started.answer.sdp)
          });
          setState('playing');

          const audio = receiver.getReceivers().find(item => item.track && item.track.kind === 'audio');
          const video = receiver.getReceivers().find(item => item.track && item.track.kind === 'video');
          if (!audio || !video) {
            throw new Error('Chrome receiver lookup failed');
          }
          const firstStats = await waitForMedia(audio, video);
          await delay(4500);
          const finalAudioStats = await readInbound('audio', audio);
          const finalVideoStats = await readInbound('video', video);
          audioPackets.textContent = String(finalAudioStats.packetsReceived);
          videoFrames.textContent = String(finalVideoStats.framesDecoded);
          setState('diagnostics');
          const finishedCall = await postJson('/api/finish-call', {sessionId});
          sessionId = '';
          const diagnostics = finishedCall.diagnostics || {};
          senderRtp.textContent = String(diagnostics.rtpPackets || 0);
          writeLog('diagnostics=' + JSON.stringify(diagnostics));
          setState('complete');
          finished = true;
          stop.disabled = false;
          window.__uyaManualPreviewResult = {
            ok: true,
            browser: navigator.userAgent,
            states,
            tracks,
            receiverConnectionState: receiver.connectionState,
            audioPacketsReceived: finalAudioStats.packetsReceived || firstStats.audioStats.packetsReceived,
            audioCodecMimeType: finalAudioStats.codecMimeType || firstStats.audioStats.codecMimeType,
            videoPacketsReceived: finalVideoStats.packetsReceived || firstStats.videoStats.packetsReceived,
            videoFramesDecoded: finalVideoStats.framesDecoded || firstStats.videoStats.framesDecoded,
            videoCodecMimeType: finalVideoStats.codecMimeType || firstStats.videoStats.codecMimeType,
            offerSdp: receiver.localDescription ? receiver.localDescription.sdp : '',
            answerSdp: started.answer.sdp,
            senderDiagnostics: diagnostics,
            progress: window.__uyaManualPreviewProgress.slice()
          };
        }

        start.addEventListener('click', async () => {
          start.disabled = true;
          stop.disabled = false;
          finished = false;
          window.__uyaManualPreviewResult = null;
          window.__uyaManualPreviewProgress = [];
          try {
            await runOneClickPreview();
          } catch (error) {
            await stopSession();
            fail('Uya preview call failed', error);
          }
        });
        stop.addEventListener('click', async () => {
          if (!finished) {
            setState('stopping');
          }
          await stopSession();
          if (!finished) {
            setState('stopped');
          }
        });
        </script>
        """
    ).strip().replace("__SOURCE_STATS__", stats_json)


def evaluate_json(client: CDPClient, session_id: str, expression: str) -> Any:
    response = client.command(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
        session_id=session_id,
    )
    evaluated = response.get("result")
    if not isinstance(evaluated, dict):
        return None
    value = evaluated.get("value")
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def wait_for_offer(client: CDPClient, session_id: str) -> dict[str, str]:
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        offer = evaluate_json(
            client,
            session_id,
            "window.__uyaDirectOffer ? JSON.stringify(window.__uyaDirectOffer) : null",
        )
        if isinstance(offer, dict) and offer.get("type") == "offer" and isinstance(offer.get("sdp"), str):
            return {"type": "offer", "sdp": str(offer["sdp"])}
        time.sleep(0.2)
    raise TimeoutError("Chrome did not publish a recvonly offer for UyaDirectSender")


def apply_answer(client: CDPClient, session_id: str, answer_sdp: str) -> None:
    answer_json = json.dumps({"sdp": answer_sdp})
    response = client.command(
        "Runtime.evaluate",
        {
            "expression": (
                "(() => {"
                "if (typeof window.__uyaDirectApplyAnswer !== 'function') {"
                "fail('Chrome answer/media receive failed', new Error('apply-answer function missing'));"
                "return false;"
                "}"
                f"window.__uyaDirectApplyAnswer({answer_json})"
                ".catch(error => fail('Chrome answer/media receive failed', error));"
                "return true;"
                "})()"
            ),
            "returnByValue": True,
        },
        session_id=session_id,
    )
    result = response.get("result")
    if not isinstance(result, dict) or result.get("value") is not True:
        raise AssertionError(f"Chrome did not start applying the Uya answer: {response}")


def read_chrome_debug_state(client: CDPClient, session_id: str) -> dict[str, Any]:
    state = evaluate_json(
        client,
        session_id,
        textwrap.dedent(
            """
            JSON.stringify((() => {
              const peer = window.__uyaDirectPeer || null;
              return {
                progress: window.__ffmpegChromeCallProgress || [],
                result: window.__ffmpegChromeCallResult || null,
                hasOffer: !!window.__uyaDirectOffer,
                hasApplyAnswer: typeof window.__uyaDirectApplyAnswer === 'function',
                signalingState: peer ? peer.signalingState : '',
                connectionState: peer ? peer.connectionState : '',
                iceConnectionState: peer ? peer.iceConnectionState : '',
                iceGatheringState: peer ? peer.iceGatheringState : '',
                localDescriptionType: peer && peer.localDescription ? peer.localDescription.type : '',
                remoteDescriptionType: peer && peer.remoteDescription ? peer.remoteDescription.type : ''
              };
            })())
            """
        ),
    )
    if isinstance(state, dict):
        return state
    return {}


def wait_for_result(client: CDPClient, session_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = evaluate_json(
            client,
            session_id,
            "window.__ffmpegChromeCallResult ? JSON.stringify(window.__ffmpegChromeCallResult) : null",
        )
        if isinstance(result, dict):
            return result
        time.sleep(0.2)
    raise TimeoutError(f"Chrome did not publish inbound RTP result; state={read_chrome_debug_state(client, session_id)}")


def evaluate_value(client: CDPClient, session_id: str, expression: str) -> Any:
    response = client.command(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
        session_id=session_id,
    )
    result = response.get("result")
    if isinstance(result, dict):
        return result.get("value")
    return None


def wait_for_manual_preview_ready(client: CDPClient, session_id: str) -> None:
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
    last_state: Any = None
    while time.monotonic() < deadline:
        last_state = evaluate_json(
            client,
            session_id,
            textwrap.dedent(
                """
                JSON.stringify({
                  ready: !!document.getElementById('start'),
                  readyState: document.readyState,
                  href: location.href,
                  title: document.title,
                  hasStart: !!document.getElementById('start'),
                  bodyPrefix: document.body ? document.body.textContent.slice(0, 120) : ''
                })
                """
            ),
        )
        if isinstance(last_state, dict) and last_state.get("ready") is True:
            return
        time.sleep(0.1)
    raise TimeoutError(f"manual preview page did not become ready: {last_state}")


def click_manual_preview_start(client: CDPClient, session_id: str) -> None:
    clicked = evaluate_value(
        client,
        session_id,
        "(() => { const button = document.getElementById('start'); if (!button) return false; button.click(); return true; })()",
    )
    require(clicked is True, "manual preview start button was not clickable")


def read_manual_preview_state(client: CDPClient, session_id: str) -> dict[str, Any]:
    state = evaluate_json(
        client,
        session_id,
        textwrap.dedent(
            """
            JSON.stringify({
              progress: window.__uyaManualPreviewProgress || [],
              result: window.__uyaManualPreviewResult || null,
              state: document.getElementById('state') ? document.getElementById('state').textContent : '',
              audioPackets: document.getElementById('audioPackets') ? document.getElementById('audioPackets').textContent : '',
              videoFrames: document.getElementById('videoFrames') ? document.getElementById('videoFrames').textContent : '',
              senderRtp: document.getElementById('senderRtp') ? document.getElementById('senderRtp').textContent : ''
            })
            """
        ),
    )
    if isinstance(state, dict):
        return state
    return {}


def wait_for_manual_preview_result(client: CDPClient, session_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 35.0
    while time.monotonic() < deadline:
        result = evaluate_json(
            client,
            session_id,
            "window.__uyaManualPreviewResult ? JSON.stringify(window.__uyaManualPreviewResult) : null",
        )
        if isinstance(result, dict):
            return result
        time.sleep(0.2)
    raise TimeoutError(f"manual preview did not publish a result; state={read_manual_preview_state(client, session_id)}")


def read_text_tail(path: Path, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace")
    if len(content) <= limit:
        return content
    return content[-limit:]


def sender_failure_message(message: str, handle: UyaDirectSenderHandle | None, stdout_path: Path, stderr_path: Path) -> str:
    return (
        f"{message}\n"
        f"returncode={handle.proc.poll() if handle is not None else 'not-started'}\n"
        f"stdout:\n{read_text_tail(stdout_path)}\n"
        f"stderr:\n{read_text_tail(stderr_path)}"
    )


def wait_for_answer(
    proc: subprocess.Popen[str],
    answer_path: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> str:
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
    last_json_error: json.JSONDecodeError | None = None
    while time.monotonic() < deadline:
        if answer_path.exists():
            try:
                answer = json.loads(answer_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                last_json_error = exc
            else:
                if isinstance(answer, dict) and isinstance(answer.get("sdp"), str):
                    if proc.poll() is not None:
                        raise AssertionError(
                            "uya_ffmpeg_direct_sender exited before Chrome could apply its answer\n"
                            f"returncode={proc.returncode}\n"
                            f"stdout:\n{read_text_tail(stdout_path)}\n"
                            f"stderr:\n{read_text_tail(stderr_path)}"
                        )
                    return str(answer["sdp"])
                raise AssertionError(f"invalid Uya answer JSON: {answer!r}")
        if proc.poll() is not None:
            raise AssertionError(
                "uya_ffmpeg_direct_sender exited before writing an SDP answer\n"
                f"returncode={proc.returncode}\n"
                f"stdout:\n{read_text_tail(stdout_path)}\n"
                f"stderr:\n{read_text_tail(stderr_path)}"
            )
        time.sleep(0.1)
    if last_json_error is not None:
        raise TimeoutError(f"Uya answer JSON was not complete before timeout: {last_json_error}")
    raise TimeoutError("uya_ffmpeg_direct_sender did not write an SDP answer before timeout")


def start_uya_direct_sender(
    offer: dict[str, str],
    media_path: Path,
    workdir: Path,
    raw_video_path: Path | None = None,
    raw_audio_path: Path | None = None,
) -> UyaDirectSenderHandle:
    if not UYA_DIRECT_SENDER_MAIN.exists():
        raise AssertionError(
            "Uya direct sender CLI is not implemented yet: expected "
            f"{UYA_DIRECT_SENDER_MAIN.relative_to(REPO_ROOT)}"
        )
    if not UYA_BIN.exists():
        raise AssertionError(f"Uya compiler/runtime not found at {UYA_BIN}")

    offer_path = workdir / "chrome_offer.json"
    answer_path = workdir / "uya_answer.json"
    diagnostics_path = workdir / "uya_direct_sender_diagnostics.json"
    stdout_path = workdir / "uya_direct_sender.stdout.log"
    stderr_path = workdir / "uya_direct_sender.stderr.log"
    offer_path.write_text(json.dumps(offer), encoding="utf-8")

    stdout_file = stdout_path.open("w", encoding="utf-8")
    stderr_file = stderr_path.open("w", encoding="utf-8")
    try:
        command = [
            str(UYA_BIN),
            "run",
            str(UYA_DIRECT_SENDER_MAIN.relative_to(REPO_ROOT)),
            "--",
            "--offer-json",
            str(offer_path),
            "--media",
            str(media_path),
            "--answer-json",
            str(answer_path),
            "--diagnostics-json",
            str(diagnostics_path),
            "--codec",
            "ffmpeg",
        ]
        if raw_video_path is not None:
            command.extend(["--raw-video-i420", str(raw_video_path)])
        if raw_audio_path is not None:
            command.extend(["--raw-audio-s16le", str(raw_audio_path)])
        proc = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=stdout_file,
            stderr=stderr_file,
        )
    finally:
        stdout_file.close()
        stderr_file.close()

    try:
        answer_sdp = wait_for_answer(proc, answer_path, stdout_path, stderr_path)
    except Exception:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5.0)
        raise
    return UyaDirectSenderHandle(
        proc=proc,
        answer_sdp=answer_sdp,
        diagnostics_path=diagnostics_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def read_sender_diagnostics(path: Path) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    if path.exists():
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            diagnostics = parsed
    return diagnostics


def wait_for_uya_direct_sender(handle: UyaDirectSenderHandle) -> dict[str, Any]:
    try:
        returncode = handle.proc.wait(timeout=DEFAULT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        handle.proc.terminate()
        try:
            handle.proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            handle.proc.kill()
            handle.proc.wait(timeout=5.0)
        raise AssertionError(
            sender_failure_message(
                "uya_ffmpeg_direct_sender did not exit after Chrome received media",
                handle,
                handle.stdout_path,
                handle.stderr_path,
            )
        ) from exc
    if returncode != 0:
        raise AssertionError(
            sender_failure_message(
                "uya_ffmpeg_direct_sender failed while Chrome was receiving media",
                handle,
                handle.stdout_path,
                handle.stderr_path,
            )
        )
    return read_sender_diagnostics(handle.diagnostics_path)


def stop_uya_direct_sender(handle: UyaDirectSenderHandle | None) -> None:
    if handle is None or handle.proc.poll() is not None:
        return
    handle.proc.terminate()
    try:
        handle.proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        handle.proc.kill()
        handle.proc.wait(timeout=5.0)


class ManualPreviewState:
    def __init__(
        self,
        preview_dir: Path,
        media_path: Path,
        raw_video_path: Path | None = None,
        raw_audio_path: Path | None = None,
    ) -> None:
        self.preview_dir = preview_dir
        self.media_path = media_path
        self.raw_video_path = raw_video_path
        self.raw_audio_path = raw_audio_path
        self.sessions_dir = preview_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, ManualPreviewSession] = {}
        self.lock = threading.Lock()

    def start_call(self, offer: dict[str, str]) -> tuple[str, str]:
        session_id = uuid.uuid4().hex[:12]
        workdir = self.sessions_dir / session_id
        workdir.mkdir(parents=True, exist_ok=False)
        handle = start_uya_direct_sender(
            offer,
            self.media_path,
            workdir,
            raw_video_path=self.raw_video_path,
            raw_audio_path=self.raw_audio_path,
        )
        with self.lock:
            self.sessions[session_id] = ManualPreviewSession(session_id, handle, workdir)
        return session_id, handle.answer_sdp

    def finish_call(self, session_id: str) -> dict[str, Any]:
        session = self._pop_session(session_id)
        diagnostics = wait_for_uya_direct_sender(session.handle)
        return diagnostics

    def stop_call(self, session_id: str) -> dict[str, Any]:
        session = self._pop_session(session_id)
        stop_uya_direct_sender(session.handle)
        return read_sender_diagnostics(session.handle.diagnostics_path)

    def stop_all(self) -> None:
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions:
            stop_uya_direct_sender(session.handle)

    def _pop_session(self, session_id: str) -> ManualPreviewSession:
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if session is None:
            raise AssertionError(f"unknown manual preview session: {session_id}")
        return session


class ManualPreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, directory: str, state: ManualPreviewState, **kwargs: Any) -> None:
        self.preview_state = state
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:
        try:
            if self.path == "/api/start-call":
                body = self._read_json_body()
                offer = body.get("offer") if isinstance(body, dict) else None
                if not isinstance(offer, dict) or offer.get("type") != "offer" or not isinstance(offer.get("sdp"), str):
                    raise AssertionError("manual preview start-call requires an offer SDP")
                session_id, answer_sdp = self.preview_state.start_call(
                    {"type": "offer", "sdp": str(offer["sdp"])}
                )
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "sessionId": session_id,
                        "answer": {"type": "answer", "sdp": answer_sdp},
                    },
                )
                return
            if self.path == "/api/finish-call":
                body = self._read_json_body()
                session_id = self._body_session_id(body)
                diagnostics = self.preview_state.finish_call(session_id)
                self._send_json(200, {"ok": True, "diagnostics": diagnostics})
                return
            if self.path == "/api/stop-call":
                body = self._read_json_body()
                session_id = self._body_session_id(body)
                diagnostics = self.preview_state.stop_call(session_id)
                self._send_json(200, {"ok": True, "diagnostics": diagnostics})
                return
            self._send_json(404, {"ok": False, "error": "unknown preview endpoint"})
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})

    def _read_json_body(self) -> Any:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        if content_length > 1024 * 1024:
            raise AssertionError("manual preview request body is too large")
        return json.loads(self.rfile.read(content_length).decode("utf-8"))

    def _body_session_id(self, body: Any) -> str:
        if not isinstance(body, dict) or not isinstance(body.get("sessionId"), str) or not body["sessionId"]:
            raise AssertionError("manual preview endpoint requires sessionId")
        return str(body["sessionId"])

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_manual_preview_server(
    preview_dir: Path,
    media_path: Path,
    raw_video_path: Path | None = None,
    raw_audio_path: Path | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread, int, ManualPreviewState]:
    state = ManualPreviewState(preview_dir, media_path, raw_video_path, raw_audio_path)
    port = find_free_port()
    handler = partial(ManualPreviewHandler, directory=str(preview_dir), state=state)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port, state


def run_chrome_page(tempdir_path: Path, media_path: Path) -> dict[str, Any]:
    browser_exe = find_browser_executable()
    server, thread, http_port = start_http_server(tempdir_path)
    browser_user_data_dir = tempdir_path / "profile"
    browser_user_data_dir.mkdir(exist_ok=True)
    debug_port = find_free_port()
    proc = subprocess.Popen(
        [
            str(browser_exe),
            f"--remote-debugging-port={debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--autoplay-policy=no-user-gesture-required",
            "--user-data-dir=" + str(browser_user_data_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        version_url = f"http://127.0.0.1:{debug_port}/json/version"
        deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
        version: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(version_url, timeout=1.0) as response:
                    version = json.loads(response.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(0.2)
        require(version is not None, "browser remote debugging endpoint did not become ready")
        browser_ws_url = str(version.get("webSocketDebuggerUrl"))
        require(browser_ws_url.startswith("ws://"), "browser version endpoint missing websocket url")

        client = CDPClient(browser_ws_url)
        client.connect()
        sender_handle: UyaDirectSenderHandle | None = None
        try:
            target = client.command("Target.createTarget", {"url": "about:blank"})
            target_id = str(target["targetId"])
            attached = client.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
            session_id = str(attached["sessionId"])
            client.command("Runtime.enable", session_id=session_id)
            client.command("Page.enable", session_id=session_id)
            client.command("Page.navigate", {"url": f"http://127.0.0.1:{http_port}/index.html"}, session_id=session_id)
            offer = wait_for_offer(client, session_id)
            sender_handle = start_uya_direct_sender(offer, media_path, tempdir_path)
            apply_answer(client, session_id, sender_handle.answer_sdp)
            result = wait_for_result(client, session_id)
            result["senderDiagnostics"] = wait_for_uya_direct_sender(sender_handle)
            return result
        finally:
            stop_uya_direct_sender(sender_handle)
            client.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def run_manual_preview_chrome_page(
    preview_dir: Path,
    media_path: Path,
    raw_video_path: Path | None = None,
    raw_audio_path: Path | None = None,
) -> dict[str, Any]:
    browser_exe = find_browser_executable()
    server, thread, http_port, state = start_manual_preview_server(
        preview_dir,
        media_path,
        raw_video_path=raw_video_path,
        raw_audio_path=raw_audio_path,
    )
    browser_user_data_dir = preview_dir / "manual-profile"
    browser_user_data_dir.mkdir(exist_ok=True)
    debug_port = find_free_port()
    proc = subprocess.Popen(
        [
            str(browser_exe),
            f"--remote-debugging-port={debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--autoplay-policy=no-user-gesture-required",
            "--user-data-dir=" + str(browser_user_data_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        version_url = f"http://127.0.0.1:{debug_port}/json/version"
        deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
        version: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(version_url, timeout=1.0) as response:
                    version = json.loads(response.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(0.2)
        require(version is not None, "browser remote debugging endpoint did not become ready")
        browser_ws_url = str(version.get("webSocketDebuggerUrl"))
        require(browser_ws_url.startswith("ws://"), "browser version endpoint missing websocket url")

        client = CDPClient(browser_ws_url)
        client.connect()
        try:
            target = client.command("Target.createTarget", {"url": "about:blank"})
            target_id = str(target["targetId"])
            attached = client.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
            session_id = str(attached["sessionId"])
            client.command("Runtime.enable", session_id=session_id)
            client.command("Page.enable", session_id=session_id)
            client.command("Page.navigate", {"url": f"http://127.0.0.1:{http_port}/index.html"}, session_id=session_id)
            wait_for_manual_preview_ready(client, session_id)
            click_manual_preview_start(client, session_id)
            return wait_for_manual_preview_result(client, session_id)
        finally:
            client.close()
    finally:
        state.stop_all()
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def validate_media_result(result: dict[str, Any], require_closed: bool) -> None:
    require(result.get("ok") is True, f"browser page reported failure: {result}")
    if require_closed:
        require(result.get("receiverConnectionState") == "closed", "Chrome receiver should be closed after cleanup")
    tracks = result.get("tracks")
    require(isinstance(tracks, list) and "audio" in tracks, "Chrome did not surface an audio track")
    require(isinstance(tracks, list) and "video" in tracks, "Chrome did not surface a video track")
    require(int(result.get("audioPacketsReceived", 0)) > 0, "Chrome received no Uya audio packets")
    require(int(result.get("videoPacketsReceived", 0)) > 0, "Chrome received no Uya video packets")
    require(int(result.get("videoFramesDecoded", 0)) > 0, "Chrome decoded no Uya VP8 frames")
    offer_sdp = str(result.get("offerSdp", "")).lower()
    answer_sdp = str(result.get("answerSdp", "")).lower()
    require("m=audio" in offer_sdp and "m=audio" in answer_sdp, "SDP missing audio m-line")
    require("m=video" in offer_sdp and "m=video" in answer_sdp, "SDP missing video m-line")
    require("opus/48000" in offer_sdp or "opus/48000" in answer_sdp, "SDP missing Opus negotiation")
    require("vp8/90000" in offer_sdp or "vp8/90000" in answer_sdp, "SDP missing VP8 negotiation")
    diagnostics = result.get("senderDiagnostics")
    require(isinstance(diagnostics, dict), "Uya sender diagnostics missing")
    require(diagnostics.get("codecProvider") == "ffmpeg", "Uya sender did not select the FFmpeg codec provider")
    require(diagnostics.get("codecProviderSwitchable") is True, "Uya sender codec provider is not switchable")
    require(diagnostics.get("codecProviderReady") is True, "Uya sender FFmpeg codec provider is not ready")
    require(diagnostics.get("codecProviderUsesExtern") is True, "FFmpeg codec provider should be the only extern provider")
    require(diagnostics.get("codecBridgeRequired") is False, "FFmpeg direct sender should not require the Uya codec bridge")
    require(diagnostics.get("ffmpegMediaPathSeen") is True, "Uya sender did not report the FFmpeg media path")
    require(int(diagnostics.get("rtpPackets", 0)) > 0, "Uya sender reported no RTP packets")
    require(int(diagnostics.get("srtcpPackets", 0)) > 0, "Uya sender reported no SRTCP packets")
    require(int(diagnostics.get("rtcpSenderReports", 0)) > 0, "Uya sender reported no RTCP Sender Reports")
    require(int(diagnostics.get("srtcpPacketsReceived", 0)) > 0, "Uya sender received no SRTCP feedback packets from Chrome")
    require(int(diagnostics.get("rtcpPacketsReceived", 0)) > 0, "Uya sender parsed no RTCP receiver feedback from Chrome")
    receiver_reports = int(diagnostics.get("rtcpReceiverReportsReceived", 0))
    feedback_packets = int(diagnostics.get("rtcpFeedbackPacketsReceived", 0))
    require(receiver_reports + feedback_packets > 0, "Uya sender parsed neither RTCP Receiver Reports nor RTP/PS feedback")
    require(int(diagnostics.get("udpPackets", 0)) > 0, "Uya sender reported no UDP packets")


def validate_browser_result(result: dict[str, Any]) -> None:
    validate_media_result(result, require_closed=True)


def validate_manual_preview_result(result: dict[str, Any]) -> None:
    validate_media_result(result, require_closed=False)
    progress = result.get("progress")
    require(isinstance(progress, list) and "playing" in progress, "manual preview did not reach playing state")
    require(isinstance(progress, list) and "complete" in progress, "manual preview did not reach complete state")


def assert_contract() -> str:
    source = Path(__file__).read_text(encoding="utf-8")
    required = [
        "UyaDirectSender",
        "uya_ffmpeg_direct_sender",
        "rtp_packetize_encoded_frame",
        "SRTP/SRTCP -> UDP",
        "rtcpSenderReports",
        "rtcpPacketsReceived",
        "recvonly",
        "Start Uya Video",
        "remoteVideo",
        "/api/start-call",
        "/api/finish-call",
        "window.__uyaManualPreviewResult",
        "run_manual_preview_chrome_page",
        "prepare_mp4_raw_preview",
        "--source-mp4",
        "--raw-video-i420",
        "--raw-audio-s16le",
        "preview_manifest.json",
    ]
    missing = [item for item in required if item not in source]
    if missing:
        raise AssertionError(f"direct sender harness missing required tokens: {missing}")
    return "ffmpeg chrome direct sender harness contract checks passed"


def run_flow(keep_temp: bool = False) -> str:
    with tempfile.TemporaryDirectory(prefix="webrtc-ffmpeg-chrome-direct-") as tmp:
        tempdir_path = Path(tmp)
        media_path, ffmpeg_stats = generate_ffmpeg_media(tempdir_path)
        page_path = tempdir_path / "index.html"
        page_path.write_text(make_call_page(), encoding="utf-8")
        result = run_chrome_page(tempdir_path, media_path)
        validate_browser_result(result)
        diagnostics = result.get("senderDiagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}

        if keep_temp:
            kept = Path(tempfile.mkdtemp(prefix="webrtc-ffmpeg-chrome-direct-kept-"))
            for path in tempdir_path.iterdir():
                if path.is_file():
                    (kept / path.name).write_bytes(path.read_bytes())
            temp_note = f" kept={kept}"
        else:
            temp_note = ""

        return (
            "ffmpeg chrome direct call checks passed: "
            f"source_audio_codec={ffmpeg_stats['audio_codec']} "
            f"source_audio_packets={ffmpeg_stats['audio_packets']} "
            f"source_video_codec={ffmpeg_stats['video_codec']} "
            f"source_video_packets={ffmpeg_stats['video_packets']} "
            f"chrome_audio_packets={result.get('audioPacketsReceived')} "
            f"chrome_video_packets={result.get('videoPacketsReceived')} "
            f"chrome_video_frames={result.get('videoFramesDecoded')}"
            f" sender_ffmpeg_frames={diagnostics.get('ffmpegFrames')} "
            f"sender_rtp_packets={diagnostics.get('rtpPackets')} "
            f"sender_srtp_packets={diagnostics.get('srtpPackets')} "
            f"sender_srtcp_packets={diagnostics.get('srtcpPackets')} "
            f"sender_rtcp_sender_reports={diagnostics.get('rtcpSenderReports')} "
            f"sender_srtcp_packets_received={diagnostics.get('srtcpPacketsReceived')} "
            f"sender_rtcp_packets_received={diagnostics.get('rtcpPacketsReceived')} "
            f"sender_rtcp_receiver_reports={diagnostics.get('rtcpReceiverReportsReceived')} "
            f"sender_rtcp_feedback_packets_received={diagnostics.get('rtcpFeedbackPacketsReceived')} "
            f"sender_udp_packets={diagnostics.get('udpPackets')}"
            f"{temp_note}"
        )


def run_manual_preview_flow(keep_temp: bool = False, source_mp4: Path | None = None) -> str:
    with tempfile.TemporaryDirectory(prefix="webrtc-ffmpeg-chrome-manual-preview-") as tmp:
        tempdir_path = Path(tmp)
        assets = prepare_preview_media(tempdir_path, source_mp4=source_mp4)
        page_path = tempdir_path / "index.html"
        page_path.write_text(make_preview_page(assets.ffmpeg_stats), encoding="utf-8")
        result = run_manual_preview_chrome_page(
            tempdir_path,
            assets.media_path,
            raw_video_path=assets.raw_video_path,
            raw_audio_path=assets.raw_audio_path,
        )
        validate_manual_preview_result(result)
        diagnostics = result.get("senderDiagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}

        if keep_temp:
            kept = Path(tempfile.mkdtemp(prefix="webrtc-ffmpeg-chrome-manual-preview-kept-"))
            for path in tempdir_path.iterdir():
                target = kept / path.name
                if path.is_dir():
                    shutil.copytree(path, target)
                elif path.is_file():
                    target.write_bytes(path.read_bytes())
            temp_note = f" kept={kept}"
        else:
            temp_note = ""

        return (
            "ffmpeg chrome manual preview checks passed: "
            f"source_kind={assets.ffmpeg_stats.get('source_kind')} "
            f"chrome_audio_packets={result.get('audioPacketsReceived')} "
            f"chrome_video_packets={result.get('videoPacketsReceived')} "
            f"chrome_video_frames={result.get('videoFramesDecoded')}"
            f" sender_ffmpeg_frames={diagnostics.get('ffmpegFrames')} "
            f"sender_rtp_packets={diagnostics.get('rtpPackets')} "
            f"sender_srtp_packets={diagnostics.get('srtpPackets')} "
            f"sender_srtcp_packets={diagnostics.get('srtcpPackets')} "
            f"sender_rtcp_sender_reports={diagnostics.get('rtcpSenderReports')} "
            f"sender_srtcp_packets_received={diagnostics.get('srtcpPacketsReceived')} "
            f"sender_rtcp_packets_received={diagnostics.get('rtcpPacketsReceived')} "
            f"sender_rtcp_receiver_reports={diagnostics.get('rtcpReceiverReportsReceived')} "
            f"sender_udp_packets={diagnostics.get('udpPackets')}"
            f"{temp_note}"
        )


def write_preview_manifest(preview_dir: Path, assets: PreviewMediaAssets) -> None:
    manifest = {
        "media_path": str(assets.media_path),
        "raw_video_path": str(assets.raw_video_path) if assets.raw_video_path is not None else "",
        "raw_audio_path": str(assets.raw_audio_path) if assets.raw_audio_path is not None else "",
        "ffmpeg_stats": assets.ffmpeg_stats,
    }
    (preview_dir / "preview_manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def read_preview_manifest(preview_dir: Path) -> PreviewMediaAssets:
    manifest_path = preview_dir / "preview_manifest.json"
    if not manifest_path.exists():
        media_path = preview_dir / "ffmpeg_chrome_direct.webm"
        if not media_path.exists():
            raise AssertionError(f"manual preview media file is missing: {media_path}")
        return PreviewMediaAssets(media_path=media_path, ffmpeg_stats={})
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("media_path"), str):
        raise AssertionError(f"invalid manual preview manifest: {manifest_path}")
    raw_video_text = str(manifest.get("raw_video_path") or "")
    raw_audio_text = str(manifest.get("raw_audio_path") or "")
    ffmpeg_stats = manifest.get("ffmpeg_stats") if isinstance(manifest.get("ffmpeg_stats"), dict) else {}
    return PreviewMediaAssets(
        media_path=Path(str(manifest["media_path"])),
        raw_video_path=Path(raw_video_text) if raw_video_text else None,
        raw_audio_path=Path(raw_audio_text) if raw_audio_text else None,
        ffmpeg_stats=ffmpeg_stats,
    )


def write_preview(preview_dir: Path, source_mp4: Path | None = None) -> str:
    preview_dir.mkdir(parents=True, exist_ok=True)
    assets = prepare_preview_media(preview_dir, source_mp4=source_mp4)
    page_path = preview_dir / "index.html"
    page_path.write_text(make_preview_page(assets.ffmpeg_stats), encoding="utf-8")
    write_preview_manifest(preview_dir, assets)
    source_note = f" source={assets.media_path}" if source_mp4 is not None else ""
    return f"ffmpeg chrome direct preview written: dir={preview_dir} page={page_path}{source_note}"


def serve_preview(preview_dir: Path) -> int:
    assets = read_preview_manifest(preview_dir)
    server, thread, http_port, state = start_manual_preview_server(
        preview_dir,
        assets.media_path,
        raw_video_path=assets.raw_video_path,
        raw_audio_path=assets.raw_audio_path,
    )
    url = f"http://127.0.0.1:{http_port}/"
    print(f"ffmpeg chrome direct preview serving: {url}", flush=True)
    print("press Ctrl-C to stop", flush=True)
    try:
        while True:
            time.sleep(3600.0)
    except KeyboardInterrupt:
        print("ffmpeg chrome direct preview stopped", flush=True)
        return 0
    finally:
        state.stop_all()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-temp", action="store_true", help="copy generated headless-test artifacts to a retained temp directory")
    parser.add_argument("--preview-dir", type=Path, help="write a manual Chrome receiver preview page into this directory")
    parser.add_argument("--source-mp4", type=Path, help="prepare this MP4 as the raw preview source for the Uya sender")
    parser.add_argument("--serve-preview", action="store_true", help="serve the manual preview page and wait until Ctrl-C")
    parser.add_argument("--manual-preview-e2e", action="store_true", help="launch Chrome, click the manual preview button, and verify Uya-originated media")
    parser.add_argument("--contract-only", action="store_true", help="validate the direct sender harness contract without launching Chrome")
    args = parser.parse_args()
    try:
        if args.contract_only:
            print(assert_contract(), flush=True)
            return 0
        if args.manual_preview_e2e:
            print(run_manual_preview_flow(args.keep_temp, source_mp4=args.source_mp4), flush=True)
            return 0
        if args.preview_dir is not None or args.serve_preview:
            preview_dir = args.preview_dir or Path(tempfile.mkdtemp(prefix="webrtc-ffmpeg-chrome-direct-preview-"))
            print(write_preview(preview_dir, source_mp4=args.source_mp4), flush=True)
            if args.serve_preview:
                return serve_preview(preview_dir)
            return 0

        print(run_flow(args.keep_temp))
        return 0
    except SkipFlow as exc:
        print(f"ffmpeg chrome direct call skipped: {exc}")
        return 0
    except (AssertionError, InteropError, TimeoutError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
