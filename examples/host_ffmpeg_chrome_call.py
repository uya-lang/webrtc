#!/usr/bin/env python3
"""Manual host-device FFmpeg <-> Chrome bidirectional media call.

The Uya side uses ``src/webrtc_ffmpeg_direct_sender_main.uya`` through the
PeerConnection direct API. Uya video defaults to a synthetic I420 source so a
single host camera can be reserved for Chrome; audio is captured by FFmpeg into
a PCM FIFO. Chrome captures the host camera and microphone with getUserMedia,
sends them back on the same PeerConnection, and renders the Uya-originated
remote stream.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from browser_datachannel_interop import find_free_port  # noqa: E402
from ffmpeg_chrome_call import (  # noqa: E402
    ManualPreviewHandler,
    UyaDirectSenderHandle,
    read_sender_diagnostics,
    start_uya_direct_sender,
    stop_uya_direct_sender,
    wait_for_uya_direct_sender,
)


DEFAULT_VIDEO_DEVICE = "synthetic"
DEFAULT_V4L2_FORMAT = "yuyv"
DEFAULT_WIDTH = 320
DEFAULT_HEIGHT = 240
DEFAULT_FPS = 15
DEFAULT_DURATION_US = 120_000_000
DEFAULT_AUDIO_FORMAT = "alsa"
DEFAULT_AUDIO_DEVICE = "default"
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_LOCAL_HOST = "auto"
DEFAULT_PLAYBACK = "1"


@dataclass
class HostCallConfig:
    local_host: str
    video_device: str | None
    v4l2_format: str
    video_width: int
    video_height: int
    fps: int
    media_duration_us: int
    audio_format: str
    audio_device: str
    playback: bool

    @property
    def video_frame_duration_us(self) -> int:
        return max(1, int(round(1_000_000 / max(1, self.fps))))

    @property
    def uya_video_source(self) -> str:
        if self.video_device is None:
            return "synthetic"
        return self.video_device


@dataclass
class HostCallSession:
    session_id: str
    handle: UyaDirectSenderHandle
    workdir: Path
    audio_proc: subprocess.Popen[str] | None
    playback_procs: list[subprocess.Popen[str]]
    fifo_anchor_fds: list[int]


class HostCallState:
    def __init__(self, workdir: Path, config: HostCallConfig) -> None:
        self.workdir = workdir
        self.config = config
        self.sessions_dir = workdir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: dict[str, HostCallSession] = {}
        self.lock = threading.Lock()

    def start_call(self, offer: dict[str, str], video_settings: dict[str, Any] | None = None) -> tuple[str, str]:
        session_id = uuid.uuid4().hex[:12]
        workdir = self.sessions_dir / session_id
        workdir.mkdir(parents=True, exist_ok=False)
        playback_width, playback_height, playback_fps = normalize_chrome_video_settings(video_settings, self.config)
        media_path = workdir / "host_ffmpeg_placeholder.webm"
        media_path.write_text("host ffmpeg live device source\n", encoding="utf-8")
        audio_fifo = workdir / "mic_48000_mono_s16le.fifo"
        os.mkfifo(audio_fifo)
        playback_audio_fifo: Path | None = None
        playback_video_fifo: Path | None = None
        if self.config.playback:
            playback_audio_fifo = workdir / "chrome_to_uya_48000_mono_s16le.fifo"
            playback_video_fifo = workdir / "chrome_to_uya_i420.fifo"
            os.mkfifo(playback_audio_fifo)
            os.mkfifo(playback_video_fifo)
        offer_sdp = str(offer.get("sdp") or "")
        local_host = select_uya_local_host(offer_sdp, self.config.local_host)

        handle: UyaDirectSenderHandle | None = None
        audio_proc: subprocess.Popen[str] | None = None
        playback_procs: list[subprocess.Popen[str]] = []
        fifo_anchor_fds: list[int] = []
        try:
            if self.config.playback:
                assert playback_audio_fifo is not None and playback_video_fifo is not None
                fifo_anchor_fds = open_fifo_read_anchors([playback_audio_fifo, playback_video_fifo])
                playback_procs = start_ffplay_playback(
                    playback_audio_fifo,
                    playback_video_fifo,
                    playback_width,
                    playback_height,
                    playback_fps,
                )
            audio_proc = start_ffmpeg_audio_fifo(
                audio_fifo,
                self.config.audio_format,
                self.config.audio_device,
            )
            handle = start_uya_direct_sender(
                offer,
                media_path,
                workdir,
                raw_audio_path=audio_fifo,
                playback_audio_path=playback_audio_fifo,
                playback_video_path=playback_video_fifo,
                raw_video_width=playback_width,
                raw_video_height=playback_height,
                media_duration_us=self.config.media_duration_us,
                video_frame_duration_us=max(1, int(round(1_000_000 / max(1, playback_fps)))),
                local_host=local_host,
                v4l2_device=self.config.video_device,
                v4l2_format=self.config.v4l2_format,
                force_video_dimensions=True,
            )
        except Exception:
            close_fifo_anchors(fifo_anchor_fds)
            stop_processes(playback_procs)
            if audio_proc is not None:
                stop_process(audio_proc)
            if handle is not None:
                stop_uya_direct_sender(handle)
            raise

        with self.lock:
            self.sessions[session_id] = HostCallSession(session_id, handle, workdir, audio_proc, playback_procs, fifo_anchor_fds)
        return session_id, handle.answer_sdp

    def finish_call(self, session_id: str) -> dict[str, Any]:
        session = self._pop_session(session_id)
        try:
            diagnostics = wait_for_uya_direct_sender(session.handle)
        finally:
            if session.audio_proc is not None:
                stop_process(session.audio_proc)
            stop_processes(session.playback_procs)
            close_fifo_anchors(session.fifo_anchor_fds)
        return diagnostics

    def stop_call(self, session_id: str) -> dict[str, Any]:
        session = self._pop_session(session_id)
        stop_uya_direct_sender(session.handle)
        if session.audio_proc is not None:
            stop_process(session.audio_proc)
        stop_processes(session.playback_procs)
        close_fifo_anchors(session.fifo_anchor_fds)
        return read_sender_diagnostics(session.handle.diagnostics_path)

    def stop_all(self) -> None:
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions:
            stop_uya_direct_sender(session.handle)
            if session.audio_proc is not None:
                stop_process(session.audio_proc)
            stop_processes(session.playback_procs)
            close_fifo_anchors(session.fifo_anchor_fds)

    def _pop_session(self, session_id: str) -> HostCallSession:
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if session is None:
            raise AssertionError(f"unknown host call session: {session_id}")
        return session


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)


def stop_processes(procs: list[subprocess.Popen[str]]) -> None:
    for proc in procs:
        stop_process(proc)


def open_fifo_read_anchors(paths: list[Path]) -> list[int]:
    fds: list[int] = []
    try:
        for path in paths:
            fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
    except Exception:
        close_fifo_anchors(fds)
        raise
    return fds


def close_fifo_anchors(fds: list[int]) -> None:
    while fds:
        fd = fds.pop()
        try:
            os.close(fd)
        except OSError:
            pass


def even_positive(value: Any, fallback: int) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = fallback
    if parsed <= 0:
        parsed = fallback
    if parsed % 2 != 0:
        parsed -= 1
    if parsed <= 0:
        parsed = fallback if fallback % 2 == 0 else fallback - 1
    return max(2, parsed)


def positive_fps(value: Any, fallback: int) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = fallback
    if parsed <= 0:
        parsed = fallback
    return max(1, parsed)


def normalize_chrome_video_settings(video_settings: dict[str, Any] | None, config: HostCallConfig) -> tuple[int, int, int]:
    if not isinstance(video_settings, dict):
        return config.video_width, config.video_height, config.fps
    width = even_positive(video_settings.get("width"), config.video_width)
    height = even_positive(video_settings.get("height"), config.video_height)
    fps = positive_fps(video_settings.get("frameRate"), config.fps)
    return width, height, fps


def start_ffmpeg_audio_fifo(
    fifo_path: Path,
    audio_format: str,
    audio_device: str,
) -> subprocess.Popen[str]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AssertionError("ffmpeg not found on PATH; it is required for host microphone capture")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-nostdin",
        "-f",
        audio_format,
        "-channels",
        "1",
        "-sample_rate",
        "48000",
        "-i",
        audio_device,
        "-ac",
        "1",
        "-ar",
        "48000",
        "-acodec",
        "pcm_s16le",
        "-f",
        "s16le",
        str(fifo_path),
    ]
    return subprocess.Popen(command, cwd=REPO_ROOT, text=True)


def start_ffplay_playback(
    audio_fifo: Path,
    video_fifo: Path,
    width: int,
    height: int,
    fps: int,
) -> list[subprocess.Popen[str]]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AssertionError("ffmpeg not found on PATH; it is required for synchronized Uya-side playback")
    ffplay = shutil.which("ffplay")
    if ffplay is None:
        raise AssertionError("ffplay not found on PATH; it is required for Uya-side received media playback")
    mux_command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-fflags",
        "nobuffer",
        "-thread_queue_size",
        "64",
        "-use_wallclock_as_timestamps",
        "1",
        "-f",
        "s16le",
        "-ar",
        "48000",
        "-ac",
        "1",
        "-i",
        str(audio_fifo),
        "-thread_queue_size",
        "64",
        "-use_wallclock_as_timestamps",
        "1",
        "-f",
        "rawvideo",
        "-pixel_format",
        "yuv420p",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(fps),
        "-i",
        str(video_fifo),
        "-map",
        "0:a:0",
        "-map",
        "1:v:0",
        "-c:a",
        "pcm_s16le",
        "-c:v",
        "rawvideo",
        "-flush_packets",
        "1",
        "-max_delay",
        "500000",
        "-f",
        "nut",
        "pipe:1",
    ]
    ffplay_command = [
        ffplay,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-window_title",
        "Uya received Chrome AV",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-framedrop",
        "-sync",
        "audio",
        "-probesize",
        "2048",
        "-analyzeduration",
        "0",
        "-max_delay",
        "500000",
        "-",
    ]
    mux_proc = subprocess.Popen(
        mux_command,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
    )
    if mux_proc.stdout is None:
        stop_process(mux_proc)
        raise AssertionError("ffmpeg playback muxer did not expose stdout")
    ffplay_proc = subprocess.Popen(
        ffplay_command,
        cwd=REPO_ROOT,
        stdin=mux_proc.stdout,
        stdout=subprocess.DEVNULL,
    )
    mux_proc.stdout.close()
    procs = [ffplay_proc, mux_proc]
    time.sleep(0.5)
    for proc, command in zip(procs, (ffplay_command, mux_command)):
        if proc.poll() is not None:
            stop_processes(procs)
            raise AssertionError(f"playback process exited during startup: {' '.join(command)}")
    return procs


def make_host_call_page(config: HostCallConfig) -> str:
    config_json = json.dumps(
        {
            "videoWidth": config.video_width,
            "videoHeight": config.video_height,
            "fps": config.fps,
            "mediaDurationUs": config.media_duration_us,
            "videoDevice": config.uya_video_source,
            "audioDevice": config.audio_device,
            "playback": config.playback,
        },
        sort_keys=True,
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Host FFmpeg Chrome Call</title>
<style>
  :root {{ color-scheme: light; font-family: system-ui, -apple-system, Segoe UI, sans-serif; }}
  body {{ margin: 0; background: #f6f8fb; color: #172033; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 18px; }}
  header {{ align-items: center; display: flex; justify-content: space-between; gap: 12px; margin-bottom: 14px; }}
  h1 {{ font-size: 22px; margin: 0; }}
  .actions {{ display: flex; gap: 8px; }}
  button {{ border: 0; border-radius: 6px; background: #0f766e; color: white; cursor: pointer; font: inherit; font-weight: 700; min-height: 40px; padding: 0 16px; }}
  button.secondary {{ background: #475569; }}
  button:disabled {{ cursor: default; opacity: .55; }}
  .devices {{ align-items: end; display: grid; grid-template-columns: 1fr 1fr auto; gap: 8px; margin-bottom: 12px; }}
  label {{ color: #42526b; display: grid; font-size: 12px; gap: 4px; }}
  select {{ border: 1px solid #cbd5e1; border-radius: 6px; font: inherit; min-height: 38px; padding: 0 10px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  .pane {{ background: white; border: 1px solid #d7dee8; border-radius: 8px; overflow: hidden; }}
  .pane h2 {{ font-size: 14px; margin: 0; padding: 10px 12px; border-bottom: 1px solid #e5e9f0; }}
  video {{ aspect-ratio: 16 / 9; background: #05070c; display: block; object-fit: contain; width: 100%; }}
  .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }}
  .metric {{ background: white; border: 1px solid #d7dee8; border-radius: 8px; padding: 9px 11px; }}
  .label {{ color: #64748b; display: block; font-size: 12px; }}
  .value {{ font-size: 18px; font-weight: 750; }}
  pre {{ background: #101624; border-radius: 8px; color: #d7e2f0; min-height: 160px; overflow: auto; padding: 12px; white-space: pre-wrap; }}
  @media (max-width: 760px) {{ .grid, .metrics, .devices {{ grid-template-columns: 1fr; }} header {{ align-items: flex-start; flex-direction: column; }} }}
</style>
<main>
  <header>
    <h1>Host FFmpeg Chrome Call</h1>
    <div class="actions">
      <button id="start">Start</button>
      <button id="stop" class="secondary" disabled>Stop</button>
    </div>
  </header>
  <section class="devices">
    <label>Camera<select id="videoDevice"><option value="">Auto</option></select></label>
    <label>Microphone<select id="audioDevice"><option value="">Auto</option></select></label>
    <button id="refreshDevices" class="secondary">Refresh Devices</button>
  </section>
  <section class="grid">
    <div class="pane"><h2>Chrome Local</h2><video id="localVideo" muted playsinline autoplay></video></div>
    <div class="pane"><h2>Uya Remote ({config.uya_video_source})</h2><video id="remoteVideo" playsinline autoplay controls></video></div>
  </section>
  <section class="metrics">
    <div class="metric"><span class="label">State</span><span id="state" class="value">idle</span></div>
    <div class="metric"><span class="label">Chrome In A/V</span><span id="chromeIn" class="value">0 / 0</span></div>
    <div class="metric"><span class="label">Chrome Out A/V</span><span id="chromeOut" class="value">0 / 0</span></div>
    <div class="metric"><span class="label">Uya In A/V</span><span id="uyaIn" class="value">0 / 0</span></div>
  </section>
  <pre id="log"></pre>
</main>
<script>
const config = {config_json};
let peer = null;
let localStream = null;
let remoteStream = null;
let sessionId = '';
let statsTimer = 0;
let latestStats = {{}};
const startButton = document.getElementById('start');
const stopButton = document.getElementById('stop');
const refreshDevicesButton = document.getElementById('refreshDevices');
const videoDeviceSelect = document.getElementById('videoDevice');
const audioDeviceSelect = document.getElementById('audioDevice');
const localVideo = document.getElementById('localVideo');
const remoteVideo = document.getElementById('remoteVideo');
const stateText = document.getElementById('state');
const chromeIn = document.getElementById('chromeIn');
const chromeOut = document.getElementById('chromeOut');
const uyaIn = document.getElementById('uyaIn');
const log = document.getElementById('log');

function writeLog(message) {{
  log.textContent += String(message) + '\\n';
  log.scrollTop = log.scrollHeight;
}}

function setState(value) {{
  stateText.textContent = value;
  writeLog('state=' + value);
}}

function replaceOptions(select, devices, fallbackLabel) {{
  const previous = select.value;
  select.innerHTML = '';
  const auto = document.createElement('option');
  auto.value = '';
  auto.textContent = 'Auto';
  select.appendChild(auto);
  devices.forEach((device, index) => {{
    const option = document.createElement('option');
    option.value = device.deviceId;
    option.textContent = device.label || fallbackLabel + ' ' + String(index + 1);
    select.appendChild(option);
  }});
  if ([...select.options].some(option => option.value === previous)) {{
    select.value = previous;
  }}
}}

async function refreshDeviceList() {{
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {{
    writeLog('mediaDevices.enumerateDevices unavailable');
    return {{audioInputs: [], videoInputs: []}};
  }}
  const devices = await navigator.mediaDevices.enumerateDevices();
  const audioInputs = devices.filter(device => device.kind === 'audioinput');
  const videoInputs = devices.filter(device => device.kind === 'videoinput');
  replaceOptions(audioDeviceSelect, audioInputs, 'Microphone');
  replaceOptions(videoDeviceSelect, videoInputs, 'Camera');
  writeLog('chrome_devices audioinput=' + String(audioInputs.length) + ' videoinput=' + String(videoInputs.length));
  audioInputs.forEach((device, index) => writeLog('audioinput[' + index + ']=' + (device.label || '(label hidden)')));
  videoInputs.forEach((device, index) => writeLog('videoinput[' + index + ']=' + (device.label || '(label hidden)')));
  return {{audioInputs, videoInputs}};
}}

function makeMediaConstraints(simple) {{
  if (simple) {{
    return {{audio: true, video: true}};
  }}
  let audio = true;
  if (audioDeviceSelect.value) {{
    audio = {{deviceId: {{exact: audioDeviceSelect.value}}}};
  }}
  const video = {{
    width: {{exact: config.videoWidth}},
    height: {{exact: config.videoHeight}},
    frameRate: {{ideal: config.fps, max: config.fps}}
  }};
  if (videoDeviceSelect.value) {{
    video.deviceId = {{exact: videoDeviceSelect.value}};
  }}
  return {{audio, video}};
}}

async function openLocalMedia() {{
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
    throw new Error('Chrome mediaDevices.getUserMedia unavailable; use a normal Chrome window on http://127.0.0.1');
  }}
  await refreshDeviceList();
  try {{
    return await navigator.mediaDevices.getUserMedia(makeMediaConstraints(false));
  }} catch (error) {{
    writeLog('getUserMedia failed: ' + String(error.name || '') + ' ' + String(error.message || error));
    await refreshDeviceList().catch(deviceError => writeLog('enumerate after failure failed: ' + String(deviceError.message || deviceError)));
    if (!audioDeviceSelect.value && !videoDeviceSelect.value) {{
      writeLog('retrying getUserMedia with simple audio/video constraints');
      try {{
        return await navigator.mediaDevices.getUserMedia(makeMediaConstraints(true));
      }} catch (retryError) {{
        writeLog('simple getUserMedia failed: ' + String(retryError.name || '') + ' ' + String(retryError.message || retryError));
      }}
    }}
    throw new Error('Chrome could not open both camera and microphone: ' + String(error.name || '') + ' ' + String(error.message || error));
  }}
}}

function delay(ms) {{
  return new Promise(resolve => setTimeout(resolve, ms));
}}

function captureVideoSettings(track) {{
  const settings = track && track.getSettings ? track.getSettings() : {{}};
  const width = Math.max(2, Number(settings.width || config.videoWidth) | 0);
  const height = Math.max(2, Number(settings.height || config.videoHeight) | 0);
  const frameRate = Math.max(1, Math.round(Number(settings.frameRate || config.fps)));
  const normalized = {{
    width: width % 2 === 0 ? width : width - 1,
    height: height % 2 === 0 ? height : height - 1,
    frameRate
  }};
  writeLog('chrome_video_settings=' + String(normalized.width) + 'x' + String(normalized.height) + '@' + String(normalized.frameRate));
  return normalized;
}}

async function postJson(path, body) {{
  const response = await fetch(path, {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body)
  }});
  const data = await response.json();
  if (!response.ok || !data || data.ok !== true) {{
    throw new Error((data && data.error) || path + ' failed');
  }}
  return data;
}}

function preferredCodecs(kind, mimeType) {{
  const capabilities = RTCRtpReceiver.getCapabilities(kind);
  if (!capabilities || !capabilities.codecs) return [];
  const wanted = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase() === mimeType);
  const helpers = capabilities.codecs.filter(codec => String(codec.mimeType).toLowerCase().indexOf('rtx') >= 0);
  return wanted.concat(helpers);
}}

function waitForEvent(target, name, predicate) {{
  return new Promise((resolve, reject) => {{
    const handler = event => {{
      try {{
        if (!predicate || predicate(event)) {{
          target.removeEventListener(name, handler);
          resolve(event);
        }}
      }} catch (error) {{
        target.removeEventListener(name, handler);
        reject(error);
      }}
    }};
    target.addEventListener(name, handler);
  }});
}}

async function waitForGatheringComplete(pc) {{
  if (pc.iceGatheringState === 'complete') return;
  await waitForEvent(pc, 'icegatheringstatechange', () => pc.iceGatheringState === 'complete');
}}

async function readInbound(kind, receiver) {{
  if (!receiver) return {{packets: 0, frames: 0}};
  const stats = await receiver.getStats();
  for (const stat of stats.values()) {{
    if (stat.type !== 'inbound-rtp') continue;
    if (stat.kind !== kind && stat.mediaType !== kind) continue;
    return {{packets: stat.packetsReceived || 0, frames: stat.framesDecoded || stat.framesReceived || 0}};
  }}
  return {{packets: 0, frames: 0}};
}}

async function readOutbound(kind, sender) {{
  if (!sender) return {{packets: 0, frames: 0}};
  const stats = await sender.getStats();
  for (const stat of stats.values()) {{
    if (stat.type !== 'outbound-rtp') continue;
    if (stat.kind !== kind && stat.mediaType !== kind) continue;
    return {{packets: stat.packetsSent || 0, frames: stat.framesEncoded || 0}};
  }}
  return {{packets: 0, frames: 0}};
}}

async function updateChromeStats() {{
  if (!peer) return;
  const audioReceiver = peer.getReceivers().find(item => item.track && item.track.kind === 'audio');
  const videoReceiver = peer.getReceivers().find(item => item.track && item.track.kind === 'video');
  const audioSender = peer.getSenders().find(item => item.track && item.track.kind === 'audio');
  const videoSender = peer.getSenders().find(item => item.track && item.track.kind === 'video');
  const inAudio = await readInbound('audio', audioReceiver);
  const inVideo = await readInbound('video', videoReceiver);
  const outAudio = await readOutbound('audio', audioSender);
  const outVideo = await readOutbound('video', videoSender);
  latestStats = {{inAudio, inVideo, outAudio, outVideo}};
  chromeIn.textContent = String(inAudio.packets) + ' / ' + String(inVideo.frames || inVideo.packets);
  chromeOut.textContent = String(outAudio.packets) + ' / ' + String(outVideo.frames || outVideo.packets);
  if (inAudio.packets > 0 && inVideo.frames > 0 && outAudio.packets > 0 && outVideo.packets > 0 && stateText.textContent !== 'live') {{
    setState('live');
  }}
}}

async function startCall() {{
  startButton.disabled = true;
  stopButton.disabled = false;
  log.textContent = '';
  setState('media');
  localStream = await openLocalMedia();
  localVideo.srcObject = localStream;
  remoteStream = new MediaStream();
  remoteVideo.srcObject = remoteStream;

  peer = new RTCPeerConnection({{iceServers: []}});
  peer.addEventListener('connectionstatechange', () => writeLog('connection=' + peer.connectionState));
  peer.addEventListener('iceconnectionstatechange', () => writeLog('ice=' + peer.iceConnectionState));
  peer.addEventListener('track', event => {{
    remoteStream.addTrack(event.track);
    remoteVideo.play().catch(error => writeLog('remoteVideo.play=' + String(error.message || error)));
  }});

  const audioTrack = localStream.getAudioTracks()[0];
  const videoTrack = localStream.getVideoTracks()[0];
  if (!audioTrack || !videoTrack) throw new Error('Chrome did not open both microphone and camera');
  const videoSettings = captureVideoSettings(videoTrack);
  const audioTransceiver = peer.addTransceiver(audioTrack, {{direction: 'sendrecv'}});
  const opus = preferredCodecs('audio', 'audio/opus');
  if (opus.length > 0) audioTransceiver.setCodecPreferences(opus);
  const videoTransceiver = peer.addTransceiver(videoTrack, {{direction: 'sendrecv'}});
  const vp8 = preferredCodecs('video', 'video/vp8');
  if (vp8.length > 0) videoTransceiver.setCodecPreferences(vp8);

  setState('offer');
  const offer = await peer.createOffer();
  await peer.setLocalDescription(offer);
  await waitForGatheringComplete(peer);
  const started = await postJson('/api/start-call', {{
    offer: {{type: peer.localDescription.type, sdp: peer.localDescription.sdp}},
    videoSettings
  }});
  sessionId = String(started.sessionId || '');
  if (!sessionId || !started.answer || !started.answer.sdp) throw new Error('missing Uya answer');
  setState('answer');
  await peer.setRemoteDescription({{type: 'answer', sdp: String(started.answer.sdp)}});
  writeLog('session=' + sessionId);
  statsTimer = window.setInterval(() => updateChromeStats().catch(error => writeLog('stats=' + String(error.message || error))), 500);
  await updateChromeStats();
}}

async function stopCall() {{
  stopButton.disabled = true;
  if (statsTimer) {{
    window.clearInterval(statsTimer);
    statsTimer = 0;
  }}
  let diagnostics = {{}};
  if (sessionId) {{
    setState('stopping');
    const stopped = await postJson('/api/stop-call', {{sessionId}});
    diagnostics = stopped.diagnostics || {{}};
    sessionId = '';
    uyaIn.textContent = String(diagnostics.audioRtpPacketsReceived || 0) + ' / ' + String(diagnostics.videoFramesReceived || diagnostics.videoRtpPacketsReceived || 0);
    writeLog('diagnostics=' + JSON.stringify(diagnostics));
  }}
  if (peer) {{
    peer.close();
    peer = null;
  }}
  if (localStream) {{
    localStream.getTracks().forEach(track => track.stop());
    localStream = null;
  }}
  setState('stopped');
  startButton.disabled = false;
  window.__hostFfmpegChromeCallResult = {{
    ok: true,
    chromeStats: latestStats,
    senderDiagnostics: diagnostics
  }};
}}

startButton.addEventListener('click', () => startCall().catch(async error => {{
  writeLog('ERROR: ' + String(error.stack || error.message || error));
  await stopCall().catch(stopError => writeLog('stop error=' + String(stopError.message || stopError)));
  startButton.disabled = false;
}}));
stopButton.addEventListener('click', () => stopCall().catch(error => writeLog('ERROR: ' + String(error.stack || error.message || error))));
refreshDevicesButton.addEventListener('click', () => refreshDeviceList().catch(error => writeLog('ERROR: ' + String(error.stack || error.message || error))));
refreshDeviceList().catch(error => writeLog('initial enumerate failed: ' + String(error.message || error)));
</script>
"""


def start_host_call_server(workdir: Path, state: HostCallState, host: str, port: int) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    page_path = workdir / "index.html"
    page_path.write_text(make_host_call_page(state.config), encoding="utf-8")
    bind_port = port if port > 0 else find_free_port()
    handler = partial(ManualPreviewHandler, directory=str(workdir), state=state)
    server = ThreadingHTTPServer((host, bind_port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, bind_port


def serve(config: HostCallConfig, workdir: Path, host: str, port: int) -> int:
    workdir.mkdir(parents=True, exist_ok=True)
    state = HostCallState(workdir, config)
    server, thread, bind_port = start_host_call_server(workdir, state, host, port)
    url_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"host ffmpeg chrome call serving: http://{url_host}:{bind_port}/", flush=True)
    print("press Ctrl-C to stop", flush=True)
    try:
        while True:
            time.sleep(3600.0)
    except KeyboardInterrupt:
        print("host ffmpeg chrome call stopped", flush=True)
        return 0
    finally:
        state.stop_all()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def normalize_video_device(value: str) -> str | None:
    text = value.strip()
    if text == "" or text.lower() in {"synthetic", "none", "off", "false", "0"}:
        return None
    return text


def parse_bool(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "off", "no", "none"}


def is_auto_local_host(value: str) -> bool:
    return value.strip().lower() in {"", "auto"}


def usable_ipv4_host(value: str) -> str | None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if address.version != 4 or address.is_unspecified or address.is_loopback:
        return None
    return str(address)


def offer_udp_host_candidates(sdp: str) -> list[str]:
    hosts: list[str] = []
    for raw_line in sdp.splitlines():
        line = raw_line.strip()
        if not line.startswith("a=candidate:"):
            continue
        fields = line[len("a=candidate:") :].split()
        if len(fields) < 8:
            continue
        if fields[2].lower() != "udp":
            continue
        if fields[6].lower() != "typ" or fields[7].lower() != "host":
            continue
        host = usable_ipv4_host(fields[4])
        if host is not None and host not in hosts:
            hosts.append(host)
    return hosts


def offer_connection_hosts(sdp: str) -> list[str]:
    hosts: list[str] = []
    for raw_line in sdp.splitlines():
        fields = raw_line.strip().split()
        if len(fields) == 3 and fields[0] == "c=IN" and fields[1] == "IP4":
            host = usable_ipv4_host(fields[2])
            if host is not None and host not in hosts:
                hosts.append(host)
    return hosts


def default_route_ipv4() -> str | None:
    route_host = default_route_ipv4_from_ip_route()
    if route_host is not None:
        return route_host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            host = usable_ipv4_host(sock.getsockname()[0])
    except OSError:
        return None
    return host


def default_route_ipv4_from_ip_route() -> str | None:
    try:
        output = subprocess.check_output(
            ["ip", "-4", "route", "show", "default"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in output.splitlines():
        fields = line.split()
        if "src" not in fields:
            continue
        index = fields.index("src")
        if index + 1 >= len(fields):
            continue
        host = usable_ipv4_host(fields[index + 1])
        if host is not None:
            return host
    return None


def select_uya_local_host(offer_sdp: str, configured_host: str) -> str:
    if not is_auto_local_host(configured_host):
        return configured_host.strip()
    default_host = default_route_ipv4()
    if default_host is not None:
        return default_host
    hosts = offer_udp_host_candidates(offer_sdp)
    if len(hosts) == 0:
        hosts = offer_connection_hosts(offer_sdp)
    if len(hosts) > 0:
        return hosts[0]
    return DEFAULT_BIND_HOST


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_BIND_HOST)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--workdir", type=Path, default=REPO_ROOT / "build" / "host-ffmpeg-chrome-call")
    parser.add_argument(
        "--local-host",
        default=os.environ.get("HOST_CALL_LOCAL_HOST", DEFAULT_LOCAL_HOST),
        help="IP written into Uya ICE host candidates; auto prefers the OS default-route IPv4",
    )
    parser.add_argument(
        "--video-device",
        default=os.environ.get("HOST_CALL_VIDEO_DEV", DEFAULT_VIDEO_DEVICE),
        help="Uya-side video device; use synthetic/none to avoid opening a host camera",
    )
    parser.add_argument("--v4l2-format", default=os.environ.get("PIXEL_FORMAT", DEFAULT_V4L2_FORMAT))
    parser.add_argument("--width", type=int, default=int(os.environ.get("WIDTH", DEFAULT_WIDTH)))
    parser.add_argument("--height", type=int, default=int(os.environ.get("HEIGHT", DEFAULT_HEIGHT)))
    parser.add_argument("--fps", type=int, default=int(os.environ.get("FPS", DEFAULT_FPS)))
    parser.add_argument("--duration-us", type=int, default=int(os.environ.get("MEDIA_DURATION_US", DEFAULT_DURATION_US)))
    parser.add_argument("--audio-format", default=os.environ.get("AUDIO_FORMAT", DEFAULT_AUDIO_FORMAT))
    parser.add_argument("--audio-device", default=os.environ.get("AUDIO_DEV", DEFAULT_AUDIO_DEVICE))
    parser.add_argument(
        "--playback",
        default=os.environ.get("HOST_CALL_PLAYBACK", DEFAULT_PLAYBACK),
        help="enable Uya-side decoded media playback through ffplay FIFOs",
    )
    args = parser.parse_args()

    if args.width <= 0 or args.height <= 0 or args.fps <= 0 or args.duration_us <= 0:
        parser.error("width, height, fps, and duration-us must be positive")
    if args.width % 2 != 0 or args.height % 2 != 0:
        parser.error("width and height must be even for I420 conversion")

    config = HostCallConfig(
        local_host=args.local_host,
        video_device=normalize_video_device(args.video_device),
        v4l2_format=args.v4l2_format,
        video_width=args.width,
        video_height=args.height,
        fps=args.fps,
        media_duration_us=args.duration_us,
        audio_format=args.audio_format,
        audio_device=args.audio_device,
        playback=parse_bool(args.playback),
    )
    return serve(config, args.workdir, args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
