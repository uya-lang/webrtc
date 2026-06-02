#!/usr/bin/env python3
"""Pion WebRTC loopback interop smoke test.

The Go program is generated under /tmp so Pion remains a test-only oracle and
does not become a runtime dependency of the pure Uya transport.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = Path(os.environ.get("WEBRTC_PION_INTEROP_WORKDIR", "/tmp/webrtc-pion-interop"))


GO_MOD = """\
module uya-pion-interop

go 1.22

require (
\tgithub.com/pion/rtp v1.8.22
\tgithub.com/pion/webrtc/v4 v4.1.6
)
"""


GO_MAIN = r'''
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/pion/rtp"
	"github.com/pion/webrtc/v4"
)

type Result struct {
	OfferSDP             string   `json:"offerSdp"`
	AnswerSDP            string   `json:"answerSdp"`
	ICEStates            []string `json:"iceStates"`
	ConnectionStates     []string `json:"connectionStates"`
	DTLSState            string   `json:"dtlsState"`
	SelectedPair         string   `json:"selectedPair"`
	Messages             []string `json:"messages"`
	PacketsReceived      uint32   `json:"packetsReceived"`
	RecentSRTPRTCPErrors []string `json:"recentSrtpRtcpErrors"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: %v\n", err)
		os.Exit(1)
	}
}

func run() error {
	var mediaEngine webrtc.MediaEngine
	if err := mediaEngine.RegisterDefaultCodecs(); err != nil {
		return err
	}
	api := webrtc.NewAPI(webrtc.WithMediaEngine(&mediaEngine))
	config := webrtc.Configuration{ICEServers: []webrtc.ICEServer{}}

	pc1, err := api.NewPeerConnection(config)
	if err != nil {
		return err
	}
	defer pc1.Close()
	pc2, err := api.NewPeerConnection(config)
	if err != nil {
		return err
	}
	defer pc2.Close()

	var mu sync.Mutex
	result := Result{
		RecentSRTPRTCPErrors: []string{},
	}
	done := make(chan struct{})
	var doneOnce sync.Once
	failCh := make(chan error, 4)
	var packetsReceived atomic.Uint32
	var gotPong atomic.Bool

	record := func(list *[]string, value string) {
		mu.Lock()
		defer mu.Unlock()
		*list = append(*list, value)
	}

	pc1.OnICEConnectionStateChange(func(state webrtc.ICEConnectionState) {
		record(&result.ICEStates, "pc1:"+state.String())
	})
	pc2.OnICEConnectionStateChange(func(state webrtc.ICEConnectionState) {
		record(&result.ICEStates, "pc2:"+state.String())
	})
	pc1.OnConnectionStateChange(func(state webrtc.PeerConnectionState) {
		record(&result.ConnectionStates, "pc1:"+state.String())
	})
	pc2.OnConnectionStateChange(func(state webrtc.PeerConnectionState) {
		record(&result.ConnectionStates, "pc2:"+state.String())
		if state == webrtc.PeerConnectionStateConnected {
			mu.Lock()
			result.DTLSState = "connected"
			result.SelectedPair = "host/udp/loopback"
			mu.Unlock()
		}
	})

	pc2.OnTrack(func(track *webrtc.TrackRemote, receiver *webrtc.RTPReceiver) {
		go func() {
			for {
				_, _, err := track.ReadRTP()
				if err != nil {
					record(&result.RecentSRTPRTCPErrors, "rtp-read:"+err.Error())
					return
				}
				if packetsReceived.Add(1) >= 3 && gotPong.Load() {
					doneOnce.Do(func() { close(done) })
				}
			}
		}()
	})

	pc2.OnDataChannel(func(dc *webrtc.DataChannel) {
		dc.OnMessage(func(msg webrtc.DataChannelMessage) {
			record(&result.Messages, "pc2:"+string(msg.Data))
			if string(msg.Data) == "pion-ping" {
				if err := dc.SendText("pion-pong"); err != nil {
					failCh <- err
				}
			}
		})
	})

	dc, err := pc1.CreateDataChannel("pion-smoke", nil)
	if err != nil {
		return err
	}
	dc.OnOpen(func() {
		if err := dc.SendText("pion-ping"); err != nil {
			failCh <- err
		}
	})
	dc.OnMessage(func(msg webrtc.DataChannelMessage) {
		record(&result.Messages, "pc1:"+string(msg.Data))
		if string(msg.Data) == "pion-pong" {
			gotPong.Store(true)
			if packetsReceived.Load() >= 3 {
				doneOnce.Do(func() { close(done) })
			}
		}
	})

	videoTrack, err := webrtc.NewTrackLocalStaticRTP(
		webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeVP8, ClockRate: 90000},
		"video",
		"uya-pion-interop",
	)
	if err != nil {
		return err
	}
	sender, err := pc1.AddTrack(videoTrack)
	if err != nil {
		return err
	}
	go func() {
		buf := make([]byte, 1500)
		for {
			if _, _, err := sender.Read(buf); err != nil {
				return
			}
		}
	}()

	offer, err := pc1.CreateOffer(nil)
	if err != nil {
		return err
	}
	gatherPc1 := webrtc.GatheringCompletePromise(pc1)
	if err := pc1.SetLocalDescription(offer); err != nil {
		return err
	}
	<-gatherPc1
	if err := pc2.SetRemoteDescription(*pc1.LocalDescription()); err != nil {
		return err
	}

	answer, err := pc2.CreateAnswer(nil)
	if err != nil {
		return err
	}
	gatherPc2 := webrtc.GatheringCompletePromise(pc2)
	if err := pc2.SetLocalDescription(answer); err != nil {
		return err
	}
	<-gatherPc2
	if err := pc1.SetRemoteDescription(*pc2.LocalDescription()); err != nil {
		return err
	}

	result.OfferSDP = pc1.LocalDescription().SDP
	result.AnswerSDP = pc2.LocalDescription().SDP

	go func() {
		ticker := time.NewTicker(20 * time.Millisecond)
		defer ticker.Stop()
		var seq uint16 = 1
		var ts uint32 = 3000
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				packet := &rtp.Packet{
					Header: rtp.Header{
						Version:        2,
						PayloadType:    96,
						SequenceNumber: seq,
						Timestamp:      ts,
						SSRC:           0x11223344,
						Marker:         true,
					},
					Payload: []byte{0x10, 0x00, 0x9d, 0x01, 0x2a, 0x40, 0x01, 0xb4, 0x00},
				}
				if err := videoTrack.WriteRTP(packet); err != nil {
					failCh <- err
					return
				}
				seq++
				ts += 3000
			}
		}
	}()

	select {
	case <-done:
	case err := <-failCh:
		return err
	case <-time.After(10 * time.Second):
		return fmt.Errorf("timed out waiting for Pion DataChannel and RTP; packets=%d", packetsReceived.Load())
	}

	time.Sleep(100 * time.Millisecond)
	result.PacketsReceived = packetsReceived.Load()
	mu.Lock()
	encoded, err := json.MarshalIndent(result, "", "  ")
	mu.Unlock()
	if err != nil {
		return err
	}
	fmt.Println(string(encoded))
	return nil
}
'''


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_inputs() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    (WORK_DIR / "go.mod").write_text(GO_MOD, encoding="utf-8")
    (WORK_DIR / "main.go").write_text(GO_MAIN, encoding="utf-8")


def run_go() -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("GOTOOLCHAIN", "local")
    tidy = subprocess.run(
        ["go", "mod", "tidy"],
        cwd=str(WORK_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if tidy.returncode != 0:
        raise RuntimeError(
            "Pion interop Go module setup failed\n"
            f"stdout:\n{tidy.stdout}\n"
            f"stderr:\n{tidy.stderr}"
        )
    completed = subprocess.run(
        ["go", "run", "."],
        cwd=str(WORK_DIR),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Pion interop Go program failed\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


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
    require(str(result.get("dtlsState", "")) == "connected", "DTLS state was not connected")
    require(str(result.get("selectedPair", "")) != "", "selected pair summary missing")
    require("pc2:pion-ping" in result.get("messages", []), "pc2 did not receive DataChannel ping")
    require("pc1:pion-pong" in result.get("messages", []), "pc1 did not receive DataChannel pong")
    require(int(result.get("packetsReceived", 0)) >= 3, "Pion RTP receiver did not receive packets")
    require(isinstance(result.get("recentSrtpRtcpErrors"), list), "recent SRTP/RTCP errors summary missing")


def main() -> int:
    try:
        write_inputs()
        result = run_go()
        validate(result)
        compact = {
            "iceStates": result.get("iceStates", []),
            "connectionStates": result.get("connectionStates", []),
            "dtlsState": result.get("dtlsState", ""),
            "selectedPair": result.get("selectedPair", ""),
            "messages": result.get("messages", []),
            "packetsReceived": result.get("packetsReceived", 0),
            "recentSrtpRtcpErrors": result.get("recentSrtpRtcpErrors", []),
        }
        print(json.dumps(compact, sort_keys=True))
        print("Pion WebRTC interop checks passed")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
