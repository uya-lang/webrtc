#!/usr/bin/env python3
"""SRTP test vectors validation."""

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "srtp"


def read_vectors(name):
    path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    vectors = read_vectors("rfc3711_vectors.json")
    
    seq_wrap = vectors["sequence_wrap"]["vectors"]
    for v in seq_wrap:
        seq = int(v["seq_hex"], 16)
        roc = int(v["roc_hex"], 16)
        expected_index = int(v["expected_index_hex"], 16)
        actual_index = (roc << 16) | seq
        assert actual_index == expected_index
    
    replay = vectors["replay_window"]["vectors"]
    for v in replay:
        index = int(v["index_hex"], 16)
        window = int(v["window_hex"], 16)
        expected_accept = v["expected_accept"]
        expected_window = int(v["expected_window_hex"], 16)
        
        if index >63:
            actual_accept =True
            actual_window = 1
        elif window& (1 << index):
            actual_accept = False
            actual_window = window
        else:
            actual_accept = True
            actual_window = window | (1 << index)
        
        assert actual_accept == expected_accept
        assert actual_window == expected_window
    
    print("All SRTP vector validations passed.")


if __name__ == "__main__":
    main()
