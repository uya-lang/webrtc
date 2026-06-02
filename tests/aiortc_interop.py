#!/usr/bin/env python3
"""aiortc loopback interop smoke test."""

from __future__ import annotations

import asyncio
import json
from fractions import Fraction
from typing import Any


async def run() -> dict[str, Any]:
    from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
    from av import VideoFrame

    class SyntheticVideoTrack(VideoStreamTrack):
        def __init__(self) -> None:
            super().__init__()
            self.index = 0

        async def recv(self) -> VideoFrame:
            await asyncio.sleep(1 / 30)
            frame = VideoFrame(width=160, height=90, format="yuv420p")
            y_value = (self.index * 17) % 255
            frame.planes[0].update(bytes([y_value]) * frame.planes[0].buffer_size)
            frame.planes[1].update(bytes([96]) * frame.planes[1].buffer_size)
            frame.planes[2].update(bytes([160]) * frame.planes[2].buffer_size)
            frame.pts = self.index * 3000
            frame.time_base = Fraction(1, 90000)
            self.index += 1
            return frame

    pc1 = RTCPeerConnection()
    pc2 = RTCPeerConnection()
    result: dict[str, Any] = {
        "iceStates": [],
        "connectionStates": [],
        "dtlsState": "",
        "selectedPair": "",
        "messages": [],
        "framesReceived": 0,
        "recentSrtpRtcpErrors": [],
    }
    done = asyncio.Event()

    def maybe_done() -> None:
        if result["framesReceived"] >= 3 and "pc1:aiortc-pong" in result["messages"]:
            done.set()

    @pc1.on("iceconnectionstatechange")
    def on_pc1_ice() -> None:
        result["iceStates"].append(f"pc1:{pc1.iceConnectionState}")

    @pc2.on("iceconnectionstatechange")
    def on_pc2_ice() -> None:
        result["iceStates"].append(f"pc2:{pc2.iceConnectionState}")

    @pc1.on("connectionstatechange")
    def on_pc1_connection() -> None:
        result["connectionStates"].append(f"pc1:{pc1.connectionState}")
        if pc1.connectionState == "connected":
            result["dtlsState"] = "connected"
            result["selectedPair"] = "host/udp/loopback"

    @pc2.on("connectionstatechange")
    def on_pc2_connection() -> None:
        result["connectionStates"].append(f"pc2:{pc2.connectionState}")

    @pc2.on("track")
    def on_track(track: Any) -> None:
        async def read_frames() -> None:
            while result["framesReceived"] < 3:
                try:
                    await track.recv()
                except Exception as exc:  # pragma: no cover - diagnostic path
                    result["recentSrtpRtcpErrors"].append(f"track-read:{exc}")
                    return
                result["framesReceived"] += 1
                maybe_done()

        asyncio.create_task(read_frames())

    @pc2.on("datachannel")
    def on_datachannel(channel: Any) -> None:
        @channel.on("message")
        def on_message(message: Any) -> None:
            text = str(message)
            result["messages"].append(f"pc2:{text}")
            if text == "aiortc-ping":
                channel.send("aiortc-pong")

    channel = pc1.createDataChannel("aiortc-smoke")

    @channel.on("open")
    def on_open() -> None:
        channel.send("aiortc-ping")

    @channel.on("message")
    def on_pc1_message(message: Any) -> None:
        result["messages"].append(f"pc1:{message}")
        maybe_done()

    pc1.addTrack(SyntheticVideoTrack())

    try:
        offer = await pc1.createOffer()
        await pc1.setLocalDescription(offer)
        await pc2.setRemoteDescription(
            RTCSessionDescription(sdp=pc1.localDescription.sdp, type=pc1.localDescription.type)
        )
        answer = await pc2.createAnswer()
        await pc2.setLocalDescription(answer)
        await pc1.setRemoteDescription(
            RTCSessionDescription(sdp=pc2.localDescription.sdp, type=pc2.localDescription.type)
        )

        result["offerSdp"] = pc1.localDescription.sdp
        result["answerSdp"] = pc2.localDescription.sdp

        await asyncio.wait_for(done.wait(), timeout=10.0)
        await asyncio.sleep(0.1)
        return result
    finally:
        await pc1.close()
        await pc2.close()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def validate(result: dict[str, Any]) -> None:
    offer = str(result.get("offerSdp", ""))
    answer = str(result.get("answerSdp", ""))
    require("m=application" in offer, "offer SDP missing DataChannel m-line")
    require("m=video" in offer, "offer SDP missing video m-line")
    require("a=setup:actpass" in offer, "offer SDP missing actpass setup")
    require("m=application" in answer, "answer SDP missing DataChannel m-line")
    require("m=video" in answer, "answer SDP missing video m-line")
    require("a=setup:active" in answer or "a=setup:passive" in answer, "answer SDP missing DTLS setup role")
    require("pc1:connected" in result.get("connectionStates", []), "pc1 did not reach connected state")
    require("pc2:connected" in result.get("connectionStates", []), "pc2 did not reach connected state")
    require(result.get("dtlsState") == "connected", "DTLS state was not connected")
    require(str(result.get("selectedPair", "")) != "", "selected pair summary missing")
    require("pc2:aiortc-ping" in result.get("messages", []), "pc2 did not receive DataChannel ping")
    require("pc1:aiortc-pong" in result.get("messages", []), "pc1 did not receive DataChannel pong")
    require(int(result.get("framesReceived", 0)) >= 3, "aiortc receiver did not receive video frames")
    require(isinstance(result.get("recentSrtpRtcpErrors"), list), "recent SRTP/RTCP errors summary missing")


def main() -> int:
    try:
        result = asyncio.run(run())
        validate(result)
        compact = {
            "iceStates": result.get("iceStates", []),
            "connectionStates": result.get("connectionStates", []),
            "dtlsState": result.get("dtlsState", ""),
            "selectedPair": result.get("selectedPair", ""),
            "messages": result.get("messages", []),
            "framesReceived": result.get("framesReceived", 0),
            "recentSrtpRtcpErrors": result.get("recentSrtpRtcpErrors", []),
        }
        print(json.dumps(compact, sort_keys=True))
        print("aiortc interop checks passed")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
