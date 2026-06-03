#!/usr/bin/env python3
"""Validate a Chrome audio/video call fed by FFmpeg codecs.

The script generates a deterministic VP8/Opus WebM file with FFmpeg, serves it
to a headless Chrome page, captures the media element as a MediaStream, and
verifies that a browser RTCPeerConnection receives audio and video over WebRTC.
This is a reference-codec interop gate; it does not make FFmpeg a default Uya
runtime dependency.
"""

from __future__ import annotations

import json
import argparse
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
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


def generate_ffmpeg_media(workdir: Path) -> tuple[Path, dict[str, int | str]]:
    ffmpeg = require_tool("ffmpeg")
    ffprobe = require_tool("ffprobe")
    require_ffmpeg_codec(ffmpeg, "encoder", "libopus")
    require_ffmpeg_codec(ffmpeg, "encoder", "libvpx")
    require_ffmpeg_codec(ffmpeg, "decoder", "opus")
    require_ffmpeg_codec(ffmpeg, "decoder", "vp8")

    media_path = workdir / "ffmpeg_chrome_call.webm"
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


def make_call_page(media_name: str) -> str:
    media_json = json.dumps(media_name)
    return textwrap.dedent(
        """
        <!doctype html>
        <meta charset="utf-8">
        <title>FFmpeg Chrome WebRTC Call</title>
        <script>
        window.__ffmpegChromeCallResult = null;
        window.__ffmpegChromeCallProgress = [];

        function mark(step) {
          window.__ffmpegChromeCallProgress.push(step);
        }

        function fail(message, error) {
          const detail = [];
          if (error) {
            if (error.name) {
              detail.push(String(error.name));
            }
            if (error.message) {
              detail.push(String(error.message));
            }
            if (error.stack) {
              detail.push(String(error.stack));
            } else {
              detail.push(String(error));
            }
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

        function waitForState(target, name, predicate) {
          if (predicate()) {
            return Promise.resolve();
          }
          return waitForEvent(target, name, () => predicate());
        }

        function makeIceRelay(source, sink, sinkName) {
          const queue = [];
          let ready = false;
          source.addEventListener('icecandidate', event => {
            if (!event.candidate) {
              return;
            }
            if (ready) {
              void sink.addIceCandidate(event.candidate).catch(error => {
                fail(sinkName + ' addIceCandidate failed', error);
              });
              return;
            }
            queue.push(event.candidate);
          });
          return {
            async enable() {
              ready = true;
              for (const candidate of queue.splice(0)) {
                await sink.addIceCandidate(candidate);
              }
            }
          };
        }

        function codecPreferences(kind, mimeType) {
          const capabilities = RTCRtpSender.getCapabilities(kind);
          if (!capabilities || !capabilities.codecs) {
            return [];
          }
          const wanted = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase() === mimeType);
          const helpers = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase().indexOf('rtx') >= 0);
          return wanted.concat(helpers);
        }

        async function waitForInbound(kind, receiver) {
          const deadline = Date.now() + 8000;
          while (Date.now() < deadline) {
            const stats = await receiver.getStats();
            for (const stat of stats.values()) {
              if (stat.type !== 'inbound-rtp') {
                continue;
              }
              if (stat.kind !== kind && stat.mediaType !== kind) {
                continue;
              }
              const packets = stat.packetsReceived || 0;
              const frames = stat.framesDecoded || stat.framesReceived || 0;
              let codecMimeType = '';
              if (stat.codecId) {
                const codec = stats.get(stat.codecId);
                if (codec && codec.mimeType) {
                  codecMimeType = String(codec.mimeType);
                }
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

        async function run() {
          mark('start');
          const video = document.createElement('video');
          video.src = __MEDIA_NAME__;
          video.autoplay = true;
          video.controls = false;
          video.loop = true;
          video.muted = false;
          video.playsInline = true;
          video.width = 320;
          video.height = 180;
          document.documentElement.appendChild(video);
          video.preload = 'auto';
          await waitForState(video, 'loadedmetadata', () => video.readyState >= 1);
          await video.play();
          mark('media-playing');

          const capture = video.captureStream ? video.captureStream() : video.mozCaptureStream();
          if (!capture) {
            throw new Error('media element captureStream is unavailable');
          }
          const audioTrack = capture.getAudioTracks()[0];
          const videoTrack = capture.getVideoTracks()[0];
          if (!audioTrack) {
            throw new Error('captured FFmpeg media has no audio track');
          }
          if (!videoTrack) {
            throw new Error('captured FFmpeg media has no video track');
          }

          const pc1 = new RTCPeerConnection({iceServers: []});
          const pc2 = new RTCPeerConnection({iceServers: []});
          const relay12 = makeIceRelay(pc1, pc2, 'pc2');
          const relay21 = makeIceRelay(pc2, pc1, 'pc1');
          const states = [];
          const tracks = [];
          pc1.addEventListener('connectionstatechange', () => states.push('pc1:' + pc1.connectionState));
          pc2.addEventListener('connectionstatechange', () => states.push('pc2:' + pc2.connectionState));

          const audioEventPromise = waitForEvent(pc2, 'track', event => event.track.kind === 'audio');
          const videoEventPromise = waitForEvent(pc2, 'track', event => event.track.kind === 'video');
          pc2.addEventListener('track', event => tracks.push(event.track.kind));

          const audioTransceiver = pc1.addTransceiver(audioTrack, {direction: 'sendonly'});
          const opus = codecPreferences('audio', 'audio/opus');
          if (opus.length > 0) {
            audioTransceiver.setCodecPreferences(opus);
          }
          const videoTransceiver = pc1.addTransceiver(videoTrack, {direction: 'sendonly'});
          const vp8 = codecPreferences('video', 'video/vp8');
          if (vp8.length > 0) {
            videoTransceiver.setCodecPreferences(vp8);
          }
          mark('transceivers-added');

          const offer = await pc1.createOffer();
          await pc1.setLocalDescription(offer);
          await pc2.setRemoteDescription(pc1.localDescription);
          await relay12.enable();

          const answer = await pc2.createAnswer();
          await pc2.setLocalDescription(answer);
          await pc1.setRemoteDescription(pc2.localDescription);
          await relay21.enable();
          mark('sdp-exchanged');

          const audioEvent = await audioEventPromise;
          const videoEvent = await videoEventPromise;
          await Promise.all([
            waitForState(pc1, 'connectionstatechange', () => pc1.connectionState === 'connected'),
            waitForState(pc2, 'connectionstatechange', () => pc2.connectionState === 'connected'),
          ]);
          mark('connected');

          const audioReceiver = pc2.getReceivers().find(receiver => receiver.track === audioEvent.track);
          const videoReceiver = pc2.getReceivers().find(receiver => receiver.track === videoEvent.track);
          if (!audioReceiver || !videoReceiver) {
            throw new Error('receiver lookup failed');
          }

          const audioStats = await waitForInbound('audio', audioReceiver);
          const videoStats = await waitForInbound('video', videoReceiver);
          if (audioStats.packetsReceived <= 0) {
            throw new Error('audio packets were not received from FFmpeg media call');
          }
          if (videoStats.packetsReceived <= 0 || videoStats.framesDecoded <= 0) {
            throw new Error('video frames were not received from FFmpeg media call');
          }
          mark('media-received');

          const offerSdp = pc1.localDescription ? pc1.localDescription.sdp : '';
          const answerSdp = pc2.localDescription ? pc2.localDescription.sdp : '';
          const mediaCurrentTime = video.currentTime;

          audioTrack.stop();
          videoTrack.stop();
          pc1.close();
          pc2.close();
          await delay(25);
          video.pause();

          let pc1ConnectionState = '';
          let pc2ConnectionState = '';
          try {
            pc1ConnectionState = pc1.connectionState;
          } catch (error) {
            pc1ConnectionState = 'closed';
          }
          try {
            pc2ConnectionState = pc2.connectionState;
          } catch (error) {
            pc2ConnectionState = 'closed';
          }

          window.__ffmpegChromeCallResult = {
            ok: true,
            browser: navigator.userAgent,
            states,
            tracks,
            pc1ConnectionState,
            pc2ConnectionState,
            audioPacketsReceived: audioStats.packetsReceived,
            audioCodecMimeType: audioStats.codecMimeType,
            videoPacketsReceived: videoStats.packetsReceived,
            videoFramesDecoded: videoStats.framesDecoded,
            videoCodecMimeType: videoStats.codecMimeType,
            mediaCurrentTime,
            offerSdp,
            answerSdp,
            progress: window.__ffmpegChromeCallProgress.slice()
          };
        }

        run().catch(error => fail('ffmpeg chrome call failed', error));
        </script>
        """
    ).strip().replace("__MEDIA_NAME__", media_json)


def make_preview_page(media_name: str, ffmpeg_stats: dict[str, int | str]) -> str:
    media_json = json.dumps(media_name)
    stats_json = json.dumps(ffmpeg_stats, sort_keys=True)
    return textwrap.dedent(
        """
        <!doctype html>
        <meta charset="utf-8">
        <title>FFmpeg Chrome WebRTC Preview</title>
        <style>
          :root {
            color-scheme: light;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f7f8fb;
            color: #1f2937;
          }
          body {
            margin: 0;
            min-height: 100vh;
          }
          main {
            max-width: 1120px;
            margin: 0 auto;
            padding: 24px;
          }
          header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 16px;
          }
          h1 {
            margin: 0;
            font-size: 22px;
            font-weight: 700;
          }
          button {
            border: 0;
            border-radius: 6px;
            background: #14532d;
            color: white;
            cursor: pointer;
            font: inherit;
            font-weight: 700;
            min-height: 40px;
            padding: 0 16px;
          }
          button:disabled {
            background: #94a3b8;
            cursor: default;
          }
          .videos {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
          }
          .pane {
            background: white;
            border: 1px solid #d9dee8;
            border-radius: 8px;
            overflow: hidden;
          }
          .pane h2 {
            border-bottom: 1px solid #e5e7eb;
            font-size: 15px;
            margin: 0;
            padding: 10px 12px;
          }
          video {
            aspect-ratio: 16 / 9;
            background: #111827;
            display: block;
            width: 100%;
          }
          .status {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 8px;
            margin-top: 16px;
          }
          .metric {
            background: white;
            border: 1px solid #d9dee8;
            border-radius: 8px;
            padding: 10px 12px;
          }
          .label {
            color: #64748b;
            display: block;
            font-size: 12px;
            margin-bottom: 4px;
          }
          .value {
            font-size: 18px;
            font-weight: 700;
          }
          pre {
            background: #111827;
            border-radius: 8px;
            color: #e5e7eb;
            font-size: 12px;
            margin: 16px 0 0;
            overflow: auto;
            padding: 12px;
            white-space: pre-wrap;
          }
          @media (max-width: 760px) {
            main {
              padding: 16px;
            }
            header {
              align-items: stretch;
              flex-direction: column;
            }
            .videos,
            .status {
              grid-template-columns: 1fr;
            }
          }
        </style>
        <main>
          <header>
            <h1>FFmpeg VP8/Opus WebRTC Preview</h1>
            <button id="start">Start Call</button>
          </header>
          <section class="videos">
            <div class="pane">
              <h2>FFmpeg Source</h2>
              <video id="source" controls loop playsinline></video>
            </div>
            <div class="pane">
              <h2>Chrome WebRTC Receiver</h2>
              <video id="remote" autoplay controls playsinline></video>
            </div>
          </section>
          <section class="status">
            <div class="metric"><span class="label">State</span><span class="value" id="state">idle</span></div>
            <div class="metric"><span class="label">Audio Packets</span><span class="value" id="audioPackets">0</span></div>
            <div class="metric"><span class="label">Video Packets</span><span class="value" id="videoPackets">0</span></div>
            <div class="metric"><span class="label">Video Frames</span><span class="value" id="videoFrames">0</span></div>
          </section>
          <pre id="log"></pre>
        </main>
        <script>
        const mediaName = __MEDIA_NAME__;
        const sourceStats = __SOURCE_STATS__;
        const source = document.getElementById('source');
        const remote = document.getElementById('remote');
        const start = document.getElementById('start');
        const state = document.getElementById('state');
        const audioPackets = document.getElementById('audioPackets');
        const videoPackets = document.getElementById('videoPackets');
        const videoFrames = document.getElementById('videoFrames');
        const log = document.getElementById('log');
        source.src = mediaName;
        remote.muted = true;

        function writeLog(line) {
          log.textContent += line + '\\n';
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

        function waitForState(target, name, predicate) {
          if (predicate()) {
            return Promise.resolve();
          }
          return waitForEvent(target, name, () => predicate());
        }

        function makeIceRelay(sourcePc, sinkPc) {
          const queue = [];
          let ready = false;
          sourcePc.addEventListener('icecandidate', event => {
            if (!event.candidate) {
              return;
            }
            if (ready) {
              void sinkPc.addIceCandidate(event.candidate);
            } else {
              queue.push(event.candidate);
            }
          });
          return {
            async enable() {
              ready = true;
              for (const candidate of queue.splice(0)) {
                await sinkPc.addIceCandidate(candidate);
              }
            }
          };
        }

        function codecPreferences(kind, mimeType) {
          const capabilities = RTCRtpSender.getCapabilities(kind);
          if (!capabilities || !capabilities.codecs) {
            return [];
          }
          const wanted = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase() === mimeType);
          const helpers = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase().indexOf('rtx') >= 0);
          return wanted.concat(helpers);
        }

        async function statsLoop(audioReceiver, videoReceiver) {
          while (true) {
            for (const stat of (await audioReceiver.getStats()).values()) {
              if (stat.type === 'inbound-rtp' && (stat.kind === 'audio' || stat.mediaType === 'audio')) {
                audioPackets.textContent = String(stat.packetsReceived || 0);
              }
            }
            for (const stat of (await videoReceiver.getStats()).values()) {
              if (stat.type === 'inbound-rtp' && (stat.kind === 'video' || stat.mediaType === 'video')) {
                videoPackets.textContent = String(stat.packetsReceived || 0);
                videoFrames.textContent = String(stat.framesDecoded || stat.framesReceived || 0);
              }
            }
            await new Promise(resolve => setTimeout(resolve, 500));
          }
        }

        async function run() {
          start.disabled = true;
          state.textContent = 'starting';
          writeLog('source=' + JSON.stringify(sourceStats));
          await waitForState(source, 'loadedmetadata', () => source.readyState >= 1);
          await source.play();

          const capture = source.captureStream ? source.captureStream() : source.mozCaptureStream();
          if (!capture) {
            throw new Error('captureStream is unavailable');
          }
          const audioTrack = capture.getAudioTracks()[0];
          const videoTrack = capture.getVideoTracks()[0];
          if (!audioTrack || !videoTrack) {
            throw new Error('captured stream is missing audio or video');
          }

          const pc1 = new RTCPeerConnection({iceServers: []});
          const pc2 = new RTCPeerConnection({iceServers: []});
          const relay12 = makeIceRelay(pc1, pc2);
          const relay21 = makeIceRelay(pc2, pc1);
          const remoteStream = new MediaStream();
          remote.srcObject = remoteStream;

          const audioEventPromise = waitForEvent(pc2, 'track', event => event.track.kind === 'audio');
          const videoEventPromise = waitForEvent(pc2, 'track', event => event.track.kind === 'video');
          pc2.addEventListener('track', event => {
            remoteStream.addTrack(event.track);
          });

          const audioTransceiver = pc1.addTransceiver(audioTrack, {direction: 'sendonly'});
          const opus = codecPreferences('audio', 'audio/opus');
          if (opus.length > 0) {
            audioTransceiver.setCodecPreferences(opus);
          }
          const videoTransceiver = pc1.addTransceiver(videoTrack, {direction: 'sendonly'});
          const vp8 = codecPreferences('video', 'video/vp8');
          if (vp8.length > 0) {
            videoTransceiver.setCodecPreferences(vp8);
          }

          const offer = await pc1.createOffer();
          await pc1.setLocalDescription(offer);
          await pc2.setRemoteDescription(pc1.localDescription);
          await relay12.enable();
          const answer = await pc2.createAnswer();
          await pc2.setLocalDescription(answer);
          await pc1.setRemoteDescription(pc2.localDescription);
          await relay21.enable();

          const audioEvent = await audioEventPromise;
          const videoEvent = await videoEventPromise;
          await Promise.all([
            waitForState(pc1, 'connectionstatechange', () => pc1.connectionState === 'connected'),
            waitForState(pc2, 'connectionstatechange', () => pc2.connectionState === 'connected'),
          ]);
          const audioReceiver = pc2.getReceivers().find(receiver => receiver.track === audioEvent.track);
          const videoReceiver = pc2.getReceivers().find(receiver => receiver.track === videoEvent.track);
          if (!audioReceiver || !videoReceiver) {
            throw new Error('receiver lookup failed');
          }

          state.textContent = 'connected';
          writeLog('offer has audio=' + pc1.localDescription.sdp.includes('m=audio'));
          writeLog('offer has video=' + pc1.localDescription.sdp.includes('m=video'));
          void statsLoop(audioReceiver, videoReceiver);
        }

        start.addEventListener('click', () => {
          run().catch(error => {
            state.textContent = 'failed';
            writeLog(error.stack || String(error));
            start.disabled = false;
          });
        });
        </script>
        """
    ).strip().replace("__MEDIA_NAME__", media_json).replace("__SOURCE_STATS__", stats_json)


def wait_for_result(client: CDPClient, session_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = client.command(
            "Runtime.evaluate",
            {
                "expression": "typeof window.__ffmpegChromeCallResult === 'undefined' ? null : JSON.stringify(window.__ffmpegChromeCallResult)",
                "returnByValue": True,
            },
            session_id=session_id,
        )
        evaluated = response.get("result")
        if isinstance(evaluated, dict) and evaluated.get("type") == "string":
            result_text = str(evaluated.get("value", ""))
            if result_text:
                parsed = json.loads(result_text)
                if isinstance(parsed, dict):
                    return parsed
        time.sleep(0.2)
    raise TimeoutError("browser page did not publish ffmpeg chrome call result")


def run_chrome_page(tempdir_path: Path) -> dict[str, Any]:
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
        try:
            target = client.command("Target.createTarget", {"url": "about:blank"})
            target_id = str(target["targetId"])
            attached = client.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
            session_id = str(attached["sessionId"])
            client.command("Runtime.enable", session_id=session_id)
            client.command("Page.enable", session_id=session_id)
            client.command("Page.navigate", {"url": f"http://127.0.0.1:{http_port}/index.html"}, session_id=session_id)
            return wait_for_result(client, session_id)
        finally:
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


def validate_browser_result(result: dict[str, Any]) -> None:
    require(result.get("ok") is True, f"browser page reported failure: {result}")
    require(result.get("pc1ConnectionState") == "closed", "pc1 should be closed after cleanup")
    require(result.get("pc2ConnectionState") == "closed", "pc2 should be closed after cleanup")
    tracks = result.get("tracks")
    require(isinstance(tracks, list) and "audio" in tracks, "Chrome did not surface an audio track")
    require(isinstance(tracks, list) and "video" in tracks, "Chrome did not surface a video track")
    require(int(result.get("audioPacketsReceived", 0)) > 0, "Chrome received no audio packets")
    require(int(result.get("videoPacketsReceived", 0)) > 0, "Chrome received no video packets")
    require(int(result.get("videoFramesDecoded", 0)) > 0, "Chrome decoded no video frames")
    offer_sdp = str(result.get("offerSdp", "")).lower()
    answer_sdp = str(result.get("answerSdp", "")).lower()
    require("m=audio" in offer_sdp and "m=audio" in answer_sdp, "SDP missing audio m-line")
    require("m=video" in offer_sdp and "m=video" in answer_sdp, "SDP missing video m-line")
    require("opus/48000" in offer_sdp or "opus/48000" in answer_sdp, "SDP missing Opus negotiation")
    require("vp8/90000" in offer_sdp or "vp8/90000" in answer_sdp, "SDP missing VP8 negotiation")


def run_flow(keep_temp: bool = False) -> str:
    with tempfile.TemporaryDirectory(prefix="webrtc-ffmpeg-chrome-call-") as tmp:
        tempdir_path = Path(tmp)
        media_path, ffmpeg_stats = generate_ffmpeg_media(tempdir_path)
        page_path = tempdir_path / "index.html"
        page_path.write_text(make_call_page(media_path.name), encoding="utf-8")
        result = run_chrome_page(tempdir_path)
        validate_browser_result(result)

        if keep_temp:
            kept = Path(tempfile.mkdtemp(prefix="webrtc-ffmpeg-chrome-call-kept-"))
            for path in tempdir_path.iterdir():
                if path.is_file():
                    (kept / path.name).write_bytes(path.read_bytes())
            temp_note = f" kept={kept}"
        else:
            temp_note = ""

        return (
            "ffmpeg chrome call checks passed: "
            f"source_audio_codec={ffmpeg_stats['audio_codec']} "
            f"source_audio_packets={ffmpeg_stats['audio_packets']} "
            f"source_video_codec={ffmpeg_stats['video_codec']} "
            f"source_video_packets={ffmpeg_stats['video_packets']} "
            f"chrome_audio_packets={result.get('audioPacketsReceived')} "
            f"chrome_video_packets={result.get('videoPacketsReceived')} "
            f"chrome_video_frames={result.get('videoFramesDecoded')}"
            f"{temp_note}"
        )


def write_preview(preview_dir: Path) -> str:
    preview_dir.mkdir(parents=True, exist_ok=True)
    media_path, ffmpeg_stats = generate_ffmpeg_media(preview_dir)
    page_path = preview_dir / "index.html"
    page_path.write_text(make_preview_page(media_path.name, ffmpeg_stats), encoding="utf-8")
    return f"ffmpeg chrome preview written: dir={preview_dir} page={page_path}"


def serve_preview(preview_dir: Path) -> int:
    server, thread, http_port = start_http_server(preview_dir)
    url = f"http://127.0.0.1:{http_port}/"
    print(f"ffmpeg chrome preview serving: {url}", flush=True)
    print("press Ctrl-C to stop", flush=True)
    try:
        while True:
            time.sleep(3600.0)
    except KeyboardInterrupt:
        print("ffmpeg chrome preview stopped", flush=True)
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-temp", action="store_true", help="copy generated headless-test artifacts to a retained temp directory")
    parser.add_argument("--preview-dir", type=Path, help="write a manual Chrome preview page into this directory")
    parser.add_argument("--serve-preview", action="store_true", help="serve the manual preview page and wait until Ctrl-C")
    args = parser.parse_args()
    try:
        if args.preview_dir is not None or args.serve_preview:
            preview_dir = args.preview_dir or Path(tempfile.mkdtemp(prefix="webrtc-ffmpeg-chrome-preview-"))
            print(write_preview(preview_dir), flush=True)
            if args.serve_preview:
                return serve_preview(preview_dir)
            return 0

        print(run_flow(args.keep_temp))
        return 0
    except SkipFlow as exc:
        print(f"ffmpeg chrome call skipped: {exc}")
        return 0
    except (AssertionError, InteropError, TimeoutError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
