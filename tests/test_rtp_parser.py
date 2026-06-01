#!/usr/bin/env python3
"""RTP/RTCP parser fixture checks with truncation and extension boundary cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "rtp" / "parser_cases.json"
ONE_BYTE_PROFILE = 0xBEDE
TWO_BYTE_PROFILE_PREFIX = 0x1000


class ParseError(ValueError):
    """Fixture parser error with stable code string."""


def parse_one_byte_extensions(data: bytes) -> list[dict[str, int | str]]:
    elements: list[dict[str, int | str]] = []
    cursor = 0
    while cursor < len(data):
        header = data[cursor]
        if header == 0:
            cursor += 1
            continue
        ext_id = header >> 4
        ext_len = (header & 0x0F) + 1
        if ext_id == 15:
            break
        cursor += 1
        if cursor + ext_len > len(data):
            raise ParseError("RTP_EXTENSION_ELEMENT_TRUNCATED")
        elements.append(
            {
                "id": ext_id,
                "length": ext_len,
                "data": data[cursor : cursor + ext_len].hex(),
            }
        )
        cursor += ext_len
    return elements


def parse_two_byte_extensions(data: bytes) -> list[dict[str, int | str]]:
    elements: list[dict[str, int | str]] = []
    cursor = 0
    while cursor < len(data):
        ext_id = data[cursor]
        if ext_id == 0:
            cursor += 1
            continue
        if cursor + 1 >= len(data):
            raise ParseError("RTP_EXTENSION_ELEMENT_TRUNCATED")
        ext_len = data[cursor + 1]
        cursor += 2
        if cursor + ext_len > len(data):
            raise ParseError("RTP_EXTENSION_ELEMENT_TRUNCATED")
        elements.append(
            {
                "id": ext_id,
                "length": ext_len,
                "data": data[cursor : cursor + ext_len].hex(),
            }
        )
        cursor += ext_len
    return elements


def parse_rtp_header(packet: bytes) -> dict[str, object]:
    if len(packet) < 12:
        raise ParseError("RTP_PACKET_TOO_SMALL")

    first = packet[0]
    second = packet[1]
    version = (first >> 6) & 0x03
    if version != 2:
        raise ParseError("RTP_INVALID_VERSION")

    padding = ((first >> 5) & 0x01) != 0
    has_extension = ((first >> 4) & 0x01) != 0
    csrc_count = first & 0x0F
    marker = ((second >> 7) & 0x01) != 0
    payload_type = second & 0x7F
    sequence_number = int.from_bytes(packet[2:4], "big")
    timestamp = int.from_bytes(packet[4:8], "big")
    ssrc = int.from_bytes(packet[8:12], "big")

    result: dict[str, object] = {
        "version": version,
        "padding": padding,
        "extension": has_extension,
        "csrc_count": csrc_count,
        "marker": marker,
        "payload_type": payload_type,
        "sequence_number": sequence_number,
        "timestamp": timestamp,
        "ssrc": ssrc,
    }

    cursor = 12
    if csrc_count:
        csrc_bytes = csrc_count * 4
        if cursor + csrc_bytes > len(packet):
            raise ParseError("RTP_INVALID_CSRC_LENGTH")
        csrc = []
        for offset in range(csrc_count):
            begin = cursor + (offset * 4)
            csrc.append(int.from_bytes(packet[begin : begin + 4], "big"))
        result["csrc"] = csrc
        cursor += csrc_bytes

    if has_extension:
        if cursor + 4 > len(packet):
            raise ParseError("RTP_INVALID_EXTENSION_HEADER")
        profile = int.from_bytes(packet[cursor : cursor + 2], "big")
        length_words = int.from_bytes(packet[cursor + 2 : cursor + 4], "big")
        cursor += 4
        extension_len = length_words * 4
        if cursor + extension_len > len(packet):
            raise ParseError("RTP_INVALID_EXTENSION_LENGTH")
        extension_data = packet[cursor : cursor + extension_len]
        cursor += extension_len

        result["extension_profile"] = profile
        result["extension_length_words"] = length_words
        if profile == ONE_BYTE_PROFILE:
            result["extension_elements"] = parse_one_byte_extensions(extension_data)
        elif (profile & 0xFFF0) == TWO_BYTE_PROFILE_PREFIX:
            result["extension_elements"] = parse_two_byte_extensions(extension_data)
        else:
            result["extension_elements"] = []

    if padding:
        if cursor >= len(packet):
            raise ParseError("RTP_INVALID_PADDING")
        padding_size = packet[-1]
        if padding_size == 0 or padding_size > len(packet) - cursor:
            raise ParseError("RTP_INVALID_PADDING")
        result["padding_size"] = padding_size

    return result


def parse_rtcp_header(packet: bytes) -> dict[str, int | bool]:
    if len(packet) < 4:
        raise ParseError("RTCP_PACKET_TOO_SMALL")

    first = packet[0]
    version = (first >> 6) & 0x03
    if version != 2:
        raise ParseError("RTCP_INVALID_VERSION")

    packet_type = packet[1]
    if packet_type < 192 or packet_type > 223:
        raise ParseError("RTCP_INVALID_PACKET_TYPE")

    length_words_minus_one = int.from_bytes(packet[2:4], "big")
    packet_len = (length_words_minus_one + 1) * 4
    if len(packet) < packet_len:
        raise ParseError("RTCP_INVALID_LENGTH")

    return {
        "version": version,
        "padding": ((first >> 5) & 0x01) != 0,
        "count": first & 0x1F,
        "packet_type": packet_type,
        "length_words_minus_one": length_words_minus_one,
        "packet_len_bytes": packet_len,
    }


def assert_expected_fields(parsed: dict[str, object], expected: dict[str, object], name: str) -> None:
    for key, value in expected.items():
        if key == "extension_element_count":
            elements = parsed.get("extension_elements")
            if not isinstance(elements, list) or len(elements) != value:
                raise AssertionError(f"{name}: extension element count mismatch")
            continue
        if parsed.get(key) != value:
            raise AssertionError(f"{name}: {key} expected {value}, got {parsed.get(key)}")


def check_valid_cases(cases: list[dict[str, object]], parser, label: str) -> None:
    for case in cases:
        name = str(case["name"])
        packet = bytes.fromhex(str(case["hex"]))
        expected = dict(case["expected"])  # shallow copy
        parsed = parser(packet)
        assert_expected_fields(parsed, expected, f"{label}/{name}")


def check_invalid_cases(cases: list[dict[str, object]], parser, label: str) -> None:
    for case in cases:
        name = str(case["name"])
        packet = bytes.fromhex(str(case["hex"]))
        expected_error = str(case["error"])
        try:
            parser(packet)
        except ParseError as exc:
            if str(exc) != expected_error:
                raise AssertionError(f"{label}/{name}: expected {expected_error}, got {exc}") from exc
        else:
            raise AssertionError(f"{label}/{name}: expected error {expected_error}, got success")


def check_extension_boundary_cases(cases: list[dict[str, object]]) -> None:
    for case in cases:
        name = str(case["name"])
        raw = bytes.fromhex(str(case["hex"]))
        profile = str(case["profile"])
        parser = parse_one_byte_extensions if profile == "one-byte" else parse_two_byte_extensions
        if "error" in case:
            expected_error = str(case["error"])
            try:
                parser(raw)
            except ParseError as exc:
                if str(exc) != expected_error:
                    raise AssertionError(f"extension/{name}: expected {expected_error}, got {exc}") from exc
            else:
                raise AssertionError(f"extension/{name}: expected error {expected_error}, got success")
            continue
        expected_elements = int(case["expected_elements"])
        actual_elements = len(parser(raw))
        if actual_elements != expected_elements:
            raise AssertionError(
                f"extension/{name}: expected {expected_elements} elements, got {actual_elements}"
            )


def main() -> int:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    check_valid_cases(fixture["rtp_valid_packets"], parse_rtp_header, "rtp_valid")
    check_invalid_cases(fixture["rtp_invalid_packets"], parse_rtp_header, "rtp_invalid")
    check_extension_boundary_cases(fixture["extension_boundary_cases"])
    check_valid_cases(fixture["rtcp_valid_packets"], parse_rtcp_header, "rtcp_valid")
    check_invalid_cases(fixture["rtcp_invalid_packets"], parse_rtcp_header, "rtcp_invalid")

    print("RTP/RTCP parser fixture tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
