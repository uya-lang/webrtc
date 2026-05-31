#!/usr/bin/env python3
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "dtls" / "fuzz"
DTLS_RECORD_HEADER_BYTES = 13


def read_hex(name: str) -> bytes:
    text = (FIXTURE_DIR / name).read_text(encoding="utf-8").strip()
    return bytes.fromhex(text)


def main() -> None:
    truncated = read_hex("truncated_record_header.hex")
    assert len(truncated) < DTLS_RECORD_HEADER_BYTES

    edge = read_hex("record_epoch_sequence_edge.hex")
    assert len(edge) == DTLS_RECORD_HEADER_BYTES
    assert edge[3:5] == b"\xff\xff"
    assert edge[5:11] == b"\xff\xff\xff\x00\x00\x01"

    mismatch = read_hex("fragment_length_mismatch.hex")
    assert len(mismatch) >= DTLS_RECORD_HEADER_BYTES + 12
    body_len = int.from_bytes(mismatch[11:13], "big")
    assert body_len != len(mismatch) - DTLS_RECORD_HEADER_BYTES

    overlap = read_hex("reassembly_overlap.hex")
    gap = read_hex("reassembly_gap.hex")
    assert len(overlap) > DTLS_RECORD_HEADER_BYTES + 12
    assert len(gap) > DTLS_RECORD_HEADER_BYTES + 12


if __name__ == "__main__":
    main()
