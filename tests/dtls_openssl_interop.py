#!/usr/bin/env python3
"""DTLS OpenSSL/browser interoperability fixture utilities.

Commands:
  generate      Generate OpenSSL certificate fixture.
  validate      Validate OpenSSL fixture only (backward compatible).
  validate-all  Validate OpenSSL + browser fixtures.
  help          Print this help.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURE_DIR = TESTS_DIR / "fixtures" / "dtls"
OPENSSL_FIXTURE = FIXTURE_DIR / "openssl_handshake.json"
BROWSER_FIXTURE_VALIDATOR = TESTS_DIR / "dtls_browser_fixtures.py"


class InteropError(Exception):
    pass


def run_checked(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def generate_openssl_cert_and_fingerprint() -> tuple[str, str]:
    """Generate a self-signed P-256 cert and return DER hex and SHA-256 fingerprint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        cert_path = tmppath / "interop_test.crt"
        key_path = tmppath / "interop_test.key"

        run_checked(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "ec",
                "-pkeyopt",
                "ec_paramgen_curve:prime256v1",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
                "-days",
                "30",
                "-nodes",
                "-subj",
                "/CN=uya-dtls-interop-test",
            ]
        )

        der_result = run_checked(["openssl", "x509", "-in", str(cert_path), "-outform", "DER"])
        cert_der_hex = der_result.stdout.encode("latin1").hex()

        fp_result = run_checked(
            [
                "openssl",
                "x509",
                "-in",
                str(cert_path),
                "-outform",
                "DER",
                "-fingerprint",
                "-sha256",
                "-noout",
            ]
        )
        fingerprint = ""
        if "=" in fp_result.stdout:
            fingerprint = fp_result.stdout.strip().split("=", 1)[1].replace(":", "").lower()

    return cert_der_hex, fingerprint


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise InteropError(f"failed to parse JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InteropError(f"fixture root must be object: {path}")
    return data


def validate_openssl_fixture() -> None:
    if not OPENSSL_FIXTURE.exists():
        raise InteropError(f"fixture file not found: {OPENSSL_FIXTURE}")

    data = load_json(OPENSSL_FIXTURE)

    required_fields = [
        "description",
        "openssl_version",
        "certificate_der_hex",
        "certificate_sha256_fingerprint_hex",
        "cipher_suite",
        "cipher_suite_id",
        "srtp_profile",
        "srtp_profile_id",
        "certificate_cn",
        "named_curve",
    ]

    missing = [field for field in required_fields if field not in data]
    if missing:
        raise InteropError(f"missing required OpenSSL fixture fields: {missing}")

    cert_hex = str(data["certificate_der_hex"])
    if not cert_hex:
        raise InteropError("certificate_der_hex must not be empty")

    try:
        cert_bytes = bytes.fromhex(cert_hex)
    except ValueError as exc:
        raise InteropError(f"certificate_der_hex is not valid hex: {exc}") from exc

    with tempfile.NamedTemporaryFile(suffix=".der", delete=False) as tmp:
        tmp.write(cert_bytes)
        tmp_path = Path(tmp.name)

    try:
        result = run_checked(["openssl", "x509", "-inform", "DER", "-in", str(tmp_path), "-noout", "-text"])
        _ = result.stdout
    finally:
        tmp_path.unlink(missing_ok=True)

    print("OpenSSL fixture validation passed")
    print(f"  OpenSSL version: {data['openssl_version']}")
    print(f"  Certificate CN: {data['certificate_cn']}")
    print(f"  SHA-256 fingerprint: {data['certificate_sha256_fingerprint_hex']}")


def validate_browser_fixture() -> None:
    if not BROWSER_FIXTURE_VALIDATOR.exists():
        raise InteropError(f"browser fixture validator not found: {BROWSER_FIXTURE_VALIDATOR}")

    result = subprocess.run(
        [sys.executable, str(BROWSER_FIXTURE_VALIDATOR)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        detail = "\n".join(part for part in [stdout, stderr] if part)
        raise InteropError(f"browser fixture validation failed\n{detail}")

    output = result.stdout.strip()
    if output:
        print(output)


def command_generate() -> int:
    print("Generating OpenSSL DTLS handshake fixture...")
    cert_der_hex, fingerprint = generate_openssl_cert_and_fingerprint()

    openssl_ver = run_checked(["openssl", "version"]).stdout.strip()
    fixtures = {
        "description": "OpenSSL DTLS 1.2 handshake fixtures for WebRTC interop",
        "openssl_version": openssl_ver,
        "certificate_der_hex": cert_der_hex,
        "certificate_sha256_fingerprint_hex": fingerprint,
        "cipher_suite": "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
        "cipher_suite_id": "0xc02b",
        "srtp_profile": "SRTP_AES128_CM_HMAC_SHA1_80",
        "srtp_profile_id": "0x0001",
        "certificate_cn": "uya-dtls-interop-test",
        "named_curve": "secp256r1",
        "notes": [
            "certificate_der_hex is a real P-256 self-signed cert from OpenSSL",
            "certificate_sha256_fingerprint_hex can be compared against Uya SHA-256 output",
            "use together with browser fixtures for DTLS interop gating",
        ],
    }
    OPENSSL_FIXTURE.write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote fixture: {OPENSSL_FIXTURE}")
    print(f"  OpenSSL version: {openssl_ver}")
    print(f"  Certificate fingerprint: {fingerprint}")
    return 0


def command_validate() -> int:
    print("Validating OpenSSL DTLS fixture...")
    validate_openssl_fixture()
    return 0


def command_validate_all() -> int:
    print("Validating OpenSSL and browser DTLS fixtures...")
    validate_openssl_fixture()
    validate_browser_fixture()
    print("DTLS fixture interop checks passed")
    return 0


def command_help() -> int:
    print(__doc__)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="DTLS OpenSSL/browser interop utilities")
    parser.add_argument(
        "command",
        choices=["generate", "validate", "validate-all", "help"],
        help="command to execute",
    )
    args = parser.parse_args()

    try:
        if args.command == "generate":
            return command_generate()
        if args.command == "validate":
            return command_validate()
        if args.command == "validate-all":
            return command_validate_all()
        return command_help()
    except (InteropError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
