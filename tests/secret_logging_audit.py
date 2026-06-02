#!/usr/bin/env python3
"""Fail if runtime logging can print known WebRTC secret material."""

from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_GLOBS = ("src/**/*.uya", "src/*.uya", "benchmarks/**/*.uya")
LOG_FUNCTIONS = ("printf", "fprintf")

SENSITIVE = re.compile(
    r"(?i)(?:"
    r"\bice[-_]?pwd\b|"
    r"\bpwd(?:_len)?\b|"
    r"\bpassword\b|"
    r"\bsecret\b|"
    r"\bprivate[-_]?key\b|"
    r"\bmaster[-_]?key\b|"
    r"\bauth[-_]?key\b|"
    r"\bcipher[-_]?key\b|"
    r"\bsrtp[-_]?key\b|"
    r"\breservation[-_]?token\b|"
    r"\bcookie\b|"
    r"\bfingerprint\b|"
    r"\bmessage[-_]?integrity\b"
    r")"
)

SENSITIVE_FORMAT_VALUE = re.compile(
    r"(?i)(?:ice[-_]?pwd|pwd|password|secret|private[-_]?key|master[-_]?key|auth[-_]?key|"
    r"cipher[-_]?key|srtp[-_]?key|reservation[-_]?token|cookie|fingerprint|"
    r"message[-_]?integrity)\s*[:=]\s*%"
)

ALLOWED_PATH_PARTS = {
    "webrtc_secret_logging_audit_fixture.uya",
}


def strip_string_literals(text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            result.append(" ")
            continue
        if char == '"':
            in_string = True
            result.append(" ")
            continue
        result.append(char)
    return "".join(result)


def collect_call(source: str, start: int) -> tuple[str, int]:
    depth = 0
    index = start
    in_string = False
    escaped = False
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
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[start : index + 1], index + 1
        index += 1
    return source[start:], len(source)


def split_top_level_args(call: str) -> list[str]:
    open_paren = call.find("(")
    close_paren = call.rfind(")")
    if open_paren < 0 or close_paren < open_paren:
        return []
    text = call[open_paren + 1 : close_paren]
    args: list[str] = []
    start = 0
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        args.append(tail)
    return args


def first_string_literal(text: str) -> str:
    match = re.search(r'"(?:\\.|[^"\\])*"', text)
    if not match:
        return ""
    return match.group(0)


def audit_file(path: pathlib.Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    if path.name in ALLOWED_PATH_PARTS:
        return []

    findings: list[str] = []
    for function in LOG_FUNCTIONS:
        pattern = re.compile(rf"\b{function}\s*\(")
        for match in pattern.finditer(source):
            call, _ = collect_call(source, match.start())
            args = split_top_level_args(call)
            if not args:
                continue
            format_arg_index = 1 if function == "fprintf" and len(args) > 1 else 0
            format_literal = first_string_literal(args[format_arg_index])
            logged_args = args[format_arg_index + 1 :]
            logged_arg_text = strip_string_literals("\n".join(logged_args))
            if SENSITIVE.search(logged_arg_text) or SENSITIVE_FORMAT_VALUE.search(format_literal):
                line = source.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {function} may log secret material")
    return findings


def main() -> int:
    files: list[pathlib.Path] = []
    for glob in SCAN_GLOBS:
        files.extend(ROOT.glob(glob))
    unique_files = sorted(set(path for path in files if path.is_file()))

    findings: list[str] = []
    for path in unique_files:
        findings.extend(audit_file(path))

    if findings:
        print("secret logging audit failed:")
        for finding in findings:
            print(finding)
        return 1

    print(f"secret logging audit passed ({len(unique_files)} files scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
