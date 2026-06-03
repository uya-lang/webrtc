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
import json
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


REPO_ROOT = Path(__file__).resolve().parent.parent
UYA_DIRECT_SENDER_MAIN = REPO_ROOT / "src" / "webrtc_ffmpeg_direct_sender_main.uya"
UYA_BIN = REPO_ROOT.parent / "uya" / "bin" / "uya"


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


def make_call_page() -> str:
    return textwrap.dedent(
        """
        <!doctype html>
        <meta charset="utf-8">
        <title>Uya FFmpeg Direct Chrome Receiver</title>
        <script>
        window.__uyaDirectOffer = null;
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
          const states = [];
          const tracks = [];
          receiver.addEventListener('connectionstatechange', () => {
            states.push('receiver:' + receiver.connectionState);
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
            receiver.close();
            await delay(25);
            window.__ffmpegChromeCallResult = {
              ok: true,
              browser: navigator.userAgent,
              states,
              tracks,
              receiverConnectionState: receiver.connectionState,
              audioPacketsReceived: audioStats.packetsReceived,
              audioCodecMimeType: audioStats.codecMimeType,
              videoPacketsReceived: videoStats.packetsReceived,
              videoFramesDecoded: videoStats.framesDecoded,
              videoCodecMimeType: videoStats.codecMimeType,
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
        <title>Uya FFmpeg Direct Receiver Preview</title>
        <style>
          :root {
            color-scheme: light;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f7f8fb;
            color: #1f2937;
          }
          body { margin: 0; min-height: 100vh; }
          main { max-width: 1120px; margin: 0 auto; padding: 24px; }
          h1 { margin: 0 0 16px; font-size: 22px; }
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
          .status {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
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
            overflow: auto;
            padding: 12px;
            white-space: pre-wrap;
          }
          @media (max-width: 760px) {
            main { padding: 16px; }
            .status { grid-template-columns: 1fr; }
          }
        </style>
        <main>
          <h1>Uya FFmpeg Direct Receiver Preview</h1>
          <button id="start">Create Chrome Offer</button>
          <section class="status">
            <div class="metric"><span class="label">State</span><span class="value" id="state">idle</span></div>
            <div class="metric"><span class="label">Audio Packets</span><span class="value" id="audioPackets">0</span></div>
            <div class="metric"><span class="label">Video Frames</span><span class="value" id="videoFrames">0</span></div>
          </section>
          <pre id="log"></pre>
        </main>
        <script>
        const sourceStats = __SOURCE_STATS__;
        const start = document.getElementById('start');
        const state = document.getElementById('state');
        const log = document.getElementById('log');
        function writeLog(line) { log.textContent += line + '\\n'; }
        start.addEventListener('click', async () => {
          start.disabled = true;
          state.textContent = 'offer';
          writeLog('ffmpeg=' + JSON.stringify(sourceStats));
          writeLog('Use the headless test to pass this offer into uya_ffmpeg_direct_sender.');
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
    client.command(
        "Runtime.evaluate",
        {
            "expression": f"window.__uyaDirectApplyAnswer({answer_json}).catch(error => {{ throw error; }})",
            "awaitPromise": True,
            "returnByValue": True,
        },
        session_id=session_id,
    )


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
    raise TimeoutError("Chrome did not publish inbound RTP result")


def run_uya_direct_sender(offer: dict[str, str], media_path: Path, workdir: Path) -> dict[str, Any]:
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
    offer_path.write_text(json.dumps(offer), encoding="utf-8")

    completed = subprocess.run(
        [
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
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "uya_ffmpeg_direct_sender failed\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    if not answer_path.exists():
        raise AssertionError("uya_ffmpeg_direct_sender did not write an SDP answer")
    answer = json.loads(answer_path.read_text(encoding="utf-8"))
    if not isinstance(answer, dict) or not isinstance(answer.get("sdp"), str):
        raise AssertionError(f"invalid Uya answer JSON: {answer!r}")
    diagnostics: dict[str, Any] = {}
    if diagnostics_path.exists():
        parsed = json.loads(diagnostics_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            diagnostics = parsed
    return {"answerSdp": str(answer["sdp"]), "diagnostics": diagnostics}


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
        try:
            target = client.command("Target.createTarget", {"url": "about:blank"})
            target_id = str(target["targetId"])
            attached = client.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
            session_id = str(attached["sessionId"])
            client.command("Runtime.enable", session_id=session_id)
            client.command("Page.enable", session_id=session_id)
            client.command("Page.navigate", {"url": f"http://127.0.0.1:{http_port}/index.html"}, session_id=session_id)
            offer = wait_for_offer(client, session_id)
            sender_result = run_uya_direct_sender(offer, media_path, tempdir_path)
            apply_answer(client, session_id, sender_result["answerSdp"])
            result = wait_for_result(client, session_id)
            result["senderDiagnostics"] = sender_result.get("diagnostics", {})
            return result
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
    require(int(diagnostics.get("rtpPackets", 0)) > 0, "Uya sender reported no RTP packets")
    require(int(diagnostics.get("udpPackets", 0)) > 0, "Uya sender reported no UDP packets")


def assert_contract() -> str:
    source = Path(__file__).read_text(encoding="utf-8")
    required = [
        "UyaDirectSender",
        "uya_ffmpeg_direct_sender",
        "rtp_packetize_encoded_frame",
        "SRTP/SRTCP -> UDP",
        "recvonly",
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
            f"{temp_note}"
        )


def write_preview(preview_dir: Path) -> str:
    preview_dir.mkdir(parents=True, exist_ok=True)
    _, ffmpeg_stats = generate_ffmpeg_media(preview_dir)
    page_path = preview_dir / "index.html"
    page_path.write_text(make_preview_page(ffmpeg_stats), encoding="utf-8")
    return f"ffmpeg chrome direct preview written: dir={preview_dir} page={page_path}"


def serve_preview(preview_dir: Path) -> int:
    server, thread, http_port = start_http_server(preview_dir)
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
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-temp", action="store_true", help="copy generated headless-test artifacts to a retained temp directory")
    parser.add_argument("--preview-dir", type=Path, help="write a manual Chrome receiver preview page into this directory")
    parser.add_argument("--serve-preview", action="store_true", help="serve the manual preview page and wait until Ctrl-C")
    parser.add_argument("--contract-only", action="store_true", help="validate the direct sender harness contract without launching Chrome")
    args = parser.parse_args()
    try:
        if args.contract_only:
            print(assert_contract(), flush=True)
            return 0
        if args.preview_dir is not None or args.serve_preview:
            preview_dir = args.preview_dir or Path(tempfile.mkdtemp(prefix="webrtc-ffmpeg-chrome-direct-preview-"))
            print(write_preview(preview_dir), flush=True)
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
