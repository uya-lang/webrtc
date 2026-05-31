#!/usr/bin/env python3
import hashlib
import hmac
import json
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "crypto"


def load_json(name: str) -> dict:
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def decode_field(case: dict, ascii_key: str, hex_key: str) -> bytes:
    if ascii_key in case:
        return case[ascii_key].encode("utf-8")
    if hex_key in case:
        return bytes.fromhex(case[hex_key])
    raise AssertionError(f"missing {ascii_key}/{hex_key} in {case['id']}")


def run_hash_vectors(filename: str, algorithm: str) -> None:
    fixture = load_json(filename)
    assert fixture["algorithm"] == algorithm
    for case in fixture["cases"]:
        payload = decode_field(case, "input_ascii", "input_hex")
        digest = hashlib.new(algorithm.replace("-", ""), payload).hexdigest()
        assert digest == case["digest_hex"], case["id"]


def run_hmac_vectors(filename: str, digest_name: str) -> None:
    fixture = load_json(filename)
    for case in fixture["cases"]:
        key = decode_field(case, "key_ascii", "key_hex")
        message = decode_field(case, "message_ascii", "message_hex")
        digest = hmac.new(key, message, getattr(hashlib, digest_name)).hexdigest()
        assert digest == case["tag_hex"], case["id"]


def run_hmac_negative_vectors(filename: str, digest_name: str) -> None:
    fixture = load_json(filename)
    assert fixture["style"] == "wycheproof-like"
    for case in fixture["cases"]:
        key = decode_field(case, "key_ascii", "key_hex")
        message = decode_field(case, "message_ascii", "message_hex")
        actual = hmac.new(key, message, getattr(hashlib, digest_name)).digest()
        provided = bytes.fromhex(case["tag_hex"])
        assert case["valid"] is False, case["id"]
        assert not hmac.compare_digest(actual, provided), case["id"]
        assert case["flags"], case["id"]


def main() -> None:
    run_hash_vectors("sha1_vectors.json", "sha-1")
    run_hash_vectors("sha256_vectors.json", "sha-256")
    run_hmac_vectors("hmac_sha1_vectors.json", "sha1")
    run_hmac_vectors("hmac_sha256_vectors.json", "sha256")
    run_hmac_negative_vectors("wycheproof_like_hmac_sha1.json", "sha1")
    run_hmac_negative_vectors("wycheproof_like_hmac_sha256.json", "sha256")


if __name__ == "__main__":
    main()
