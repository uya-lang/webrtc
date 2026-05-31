#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
from pathlib import Path
import struct
import zlib


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "stun"
FUZZ_DIR = FIXTURE_DIR / "fuzz"
HEADER_BYTES = 20
ATTRIBUTE_HEADER_BYTES = 4
MAGIC_COOKIE = 0x2112A442
MAGIC_COOKIE_BYTES = MAGIC_COOKIE.to_bytes(4, "big")
BINDING_METHOD = 0x0001
CLASS_REQUEST = 0
CLASS_INDICATION = 1
CLASS_SUCCESS_RESPONSE = 2
CLASS_ERROR_RESPONSE = 3
ATTR_USERNAME = 0x0006
ATTR_MESSAGE_INTEGRITY = 0x0008
ATTR_ERROR_CODE = 0x0009
ATTR_MESSAGE_INTEGRITY_SHA256 = 0x001C
ATTR_XOR_MAPPED_ADDRESS = 0x0020
ATTR_PRIORITY = 0x0024
ATTR_USE_CANDIDATE = 0x0025
ATTR_SOFTWARE = 0x8022
ATTR_FINGERPRINT = 0x8028
ATTR_ICE_CONTROLLED = 0x8029
ATTR_ICE_CONTROLLING = 0x802A
RFC5769_PASSWORD = b"VOkJxbRl1RmTxUk/WvJxBt"


class StunError(Exception):
    pass


@dataclass(frozen=True)
class StunHeader:
    raw_type: int
    method: int
    message_class: int
    message_length: int
    transaction_id: bytes


@dataclass(frozen=True)
class StunAttribute:
    attr_type: int
    value: bytes
    offset: int


def load_hex_fixture(path: Path) -> bytes:
    compact = "".join(path.read_text(encoding="utf-8").split())
    return bytes.fromhex(compact)


def encode_message_type(method: int, message_class: int) -> int:
    return (
        (method & 0x000F)
        | ((method & 0x0070) << 1)
        | ((method & 0x0F80) << 2)
        | ((message_class & 0x01) << 4)
        | ((message_class & 0x02) << 7)
    )


def decode_message_type(raw_type: int) -> tuple[int, int]:
    method = (raw_type & 0x000F) | ((raw_type & 0x00E0) >> 1) | ((raw_type & 0x3E00) >> 2)
    message_class = ((raw_type >> 4) & 0x01) | ((raw_type >> 7) & 0x02)
    return method, message_class


def parse_header(packet: bytes) -> StunHeader:
    if len(packet) < HEADER_BYTES:
        raise StunError("truncated header")
    raw_type, message_length, magic_cookie = struct.unpack("!HHI", packet[:8])
    if raw_type & 0xC000:
        raise StunError("invalid message type high bits")
    if magic_cookie != MAGIC_COOKIE:
        raise StunError("invalid magic cookie")
    if message_length % 4 != 0:
        raise StunError("message length is not 32-bit aligned")
    if len(packet) != HEADER_BYTES + message_length:
        raise StunError("message length does not match packet size")
    method, message_class = decode_message_type(raw_type)
    return StunHeader(
        raw_type=raw_type,
        method=method,
        message_class=message_class,
        message_length=message_length,
        transaction_id=packet[8:20],
    )


def iter_attributes(packet: bytes, header: StunHeader) -> list[StunAttribute]:
    payload = packet[HEADER_BYTES:]
    out: list[StunAttribute] = []
    cursor = 0
    while cursor < len(payload):
        if len(payload) - cursor < ATTRIBUTE_HEADER_BYTES:
            raise StunError("truncated attribute header")
        attr_type, attr_len = struct.unpack("!HH", payload[cursor : cursor + ATTRIBUTE_HEADER_BYTES])
        value_start = cursor + ATTRIBUTE_HEADER_BYTES
        value_end = value_start + attr_len
        if value_end > len(payload):
            raise StunError("attribute length exceeds message payload")
        padded_end = value_end + ((4 - (attr_len % 4)) % 4)
        if padded_end > len(payload):
            raise StunError("attribute padding exceeds message payload")
        out.append(
            StunAttribute(
                attr_type=attr_type,
                value=payload[value_start:value_end],
                offset=HEADER_BYTES + cursor,
            )
        )
        cursor = padded_end
    return out


def is_comprehension_required(attr_type: int) -> bool:
    return (attr_type & 0x8000) == 0


def parse_username(attr: StunAttribute) -> str:
    if not attr.value:
        raise StunError("empty username")
    return attr.value.decode("utf-8")


def parse_priority(attr: StunAttribute) -> int:
    if len(attr.value) != 4:
        raise StunError("invalid priority length")
    return struct.unpack("!I", attr.value)[0]


def parse_use_candidate(attr: StunAttribute) -> bool:
    if attr.value:
        raise StunError("USE-CANDIDATE must be empty")
    return True


def parse_ice_role_tiebreaker(attr: StunAttribute) -> int:
    if len(attr.value) != 8:
        raise StunError("invalid ICE role attribute length")
    return struct.unpack("!Q", attr.value)[0]


def parse_xor_mapped_address(attr: StunAttribute, transaction_id: bytes) -> tuple[str, int]:
    if len(attr.value) < 4:
        raise StunError("truncated XOR-MAPPED-ADDRESS")
    if attr.value[0] != 0:
        raise StunError("invalid XOR-MAPPED-ADDRESS reserved byte")

    family = attr.value[1]
    x_port = struct.unpack("!H", attr.value[2:4])[0]
    port = x_port ^ (MAGIC_COOKIE >> 16)

    if family == 0x01:
        if len(attr.value) != 8:
            raise StunError("invalid IPv4 XOR-MAPPED-ADDRESS length")
        raw_ip = bytes(a ^ b for a, b in zip(attr.value[4:8], MAGIC_COOKIE_BYTES))
        return str(ipaddress.IPv4Address(raw_ip)), port
    if family == 0x02:
        if len(attr.value) != 20:
            raise StunError("invalid IPv6 XOR-MAPPED-ADDRESS length")
        mask = MAGIC_COOKIE_BYTES + transaction_id
        raw_ip = bytes(a ^ b for a, b in zip(attr.value[4:20], mask))
        return str(ipaddress.IPv6Address(raw_ip)), port
    raise StunError(f"unsupported XOR-MAPPED-ADDRESS family {family}")


def parse_error_code(attr: StunAttribute) -> tuple[int, str]:
    if len(attr.value) < 4:
        raise StunError("truncated ERROR-CODE")
    if attr.value[0] != 0 or attr.value[1] != 0 or attr.value[2] & 0xF8:
        raise StunError("invalid ERROR-CODE reserved bits")
    code_class = attr.value[2] & 0x07
    code_number = attr.value[3]
    code = code_class * 100 + code_number
    if code_class < 3 or code_class > 6 or code_number > 99:
        raise StunError("invalid ERROR-CODE value")
    return code, attr.value[4:].decode("utf-8")


def parse_binding_request(packet: bytes) -> tuple[StunHeader, dict[str, object]]:
    header = parse_header(packet)
    if header.method != BINDING_METHOD or header.message_class != CLASS_REQUEST:
        raise StunError("not a Binding request")

    seen: set[int] = set()
    out: dict[str, object] = {
        "username": None,
        "priority": None,
        "use_candidate": False,
        "ice_controlled": None,
        "ice_controlling": None,
        "software": None,
    }
    allowed = {
        ATTR_USERNAME,
        ATTR_PRIORITY,
        ATTR_USE_CANDIDATE,
        ATTR_ICE_CONTROLLED,
        ATTR_ICE_CONTROLLING,
        ATTR_MESSAGE_INTEGRITY,
        ATTR_MESSAGE_INTEGRITY_SHA256,
        ATTR_FINGERPRINT,
        ATTR_SOFTWARE,
    }
    unique = {
        ATTR_USERNAME,
        ATTR_PRIORITY,
        ATTR_USE_CANDIDATE,
        ATTR_ICE_CONTROLLED,
        ATTR_ICE_CONTROLLING,
        ATTR_MESSAGE_INTEGRITY,
        ATTR_MESSAGE_INTEGRITY_SHA256,
        ATTR_FINGERPRINT,
    }

    for attr in iter_attributes(packet, header):
        if is_comprehension_required(attr.attr_type) and attr.attr_type not in allowed:
            raise StunError(f"unknown comprehension-required attribute 0x{attr.attr_type:04x}")
        if attr.attr_type in unique:
            if attr.attr_type in seen:
                raise StunError(f"duplicate attribute 0x{attr.attr_type:04x}")
            seen.add(attr.attr_type)
        if attr.attr_type == ATTR_USERNAME:
            out["username"] = parse_username(attr)
        elif attr.attr_type == ATTR_PRIORITY:
            out["priority"] = parse_priority(attr)
        elif attr.attr_type == ATTR_USE_CANDIDATE:
            out["use_candidate"] = parse_use_candidate(attr)
        elif attr.attr_type == ATTR_ICE_CONTROLLED:
            if out["ice_controlling"] is not None:
                raise StunError("ICE-CONTROLLED and ICE-CONTROLLING cannot both appear")
            out["ice_controlled"] = parse_ice_role_tiebreaker(attr)
        elif attr.attr_type == ATTR_ICE_CONTROLLING:
            if out["ice_controlled"] is not None:
                raise StunError("ICE-CONTROLLED and ICE-CONTROLLING cannot both appear")
            out["ice_controlling"] = parse_ice_role_tiebreaker(attr)
        elif attr.attr_type == ATTR_SOFTWARE:
            out["software"] = attr.value.decode("utf-8")
    return header, out


def parse_binding_success_response(packet: bytes) -> tuple[StunHeader, dict[str, object]]:
    header = parse_header(packet)
    if header.method != BINDING_METHOD or header.message_class != CLASS_SUCCESS_RESPONSE:
        raise StunError("not a Binding success response")
    out: dict[str, object] = {"software": None, "xor_mapped_address": None}
    for attr in iter_attributes(packet, header):
        if attr.attr_type == ATTR_SOFTWARE:
            out["software"] = attr.value.decode("utf-8")
        elif attr.attr_type == ATTR_XOR_MAPPED_ADDRESS:
            out["xor_mapped_address"] = parse_xor_mapped_address(attr, header.transaction_id)
    return header, out


def parse_binding_error_response(packet: bytes) -> tuple[StunHeader, dict[str, object]]:
    header = parse_header(packet)
    if header.method != BINDING_METHOD or header.message_class != CLASS_ERROR_RESPONSE:
        raise StunError("not a Binding error response")
    out: dict[str, object] = {"error_code": None}
    for attr in iter_attributes(packet, header):
        if attr.attr_type == ATTR_ERROR_CODE:
            out["error_code"] = parse_error_code(attr)
    return header, out


def find_first_attribute(packet: bytes, attr_type: int) -> StunAttribute:
    header = parse_header(packet)
    for attr in iter_attributes(packet, header):
        if attr.attr_type == attr_type:
            return attr
    raise StunError(f"missing attribute 0x{attr_type:04x}")


def verify_message_integrity(packet: bytes, key: bytes, attr_type: int = ATTR_MESSAGE_INTEGRITY) -> bool:
    digestmod = hashlib.sha1 if attr_type == ATTR_MESSAGE_INTEGRITY else hashlib.sha256
    attr = find_first_attribute(packet, attr_type)
    attr_end = attr.offset + ATTRIBUTE_HEADER_BYTES + len(attr.value)
    signed = bytearray(packet[: attr.offset])
    signed[2:4] = struct.pack("!H", attr_end - HEADER_BYTES)
    expected = hmac.new(key, signed, digestmod=digestmod).digest()
    return hmac.compare_digest(expected, attr.value)


def verify_fingerprint(packet: bytes) -> bool:
    attr = find_first_attribute(packet, ATTR_FINGERPRINT)
    if len(attr.value) != 4:
        raise StunError("invalid FINGERPRINT length")
    actual = struct.unpack("!I", attr.value)[0]
    expected = (zlib.crc32(packet[: attr.offset]) & 0xFFFFFFFF) ^ 0x5354554E
    return expected == actual


def build_attribute(attr_type: int, value: bytes) -> bytes:
    padding = b"\x00" * ((4 - (len(value) % 4)) % 4)
    return struct.pack("!HH", attr_type, len(value)) + value + padding


def append_fingerprint(packet: bytes) -> bytes:
    packet_with_length = bytearray(packet)
    final_body_len = len(packet_with_length) - HEADER_BYTES + ATTRIBUTE_HEADER_BYTES + 4
    packet_with_length[2:4] = struct.pack("!H", final_body_len)
    fingerprint = (zlib.crc32(packet_with_length) & 0xFFFFFFFF) ^ 0x5354554E
    return bytes(packet_with_length) + build_attribute(ATTR_FINGERPRINT, struct.pack("!I", fingerprint))


def append_message_integrity(packet: bytes, key: bytes, attr_type: int = ATTR_MESSAGE_INTEGRITY) -> bytes:
    digestmod = hashlib.sha1 if attr_type == ATTR_MESSAGE_INTEGRITY else hashlib.sha256
    packet_with_length = bytearray(packet)
    final_body_len = len(packet_with_length) - HEADER_BYTES + ATTRIBUTE_HEADER_BYTES + digestmod().digest_size
    packet_with_length[2:4] = struct.pack("!H", final_body_len)
    digest = hmac.new(key, packet_with_length, digestmod=digestmod).digest()
    return bytes(packet_with_length) + build_attribute(attr_type, digest)


def encode_xor_mapped_address(address: str, port: int, transaction_id: bytes) -> bytes:
    ip = ipaddress.ip_address(address)
    x_port = struct.pack("!H", port ^ (MAGIC_COOKIE >> 16))
    if ip.version == 4:
        raw = bytes(a ^ b for a, b in zip(ip.packed, MAGIC_COOKIE_BYTES))
        return b"\x00\x01" + x_port + raw
    mask = MAGIC_COOKIE_BYTES + transaction_id
    raw = bytes(a ^ b for a, b in zip(ip.packed, mask))
    return b"\x00\x02" + x_port + raw


def encode_error_code(code: int, reason: str) -> bytes:
    if code < 300 or code > 699:
        raise StunError("ERROR-CODE out of range")
    return b"\x00\x00" + bytes([code // 100, code % 100]) + reason.encode("utf-8")


def build_message(
    message_class: int,
    transaction_id: bytes,
    attrs: list[tuple[int, bytes]],
    *,
    integrity_key: bytes | None = None,
    include_fingerprint: bool = False,
) -> bytes:
    if len(transaction_id) != 12:
        raise StunError("transaction id must be 12 bytes")
    body = b"".join(build_attribute(attr_type, value) for attr_type, value in attrs)
    packet = (
        struct.pack("!HHI", encode_message_type(BINDING_METHOD, message_class), len(body), MAGIC_COOKIE)
        + transaction_id
        + body
    )
    if integrity_key is not None:
        packet = append_message_integrity(packet, integrity_key)
    if include_fingerprint:
        packet = append_fingerprint(packet)
    return packet


def build_binding_request(
    transaction_id: bytes,
    username: str,
    priority: int,
    *,
    use_candidate: bool = False,
    ice_controlled: int | None = None,
    ice_controlling: int | None = None,
    software: str | None = None,
    integrity_key: bytes | None = None,
    include_fingerprint: bool = False,
) -> bytes:
    attrs: list[tuple[int, bytes]] = []
    if software is not None:
        attrs.append((ATTR_SOFTWARE, software.encode("utf-8")))
    attrs.append((ATTR_USERNAME, username.encode("utf-8")))
    attrs.append((ATTR_PRIORITY, struct.pack("!I", priority)))
    if use_candidate:
        attrs.append((ATTR_USE_CANDIDATE, b""))
    if ice_controlled is not None and ice_controlling is not None:
        raise StunError("cannot set both ICE roles")
    if ice_controlled is not None:
        attrs.append((ATTR_ICE_CONTROLLED, struct.pack("!Q", ice_controlled)))
    if ice_controlling is not None:
        attrs.append((ATTR_ICE_CONTROLLING, struct.pack("!Q", ice_controlling)))
    return build_message(
        CLASS_REQUEST,
        transaction_id,
        attrs,
        integrity_key=integrity_key,
        include_fingerprint=include_fingerprint,
    )


def build_binding_success_response(
    transaction_id: bytes,
    address: str,
    port: int,
    *,
    software: str | None = None,
    integrity_key: bytes | None = None,
    include_fingerprint: bool = False,
) -> bytes:
    attrs: list[tuple[int, bytes]] = []
    if software is not None:
        attrs.append((ATTR_SOFTWARE, software.encode("utf-8")))
    attrs.append((ATTR_XOR_MAPPED_ADDRESS, encode_xor_mapped_address(address, port, transaction_id)))
    return build_message(
        CLASS_SUCCESS_RESPONSE,
        transaction_id,
        attrs,
        integrity_key=integrity_key,
        include_fingerprint=include_fingerprint,
    )


def build_binding_error_response(
    transaction_id: bytes,
    code: int,
    reason: str,
    *,
    software: str | None = None,
    integrity_key: bytes | None = None,
    include_fingerprint: bool = False,
) -> bytes:
    attrs: list[tuple[int, bytes]] = []
    if software is not None:
        attrs.append((ATTR_SOFTWARE, software.encode("utf-8")))
    attrs.append((ATTR_ERROR_CODE, encode_error_code(code, reason)))
    return build_message(
        CLASS_ERROR_RESPONSE,
        transaction_id,
        attrs,
        integrity_key=integrity_key,
        include_fingerprint=include_fingerprint,
    )


def assert_raises(label: str, fn) -> None:
    try:
        fn()
    except StunError:
        return
    raise AssertionError(f"{label} did not raise StunError")


def run_rfc_vector_tests() -> None:
    request = load_hex_fixture(FIXTURE_DIR / "rfc5769_binding_request.hex")
    header, parsed_request = parse_binding_request(request)
    assert header.method == BINDING_METHOD
    assert header.message_class == CLASS_REQUEST
    assert parsed_request["software"] == "STUN test client"
    assert parsed_request["username"] == "evtj:h6vY"
    assert parsed_request["priority"] == 0x6E0001FF
    assert parsed_request["ice_controlled"] == 0x932FF9B151263B36
    assert verify_message_integrity(request, RFC5769_PASSWORD)
    assert verify_fingerprint(request)

    ipv4_response = load_hex_fixture(FIXTURE_DIR / "rfc5769_binding_response_ipv4.hex")
    _, parsed_ipv4 = parse_binding_success_response(ipv4_response)
    assert parsed_ipv4["software"] == "test vector"
    assert parsed_ipv4["xor_mapped_address"] == ("192.0.2.1", 32853)
    assert verify_message_integrity(ipv4_response, RFC5769_PASSWORD)
    assert verify_fingerprint(ipv4_response)

    ipv6_response = load_hex_fixture(FIXTURE_DIR / "rfc5769_binding_response_ipv6.hex")
    _, parsed_ipv6 = parse_binding_success_response(ipv6_response)
    assert parsed_ipv6["software"] == "test vector"
    assert parsed_ipv6["xor_mapped_address"] == ("2001:db8:1234:5678:11:2233:4455:6677", 32853)
    assert verify_message_integrity(ipv6_response, RFC5769_PASSWORD)
    assert verify_fingerprint(ipv6_response)


def run_negative_tests() -> None:
    assert_raises(
        "truncated header",
        lambda: parse_header(load_hex_fixture(FUZZ_DIR / "truncated_header.hex")),
    )
    assert_raises(
        "bad length",
        lambda: parse_header(load_hex_fixture(FUZZ_DIR / "bad_length.hex")),
    )
    assert_raises(
        "bad padding",
        lambda: parse_binding_request(load_hex_fixture(FUZZ_DIR / "bad_padding.hex")),
    )
    assert_raises(
        "duplicate username",
        lambda: parse_binding_request(load_hex_fixture(FUZZ_DIR / "duplicate_username.hex")),
    )
    assert_raises(
        "unknown required attr",
        lambda: parse_binding_request(load_hex_fixture(FUZZ_DIR / "unknown_required.hex")),
    )


def run_builder_tests() -> None:
    transaction_id = bytes(range(1, 13))
    integrity_key = b"uya-secret"

    request = build_binding_request(
        transaction_id,
        "demo",
        0x6E0001FF,
        use_candidate=True,
        ice_controlling=0x1122334455667788,
        software="uya-test",
        integrity_key=integrity_key,
        include_fingerprint=True,
    )
    header, parsed_request = parse_binding_request(request)
    assert header.raw_type == 0x0001
    assert parsed_request["software"] == "uya-test"
    assert parsed_request["username"] == "demo"
    assert parsed_request["priority"] == 0x6E0001FF
    assert parsed_request["use_candidate"] is True
    assert parsed_request["ice_controlling"] == 0x1122334455667788
    assert verify_message_integrity(request, integrity_key)
    assert verify_fingerprint(request)

    success = build_binding_success_response(
        transaction_id,
        "192.0.2.33",
        3478,
        software="uya-test",
        integrity_key=integrity_key,
        include_fingerprint=True,
    )
    success_header, parsed_success = parse_binding_success_response(success)
    assert success_header.raw_type == 0x0101
    assert parsed_success["software"] == "uya-test"
    assert parsed_success["xor_mapped_address"] == ("192.0.2.33", 3478)
    assert verify_message_integrity(success, integrity_key)
    assert verify_fingerprint(success)

    error = build_binding_error_response(
        transaction_id,
        487,
        "Role Conflict",
        software="uya-test",
        integrity_key=integrity_key,
        include_fingerprint=True,
    )
    error_header, parsed_error = parse_binding_error_response(error)
    assert error_header.raw_type == 0x0111
    assert parsed_error["error_code"] == (487, "Role Conflict")
    assert verify_message_integrity(error, integrity_key)
    assert verify_fingerprint(error)

    corrupted_integrity = bytearray(request)
    corrupted_integrity[24] ^= 0x01
    assert not verify_message_integrity(bytes(corrupted_integrity), integrity_key)

    corrupted_request = request[:-1] + bytes([request[-1] ^ 0x01])
    assert not verify_fingerprint(corrupted_request)


def run_fuzz_corpus_smoke() -> None:
    expected = {
        "truncated_header.hex",
        "bad_length.hex",
        "bad_padding.hex",
        "duplicate_username.hex",
        "unknown_required.hex",
    }
    actual = {path.name for path in FUZZ_DIR.glob("*.hex")}
    assert actual == expected
    for path in sorted(FUZZ_DIR.glob("*.hex")):
        packet = load_hex_fixture(path)
        try:
            header = parse_header(packet)
            if header.message_class == CLASS_REQUEST and header.method == BINDING_METHOD:
                try:
                    parse_binding_request(packet)
                except StunError:
                    pass
        except StunError:
            pass


def main() -> None:
    run_rfc_vector_tests()
    run_negative_tests()
    run_builder_tests()
    run_fuzz_corpus_smoke()


if __name__ == "__main__":
    main()
