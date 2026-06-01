#!/usr/bin/env python3
"""Sequence wrap / ROC / replay-window failing tests for SRTP."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "srtp" / "rfc3711_vectors.json"


class ReplayWindow64:
    def __init__(self) -> None:
        self.highest_index = -1
        self.window = 0

    def check_and_mark(self, index: int) -> bool:
        if self.highest_index < 0:
            self.highest_index = index
            self.window = 1
            return True

        if index > self.highest_index:
            shift = index - self.highest_index
            if shift >= 64:
                self.window = 1
            else:
                self.window = ((self.window << shift) & ((1 << 64) - 1)) | 1
            self.highest_index = index
            return True

        delta = self.highest_index - index
        if delta >= 64:
            return False

        bit = 1 << delta
        if self.window & bit:
            return False

        self.window |= bit
        return True


def guess_index(current_roc: int, highest_index: int, seq: int) -> int:
    s_l = highest_index & 0xFFFF
    roc = current_roc
    if s_l < 0x8000:
        if seq > s_l + 0x8000:
            roc = max(roc - 1, 0)
    else:
        if s_l - 0x8000 > seq:
            roc = roc + 1
    return (roc << 16) | seq


def load_vectors() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_roc_transition_vectors(data: dict) -> None:
    vectors = data["roc_transitions"]["vectors"]
    for case in vectors:
        current_roc = int(case["current_roc_hex"], 16)
        highest_index = int(case["highest_index_hex"], 16)
        seq = int(case["seq_hex"], 16)
        expected = int(case["expected_index_hex"], 16)
        actual = guess_index(current_roc, highest_index, seq)
        assert actual == expected, f"ROC transition mismatch: {case['name']}"


def test_replay_window_vectors(data: dict) -> None:
    vectors = data["replay_window"]["vectors"]
    rw = ReplayWindow64()

    for case in vectors:
        index = int(case["index_hex"], 16)
        expected_accept = bool(case["expected_accept"])
        actual_accept = rw.check_and_mark(index)
        assert actual_accept == expected_accept, f"Replay check mismatch: {case['name']}"

    # failing paths: replay and too-old packet must be rejected
    assert not rw.check_and_mark(1), "duplicate packet should be rejected"
    assert not rw.check_and_mark(0), "too-old packet should be rejected"


def main() -> None:
    data = load_vectors()
    test_roc_transition_vectors(data)
    test_replay_window_vectors(data)
    print("SRTP sequence/ROC/replay tests passed")


if __name__ == "__main__":
    main()
