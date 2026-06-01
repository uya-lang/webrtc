#!/usr/bin/env python3
"""Validate browser DTLS handshake fixtures against SDP fixtures."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURE_PATH = TESTS_DIR / "fixtures" / "dtls" / "browser_handshake.json"
HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
PROFILE_ID_RE = re.compile(r"^0x[0-9a-f]{4}$")


class ValidationError(Exception):
    pass


def normalize_fingerprint(value: str) -> str:
    return value.replace(":", "").strip().lower()


def parse_sdp_fingerprints(sdp_text: str, algorithm: str) -> list[str]:
    want_prefix = f"a=fingerprint:{algorithm} "
    values: list[str] = []
    for line in sdp_text.splitlines():
        if line.startswith(want_prefix):
            values.append(normalize_fingerprint(line[len(want_prefix) :]))
    return values


def parse_sdp_setup_values(sdp_text: str) -> list[str]:
    values: list[str] = []
    for line in sdp_text.splitlines():
        if line.startswith("a=setup:"):
            values.append(line.split(":", 1)[1].strip())
    return values


def parse_sdp_transport_profiles(sdp_text: str) -> set[str]:
    profiles: set[str] = set()
    for line in sdp_text.splitlines():
        if not line.startswith("m="):
            continue
        parts = line.split()
        if len(parts) >= 3:
            profiles.add(parts[2].strip())
    return profiles


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_case(case: dict[str, object]) -> None:
    required = {
        "name",
        "browser",
        "source_sdp",
        "fingerprint_algorithm",
        "fingerprint_hex",
        "setup_role",
        "transport_profiles",
        "expected_use_srtp_profile_ids",
        "expected_named_group",
        "expected_signature_scheme",
    }
    missing = required.difference(case)
    require(not missing, f"case missing required keys: {sorted(missing)}")

    name = str(case["name"])
    sdp_path = REPO_ROOT / str(case["source_sdp"])
    require(sdp_path.exists(), f"{name}: missing source SDP file: {sdp_path}")
    sdp_text = sdp_path.read_text(encoding="utf-8")

    fingerprint_algorithm = str(case["fingerprint_algorithm"]).lower()
    expected_fingerprint = str(case["fingerprint_hex"]).lower()
    require(HEX_64_RE.match(expected_fingerprint) is not None, f"{name}: fingerprint_hex must be 64 hex chars")

    sdp_fingerprints = parse_sdp_fingerprints(sdp_text, fingerprint_algorithm)
    require(sdp_fingerprints, f"{name}: SDP has no fingerprint with algorithm {fingerprint_algorithm}")
    require(
        expected_fingerprint in sdp_fingerprints,
        f"{name}: fixture fingerprint does not match source SDP fingerprints",
    )

    setup_values = parse_sdp_setup_values(sdp_text)
    require(setup_values, f"{name}: SDP has no setup attribute")
    expected_setup = str(case["setup_role"])
    require(expected_setup in setup_values, f"{name}: setup role {expected_setup} missing from SDP")

    actual_profiles = parse_sdp_transport_profiles(sdp_text)
    expected_profiles = set(case["transport_profiles"])
    missing_profiles = expected_profiles.difference(actual_profiles)
    require(not missing_profiles, f"{name}: missing transport profiles in SDP: {sorted(missing_profiles)}")

    profile_ids = [str(v).lower() for v in case["expected_use_srtp_profile_ids"]]
    require(profile_ids, f"{name}: expected_use_srtp_profile_ids must not be empty")
    require("0x0001" in profile_ids, f"{name}: expected_use_srtp_profile_ids must include 0x0001")
    require(all(PROFILE_ID_RE.match(v) for v in profile_ids), f"{name}: invalid SRTP profile id format")

    require(str(case["expected_named_group"]) == "secp256r1", f"{name}: only secp256r1 is supported")
    require(
        str(case["expected_signature_scheme"]) == "ecdsa_secp256r1_sha256",
        f"{name}: expected_signature_scheme must be ecdsa_secp256r1_sha256",
    )


def main() -> int:
    if not FIXTURE_PATH.exists():
        print(f"ERROR: fixture file not found: {FIXTURE_PATH}")
        return 1

    try:
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"ERROR: failed to parse {FIXTURE_PATH}: {exc}")
        return 1

    if not isinstance(data, dict):
        print("ERROR: fixture root must be a JSON object")
        return 1

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        print("ERROR: fixture cases must be a non-empty array")
        return 1

    try:
        for case in cases:
            if not isinstance(case, dict):
                raise ValidationError("case entry must be an object")
            validate_case(case)
    except ValidationError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Browser DTLS fixtures validated: {len(cases)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
