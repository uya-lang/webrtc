#!/usr/bin/env python3
"""Validate the RK1106 H264 preview reaches Chrome's first frame quickly."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from browser_datachannel_interop import CDPClient, find_browser_executable, find_free_port, require


TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
EXAMPLE_DIR = REPO_ROOT / "examples" / "rk1106_h264_push_client"
HOST_RUN = EXAMPLE_DIR / "host_run.sh"
SIGNALING_SERVER = EXAMPLE_DIR / "host" / "signaling_server.py"
PREVIEW_URL_PATH = "/manual_preview.html"
DEFAULT_TIMEOUT_SECONDS = 45.0


def run_checked(command: list[str], cwd: Path = REPO_ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def wait_for_http_json(url: str, timeout_seconds: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"HTTP endpoint did not become ready: {url}; last_error={last_error}")


def read_tail(path: Path, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return text[-limit:]


def evaluate_json(client: CDPClient, session_id: str, expression: str) -> Any:
    response = client.command(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True},
        session_id=session_id,
    )
    result = response.get("result")
    if not isinstance(result, dict):
        return None
    value = result.get("value")
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def read_preview_state(client: CDPClient, session_id: str) -> dict[str, Any]:
    value = evaluate_json(
        client,
        session_id,
        """
        JSON.stringify((() => {
          const offerBox = document.getElementById('offerBox');
          const answerBox = document.getElementById('answerBox');
          const video = document.getElementById('remoteVideo');
          const parseBox = (box) => {
            if (!box || !box.value) return null;
            try { return JSON.parse(box.value); } catch (error) { return {parseError: String(error)}; }
          };
          return {
            href: location.href,
            readyState: document.readyState,
            statusText: document.getElementById('status') ? document.getElementById('status').textContent : '',
            metricsText: document.getElementById('metrics') ? document.getElementById('metrics').textContent : '',
            state: window.__rk1106PreviewState || null,
            offer: parseBox(offerBox),
            answer: parseBox(answerBox),
            remoteVideoWidth: video ? video.videoWidth : 0,
            remoteVideoHeight: video ? video.videoHeight : 0,
            remoteReadyState: video ? video.readyState : 0
          };
        })())
        """,
    )
    if isinstance(value, dict):
        return value
    return {}


def parse_stat_int(text: str, key: str) -> int:
    match = re.search(rf"(?:^|\s){re.escape(key)}=(\d+)", text)
    if not match:
        return 0
    return int(match.group(1))


def parse_stat_float(text: str, key: str) -> float | None:
    match = re.search(rf"(?:^|\s){re.escape(key)}=([0-9]+(?:\.[0-9]+)?)", text)
    if not match:
        return None
    return float(match.group(1))


def launch_chromium(tempdir: Path) -> tuple[subprocess.Popen[str], CDPClient, str]:
    browser_exe = find_browser_executable()
    profile_dir = tempdir / "chrome-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    debug_port = find_free_port()
    proc = subprocess.Popen(
        [
            str(browser_exe),
            f"--remote-debugging-port={debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=CalculateNativeWinOcclusion",
            "--autoplay-policy=no-user-gesture-required",
            "--user-data-dir=" + str(profile_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    version_url = f"http://127.0.0.1:{debug_port}/json/version"
    version = wait_for_http_json(version_url, timeout_seconds=15.0)
    browser_ws_url = str(version.get("webSocketDebuggerUrl"))
    require(browser_ws_url.startswith("ws://"), "browser version endpoint missing websocket url")
    client = CDPClient(browser_ws_url)
    client.connect()
    return proc, client, browser_ws_url


def start_signaling_server(port: int, tempdir: Path, host: str = "127.0.0.1") -> subprocess.Popen[str]:
    log_path = tempdir / "signaling.log"
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(SIGNALING_SERVER), "--host", host, "--port", str(port)],
        cwd=REPO_ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._rk1106_log_file = log_file  # type: ignore[attr-defined]
    wait_for_http_json(f"http://127.0.0.1:{port}/api/state", timeout_seconds=10.0)
    return proc


def stop_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)


def start_host_sender(tempdir: Path, signal_port: int, duration_us: int, width: int, height: int, fps: int) -> subprocess.Popen[str]:
    workdir = tempdir / "host-work"
    workdir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "SIGNAL_BASE_URL": f"http://127.0.0.1:{signal_port}/api",
            "LOCAL_HOST": "127.0.0.1",
            "WORKDIR": str(workdir),
            "MEDIA_PATH": str(workdir / "host_testsrc.h264"),
            "WIDTH": str(width),
            "HEIGHT": str(height),
            "FPS": str(fps),
            "DURATION_US": str(duration_us),
            "OFFER_POLL_TRIES": "300",
            "OFFER_POLL_INTERVAL_MS": "100",
            "PRINT_LOGS_ON_EXIT": "0",
        }
    )
    log_path = tempdir / "host_run.log"
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(HOST_RUN)],
        cwd=REPO_ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._rk1106_log_file = log_file  # type: ignore[attr-defined]
    return proc


def wait_for_first_frame(
    client: CDPClient,
    session_id: str,
    host_proc: subprocess.Popen[str] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_state = read_preview_state(client, session_id)
        state = last_state.get("state")
        timing = state.get("timing") if isinstance(state, dict) else None
        metrics = str(last_state.get("metricsText") or "")
        if (
            isinstance(timing, dict)
            and timing.get("firstFrame") is not None
            and last_state.get("remoteVideoWidth", 0)
            and last_state.get("remoteVideoHeight", 0)
        ):
            return last_state
        if host_proc is not None and host_proc.poll() is not None:
            raise RuntimeError(
                "host sender exited before Chrome first frame; "
                f"status={host_proc.returncode}; state={last_state}; metrics={metrics}"
            )
        time.sleep(0.1)
    raise TimeoutError(f"Chrome first frame timed out; state={last_state}")


def wait_for_stats_after_first_frame(
    client: CDPClient,
    session_id: str,
    host_proc: subprocess.Popen[str] | None,
    first_frame_state: dict[str, Any],
    timeout_seconds: float = 4.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    best_state = first_frame_state
    while time.monotonic() < deadline:
        current_state = read_preview_state(client, session_id)
        if current_state:
            best_state = current_state
        metrics = str(best_state.get("metricsText") or "")
        if parse_stat_int(metrics, "framesDecoded") > 0 or parse_stat_int(metrics, "framesReceived") > 0:
            return best_state
        if "H264" in metrics.upper():
            return best_state
        if host_proc is not None and host_proc.poll() is not None:
            return best_state
        time.sleep(0.1)
    return best_state


def wait_for_sustained_playback(
    client: CDPClient,
    session_id: str,
    host_proc: subprocess.Popen[str] | None,
    first_frame_state: dict[str, Any],
    min_frames: int,
    observe_us: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    observe_deadline = time.monotonic() + max(0, observe_us) / 1_000_000.0
    best_state = first_frame_state
    while time.monotonic() < deadline:
        current_state = read_preview_state(client, session_id)
        if current_state:
            best_state = current_state
        preview = best_state.get("state")
        video_stats = preview.get("videoStats") if isinstance(preview, dict) else None
        metrics = str(best_state.get("metricsText") or "")
        if isinstance(video_stats, dict):
            frames = max(int(video_stats.get("framesDecoded") or 0), int(video_stats.get("framesReceived") or 0))
        else:
            frames = max(parse_stat_int(metrics, "framesDecoded"), parse_stat_int(metrics, "framesReceived"))
        if frames >= min_frames and time.monotonic() >= observe_deadline:
            return best_state
        time.sleep(0.2)
    return best_state


def wait_for_sender_exit(proc: subprocess.Popen[str], timeout_seconds: float = 15.0) -> int:
    try:
        return proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return -999


def validate_first_frame(state: dict[str, Any], threshold_ms: int) -> dict[str, Any]:
    preview = state.get("state")
    require(isinstance(preview, dict), f"preview state missing: {state}")
    timing = preview.get("timing")
    require(isinstance(timing, dict), f"preview timing missing: {state}")

    answer_to_first = timing.get("answerToFirstFrame")
    connected_to_first = timing.get("connectedToFirstFrame")
    require(isinstance(answer_to_first, int), f"answerToFirstFrame missing: {state}")
    require(isinstance(connected_to_first, int), f"connectedToFirstFrame missing: {state}")
    require(answer_to_first <= threshold_ms, f"answerToFirstFrame too slow: {answer_to_first}ms > {threshold_ms}ms")
    require(connected_to_first <= threshold_ms, f"connectedToFirstFrame too slow: {connected_to_first}ms > {threshold_ms}ms")

    offer = state.get("offer")
    answer = state.get("answer")
    require(isinstance(offer, dict) and "H264/90000" in str(offer.get("sdp", "")), "Chrome offer did not include H264")
    require(isinstance(answer, dict) and "H264/90000" in str(answer.get("sdp", "")), "Uya answer did not negotiate H264")
    require(int(state.get("remoteVideoWidth") or 0) > 0, f"Chrome remote video width missing: {state}")
    require(int(state.get("remoteVideoHeight") or 0) > 0, f"Chrome remote video height missing: {state}")

    metrics = str(state.get("metricsText") or "")
    frames_decoded = parse_stat_int(metrics, "framesDecoded")
    frames_received = parse_stat_int(metrics, "framesReceived")
    frames_dropped = parse_stat_int(metrics, "framesDropped")
    if "stats video: waiting" not in metrics:
        require(frames_decoded > 0 or frames_received > 0, f"Chrome stats showed no decoded/received video frames: {metrics}")
        require("H264" in metrics.upper(), f"Chrome stats did not report H264 codec: {metrics}")
    require(frames_dropped <= max(2, frames_decoded), f"Chrome dropped too many startup frames: {metrics}")

    return {
        "answerToFirstFrameMs": answer_to_first,
        "connectedToFirstFrameMs": connected_to_first,
        "framesDecoded": frames_decoded,
        "framesReceived": frames_received,
        "framesDropped": frames_dropped,
        "remoteVideoWidth": int(state.get("remoteVideoWidth") or 0),
        "remoteVideoHeight": int(state.get("remoteVideoHeight") or 0),
        "metrics": metrics,
    }


def validate_sustained_playback(
    state: dict[str, Any],
    min_frames: int,
    max_freeze_per_1000: float,
    max_jitter_target_delay_s: float,
) -> dict[str, Any]:
    metrics = str(state.get("metricsText") or "")
    require("stats video: waiting" not in metrics, f"Chrome stats never reached steady video: {metrics}")
    preview = state.get("state")
    video_stats = preview.get("videoStats") if isinstance(preview, dict) else None
    frames_decoded = parse_stat_int(metrics, "framesDecoded")
    frames_received = parse_stat_int(metrics, "framesReceived")
    freeze_count = parse_stat_int(metrics, "freeze")
    jitter_target_delay_s = parse_stat_float(metrics, "jitterTargetDelay")
    if isinstance(video_stats, dict):
        frames_decoded = int(video_stats.get("framesDecoded") or 0)
        frames_received = int(video_stats.get("framesReceived") or 0)
        freeze_count = int(video_stats.get("freezeCount") or 0)
        raw_jitter_target = video_stats.get("jitterTargetDelay")
        if isinstance(raw_jitter_target, (int, float)):
            jitter_target_delay_s = float(raw_jitter_target)
    frames = max(frames_decoded, frames_received)
    require(frames >= min_frames, f"steady playback decoded too few frames: {frames} < {min_frames}; metrics={metrics}")
    require(
        freeze_count * 1000.0 <= frames * max_freeze_per_1000,
        f"freezeCount ratio too high: freeze={freeze_count}, frames={frames}, "
        f"maxPer1000={max_freeze_per_1000}; metrics={metrics}",
    )
    require(
        jitter_target_delay_s is not None,
        f"Chrome stats did not expose jitterTargetDelay for latency budget: {metrics}",
    )
    require(
        jitter_target_delay_s <= max_jitter_target_delay_s,
        f"Chrome receiver target delay too high: {jitter_target_delay_s:.3f}s > "
        f"{max_jitter_target_delay_s:.3f}s; metrics={metrics}",
    )
    return {
        "steadyFrames": frames,
        "steadyFramesDecoded": frames_decoded,
        "steadyFramesReceived": frames_received,
        "freezeCount": freeze_count,
        "freezePer1000": (freeze_count * 1000.0 / frames) if frames else 0.0,
        "jitterTargetDelayS": jitter_target_delay_s,
        "steadyMetrics": metrics,
    }


def run_e2e(args: argparse.Namespace) -> dict[str, Any]:
    if args.build and not args.external_sender:
        run_checked(["make", "-C", str(EXAMPLE_DIR), "host"])

    with tempfile.TemporaryDirectory(prefix="rk1106-h264-first-screen-") as temp:
        tempdir = Path(temp)
        signal_port = args.signal_port if args.signal_port else find_free_port()
        signaling_proc: subprocess.Popen[str] | None = None
        browser_proc: subprocess.Popen[str] | None = None
        host_proc: subprocess.Popen[str] | None = None
        client: CDPClient | None = None
        try:
            signaling_proc = start_signaling_server(signal_port, tempdir, host=args.signal_host)
            if args.external_sender:
                print(
                    f"external sender signal URL: http://<host-ip>:{signal_port}/api "
                    f"(bind={args.signal_host})",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                host_proc = start_host_sender(
                    tempdir,
                    signal_port,
                    duration_us=args.duration_us,
                    width=args.width,
                    height=args.height,
                    fps=args.fps,
                )
            browser_proc, client, _ = launch_chromium(tempdir)

            target = client.command("Target.createTarget", {"url": "about:blank"})
            target_id = str(target["targetId"])
            client.command("Target.activateTarget", {"targetId": target_id})
            attached = client.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
            session_id = str(attached["sessionId"])
            client.command("Runtime.enable", session_id=session_id)
            client.command("Page.enable", session_id=session_id)
            client.command("Page.bringToFront", session_id=session_id)
            client.command(
                "Page.navigate",
                {"url": f"http://127.0.0.1:{signal_port}{PREVIEW_URL_PATH}"},
                session_id=session_id,
            )

            first_frame_state = wait_for_first_frame(client, session_id, host_proc, args.timeout_seconds)
            first_frame_state = wait_for_stats_after_first_frame(client, session_id, host_proc, first_frame_state)
            summary = validate_first_frame(first_frame_state, args.threshold_ms)
            sustained_state = wait_for_sustained_playback(
                client,
                session_id,
                host_proc,
                first_frame_state,
                min_frames=args.steady_min_frames,
                observe_us=args.steady_observe_us,
                timeout_seconds=max(4.0, args.duration_us / 1_000_000 + 2.0),
            )
            summary.update(
                validate_sustained_playback(
                    sustained_state,
                    min_frames=args.steady_min_frames,
                    max_freeze_per_1000=args.max_freeze_per_1000,
                    max_jitter_target_delay_s=args.max_jitter_target_delay,
                )
            )
            if host_proc is not None:
                sender_status = wait_for_sender_exit(host_proc, timeout_seconds=max(15.0, args.duration_us / 1_000_000 + 10.0))
                if sender_status != 0:
                    raise RuntimeError(
                        f"host sender failed after first frame status={sender_status}\n"
                        f"---- host_run.log ----\n{read_tail(tempdir / 'host_run.log')}"
                    )
                diagnostics_path = tempdir / "host-work" / "diagnostics.json"
                if diagnostics_path.exists():
                    summary["senderDiagnostics"] = json.loads(diagnostics_path.read_text(encoding="utf-8"))
            return summary
        finally:
            if client is not None:
                client.close()
            stop_process(host_proc)
            stop_process(browser_proc)
            stop_process(signaling_proc)
            for proc in (host_proc, browser_proc, signaling_proc):
                log_file = getattr(proc, "_rk1106_log_file", None)
                if log_file is not None:
                    log_file.close()
            if args.keep_temp:
                keep_dir = Path(tempfile.mkdtemp(prefix="rk1106-h264-first-screen-keep-"))
                for path in tempdir.iterdir():
                    target = keep_dir / path.name
                    if path.is_dir():
                        shutil.copytree(path, target)
                    else:
                        shutil.copy2(path, target)
                print(f"kept artifacts: {keep_dir}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-build", dest="build", action="store_false", help="skip rebuilding the host sender")
    parser.add_argument("--threshold-ms", type=int, default=1000)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--duration-us", type=int, default=5_000_000)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--steady-min-frames", type=int, default=1)
    parser.add_argument(
        "--steady-observe-us",
        type=int,
        default=0,
        help="after the first frame, keep sampling at least this long before validating sustained stats",
    )
    parser.add_argument("--max-freeze-per-1000", type=float, default=1.0)
    parser.add_argument("--max-jitter-target-delay", type=float, default=1.0)
    parser.add_argument("--external-sender", action="store_true", help="wait for a board/external sender instead of starting host_run.sh")
    parser.add_argument("--signal-host", default="127.0.0.1", help="signaling server bind host; use 0.0.0.0 for board validation")
    parser.add_argument("--signal-port", type=int, default=0, help="signaling server port; 0 chooses a free local port")
    parser.add_argument("--keep-temp", action="store_true")
    parser.set_defaults(build=True)
    args = parser.parse_args()

    summary = run_e2e(args)
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
