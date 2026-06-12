#!/usr/bin/env python3
"""Validate Chrome video decode from live pure-Uya VP8 encoding.

The raw I420 source is prepared first, then the sibling pure Uya ``../vp8``
bridge encodes frames inside the Uya sender's live send loop:

    raw I420 -> Uya VP8 bridge -> EncodedFrame -> RTP/SRTP/UDP
    -> Chrome recvonly VP8 inbound RTP
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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
from ffmpeg_chrome_call import (
    apply_answer,
    click_manual_preview_start,
    first_video_stream,
    media_duration_timeout_seconds,
    mp4_duration_seconds,
    probe_streams,
    read_text_tail,
    stream_display_dimensions,
    wait_for_manual_preview_ready,
    wait_for_answer,
    wait_for_offer,
    wait_for_manual_preview_result,
    wait_for_result,
)
from ffmpeg_codec_flow import require_tool, run


REPO_ROOT = Path(__file__).resolve().parent.parent
UYA_BIN = REPO_ROOT.parent / "uya" / "bin" / "uya"
UYA_LIB = REPO_ROOT.parent / "uya" / "lib"
VP8_REPO = REPO_ROOT.parent / "vp8"
UYA_DIRECT_SENDER_MAIN = REPO_ROOT / "src" / "webrtc_uya_vp8_direct_sender_main.uya"
VIDEO_WIDTH = 32
VIDEO_HEIGHT = 18
MEDIA_DURATION_US = 3_000_000
UYA_VP8_DEFAULT_PREVIEW_FPS = 30
UYA_VP8_AUTO_PREVIEW_FPS = 0
UYA_VP8_DEFAULT_FRAME_DURATION_US = 33_333
UYA_VP8_DEFAULT_PREVIEW_MAX_WIDTH = 160
UYA_VP8_DEFAULT_PREVIEW_MAX_DURATION_SECONDS = 2.0
UYA_VP8_FORCE_SCALAR_ENV = "UYA_VP8_FORCE_SCALAR"
UYA_VP8_PREVIEW_CFLAGS_ENV = "UYA_VP8_PREVIEW_CFLAGS"


@dataclass
class SenderHandle:
    proc: subprocess.Popen[str]
    answer_sdp: str
    diagnostics_path: Path
    stdout_path: Path
    stderr_path: Path
    media_duration_us: int = MEDIA_DURATION_US


@dataclass
class UyaVp8PreviewAssets:
    raw_video_path: Path
    source_stats: dict[str, int | str]
    video_width: int
    video_height: int
    media_duration_us: int
    video_frame_duration_us: int = UYA_VP8_DEFAULT_FRAME_DURATION_US


@dataclass
class ManualVp8PreviewSession:
    session_id: str
    handle: SenderHandle
    workdir: Path


@dataclass
class PreviewSenderExecutable:
    path: Path
    stage_src: Path
    stdout_path: Path
    stderr_path: Path


def make_video_only_page() -> str:
    return textwrap.dedent(
        """
        <!doctype html>
        <meta charset="utf-8">
        <title>Uya VP8 Direct Chrome Receiver</title>
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
          if (peer.iceGatheringState === 'complete') return;
          await waitForEvent(peer, 'icegatheringstatechange', () => peer.iceGatheringState === 'complete');
        }

        function preferredCodecs(kind, mimeType) {
          const capabilities = RTCRtpReceiver.getCapabilities(kind);
          if (!capabilities || !capabilities.codecs) return [];
          const wanted = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase() === mimeType);
          const helpers = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase().indexOf('rtx') >= 0);
          return wanted.concat(helpers);
        }

        function makeSyntheticVideoTrack() {
          const canvas = document.createElement('canvas');
          canvas.width = 160;
          canvas.height = 90;
          const ctx = canvas.getContext('2d');
          let frame = 0;
          function draw() {
            ctx.fillStyle = '#102030';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#14b8a6';
            ctx.fillRect((frame * 5) % canvas.width, 12, 38, 24);
            ctx.fillStyle = '#f97316';
            ctx.fillRect(18, (frame * 3) % canvas.height, 24, 18);
            ctx.fillStyle = '#ffffff';
            ctx.font = '16px sans-serif';
            ctx.fillText(String(frame), 8, 82);
            frame += 1;
          }
          draw();
          const interval = setInterval(draw, 66);
          const stream = canvas.captureStream(15);
          const track = stream.getVideoTracks()[0];
          window.__uyaOutboundVideo = {canvas, stream, track, interval};
          return track;
        }

        async function waitForVideoInbound(receiver) {
          const deadline = Date.now() + 12000;
          while (Date.now() < deadline) {
            const stats = await receiver.getStats();
            for (const stat of stats.values()) {
              if (stat.type !== 'inbound-rtp') continue;
              if (stat.kind !== 'video' && stat.mediaType !== 'video') continue;
              const packets = stat.packetsReceived || 0;
              const frames = stat.framesDecoded || stat.framesReceived || 0;
              let codecMimeType = '';
              if (stat.codecId) {
                const codec = stats.get(stat.codecId);
                if (codec && codec.mimeType) codecMimeType = String(codec.mimeType);
              }
              if (packets > 0 && frames > 0) {
                return {
                  packetsReceived: packets,
                  framesDecoded: frames,
                  frameWidth: stat.frameWidth || 0,
                  frameHeight: stat.frameHeight || 0,
                  codecMimeType
                };
              }
            }
            await delay(100);
          }
          return {packetsReceived: 0, framesDecoded: 0, frameWidth: 0, frameHeight: 0, codecMimeType: ''};
        }

        async function readVideoOutbound(sender) {
          const stats = await sender.getStats();
          for (const stat of stats.values()) {
            if (stat.type !== 'outbound-rtp') continue;
            if (stat.kind !== 'video' && stat.mediaType !== 'video') continue;
            return {
              packetsSent: stat.packetsSent || 0,
              framesEncoded: stat.framesEncoded || 0
            };
          }
          return {packetsSent: 0, framesEncoded: 0};
        }

        async function runReceiver() {
          mark('start');
          const receiver = new RTCPeerConnection({iceServers: []});
          window.__uyaDirectPeer = receiver;
          const states = [];
          const tracks = [];
          receiver.addEventListener('connectionstatechange', () => states.push('receiver:' + receiver.connectionState));
          receiver.addEventListener('iceconnectionstatechange', () => states.push('ice:' + receiver.iceConnectionState));
          receiver.addEventListener('track', event => tracks.push(event.track.kind));

          const audioTransceiver = receiver.addTransceiver('audio', {direction: 'recvonly'});
          const opus = preferredCodecs('audio', 'audio/opus');
          if (opus.length > 0) audioTransceiver.setCodecPreferences(opus);
          const outboundTrack = makeSyntheticVideoTrack();
          const videoTransceiver = receiver.addTransceiver(outboundTrack, {direction: 'sendrecv'});
          const vp8 = preferredCodecs('video', 'video/vp8');
          if (vp8.length > 0) videoTransceiver.setCodecPreferences(vp8);
          mark('sendrecv-video-transceiver');

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
            const video = receiver.getReceivers().find(item => item.track && item.track.kind === 'video');
            if (!video) throw new Error('Chrome video receiver lookup failed');
            const firstVideoStats = await waitForVideoInbound(video);
            if (firstVideoStats.packetsReceived <= 0 || firstVideoStats.framesDecoded <= 0) {
              throw new Error('Chrome decoded no Uya VP8 frames');
            }
            mark('media-received');
            await delay(2500);
            const outboundVideoStats = await readVideoOutbound(videoTransceiver.sender);
            mark('rtcp-feedback-window');
            const finalVideoStats = await waitForVideoInbound(video);
            receiver.close();
            clearInterval(window.__uyaOutboundVideo.interval);
            outboundTrack.stop();
            await delay(25);
            window.__ffmpegChromeCallResult = {
              ok: true,
              browser: navigator.userAgent,
              states,
              tracks,
              receiverConnectionState: receiver.connectionState,
              audioPacketsReceived: 0,
              videoPacketsReceived: finalVideoStats.packetsReceived,
              videoFramesDecoded: finalVideoStats.framesDecoded,
              videoFrameWidth: finalVideoStats.frameWidth,
              videoFrameHeight: finalVideoStats.frameHeight,
              videoCodecMimeType: finalVideoStats.codecMimeType,
              outboundVideoPacketsSent: outboundVideoStats.packetsSent,
              outboundVideoFramesEncoded: outboundVideoStats.framesEncoded,
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


def make_manual_preview_page(source_stats: dict[str, int | str]) -> str:
    stats_json = json.dumps(source_stats, sort_keys=True)
    page = textwrap.dedent(
        """
        <!doctype html>
        <meta charset="utf-8">
        <title>Uya VP8 Direct Chrome Preview</title>
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
            <h1>Uya VP8 Direct Chrome Preview</h1>
            <div class="actions">
              <button id="start">Start Uya VP8</button>
              <button class="secondary" id="stop" disabled>Stop</button>
            </div>
          </header>
          <section class="stage">
            <video id="remoteVideo" autoplay playsinline controls muted></video>
          </section>
          <section class="status">
            <div class="metric"><span class="label">State</span><span class="value" id="state">idle</span></div>
            <div class="metric"><span class="label">Video Packets</span><span class="value" id="videoPackets">0</span></div>
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
        const videoPackets = document.getElementById('videoPackets');
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
          setState('failed');
          writeLog(message + ': ' + detail.join('\\n'));
          window.__uyaManualPreviewResult = {
            ok: false,
            error: message,
            detail: detail.join('\\n'),
            progress: window.__uyaManualPreviewProgress.slice()
          };
          start.disabled = false;
          stop.disabled = true;
        }

        async function postJson(path, body) {
          const response = await fetch(path, {
            method: 'POST',
            headers: {'content-type': 'application/json'},
            body: JSON.stringify(body)
          });
          const payload = await response.json();
          if (!response.ok || !payload.ok) {
            throw new Error(payload.error || ('request failed: ' + path));
          }
          return payload;
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
          if (peer.iceGatheringState === 'complete') return;
          await waitForEvent(peer, 'icegatheringstatechange', () => peer.iceGatheringState === 'complete');
        }

        function preferredCodecs(kind, mimeType) {
          const capabilities = RTCRtpReceiver.getCapabilities(kind);
          if (!capabilities || !capabilities.codecs) return [];
          const wanted = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase() === mimeType);
          const helpers = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase().indexOf('rtx') >= 0);
          return wanted.concat(helpers);
        }

        async function readVideoInbound(rtpReceiver) {
          const stats = await rtpReceiver.getStats();
          for (const stat of stats.values()) {
            if (stat.type !== 'inbound-rtp') continue;
            if (stat.kind !== 'video' && stat.mediaType !== 'video') continue;
            let codecMimeType = '';
            if (stat.codecId) {
              const codec = stats.get(stat.codecId);
              if (codec && codec.mimeType) codecMimeType = String(codec.mimeType);
            }
            return {
              packetsReceived: stat.packetsReceived || 0,
              framesDecoded: stat.framesDecoded || stat.framesReceived || 0,
              frameWidth: stat.frameWidth || 0,
              frameHeight: stat.frameHeight || 0,
              codecMimeType
            };
          }
          return {packetsReceived: 0, framesDecoded: 0, frameWidth: 0, frameHeight: 0, codecMimeType: ''};
        }

        async function waitForVideo(videoReceiver) {
          const deadline = Date.now() + 12000;
          while (Date.now() < deadline) {
            const stats = await readVideoInbound(videoReceiver);
            videoPackets.textContent = String(stats.packetsReceived);
            videoFrames.textContent = String(stats.framesDecoded);
            if (stats.packetsReceived > 0 && stats.framesDecoded > 0) return stats;
            await delay(150);
          }
          throw new Error('Chrome did not decode Uya VP8 media before timeout');
        }

        async function stopSession() {
          if (sessionId) {
            const id = sessionId;
            sessionId = '';
            await postJson('/api/stop-call', {sessionId: id}).catch(error => writeLog(String(error.message || error)));
          }
          if (receiver) receiver.close();
          stop.disabled = true;
          start.disabled = false;
        }

        async function runOneClickPreview() {
          const states = [];
          const tracks = [];
          setState('offer');
          writeLog('uya_vp8=' + JSON.stringify(sourceStats));
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
            if (event.track.kind === 'video') {
              remoteStream.addTrack(event.track);
              remoteVideo.play().catch(error => writeLog('video.play: ' + String(error.message || error)));
            }
          });

          const audioTransceiver = receiver.addTransceiver('audio', {direction: 'recvonly'});
          const opus = preferredCodecs('audio', 'audio/opus');
          if (opus.length > 0) audioTransceiver.setCodecPreferences(opus);
          const videoTransceiver = receiver.addTransceiver('video', {direction: 'recvonly'});
          const vp8 = preferredCodecs('video', 'video/vp8');
          if (vp8.length > 0) videoTransceiver.setCodecPreferences(vp8);

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

          const video = receiver.getReceivers().find(item => item.track && item.track.kind === 'video');
          if (!video) throw new Error('Chrome video receiver lookup failed');
          const firstStats = await waitForVideo(video);
          const playMs = Math.max(1000, Math.ceil(Number(sourceStats.preview_duration_us || 3000000) / 1000) + 1000);
          await delay(playMs);
          const finalVideoStats = await readVideoInbound(video);
          videoPackets.textContent = String(finalVideoStats.packetsReceived || firstStats.packetsReceived);
          videoFrames.textContent = String(finalVideoStats.framesDecoded || firstStats.framesDecoded);
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
            videoPacketsReceived: finalVideoStats.packetsReceived || firstStats.packetsReceived,
            videoFramesDecoded: finalVideoStats.framesDecoded || firstStats.framesDecoded,
            videoFrameWidth: finalVideoStats.frameWidth || firstStats.frameWidth || remoteVideo.videoWidth || 0,
            videoFrameHeight: finalVideoStats.frameHeight || firstStats.frameHeight || remoteVideo.videoHeight || 0,
            remoteVideoWidth: remoteVideo.videoWidth || 0,
            remoteVideoHeight: remoteVideo.videoHeight || 0,
            videoCodecMimeType: finalVideoStats.codecMimeType || firstStats.codecMimeType,
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
            fail('Uya VP8 preview call failed', error);
          }
        });
        stop.addEventListener('click', async () => {
          if (!finished) setState('stopping');
          await stopSession();
        });

        window.addEventListener('beforeunload', () => {
          if (sessionId) {
            navigator.sendBeacon('/api/stop-call', JSON.stringify({sessionId}));
          }
        });

        writeLog('ready');
        </script>
        """
    ).strip()
    return page.replace("__SOURCE_STATS__", stats_json)


def stage_vp8_package(stage_root: Path) -> Path:
    if not VP8_REPO.exists():
        raise AssertionError(f"sibling VP8 repository is missing: {VP8_REPO}")
    if not UYA_DIRECT_SENDER_MAIN.exists():
        raise AssertionError(f"Uya VP8 live sender is missing: {UYA_DIRECT_SENDER_MAIN}")
    if not UYA_LIB.exists():
        raise AssertionError(f"Uya standard library is missing: {UYA_LIB}")
    stage_src = stage_root / "src"
    shutil.rmtree(stage_root, ignore_errors=True)
    stage_src.mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "src", stage_src, dirs_exist_ok=True)
    (stage_src / "vp8").mkdir(parents=True, exist_ok=True)
    shutil.copytree(VP8_REPO / "src" / "vp8", stage_src / "vp8", dirs_exist_ok=True)
    if vp8_force_scalar_enabled():
        force_staged_vp8_scalar_kernels(stage_src)
    stage_uya_lib(stage_root / "lib")
    return stage_src


def vp8_force_scalar_enabled() -> bool:
    value = os.environ.get(UYA_VP8_FORCE_SCALAR_ENV, "")
    return value.lower() in {"1", "true", "yes", "on"}


def preview_sender_cflags() -> str:
    return os.environ.get(UYA_VP8_PREVIEW_CFLAGS_ENV, "").strip()


def uya_sender_env(stage_src: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["UYA_ROOT"] = str(stage_src.parent / "lib")
    cflags = preview_sender_cflags()
    if cflags:
        env["CFLAGS"] = cflags
    return env


def stage_uya_lib(stage_lib: Path) -> None:
    shutil.copytree(UYA_LIB, stage_lib, dirs_exist_ok=True)
    patch_staged_tls_ec_calls(stage_lib / "tls" / "crypto" / "ec.uya")


def patch_staged_tls_ec_calls(ec_path: Path) -> None:
    text = ec_path.read_text(encoding="utf-8")
    replacements = {
        "ec_p256.ec_p256_ecdh": "ec_p256_ecdh",
        "ec_p384.ec_p384_ecdh": "ec_p384_ecdh",
        "ec_p256.ec_p256_public_from_private": "ec_p256_public_from_private",
        "ec_p384.ec_p384_public_from_private": "ec_p384_public_from_private",
        "ec_p256.ec_p256_ecdsa_sign_with_k": "ec_p256_ecdsa_sign_with_k",
        "ec_p256.ec_p256_ecdsa_precompute_k": "ec_p256_ecdsa_precompute_k",
        "ec_p256.ec_p256_ecdsa_sign_precomputed": "ec_p256_ecdsa_sign_precomputed",
        "ec_p384.ec_p384_ecdsa_sign_with_k": "ec_p384_ecdsa_sign_with_k",
        "ec_p256.ec_p256_ecdsa_verify": "ec_p256_ecdsa_verify",
        "ec_p384.ec_p384_ecdsa_verify": "ec_p384_ecdsa_verify",
    }
    for old, new in replacements.items():
        if old not in text:
            raise AssertionError(f"unexpected staged TLS EC shape missing {old}: {ec_path}")
        text = text.replace(old, new)
    ec_path.write_text(text, encoding="utf-8")


def force_staged_vp8_scalar_kernels(stage_src: Path) -> None:
    dispatch_path = stage_src / "vp8" / "kernels" / "dispatch.uya"
    text = dispatch_path.read_text(encoding="utf-8")
    text = text.replace("use vp8.kernels.asm_x86.sad_16x16_x86_asm;\n", "")
    old = """fn forced_sad_16x16_fn(capabilities: &SimdCapabilities) &void {
    if capabilities.cpu.asm_x86 {
        return &sad_16x16_x86_asm;
    }
    return &sad_16x16_u8x16;
}
"""
    new = """fn forced_sad_16x16_fn(capabilities: &SimdCapabilities) &void {
    _ = capabilities;
    return &sad_16x16_u8x16;
}
"""
    old_kernel_branch = """    if table.sad_16x16_fn == (&sad_16x16_x86_asm as &void) {
        return sad_16x16_x86_asm(src, src_stride, reference, reference_stride);
    }
"""
    if old not in text:
        raise AssertionError(f"unexpected staged VP8 dispatch shape: {dispatch_path}")
    if old_kernel_branch not in text:
        raise AssertionError(f"unexpected staged VP8 SAD dispatch shape: {dispatch_path}")
    text = text.replace(old, new)
    text = text.replace(old_kernel_branch, "")
    dispatch_path.write_text(text, encoding="utf-8")


def i420_frame_bytes(width: int, height: int) -> int:
    if width <= 0 or height <= 0 or width % 2 != 0 or height % 2 != 0:
        raise AssertionError(f"invalid I420 dimensions: {width}x{height}")
    return width * height * 3 // 2


def write_synthetic_i420_source(
    workdir: Path,
    *,
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    frame_count: int = 120,
) -> Path:
    if frame_count <= 0:
        raise AssertionError("synthetic Uya VP8 source requires a positive frame count")
    raw_video_path = workdir / f"synthetic_{video_width}x{video_height}_i420.raw"
    y_bytes = video_width * video_height
    uv_bytes = y_bytes // 4
    with raw_video_path.open("wb") as output:
        for frame_index in range(frame_count):
            y_plane = bytearray(y_bytes)
            u_plane = bytearray(uv_bytes)
            v_plane = bytearray(uv_bytes)
            for index in range(y_bytes):
                y_plane[index] = (index * 13 + frame_index * 7 + 31) & 0xFF
            for index in range(uv_bytes):
                u_plane[index] = 96
                v_plane[index] = 160
            output.write(y_plane)
            output.write(u_plane)
            output.write(v_plane)
    expected_size = i420_frame_bytes(video_width, video_height) * frame_count
    if raw_video_path.stat().st_size != expected_size:
        raise AssertionError(f"synthetic raw I420 source has unexpected size: {raw_video_path}")
    return raw_video_path


def prepare_synthetic_uya_vp8_preview(workdir: Path) -> UyaVp8PreviewAssets:
    raw_video_path = write_synthetic_i420_source(workdir)
    return UyaVp8PreviewAssets(
        raw_video_path=raw_video_path,
        video_width=VIDEO_WIDTH,
        video_height=VIDEO_HEIGHT,
        media_duration_us=MEDIA_DURATION_US,
        video_frame_duration_us=UYA_VP8_DEFAULT_FRAME_DURATION_US,
        source_stats={
            "source_kind": "synthetic",
            "source_video_codec": "raw-i420",
            "encoder": "uya-vp8-live",
            "preview_width": VIDEO_WIDTH,
            "preview_height": VIDEO_HEIGHT,
            "preview_fps": UYA_VP8_DEFAULT_PREVIEW_FPS,
            "preview_duration_us": MEDIA_DURATION_US,
            "preview_frame_duration_us": UYA_VP8_DEFAULT_FRAME_DURATION_US,
            "preview_video_bytes": raw_video_path.stat().st_size,
        },
    )


def even_dimension(value: float) -> int:
    rounded = int(value)
    if rounded < 2:
        return 2
    if rounded % 2 != 0:
        rounded -= 1
    if rounded < 2:
        return 2
    return rounded


def scaled_preview_dimensions(source_width: int, source_height: int, max_video_width: int) -> tuple[int, int]:
    if source_width <= 0 or source_height <= 0:
        raise AssertionError(f"MP4 source has invalid video dimensions: {source_width}x{source_height}")
    if max_video_width > 0 and source_width > max_video_width:
        preview_width = even_dimension(float(max_video_width))
        preview_height = even_dimension((float(source_height) * float(preview_width)) / float(source_width))
        return preview_width, preview_height
    return even_dimension(float(source_width)), even_dimension(float(source_height))


def preview_duration_seconds(source_duration_seconds: float, max_duration_seconds: float) -> float:
    if max_duration_seconds > 0.0:
        return min(source_duration_seconds, max_duration_seconds)
    return source_duration_seconds


def resolve_preview_fps(video_width: int, requested_fps: int) -> int:
    if requested_fps > 0:
        return requested_fps
    if video_width >= 640:
        return 10
    if video_width >= 320:
        return 15
    return UYA_VP8_DEFAULT_PREVIEW_FPS


def preview_frame_duration_us(preview_fps: int) -> int:
    if preview_fps <= 0:
        raise AssertionError(f"Uya VP8 preview FPS must be positive: {preview_fps}")
    return max(1, int(1_000_000 / preview_fps))


def prepare_mp4_uya_vp8_preview(
    source_mp4: Path,
    workdir: Path,
    *,
    max_video_width: int = UYA_VP8_DEFAULT_PREVIEW_MAX_WIDTH,
    max_duration_seconds: float = UYA_VP8_DEFAULT_PREVIEW_MAX_DURATION_SECONDS,
    preview_fps: int = UYA_VP8_AUTO_PREVIEW_FPS,
) -> UyaVp8PreviewAssets:
    source_mp4 = source_mp4.expanduser().resolve()
    if not source_mp4.exists():
        raise AssertionError(f"MP4 source does not exist: {source_mp4}")
    if not source_mp4.is_file():
        raise AssertionError(f"MP4 source is not a file: {source_mp4}")

    ffmpeg = require_tool("ffmpeg")
    probe = probe_streams(source_mp4)
    video_stream = first_video_stream(probe)
    coded_width = int(video_stream.get("width") or 0)
    coded_height = int(video_stream.get("height") or 0)
    source_width, source_height = stream_display_dimensions(video_stream)
    source_duration_seconds = mp4_duration_seconds(probe, video_stream)
    clipped_duration_seconds = preview_duration_seconds(source_duration_seconds, max_duration_seconds)
    duration_text = f"{clipped_duration_seconds:.6f}".rstrip("0").rstrip(".")
    video_width, video_height = scaled_preview_dimensions(source_width, source_height, max_video_width)
    resolved_preview_fps = resolve_preview_fps(video_width, preview_fps)
    frame_duration_us = preview_frame_duration_us(resolved_preview_fps)
    print(
        "preparing Uya VP8 MP4 preview: "
        f"source={source_width}x{source_height} duration={source_duration_seconds:.3f}s "
        f"preview={video_width}x{video_height} duration={duration_text}s fps={resolved_preview_fps}",
        flush=True,
    )

    raw_dir = workdir / "mp4-raw-uya-vp8-preview"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_video_path = raw_dir / f"video_{video_width}x{video_height}_i420.raw"
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_mp4),
            "-t",
            duration_text,
            "-map",
            "0:v:0",
            "-vf",
            f"scale={video_width}:{video_height}:flags=bicubic,format=yuv420p",
            "-r",
            str(resolved_preview_fps),
            "-an",
            "-f",
            "rawvideo",
            str(raw_video_path),
        ]
    )

    frame_bytes = i420_frame_bytes(video_width, video_height)
    raw_size = raw_video_path.stat().st_size
    if frame_bytes <= 0 or raw_size < frame_bytes:
        raise AssertionError(f"raw MP4 video preview is too short: {raw_size} < {frame_bytes}")
    if raw_size % frame_bytes != 0:
        raise AssertionError(f"raw MP4 video size is not frame-aligned: {raw_size} % {frame_bytes}")
    frame_count = raw_size // frame_bytes
    media_duration_us = max(1, int(frame_count * frame_duration_us))
    print(
        "prepared Uya VP8 live preview source: "
        f"frames={frame_count} size={video_width}x{video_height}",
        flush=True,
    )
    format_info = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    return UyaVp8PreviewAssets(
        raw_video_path=raw_video_path,
        video_width=video_width,
        video_height=video_height,
        media_duration_us=media_duration_us,
        video_frame_duration_us=frame_duration_us,
        source_stats={
            "source_kind": "mp4",
            "source_path": str(source_mp4),
            "source_duration": str(format_info.get("duration", "")),
            "source_video_codec": str(video_stream.get("codec_name", "")),
            "source_coded_width": coded_width,
            "source_coded_height": coded_height,
            "source_width": source_width,
            "source_height": source_height,
            "preview_width": video_width,
            "preview_height": video_height,
            "preview_fps": resolved_preview_fps,
            "preview_requested_fps": preview_fps,
            "preview_max_width": max_video_width,
            "preview_max_duration_seconds": str(max_duration_seconds),
            "preview_duration_us": media_duration_us,
            "preview_frame_duration_us": frame_duration_us,
            "preview_frame_count": frame_count,
            "preview_video_bytes": raw_size,
            "encoder": "uya-vp8-live",
        },
    )


def prepare_uya_vp8_preview(
    workdir: Path,
    source_mp4: Path | None = None,
    *,
    max_video_width: int = UYA_VP8_DEFAULT_PREVIEW_MAX_WIDTH,
    max_duration_seconds: float = UYA_VP8_DEFAULT_PREVIEW_MAX_DURATION_SECONDS,
    preview_fps: int = UYA_VP8_AUTO_PREVIEW_FPS,
) -> UyaVp8PreviewAssets:
    if source_mp4 is not None:
        return prepare_mp4_uya_vp8_preview(
            source_mp4,
            workdir,
            max_video_width=max_video_width,
            max_duration_seconds=max_duration_seconds,
            preview_fps=preview_fps,
        )
    return prepare_synthetic_uya_vp8_preview(workdir)


def sender_failure_message(message: str, handle: SenderHandle | None, stdout_path: Path, stderr_path: Path) -> str:
    return (
        f"{message}\n"
        f"returncode={handle.proc.poll() if handle is not None else 'not-started'}\n"
        f"stdout:\n{read_text_tail(stdout_path)}\n"
        f"stderr:\n{read_text_tail(stderr_path)}"
    )


def build_failure_message(message: str, returncode: int, stdout_path: Path, stderr_path: Path) -> str:
    return (
        f"{message}\n"
        f"returncode={returncode}\n"
        f"stdout:\n{read_text_tail(stdout_path)}\n"
        f"stderr:\n{read_text_tail(stderr_path)}"
    )


def build_uya_vp8_sender(build_root: Path) -> PreviewSenderExecutable:
    if not UYA_BIN.exists():
        raise AssertionError(f"Uya compiler/runtime not found at {UYA_BIN}")
    shutil.rmtree(build_root, ignore_errors=True)
    build_root.mkdir(parents=True, exist_ok=True)
    stage_src = stage_vp8_package(build_root / "legacy-uya-vp8-live-source")
    exe_path = build_root / "uya_vp8_direct_sender"
    stdout_path = build_root / "uya_vp8_sender_build.stdout.log"
    stderr_path = build_root / "uya_vp8_sender_build.stderr.log"
    command = [
        str(UYA_BIN),
        "build",
        str(stage_src / UYA_DIRECT_SENDER_MAIN.name),
        "--no-split-c",
        "-o",
        str(exe_path),
    ]
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=uya_sender_env(stage_src),
            text=True,
            stdout=stdout_file,
            stderr=stderr_file,
        )
    if completed.returncode != 0:
        raise AssertionError(
            build_failure_message(
                "uya_vp8 direct sender build failed",
                completed.returncode,
                stdout_path,
                stderr_path,
            )
        )
    if not exe_path.exists():
        raise AssertionError(f"uya_vp8 direct sender build did not create executable: {exe_path}")
    return PreviewSenderExecutable(exe_path, stage_src, stdout_path, stderr_path)


def start_uya_sender(
    offer: dict[str, str],
    raw_video_path: Path,
    workdir: Path,
    *,
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    media_duration_us: int = MEDIA_DURATION_US,
    video_frame_duration_us: int = UYA_VP8_DEFAULT_FRAME_DURATION_US,
    sender_executable: PreviewSenderExecutable | None = None,
) -> SenderHandle:
    offer_path = workdir / "chrome_offer.json"
    answer_path = workdir / "uya_answer.json"
    diagnostics_path = workdir / "uya_vp8_sender_diagnostics.json"
    stdout_path = workdir / "uya_vp8_sender.stdout.log"
    stderr_path = workdir / "uya_vp8_sender.stderr.log"
    offer_path.write_text(json.dumps(offer), encoding="utf-8")
    if not UYA_BIN.exists():
        raise AssertionError(f"Uya compiler/runtime not found at {UYA_BIN}")
    if not raw_video_path.exists():
        raise AssertionError(f"raw Uya VP8 source is missing: {raw_video_path}")
    stage_src: Path | None = None
    if sender_executable is None:
        stage_src = stage_vp8_package(workdir / "legacy-uya-vp8-live-source")

    stdout_file = stdout_path.open("w", encoding="utf-8")
    stderr_file = stderr_path.open("w", encoding="utf-8")
    try:
        program_args = [
            "--offer-json",
            str(offer_path),
            "--media",
            str(raw_video_path),
            "--answer-json",
            str(answer_path),
            "--diagnostics-json",
            str(diagnostics_path),
            "--codec",
            "uya",
            "--raw-video-i420",
            str(raw_video_path),
            "--video-width",
            str(video_width),
            "--video-height",
            str(video_height),
            "--media-duration-us",
            str(media_duration_us),
            "--video-frame-duration-us",
            str(video_frame_duration_us),
            "--local-host",
            "127.0.0.1",
        ]
        if sender_executable is None:
            assert stage_src is not None
            command = [
                str(UYA_BIN),
                "run",
                str(stage_src / UYA_DIRECT_SENDER_MAIN.name),
                "--",
                *program_args,
            ]
            env = uya_sender_env(stage_src)
        else:
            command = [str(sender_executable.path), *program_args]
            env = os.environ.copy()
        proc = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
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
    return SenderHandle(proc, answer_sdp, diagnostics_path, stdout_path, stderr_path, media_duration_us=media_duration_us)


def read_sender_diagnostics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def wait_for_sender(handle: SenderHandle) -> dict[str, Any]:
    try:
        returncode = handle.proc.wait(timeout=media_duration_timeout_seconds(handle.media_duration_us))
    except subprocess.TimeoutExpired as exc:
        handle.proc.terminate()
        try:
            handle.proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            handle.proc.kill()
            handle.proc.wait(timeout=5.0)
        raise AssertionError(
            sender_failure_message(
                "uya_vp8 direct sender did not exit after Chrome received video",
                handle,
                handle.stdout_path,
                handle.stderr_path,
            )
        ) from exc
    if returncode != 0:
        raise AssertionError(
            sender_failure_message(
                "uya_vp8 direct sender failed while Chrome was receiving video",
                handle,
                handle.stdout_path,
                handle.stderr_path,
            )
        )
    return read_sender_diagnostics(handle.diagnostics_path)


def stop_sender(handle: SenderHandle | None) -> None:
    if handle is None or handle.proc.poll() is not None:
        return
    handle.proc.terminate()
    try:
        handle.proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        handle.proc.kill()
        handle.proc.wait(timeout=5.0)


class ManualVp8PreviewState:
    def __init__(
        self,
        preview_dir: Path,
        raw_video_path: Path,
        video_width: int,
        video_height: int,
        media_duration_us: int,
        video_frame_duration_us: int,
        sender_executable: PreviewSenderExecutable | None = None,
    ) -> None:
        self.preview_dir = preview_dir
        self.raw_video_path = raw_video_path
        self.video_width = video_width
        self.video_height = video_height
        self.media_duration_us = media_duration_us
        self.video_frame_duration_us = video_frame_duration_us
        self.sender_executable = sender_executable
        self.sessions_dir = preview_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, ManualVp8PreviewSession] = {}
        self.lock = threading.Lock()

    def start_call(self, offer: dict[str, str]) -> tuple[str, str]:
        session_id = uuid.uuid4().hex[:12]
        workdir = self.sessions_dir / session_id
        workdir.mkdir(parents=True, exist_ok=False)
        handle = start_uya_sender(
            offer,
            self.raw_video_path,
            workdir,
            video_width=self.video_width,
            video_height=self.video_height,
            media_duration_us=self.media_duration_us,
            video_frame_duration_us=self.video_frame_duration_us,
            sender_executable=self.sender_executable,
        )
        with self.lock:
            self.sessions[session_id] = ManualVp8PreviewSession(session_id, handle, workdir)
        return session_id, handle.answer_sdp

    def finish_call(self, session_id: str) -> dict[str, Any]:
        session = self._pop_session(session_id)
        return wait_for_sender(session.handle)

    def stop_call(self, session_id: str) -> dict[str, Any]:
        session = self._pop_session(session_id)
        stop_sender(session.handle)
        return read_sender_diagnostics(session.handle.diagnostics_path)

    def stop_all(self) -> None:
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions:
            stop_sender(session.handle)

    def _pop_session(self, session_id: str) -> ManualVp8PreviewSession:
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if session is None:
            raise AssertionError(f"unknown manual preview session: {session_id}")
        return session


class ManualVp8PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, directory: str, state: ManualVp8PreviewState, **kwargs: Any) -> None:
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
    raw_video_path: Path,
    video_width: int,
    video_height: int,
    media_duration_us: int,
    video_frame_duration_us: int,
) -> tuple[ThreadingHTTPServer, threading.Thread, int, ManualVp8PreviewState]:
    cflags_note = f" cflags={preview_sender_cflags()}" if preview_sender_cflags() else ""
    print(f"building Uya VP8 preview sender:{cflags_note}", flush=True)
    sender_executable = build_uya_vp8_sender(preview_dir / "sender-build")
    print(f"built Uya VP8 preview sender: {sender_executable.path}", flush=True)
    state = ManualVp8PreviewState(
        preview_dir,
        raw_video_path,
        video_width,
        video_height,
        media_duration_us,
        video_frame_duration_us,
        sender_executable=sender_executable,
    )
    port = find_free_port()
    handler = partial(ManualVp8PreviewHandler, directory=str(preview_dir), state=state)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port, state


def run_chrome_page(
    tempdir_path: Path,
    raw_video_path: Path,
    sender_executable: PreviewSenderExecutable | None = None,
) -> dict[str, Any]:
    browser_exe = find_browser_executable()
    server: ThreadingHTTPServer
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
        sender_handle: SenderHandle | None = None
        try:
            target = client.command("Target.createTarget", {"url": "about:blank"})
            target_id = str(target["targetId"])
            attached = client.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
            session_id = str(attached["sessionId"])
            client.command("Runtime.enable", session_id=session_id)
            client.command("Page.enable", session_id=session_id)
            client.command("Page.navigate", {"url": f"http://127.0.0.1:{http_port}/index.html"}, session_id=session_id)
            offer = wait_for_offer(client, session_id)
            sender_handle = start_uya_sender(offer, raw_video_path, tempdir_path, sender_executable=sender_executable)
            apply_answer(client, session_id, sender_handle.answer_sdp)
            result = wait_for_result(client, session_id)
            result["senderDiagnostics"] = wait_for_sender(sender_handle)
            return result
        finally:
            stop_sender(sender_handle)
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


def validate_result(
    result: dict[str, Any],
    expected_width: int = VIDEO_WIDTH,
    expected_height: int = VIDEO_HEIGHT,
    require_bidirectional: bool = True,
) -> None:
    require(result.get("ok") is True, f"browser page reported failure: {result}")
    tracks = result.get("tracks")
    require(isinstance(tracks, list) and "video" in tracks, "Chrome did not surface a video track")
    require(int(result.get("videoPacketsReceived", 0)) > 0, "Chrome received no Uya VP8 RTP packets")
    require(int(result.get("videoFramesDecoded", 0)) > 0, "Chrome decoded no Uya VP8 frames")
    if require_bidirectional:
        require(int(result.get("outboundVideoPacketsSent", 0)) > 0, "Chrome sent no VP8 RTP packets to Uya")
        require(int(result.get("outboundVideoFramesEncoded", 0)) > 0, "Chrome encoded no outbound VP8 frames")
    decoded_width = int(result.get("videoFrameWidth") or result.get("remoteVideoWidth") or 0)
    decoded_height = int(result.get("videoFrameHeight") or result.get("remoteVideoHeight") or 0)
    require(decoded_width == expected_width, f"Chrome decoded unexpected width: {result}")
    require(decoded_height == expected_height, f"Chrome decoded unexpected height: {result}")
    offer_sdp = str(result.get("offerSdp", "")).lower()
    answer_sdp = str(result.get("answerSdp", "")).lower()
    require("m=video" in offer_sdp and "m=video" in answer_sdp, "SDP missing video m-line")
    require("vp8/90000" in offer_sdp or "vp8/90000" in answer_sdp, "SDP missing VP8 negotiation")
    if require_bidirectional:
        require("a=sendrecv" in offer_sdp and "a=sendrecv" in answer_sdp, "SDP did not negotiate bidirectional video")
    diagnostics = result.get("senderDiagnostics")
    require(isinstance(diagnostics, dict), "Uya VP8 sender diagnostics missing")
    require(diagnostics.get("codecProvider") == "uya", f"unexpected codec provider: {diagnostics}")
    require(diagnostics.get("uyaVp8VideoReady") is True, "Uya VP8 video source was not reported ready")
    require(diagnostics.get("rawVideoPathSeen") is True, "raw I420 source path was not observed")
    require(diagnostics.get("encodedVideoPathSeen") is False, "Uya VP8 sender should live-encode instead of reading encoded VP8")
    require(diagnostics.get("codecProviderUsesExtern") is False, "Uya VP8 provider must not report extern codec usage")
    require(diagnostics.get("codecBridgeRequired") is True, "Uya VP8 provider should report codec bridge usage")
    require(int(diagnostics.get("vp8KeyFrames", 0)) > 0, "Uya VP8 sender reported no key frames")
    require(int(diagnostics.get("vp8InterFrames", 0)) > 0, "Uya VP8 sender reported no inter frames")
    require(int(diagnostics.get("rtpPackets", 0)) > 0, "Uya VP8 sender reported no RTP packets")
    require(int(diagnostics.get("srtpPackets", 0)) > 0, "Uya VP8 sender reported no SRTP packets")
    if require_bidirectional:
        require(int(diagnostics.get("srtpPacketsReceived", 0)) > 0, "Uya PeerConnection reported no inbound Chrome SRTP packets")
        require(int(diagnostics.get("rtpPacketsReceived", 0)) > 0, "Uya PeerConnection reported no inbound Chrome RTP packets")
        require(int(diagnostics.get("videoRtpPacketsReceived", 0)) > 0, "Uya PeerConnection reported no inbound Chrome video RTP packets")
        require(int(diagnostics.get("videoFramesReceived", 0)) > 0, "Uya PeerConnection reassembled no inbound Chrome VP8 frames")
    require(int(diagnostics.get("rtcpSenderReports", 0)) > 0, "Uya VP8 sender reported no RTCP Sender Reports")
    require(int(diagnostics.get("udpPackets", 0)) > 0, "Uya VP8 sender reported no UDP packets")


def validate_manual_preview_result(result: dict[str, Any], assets: UyaVp8PreviewAssets) -> None:
    validate_result(result, expected_width=assets.video_width, expected_height=assets.video_height, require_bidirectional=False)
    progress = result.get("progress")
    require(isinstance(progress, list) and "playing" in progress, "manual preview did not reach playing state")
    require(isinstance(progress, list) and "complete" in progress, "manual preview did not reach complete state")


def run_manual_preview_chrome_page(preview_dir: Path, assets: UyaVp8PreviewAssets) -> dict[str, Any]:
    browser_exe = find_browser_executable()
    server, thread, http_port, state = start_manual_preview_server(
        preview_dir,
        assets.raw_video_path,
        assets.video_width,
        assets.video_height,
        assets.media_duration_us,
        assets.video_frame_duration_us,
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
            return wait_for_manual_preview_result(
                client,
                session_id,
                timeout_seconds=max(35.0, media_duration_timeout_seconds(assets.media_duration_us)),
            )
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


def run_flow(keep_temp: bool = False) -> str:
    with tempfile.TemporaryDirectory(prefix="webrtc-uya-vp8-chrome-") as tmp:
        tempdir_path = Path(tmp)
        try:
            raw_video_path = write_synthetic_i420_source(tempdir_path)
            (tempdir_path / "index.html").write_text(make_video_only_page(), encoding="utf-8")
            print("building Uya VP8 Chrome sender:", flush=True)
            sender_executable = build_uya_vp8_sender(tempdir_path / "sender-build")
            print(f"built Uya VP8 Chrome sender: {sender_executable.path}", flush=True)
            result = run_chrome_page(tempdir_path, raw_video_path, sender_executable=sender_executable)
            validate_result(result)
        except Exception:
            if keep_temp:
                kept = Path(tempfile.mkdtemp(prefix="webrtc-uya-vp8-chrome-kept-"))
                for path in tempdir_path.iterdir():
                    target = kept / path.name
                    if path.is_dir():
                        shutil.copytree(path, target)
                    elif path.is_file():
                        target.write_bytes(path.read_bytes())
                print(f"kept failed run: {kept}", flush=True)
            raise
        diagnostics = result.get("senderDiagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}

        if keep_temp:
            kept = Path(tempfile.mkdtemp(prefix="webrtc-uya-vp8-chrome-kept-"))
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
            "uya vp8 chrome direct call checks passed: "
            f"source_video_codec=vp8 "
            f"source_video_size={VIDEO_WIDTH}x{VIDEO_HEIGHT} "
            f"chrome_video_packets={result.get('videoPacketsReceived')} "
            f"chrome_video_frames={result.get('videoFramesDecoded')} "
            f"sender_vp8_key_frames={diagnostics.get('vp8KeyFrames')} "
            f"sender_vp8_inter_frames={diagnostics.get('vp8InterFrames')} "
            f"sender_rtp_packets={diagnostics.get('rtpPackets')} "
            f"sender_srtp_packets={diagnostics.get('srtpPackets')} "
            f"sender_srtp_packets_received={diagnostics.get('srtpPacketsReceived')} "
            f"sender_rtp_packets_received={diagnostics.get('rtpPacketsReceived')} "
            f"sender_video_rtp_packets_received={diagnostics.get('videoRtpPacketsReceived')} "
            f"sender_video_frames_received={diagnostics.get('videoFramesReceived')} "
            f"sender_srtcp_packets={diagnostics.get('srtcpPackets')} "
            f"sender_rtcp_sender_reports={diagnostics.get('rtcpSenderReports')} "
            f"sender_udp_packets={diagnostics.get('udpPackets')}"
            f"{temp_note}"
        )


def write_preview_manifest(preview_dir: Path, assets: UyaVp8PreviewAssets) -> None:
    manifest = {
        "raw_video_path": str(assets.raw_video_path),
        "video_width": assets.video_width,
        "video_height": assets.video_height,
        "media_duration_us": assets.media_duration_us,
        "video_frame_duration_us": assets.video_frame_duration_us,
        "source_stats": assets.source_stats,
    }
    (preview_dir / "preview_manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")


def read_preview_manifest(preview_dir: Path) -> UyaVp8PreviewAssets:
    manifest_path = preview_dir / "preview_manifest.json"
    if not manifest_path.exists():
        raise AssertionError(f"Uya VP8 manual preview manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("raw_video_path"), str):
        raise AssertionError(f"invalid Uya VP8 manual preview manifest: {manifest_path}")
    source_stats = manifest.get("source_stats") if isinstance(manifest.get("source_stats"), dict) else {}
    raw_video_path = Path(str(manifest["raw_video_path"]))
    if not raw_video_path.exists():
        raise AssertionError(f"raw Uya VP8 preview source is missing: {raw_video_path}")
    return UyaVp8PreviewAssets(
        raw_video_path=raw_video_path,
        video_width=int(manifest.get("video_width") or 0),
        video_height=int(manifest.get("video_height") or 0),
        media_duration_us=int(manifest.get("media_duration_us") or MEDIA_DURATION_US),
        video_frame_duration_us=int(manifest.get("video_frame_duration_us") or UYA_VP8_DEFAULT_FRAME_DURATION_US),
        source_stats=source_stats,
    )


def write_preview(
    preview_dir: Path,
    source_mp4: Path | None = None,
    *,
    max_video_width: int = UYA_VP8_DEFAULT_PREVIEW_MAX_WIDTH,
    max_duration_seconds: float = UYA_VP8_DEFAULT_PREVIEW_MAX_DURATION_SECONDS,
    preview_fps: int = UYA_VP8_AUTO_PREVIEW_FPS,
) -> str:
    preview_dir.mkdir(parents=True, exist_ok=True)
    assets = prepare_uya_vp8_preview(
        preview_dir,
        source_mp4=source_mp4,
        max_video_width=max_video_width,
        max_duration_seconds=max_duration_seconds,
        preview_fps=preview_fps,
    )
    page_path = preview_dir / "index.html"
    page_path.write_text(make_manual_preview_page(assets.source_stats), encoding="utf-8")
    write_preview_manifest(preview_dir, assets)
    source_note = f" source={source_mp4.expanduser().resolve()}" if source_mp4 is not None else ""
    return f"uya vp8 chrome direct preview written: dir={preview_dir} page={page_path}{source_note}"


def serve_preview(preview_dir: Path) -> int:
    assets = read_preview_manifest(preview_dir)
    server, thread, http_port, state = start_manual_preview_server(
        preview_dir,
        assets.raw_video_path,
        assets.video_width,
        assets.video_height,
        assets.media_duration_us,
        assets.video_frame_duration_us,
    )
    url = f"http://127.0.0.1:{http_port}/"
    print(f"uya vp8 chrome direct preview serving: {url}", flush=True)
    print("press Ctrl-C to stop", flush=True)
    try:
        while True:
            time.sleep(3600.0)
    except KeyboardInterrupt:
        print("uya vp8 chrome direct preview stopped", flush=True)
        return 0
    finally:
        state.stop_all()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def run_manual_preview_flow(
    keep_temp: bool = False,
    source_mp4: Path | None = None,
    *,
    max_video_width: int = UYA_VP8_DEFAULT_PREVIEW_MAX_WIDTH,
    max_duration_seconds: float = UYA_VP8_DEFAULT_PREVIEW_MAX_DURATION_SECONDS,
    preview_fps: int = UYA_VP8_AUTO_PREVIEW_FPS,
) -> str:
    with tempfile.TemporaryDirectory(prefix="webrtc-uya-vp8-chrome-manual-preview-") as tmp:
        tempdir_path = Path(tmp)
        assets = prepare_uya_vp8_preview(
            tempdir_path,
            source_mp4=source_mp4,
            max_video_width=max_video_width,
            max_duration_seconds=max_duration_seconds,
            preview_fps=preview_fps,
        )
        (tempdir_path / "index.html").write_text(make_manual_preview_page(assets.source_stats), encoding="utf-8")
        write_preview_manifest(tempdir_path, assets)
        result = run_manual_preview_chrome_page(tempdir_path, assets)
        validate_manual_preview_result(result, assets)
        diagnostics = result.get("senderDiagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}

        if keep_temp:
            kept = Path(tempfile.mkdtemp(prefix="webrtc-uya-vp8-chrome-manual-preview-kept-"))
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
            "uya vp8 chrome manual preview checks passed: "
            f"source_kind={assets.source_stats.get('source_kind')} "
            f"preview_size={assets.video_width}x{assets.video_height} "
            f"preview_duration_us={assets.media_duration_us} "
            f"chrome_video_size={result.get('videoFrameWidth') or result.get('remoteVideoWidth')}x{result.get('videoFrameHeight') or result.get('remoteVideoHeight')} "
            f"chrome_video_packets={result.get('videoPacketsReceived')} "
            f"chrome_video_frames={result.get('videoFramesDecoded')} "
            f"sender_vp8_key_frames={diagnostics.get('vp8KeyFrames')} "
            f"sender_vp8_inter_frames={diagnostics.get('vp8InterFrames')} "
            f"sender_rtp_packets={diagnostics.get('rtpPackets')} "
            f"sender_srtp_packets={diagnostics.get('srtpPackets')} "
            f"sender_srtcp_packets={diagnostics.get('srtcpPackets')} "
            f"sender_rtcp_sender_reports={diagnostics.get('rtcpSenderReports')} "
            f"sender_udp_packets={diagnostics.get('udpPackets')}"
            f"{temp_note}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--preview-dir", type=Path, help="write a manual Chrome receiver preview page into this directory")
    parser.add_argument("--source-mp4", type=Path, help="prepare this MP4 as the raw source for pure Uya VP8 preview")
    parser.add_argument("--max-video-width", type=int, default=UYA_VP8_DEFAULT_PREVIEW_MAX_WIDTH, help="downscale MP4 preview to this width before pure Uya VP8 encoding; use 0 to keep source width")
    parser.add_argument("--max-duration-seconds", type=float, default=UYA_VP8_DEFAULT_PREVIEW_MAX_DURATION_SECONDS, help="clip MP4 preview duration before pure Uya VP8 encoding; use 0 for full source duration")
    parser.add_argument("--preview-fps", type=int, default=UYA_VP8_AUTO_PREVIEW_FPS, help="sample MP4 preview at this FPS and send frames at the matching interval; use 0 for automatic width-based preview FPS")
    parser.add_argument("--serve-preview", action="store_true", help="serve the manual preview page and wait until Ctrl-C")
    parser.add_argument("--manual-preview-e2e", action="store_true", help="launch Chrome, click the manual preview button, and verify Uya VP8 media")
    args = parser.parse_args()
    try:
        if args.manual_preview_e2e:
            print(
                run_manual_preview_flow(
                    keep_temp=args.keep_temp,
                    source_mp4=args.source_mp4,
                    max_video_width=args.max_video_width,
                    max_duration_seconds=args.max_duration_seconds,
                    preview_fps=args.preview_fps,
                ),
                flush=True,
            )
            return 0
        if args.preview_dir is not None or args.serve_preview:
            preview_dir = args.preview_dir or Path(tempfile.mkdtemp(prefix="webrtc-uya-vp8-chrome-direct-preview-"))
            print(
                write_preview(
                    preview_dir,
                    source_mp4=args.source_mp4,
                    max_video_width=args.max_video_width,
                    max_duration_seconds=args.max_duration_seconds,
                    preview_fps=args.preview_fps,
                ),
                flush=True,
            )
            if args.serve_preview:
                return serve_preview(preview_dir)
            return 0
        print(run_flow(keep_temp=args.keep_temp), flush=True)
        return 0
    except (AssertionError, InteropError, TimeoutError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
