#!/usr/bin/env python3
"""Generate OpenSSL DTLS handshake fixtures for WebRTC interop testing.

Captures a real P-256 self-signed certificate from OpenSSL and stores
it alongside metadata for the Uya DTLS parser tests.
"""

import json
import subprocess
import tempfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent


def generate_self_signed_cert(cert_path: Path, key_path: Path) ->str:
subprocess.run(
        [
"openssl", "req", "-x509","-newkey","ec",
            "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-keyout", str(key_path),
            "-out", str(cert_path),
"-days", "365",
            "-nodes",
            "-subj", "/CN=uya-webrtc-openssl-test",
        ],
        check=True,
        capture_output=True,
text=True,
    )
der_result = subprocess.run(
["openssl", "x509", "-in",str(cert_path),"-outform","DER"],
        check=True,
        capture_output=True,
)
    returnder_result.stdout.hex()


def openssl_version() -> str:
    result= subprocess.run(
        ["openssl", "version"], capture_output=True, text=True
    )
return result.stdout.strip()


def openssl_fingerprint_sha256(cert_path: Path) ->str:
result = subprocess.run(
        ["openssl", "x509","-in", str(cert_path), "-outform", "DER",
"-fingerprint","-sha256", "-noout"],
capture_output=True,text=True,
    )
line = result.stdout.strip()
if "=" in line:
        returnline.split("=",1)[1].replace(":","").lower()
    return ""


def main() ->None:
print("Generating OpenSSLDTLS handshake fixtures...")
with tempfile.TemporaryDirectory() as tmpdir:
tmppath =Path(tmpdir)
        cert_path= tmppath/ "test.crt"
        key_path = tmppath / "test.key"

print("  Generatingself-signed P-256certificate...")
        cert_der_hex= generate_self_signed_cert(cert_path,key_path)
        fingerprint = openssl_fingerprint_sha256(cert_path)
        ver= openssl_version()
        print(f"  OpenSSL version: {ver}")

        fixtures ={
            "description": "OpenSSL DTLS1.2 handshakefixtures for WebRTCinterop",
            "openssl_version": ver,
            "certificate_der_hex": cert_der_hex,
"certificate_sha256_fingerprint_hex": fingerprint,
            "cipher_suite": "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
"cipher_suite_id": "0xc02b",
            "srtp_profile": "SRTP_AES128_CM_HMAC_SHA1_80",
            "srtp_profile_id": "0x0001",
            "certificate_cn": "uya-webrtc-openssl-test",
            "named_curve": "secp256r1",
            "notes": [
"certificate_der_hexis a real P-256self-signed cert fromOpenSSL",
"certificate_sha256_fingerprint_hex can be comparedagainst Uya SHA-256output",
"Use with dtls_certificate_parse forinterop validation",
            ],
        }

output_path = FIXTURE_DIR / "openssl_handshake.json"
        print(f"  Writingfixtures to {output_path}...")
        output_path.write_text(
            json.dumps(fixtures, indent=2),
            encoding="utf-8",
        )
print("Done.")


if __name__ == "__main__":
main()
