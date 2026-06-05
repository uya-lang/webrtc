#!/usr/bin/env python3
"""Tiny HTTP signaling server for the RK1106 WebRTC preview example."""

from __future__ import annotations

import argparse
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Union
from urllib.parse import urlsplit


MAX_BODY_BYTES = 1024 * 1024


class SignalState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.offer: Optional[bytes] = None
        self.answer: Optional[bytes] = None

    def set_offer(self, body: bytes) -> None:
        with self.lock:
            self.offer = body
            self.answer = None

    def set_answer(self, body: bytes) -> None:
        with self.lock:
            self.answer = body

    def get_offer(self) -> Optional[bytes]:
        with self.lock:
            return self.offer

    def get_answer(self) -> Optional[bytes]:
        with self.lock:
            return self.answer

    def reset(self) -> None:
        with self.lock:
            self.offer = None
            self.answer = None

    def snapshot(self) -> Dict[str, Union[int, bool]]:
        with self.lock:
            return {
                "hasOffer": self.offer is not None,
                "offerBytes": len(self.offer or b""),
                "hasAnswer": self.answer is not None,
                "answerBytes": len(self.answer or b""),
            }


class Handler(SimpleHTTPRequestHandler):
    state: SignalState

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/api/offer", "/offer"}:
            self.send_signal_body(self.state.get_offer())
            return
        if path in {"/api/answer", "/answer"}:
            self.send_signal_body(self.state.get_answer())
            return
        if path == "/api/state":
            self.send_json(self.state.snapshot())
            return
        if path == "/":
            self.path = "/manual_preview.html"
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/reset":
            self.state.reset()
            self.send_json({"ok": True})
            return

        if path not in {"/api/offer", "/offer", "/api/answer", "/answer"}:
            self.send_error(404)
            return

        body = self.read_body()
        if body is None:
            return
        if path in {"/api/offer", "/offer"}:
            self.state.set_offer(body)
        else:
            self.state.set_answer(body)
        self.send_json({"ok": True, "bytes": len(body)})

    def read_body(self) -> Optional[bytes]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "invalid Content-Length")
            return None
        if length <= 0:
            self.send_error(400, "empty body")
            return None
        if length > MAX_BODY_BYTES:
            self.send_error(413, "body too large")
            return None
        return self.rfile.read(length)

    def send_signal_body(self, body: Optional[bytes]) -> None:
        if body is None:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b'{"error":"not ready"}\n')
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value: object) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    Handler.state = SignalState()
    handler = partial(Handler, directory=str(root))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"signaling server: http://{args.host}:{args.port}/manual_preview.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
