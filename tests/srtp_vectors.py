#!/usr/bin/env python3
"""SRTP RFC 3711 vector validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "srtp"
HEX_RE = re.compile(r"^[0-9a-f]+$")


def read_vectors(name: str) -> dict:
    path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def assert_hex(value: str, expected_bytes: int | None = None) -> None:
    require(isinstance(value, str), "hex field must be string")
    require(len(value) % 2 == 0, f"hex string must have even length: {value}")
    require(HEX_RE.match(value) is not None, f"invalid hex string: {value}")
    if expected_bytes is not None:
        require(len(value) == expected_bytes * 2, f"expected {expected_bytes} bytes, got {len(value) // 2}")


def check_aes_cm_keystream(vectors: dict) -> None:
    section = vectors["rfc3711_aes_cm"]
    require(section["session_key_hex"].lower() == "2b7e151628aed2a6abf7158809cf4f3c", "unexpected AES-CM session key")

    cases = section["vectors"]
    require(len(cases) >= 6, "need at least 6 AES-CM vectors")

    first = cases[0]
    require(first["counter_hex"].lower() == "f0f1f2f3f4f5f6f7f8f9fafbfcfd0000", "unexpected first counter")
    require(first["keystream_hex"].lower() == "e03ead0935c95e80e166b16dd92b4eb4", "unexpected first keystream")

    second = cases[1]
    require(second["counter_hex"].lower() == "f0f1f2f3f4f5f6f7f8f9fafbfcfd0001", "unexpected second counter")
    require(second["keystream_hex"].lower() == "d23513162b02d0f72a43a2fe4a5f97ab", "unexpected second keystream")

    last = cases[-1]
    require(last["counter_hex"].lower() == "f0f1f2f3f4f5f6f7f8f9fafbfcfdff01", "unexpected last counter")
    require(last["keystream_hex"].lower() == "6a2cc3787889374fbeb4c81b17ba6c44", "unexpected last keystream")

    for case in cases:
        assert_hex(case["counter_hex"], 16)
        assert_hex(case["keystream_hex"], 16)


def check_key_derivation(vectors: dict) -> None:
    section = vectors["rfc3711_key_derivation"]
    require(section["master_key_hex"].lower() == "e1f97a0d3e018be0d64fa32c06de4139", "unexpected master key")
    require(section["master_salt_hex"].lower() == "0ec675ad498afeebb6960b3aabe6", "unexpected master salt")
    require(section["index_div_kdr_hex"].lower() == "000000000000", "unexpected index_div_kdr")

    require(section["cipher_key_hex"].lower() == "c61e7a93744f39ee10734afe3ff7a087", "unexpected cipher key")
    require(section["cipher_salt_hex"].lower() == "30cbbc08863d8c85d49db34a9ae1", "unexpected cipher salt")

    expected_auth_key = (
        "cebe321f6ff7716b6fd4ab49af256a15"
        "6d38baa48f0a0acf3c34e2359e6cdbce"
        "e049646c43d9327ad175578ef7227098"
        "6371c10c9a369ac2f94a8c5fbcdddc25"
        "6d6e919a48b610ef17c2041e47403576"
        "6b68642c59bbfc2f34db60dbdfb2"
    )
    require(section["auth_key_hex"].lower() == expected_auth_key, "unexpected auth key")

    assert_hex(section["master_key_hex"], 16)
    assert_hex(section["master_salt_hex"], 14)
    assert_hex(section["cipher_key_hex"], 16)
    assert_hex(section["cipher_salt_hex"], 14)
    assert_hex(section["auth_key_hex"], 94)


def check_sequence_wrap(vectors: dict) -> None:
    seq_wrap = vectors["sequence_wrap"]["vectors"]
    for item in seq_wrap:
        seq = int(item["seq_hex"], 16)
        roc = int(item["roc_hex"], 16)
        expected_index = int(item["expected_index_hex"], 16)
        actual_index = (roc << 16) | seq
        require(actual_index == expected_index, f"sequence_wrap mismatch: {item['name']}")


def check_replay_window(vectors: dict) -> None:
    replay = vectors["replay_window"]["vectors"]
    for item in replay:
        index = int(item["index_hex"], 16)
        window = int(item["window_hex"], 16)
        expected_accept = item["expected_accept"]
        expected_window = int(item["expected_window_hex"], 16)

        if index > 63:
            actual_accept = True
            actual_window = 1
        elif window & (1 << index):
            actual_accept = False
            actual_window = window
        else:
            actual_accept = True
            actual_window = window | (1 << index)

        require(actual_accept == expected_accept, f"replay accept mismatch: {item['name']}")
        require(actual_window == expected_window, f"replay window mismatch: {item['name']}")


def main() -> None:
    vectors = read_vectors("rfc3711_vectors.json")
    check_aes_cm_keystream(vectors)
    check_key_derivation(vectors)
    check_sequence_wrap(vectors)
    check_replay_window(vectors)
    print("All SRTP RFC 3711 vector validations passed.")


if __name__ == "__main__":
    main()
