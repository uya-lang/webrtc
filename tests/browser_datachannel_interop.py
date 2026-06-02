#!/usr/bin/env python3
"""Browser DataChannel loopback interop test.

This launches a cached Playwright Chromium headless shell, opens a local
page, and verifies browser DataChannel open/send/receive/close behavior.
The page also captures the browser-generated offer/answer SDP so the test can
assert the expected DTLS/SCTP shape against the browser fixture profile.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import tempfile
import textwrap
import time
import threading
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURE_PATH = TESTS_DIR / "fixtures" / "dtls" / "browser_handshake.json"

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_TIMEOUT_SECONDS = 20.0


class InteropError(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InteropError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise InteropError(f"failed to parse JSON at {path}: {exc}") from exc


def find_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def find_browser_executable() -> Path:
    base = Path.home() / ".cache" / "ms-playwright"
    candidates = [
        *base.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"),
        *base.glob("chromium-*/chrome-linux/chrome"),
    ]
    candidates = [path for path in candidates if path.exists()]
    if not candidates:
        raise InteropError(
            "no cached Chromium executable found under ~/.cache/ms-playwright; "
            "expected chromium_headless_shell or chromium"
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_ws_url(url: str) -> tuple[str, int, str]:
    require(url.startswith("ws://"), f"unsupported websocket url: {url}")
    rest = url[len("ws://") :]
    host_port, _, path = rest.partition("/")
    path = "/" + path
    host, _, port_text = host_port.rpartition(":")
    require(host != "", f"malformed websocket url: {url}")
    require(port_text.isdigit(), f"malformed websocket port in url: {url}")
    return host, int(port_text), path


class WebSocketClient:
    def __init__(self, url: str) -> None:
        self.url = url
        self.host, self.port, self.path = parse_ws_url(url)
        self.socket: socket.socket | None = None
        self.buffer = bytearray()

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=5.0)
        sock.settimeout(5.0)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = self._read_http_response(sock)
        require(" 101 " in response.splitlines()[0], f"websocket upgrade failed: {response!r}")
        expected_accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        headers = self._parse_headers(response)
        require(headers.get("sec-websocket-accept") == expected_accept, "websocket accept mismatch")
        self.socket = sock

    def close(self) -> None:
        if self.socket is None:
            return
        try:
            self._send_frame(0x8, b"")
        except Exception:
            pass
        try:
            self.socket.close()
        finally:
            self.socket = None

    def send_json(self, payload: dict[str, Any]) -> None:
        self._send_frame(0x1, json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    def recv_json(self, timeout_seconds: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise TimeoutError("timed out waiting for websocket message")
            assert self.socket is not None
            self.socket.settimeout(remaining)
            opcode, payload = self._read_frame()
            if opcode == 0x1:
                return json.loads(payload.decode("utf-8"))
            if opcode == 0x8:
                raise InteropError("browser closed websocket connection unexpectedly")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue

    def _read_http_response(self, sock: socket.socket) -> str:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
        return data.decode("latin1")

    def _parse_headers(self, response: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in response.split("\r\n")[1:]:
            if not line or ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        return headers

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        require(self.socket is not None, "websocket not connected")
        fin_opcode = 0x80 | (opcode & 0x0F)
        frame = bytearray([fin_opcode])
        length = len(payload)
        mask_bit = 0x80
        if length < 126:
            frame.append(mask_bit | length)
        elif length < 65536:
            frame.append(mask_bit | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(mask_bit | 127)
            frame.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        frame.extend(mask)
        masked = bytearray(payload)
        for index in range(length):
            masked[index] ^= mask[index % 4]
        frame.extend(masked)
        self.socket.sendall(frame)

    def _read_exact(self, size: int) -> bytes:
        require(self.socket is not None, "websocket not connected")
        while len(self.buffer) < size:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise InteropError("websocket connection closed while reading frame")
            self.buffer.extend(chunk)
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data

    def _read_frame(self) -> tuple[int, bytes]:
        header = self._read_exact(2)
        first, second = header[0], header[1]
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = b""
        if masked:
            mask = self._read_exact(4)
        payload = bytearray(self._read_exact(length))
        if masked:
            for index in range(length):
                payload[index] ^= mask[index % 4]
        return opcode, bytes(payload)


class CDPClient:
    def __init__(self, websocket_url: str) -> None:
        self.ws = WebSocketClient(websocket_url)
        self.next_id = 1

    def connect(self) -> None:
        self.ws.connect()

    def close(self) -> None:
        self.ws.close()

    def command(self, method: str, params: dict[str, Any] | None = None, session_id: str | None = None) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        message: dict[str, Any] = {"id": request_id, "method": method}
        if params:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        self.ws.send_json(message)
        deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise TimeoutError(f"timed out waiting for CDP response to {method}")
            message = self.ws.recv_json(remaining)
            if message.get("id") == request_id:
                if "error" in message:
                    raise InteropError(f"CDP {method} failed: {message['error']}")
                return message.get("result", {})


def make_test_page() -> str:
    return textwrap.dedent(
        """
        <!doctype html>
        <meta charset="utf-8">
        <title>Phase 14 Browser DataChannel Interop</title>
        <script>
        window.__phase14Result = null;

        function fail(message, error) {
          window.__phase14Result = {
            ok: false,
            error: message,
            detail: error && error.stack ? String(error.stack) : (error ? String(error) : "")
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

        async function run() {
          const pc1 = new RTCPeerConnection({iceServers: []});
          const pc2 = new RTCPeerConnection({iceServers: []});
          const relay12 = makeIceRelay(pc1, pc2, 'pc2');
          const relay21 = makeIceRelay(pc2, pc1, 'pc1');
          const messages = [];
          const states = [];

          pc1.addEventListener('connectionstatechange', () => states.push('pc1:' + pc1.connectionState));
          pc2.addEventListener('connectionstatechange', () => states.push('pc2:' + pc2.connectionState));

          const dc1 = pc1.createDataChannel('phase14', {ordered: true});
          const dc2Promise = waitForEvent(pc2, 'datachannel');

          const dc1Open = waitForEvent(dc1, 'open');
          const dc1Close = waitForEvent(dc1, 'close');

          const offer = await pc1.createOffer();
          await pc1.setLocalDescription(offer);
          await pc2.setRemoteDescription(pc1.localDescription);
          await relay12.enable();

          const answer = await pc2.createAnswer();
          await pc2.setLocalDescription(answer);
          await pc1.setRemoteDescription(pc2.localDescription);
          await relay21.enable();

          const dc2 = (await dc2Promise).channel;
          const dc2Open = waitForEvent(dc2, 'open');
          const dc2Close = waitForEvent(dc2, 'close');
          const pong = waitForEvent(dc1, 'message', event => String(event.data) === 'phase14-pong');
          const receivedOnDc2 = waitForEvent(dc2, 'message', event => String(event.data) === 'phase14-ping');

          dc2.addEventListener('message', event => {
            const payload = String(event.data);
            messages.push('dc2:' + payload);
            if (payload === 'phase14-ping') {
              dc2.send('phase14-pong');
            }
          });
          dc1.addEventListener('message', event => {
            messages.push('dc1:' + String(event.data));
          });

          await Promise.all([
            dc1Open,
            dc2Open,
            waitForState(pc1, 'connectionstatechange', () => pc1.connectionState === 'connected'),
            waitForState(pc2, 'connectionstatechange', () => pc2.connectionState === 'connected'),
          ]);

          dc1.send('phase14-ping');
          await Promise.all([receivedOnDc2, pong]);

          dc1.close();
          await Promise.all([dc1Close, dc2Close]);

          const complete = await Promise.all([
            waitForState(pc1, 'icegatheringstatechange', () => pc1.iceGatheringState === 'complete'),
            waitForState(pc2, 'icegatheringstatechange', () => pc2.iceGatheringState === 'complete'),
          ]);
          void complete;

          pc1.close();
          pc2.close();
          await delay(25);

          window.__phase14Result = {
            ok: true,
            browser: navigator.userAgent,
            messages,
            states,
            pc1ConnectionState: pc1.connectionState,
            pc2ConnectionState: pc2.connectionState,
            dc1ReadyState: dc1.readyState,
            dc2ReadyState: dc2.readyState,
            offerSdp: pc1.localDescription ? pc1.localDescription.sdp : '',
            answerSdp: pc2.localDescription ? pc2.localDescription.sdp : '',
          };
        }

        run().catch(error => fail('phase14 browser datachannel test failed', error));
        </script>
        """
    ).strip()


def start_http_server(directory: Path) -> tuple[ThreadingHTTPServer, threading.Thread, int]:
    port = find_free_port()
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def load_browser_case() -> dict[str, Any]:
    data = read_json(FIXTURE_PATH)
    cases = data.get("cases")
    require(isinstance(cases, list) and cases, "browser fixture must contain at least one case")
    for case in cases:
        if isinstance(case, dict) and case.get("browser") == "chrome":
            return case
    raise InteropError("no chrome case found in browser_handshake.json")


def parse_transport_profiles(sdp_text: str) -> set[str]:
    profiles: set[str] = set()
    for line in sdp_text.splitlines():
        if not line.startswith("m="):
            continue
        parts = line.split()
        if len(parts) >= 3:
            profiles.add(parts[2].strip())
    return profiles


def parse_setup_values(sdp_text: str) -> list[str]:
    values: list[str] = []
    for line in sdp_text.splitlines():
        if line.startswith("a=setup:"):
            values.append(line.split(":", 1)[1].strip())
    return values


def validate_browser_result(result: dict[str, Any]) -> None:
    require(result.get("ok") is True, f"browser page reported failure: {result}")
    require(result.get("pc1ConnectionState") == "closed", "pc1 should be closed after cleanup")
    require(result.get("pc2ConnectionState") == "closed", "pc2 should be closed after cleanup")
    require(result.get("dc1ReadyState") == "closed", "dc1 should be closed after cleanup")
    require(result.get("dc2ReadyState") == "closed", "dc2 should be closed after cleanup")

    messages = result.get("messages")
    require(isinstance(messages, list), "browser result messages must be an array")
    require("dc2:phase14-ping" in messages, "browser did not receive ping on dc2")
    require("dc1:phase14-pong" in messages, "browser did not receive pong on dc1")

    offer_sdp = str(result.get("offerSdp", ""))
    answer_sdp = str(result.get("answerSdp", ""))
    require("m=application 9 UDP/DTLS/SCTP webrtc-datachannel" in offer_sdp, "offer SDP missing DataChannel m-line")
    require("a=setup:actpass" in offer_sdp, "offer SDP missing actpass setup")
    require("a=sctp-port:5000" in offer_sdp, "offer SDP missing sctp-port")
    require("a=max-message-size:262144" in offer_sdp, "offer SDP missing max-message-size")

    require("m=application 9 UDP/DTLS/SCTP webrtc-datachannel" in answer_sdp, "answer SDP missing DataChannel m-line")
    require("a=setup:active" in answer_sdp, "answer SDP missing active setup")

    browser_case = load_browser_case()
    expected_profiles = set(browser_case.get("transport_profiles", []))
    require("UDP/DTLS/SCTP" in parse_transport_profiles(offer_sdp), "browser offer transport profile mismatch")
    require(
        str(browser_case.get("setup_role")) in parse_setup_values(offer_sdp),
        "browser offer setup role mismatch",
    )
    require(expected_profiles, "browser fixture has no transport profiles")


def run_browser_test() -> dict[str, Any]:
    browser_exe = find_browser_executable()
    with tempfile.TemporaryDirectory(prefix="webrtc-browser-datachannel-") as tempdir:
        tempdir_path = Path(tempdir)
        page_path = tempdir_path / "index.html"
        page_path.write_text(make_test_page(), encoding="utf-8")

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

                deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
                result: dict[str, Any] | None = None
                while time.monotonic() < deadline:
                    response = client.command(
                        "Runtime.evaluate",
                        {
                            "expression": "typeof window.__phase14Result === 'undefined' ? null : JSON.stringify(window.__phase14Result)",
                            "returnByValue": True,
                        },
                        session_id=session_id,
                    )
                    evaluated = response.get("result")
                    if isinstance(evaluated, dict) and evaluated.get("type") == "string":
                        result_text = str(evaluated.get("value", ""))
                        if result_text:
                            result = json.loads(result_text)
                            break
                    time.sleep(0.2)
                require(result is not None, "browser page did not publish a result")
                validate_browser_result(result)
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


def main() -> int:
    try:
        result = run_browser_test()
        print("Browser DataChannel interop checks passed")
        print(f"  Browser: {result.get('browser')}")
        print(f"  Messages: {', '.join(result.get('messages', []))}")
        return 0
    except (InteropError, TimeoutError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
