#!/usr/bin/env python3
import hashlib
import hmac
import json
from pathlib import Path


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dtls" / "exporter_reference.json"


def tls12_prf_sha256(secret: bytes, label: bytes, seed: bytes, out_len: int) -> bytes:
    seed_bytes = label + seed
    a = hmac.new(secret, seed_bytes, hashlib.sha256).digest()
    out = b""
    while len(out) < out_len:
        out += hmac.new(secret, a + seed_bytes, hashlib.sha256).digest()
        a = hmac.new(secret, a, hashlib.sha256).digest()
    return out[:out_len]


def main() -> None:
    case = json.loads(FIXTURE.read_text(encoding="utf-8"))
    secret = bytes.fromhex(case["master_secret_hex"])
    client_random = bytes.fromhex(case["client_random_hex"])
    server_random = bytes.fromhex(case["server_random_hex"])
    expected = bytes.fromhex(case["expected_exporter_hex"])
    actual = tls12_prf_sha256(
        secret,
        case["label"].encode("ascii"),
        client_random + server_random,
        case["output_len"],
    )
    assert actual == expected


if __name__ == "__main__":
    main()
