#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import time
from pathlib import Path

from sdp_fixture_roundtrip import (
    FIXTURE_DIR,
    parse_session_description,
    validate_webrtc_session,
    write_session_description,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def emit(row: dict[str, object]) -> None:
    print(json.dumps(row, separators=(",", ":")))


def bench_udp_echo() -> dict[str, object]:
    iterations = 256
    payload = b"webrtc-bench-udp-echo"

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.settimeout(1.0)

        port = server.getsockname()[1]
        client.settimeout(1.0)
        client.connect(("127.0.0.1", port))

        start = time.perf_counter_ns()
        for i in range(iterations):
            frame = payload + bytes((i & 0xFF,))
            client.send(frame)
            data, addr = server.recvfrom(2048)
            if data != frame:
                raise RuntimeError("udp echo server payload mismatch")
            server.sendto(data, addr)
            echoed = client.recv(2048)
            if echoed != frame:
                raise RuntimeError("udp echo client payload mismatch")
        elapsed = max(1, time.perf_counter_ns() - start)
    finally:
        client.close()
        server.close()

    qps = iterations * 1_000_000_000 // elapsed
    throughput = (len(payload) + 1) * iterations * 2 * 1_000_000_000 // elapsed // 1_000_000
    return {
        "name": "bench_udp_echo",
        "suite": "phase2",
        "unit": "qps",
        "value": qps,
        "throughput_mb_s": throughput,
        "packets_per_s": qps,
        "p95_ns": 0,
        "p99_ns": 0,
        "allocations": 0,
        "high_watermark": 0,
        "vectorized": False,
    }


def bench_sdp_parse() -> dict[str, object]:
    texts = [
        (FIXTURE_DIR / "chrome_offer.sdp").read_text(encoding="utf-8"),
        (FIXTURE_DIR / "firefox_offer.sdp").read_text(encoding="utf-8"),
    ]
    iterations = 256
    ops = iterations * len(texts)
    high_watermark = 0

    start = time.perf_counter_ns()
    for _ in range(iterations):
        for text in texts:
            session = parse_session_description(text)
            validate_webrtc_session(session)
            rendered = write_session_description(session)
            if not rendered:
                raise RuntimeError("empty SDP render")
            high_watermark = max(high_watermark, len(session.media_sections))
    elapsed = max(1, time.perf_counter_ns() - start)

    return {
        "name": "bench_sdp_parse",
        "suite": "phase3",
        "unit": "ns/op",
        "value": elapsed // ops,
        "throughput_mb_s": 0,
        "packets_per_s": ops * 1_000_000_000 // elapsed,
        "p95_ns": 0,
        "p99_ns": 0,
        "allocations": 0,
        "high_watermark": high_watermark,
        "vectorized": False,
    }


def main() -> None:
    emit(bench_udp_echo())
    emit(bench_sdp_parse())


if __name__ == "__main__":
    main()
