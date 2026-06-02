#!/usr/bin/env python3
"""Static checks for constant-time comparison on authentication material."""

from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]

REQUIRED_CONSTANT_TIME_CALLS = {
    "src/webrtc/stun/parse.uya": (
        "stun_verify_message_integrity",
        "stun_verify_message_integrity_sha256",
    ),
    "src/webrtc/srtp/protect.uya": ("srtp_unprotect",),
    "src/webrtc/srtp/srtcp.uya": ("srtcp_unprotect",),
    "src/webrtc/crypto/gcm.uya": ("crypto_aes_gcm_decrypt_and_verify",),
    "src/webrtc/dtls/handshake.uya": (
        "dtls_finished_verify",
        "dtls_certificate_fingerprint_verify",
    ),
}


def find_matching_brace(source: str, open_index: int) -> int:
    depth = 0
    in_string = False
    escaped = False
    index = open_index
    while index < len(source):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("unclosed function body")


def function_body(source: str, name: str) -> str:
    match = re.search(rf"\bfn\s+{re.escape(name)}\s*\(", source)
    if not match:
        match = re.search(rf"\bexport\s+fn\s+{re.escape(name)}\s*\(", source)
    if not match:
        raise ValueError(f"function not found: {name}")
    open_index = source.find("{", match.end())
    if open_index < 0:
        raise ValueError(f"function body not found: {name}")
    close_index = find_matching_brace(source, open_index)
    return source[open_index + 1 : close_index]


def audit_constant_time_helper() -> list[str]:
    path = ROOT / "src/webrtc/binary.uya"
    source = path.read_text(encoding="utf-8")
    body = function_body(source, "constant_time_bytes_equal")
    findings: list[str] = []
    if "while i < max_len" not in body:
        findings.append("constant_time_bytes_equal must iterate to max_len")
    if "(lhs.len as u64) ^ (rhs.len as u64)" not in body:
        findings.append("constant_time_bytes_equal must fold length mismatch into diff")
    if "diff = diff |" not in body:
        findings.append("constant_time_bytes_equal must accumulate byte differences")
    if re.search(r"\breturn\s+false\b|\bbreak\b|\bcontinue\b", body):
        findings.append("constant_time_bytes_equal must not early-return or break")
    if "return diff == 0u64" not in body:
        findings.append("constant_time_bytes_equal must return only from accumulated diff")
    return findings


def audit_required_call_sites() -> list[str]:
    findings: list[str] = []
    for rel_path, functions in REQUIRED_CONSTANT_TIME_CALLS.items():
        source = (ROOT / rel_path).read_text(encoding="utf-8")
        for function in functions:
            body = function_body(source, function)
            if "constant_time_bytes_equal" not in body:
                findings.append(f"{rel_path}:{function} must use constant_time_bytes_equal")
            unsafe = re.search(r"\bmemcmp\b|\bbcmp\b", body)
            if unsafe:
                findings.append(f"{rel_path}:{function} uses an unsafe byte compare")
    return findings


def audit_no_memcmp() -> list[str]:
    findings: list[str] = []
    for path in sorted((ROOT / "src").glob("**/*.uya")):
        source = path.read_text(encoding="utf-8")
        if re.search(r"\bmemcmp\b|\bbcmp\b", source):
            findings.append(f"{path.relative_to(ROOT)} uses host byte compare")
    return findings


def main() -> int:
    findings = []
    findings.extend(audit_constant_time_helper())
    findings.extend(audit_required_call_sites())
    findings.extend(audit_no_memcmp())

    if findings:
        print("constant-time audit failed:")
        for finding in findings:
            print(finding)
        return 1

    print("constant-time audit passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
