#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sdp"
SUPPORTED_DIRECTIONS = {"sendrecv", "sendonly", "recvonly", "inactive"}
SUPPORTED_OPUS_FMTP = {
    "minptime",
    "maxptime",
    "useinbandfec",
    "stereo",
    "sprop-stereo",
    "usedtx",
}
SUPPORTED_VP8_RTCP_FB = {
    "nack",
    "nack pli",
    "ccm fir",
    "transport-cc",
}
SUPPORTED_VP8_FMTP = {
    "max-fs",
    "max-fr",
}
SUPPORTED_APPLICATION_PROTOCOLS = {"UDP/DTLS/SCTP", "DTLS/SCTP"}


class SdpError(Exception):
    pass


@dataclass(eq=True)
class Fingerprint:
    algorithm: str
    value: str


@dataclass(eq=True)
class Candidate:
    foundation: str
    component: int
    transport: str
    priority: int
    address: str
    port: int
    cand_type: str
    extensions: list[str] = field(default_factory=list)

    def to_line(self) -> str:
        suffix = f" {' '.join(self.extensions)}" if self.extensions else ""
        return (
            f"a=candidate:{self.foundation} {self.component} {self.transport} "
            f"{self.priority} {self.address} {self.port} typ {self.cand_type}{suffix}"
        )


@dataclass(eq=True)
class HeaderExtension:
    ext_id: int
    direction: str | None
    uri: str

    def to_line(self) -> str:
        direction = f"/{self.direction}" if self.direction else ""
        return f"a=extmap:{self.ext_id}{direction} {self.uri}"


@dataclass(eq=True)
class CodecParameters:
    payload_type: str
    encoding_name: str = ""
    clock_rate: int = 0
    channels: int | None = None
    fmtp: list[tuple[str, str]] = field(default_factory=list)
    rtcp_fb: list[str] = field(default_factory=list)

    def to_rtpmap_line(self) -> str:
        if self.channels and self.channels != 1:
            return f"a=rtpmap:{self.payload_type} {self.encoding_name}/{self.clock_rate}/{self.channels}"
        return f"a=rtpmap:{self.payload_type} {self.encoding_name}/{self.clock_rate}"

    def to_fmtp_line(self) -> str | None:
        if not self.fmtp:
            return None
        encoded = ";".join(f"{key}={value}" for key, value in self.fmtp)
        return f"a=fmtp:{self.payload_type} {encoded}"

    def to_rtcp_fb_lines(self) -> list[str]:
        return [f"a=rtcp-fb:{self.payload_type} {value}" for value in self.rtcp_fb]


@dataclass(eq=True)
class MediaSection:
    kind: str
    port: int
    protocol: str
    formats: list[str]
    connection: str | None = None
    mid: str | None = None
    direction: str = "sendrecv"
    ice_ufrag: str | None = None
    ice_pwd: str | None = None
    fingerprint: Fingerprint | None = None
    setup: str | None = None
    rtcp_mux: bool = False
    candidates: list[Candidate] = field(default_factory=list)
    codecs: dict[str, CodecParameters] = field(default_factory=dict)
    header_extensions: list[HeaderExtension] = field(default_factory=list)
    sctp_port: int | None = None
    sctpmap: tuple[int, str, int | None] | None = None
    max_message_size: int | None = None


@dataclass(eq=True)
class SessionDescription:
    version: int = 0
    origin: str = "-"
    session_name: str = "-"
    timing: str = "0 0"
    fingerprint: Fingerprint | None = None
    bundle_mids: list[str] = field(default_factory=list)
    media_sections: list[MediaSection] = field(default_factory=list)


def parse_fingerprint(value: str) -> Fingerprint:
    try:
        algorithm, fingerprint = value.split(" ", 1)
    except ValueError as exc:
        raise SdpError(f"invalid fingerprint line: {value}") from exc
    return Fingerprint(algorithm=algorithm, value=fingerprint)


def parse_candidate(value: str) -> Candidate:
    tokens = value.split()
    if len(tokens) < 8 or tokens[6] != "typ":
        raise SdpError(f"invalid candidate line: {value}")
    return Candidate(
        foundation=tokens[0],
        component=int(tokens[1]),
        transport=tokens[2],
        priority=int(tokens[3]),
        address=tokens[4],
        port=int(tokens[5]),
        cand_type=tokens[7],
        extensions=tokens[8:],
    )


def parse_rtpmap(value: str) -> tuple[str, str, int, int | None]:
    try:
        payload, spec = value.split(" ", 1)
    except ValueError as exc:
        raise SdpError(f"invalid rtpmap line: {value}") from exc
    parts = spec.split("/")
    if len(parts) not in {2, 3}:
        raise SdpError(f"invalid rtpmap payload spec: {value}")
    channels = int(parts[2]) if len(parts) == 3 else None
    return payload, parts[0], int(parts[1]), channels


def parse_fmtp(value: str) -> tuple[str, list[tuple[str, str]]]:
    try:
        payload, params = value.split(" ", 1)
    except ValueError as exc:
        raise SdpError(f"invalid fmtp line: {value}") from exc
    pairs: list[tuple[str, str]] = []
    for token in params.split(";"):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise SdpError(f"invalid fmtp token: {token}")
        key, raw_value = token.split("=", 1)
        pairs.append((key, raw_value))
    return payload, pairs


def parse_rtcp_fb(value: str) -> tuple[str, str]:
    try:
        payload, feedback = value.split(" ", 1)
    except ValueError as exc:
        raise SdpError(f"invalid rtcp-fb line: {value}") from exc
    return payload, feedback


def parse_extmap(value: str) -> HeaderExtension:
    try:
        id_part, uri = value.split(" ", 1)
    except ValueError as exc:
        raise SdpError(f"invalid extmap line: {value}") from exc
    if "/" in id_part:
        raw_id, direction = id_part.split("/", 1)
    else:
        raw_id, direction = id_part, None
    return HeaderExtension(ext_id=int(raw_id), direction=direction, uri=uri)


def ensure_codec(media: MediaSection, payload_type: str) -> CodecParameters:
    codec = media.codecs.get(payload_type)
    if codec is None:
        codec = CodecParameters(payload_type=payload_type)
        media.codecs[payload_type] = codec
    return codec


def parse_attribute(session: SessionDescription, media: MediaSection | None, value: str) -> None:
    if value.startswith("group:BUNDLE "):
        session.bundle_mids = value.removeprefix("group:BUNDLE ").split()
        return
    if value.startswith("fingerprint:"):
        fingerprint = parse_fingerprint(value.removeprefix("fingerprint:"))
        if media is None:
            session.fingerprint = fingerprint
        else:
            media.fingerprint = fingerprint
        return
    if media is None:
        raise SdpError(f"UnsupportedCapability: session attribute {value}")

    if value.startswith("mid:"):
        media.mid = value.removeprefix("mid:")
        return
    if value in SUPPORTED_DIRECTIONS:
        media.direction = value
        return
    if value.startswith("ice-ufrag:"):
        media.ice_ufrag = value.removeprefix("ice-ufrag:")
        return
    if value.startswith("ice-pwd:"):
        media.ice_pwd = value.removeprefix("ice-pwd:")
        return
    if value.startswith("setup:"):
        media.setup = value.removeprefix("setup:")
        return
    if value == "rtcp-mux":
        media.rtcp_mux = True
        return
    if value.startswith("candidate:"):
        media.candidates.append(parse_candidate(value.removeprefix("candidate:")))
        return
    if value.startswith("rtpmap:"):
        payload, name, rate, channels = parse_rtpmap(value.removeprefix("rtpmap:"))
        codec = ensure_codec(media, payload)
        codec.encoding_name = name
        codec.clock_rate = rate
        codec.channels = channels
        return
    if value.startswith("fmtp:"):
        payload, params = parse_fmtp(value.removeprefix("fmtp:"))
        codec = ensure_codec(media, payload)
        codec.fmtp = params
        return
    if value.startswith("rtcp-fb:"):
        payload, feedback = parse_rtcp_fb(value.removeprefix("rtcp-fb:"))
        codec = ensure_codec(media, payload)
        codec.rtcp_fb.append(feedback)
        return
    if value.startswith("extmap:"):
        media.header_extensions.append(parse_extmap(value.removeprefix("extmap:")))
        return
    if value.startswith("sctp-port:"):
        media.sctp_port = int(value.removeprefix("sctp-port:"))
        return
    if value.startswith("sctpmap:"):
        tokens = value.removeprefix("sctpmap:").split()
        if len(tokens) not in {2, 3}:
            raise SdpError(f"invalid sctpmap line: {value}")
        streams = int(tokens[2]) if len(tokens) == 3 else None
        media.sctpmap = (int(tokens[0]), tokens[1], streams)
        return
    if value.startswith("max-message-size:"):
        media.max_message_size = int(value.removeprefix("max-message-size:"))
        return
    raise SdpError(f"UnsupportedCapability: media attribute {value}")


def parse_session_description(text: str) -> SessionDescription:
    session = SessionDescription()
    current_media: MediaSection | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if len(line) < 2 or line[1] != "=":
            raise SdpError(f"invalid line: {line}")
        kind = line[0]
        value = line[2:]
        if kind == "v":
            session.version = int(value)
            continue
        if kind == "o":
            session.origin = value
            continue
        if kind == "s":
            session.session_name = value
            continue
        if kind == "t":
            session.timing = value
            continue
        if kind == "m":
            tokens = value.split()
            if len(tokens) < 4:
                raise SdpError(f"invalid media line: {value}")
            current_media = MediaSection(
                kind=tokens[0],
                port=int(tokens[1]),
                protocol=tokens[2],
                formats=tokens[3:],
            )
            session.media_sections.append(current_media)
            continue
        if kind == "c":
            if current_media is None:
                raise SdpError("session-level c= is not supported by this fixture harness")
            current_media.connection = value
            continue
        if kind == "a":
            parse_attribute(session, current_media, value)
            continue
        raise SdpError(f"UnsupportedCapability: line kind {kind}")
    return session


def write_session_description(session: SessionDescription) -> str:
    lines = [
        f"v={session.version}",
        f"o={session.origin}",
        f"s={session.session_name}",
        f"t={session.timing}",
    ]
    if session.fingerprint is not None:
        lines.append(f"a=fingerprint:{session.fingerprint.algorithm} {session.fingerprint.value}")
    if session.bundle_mids:
        lines.append(f"a=group:BUNDLE {' '.join(session.bundle_mids)}")

    for media in session.media_sections:
        lines.append(f"m={media.kind} {media.port} {media.protocol} {' '.join(media.formats)}")
        if media.connection is not None:
            lines.append(f"c={media.connection}")
        if media.mid is not None:
            lines.append(f"a=mid:{media.mid}")
        lines.append(f"a={media.direction}")
        if media.ice_ufrag is not None:
            lines.append(f"a=ice-ufrag:{media.ice_ufrag}")
        if media.ice_pwd is not None:
            lines.append(f"a=ice-pwd:{media.ice_pwd}")
        if media.fingerprint is not None:
            lines.append(f"a=fingerprint:{media.fingerprint.algorithm} {media.fingerprint.value}")
        if media.setup is not None:
            lines.append(f"a=setup:{media.setup}")
        if media.rtcp_mux:
            lines.append("a=rtcp-mux")
        for candidate in media.candidates:
            lines.append(candidate.to_line())
        for payload_type in media.formats:
            codec = media.codecs.get(payload_type)
            if codec is None or not codec.encoding_name:
                continue
            lines.append(codec.to_rtpmap_line())
            fmtp_line = codec.to_fmtp_line()
            if fmtp_line is not None:
                lines.append(fmtp_line)
            lines.extend(codec.to_rtcp_fb_lines())
        for header_extension in media.header_extensions:
            lines.append(header_extension.to_line())
        if media.sctp_port is not None:
            lines.append(f"a=sctp-port:{media.sctp_port}")
        if media.sctpmap is not None:
            port, app, streams = media.sctpmap
            if streams is None:
                lines.append(f"a=sctpmap:{port} {app}")
            else:
                lines.append(f"a=sctpmap:{port} {app} {streams}")
        if media.max_message_size is not None:
            lines.append(f"a=max-message-size:{media.max_message_size}")
    return "\n".join(lines) + "\n"


def validate_audio(media: MediaSection) -> None:
    for payload_type in media.formats:
        codec = media.codecs.get(payload_type)
        if codec is None:
            raise SdpError("UnsupportedCapability: missing audio codec description")
        if codec.encoding_name.lower() != "opus":
            raise SdpError(f"UnsupportedCapability: audio codec {codec.encoding_name}")
        for key, _value in codec.fmtp:
            if key not in SUPPORTED_OPUS_FMTP:
                raise SdpError(f"UnsupportedCapability: opus fmtp {key}")


def validate_video(media: MediaSection) -> None:
    for payload_type in media.formats:
        codec = media.codecs.get(payload_type)
        if codec is None:
            raise SdpError("UnsupportedCapability: missing video codec description")
        if codec.encoding_name.upper() != "VP8":
            raise SdpError(f"UnsupportedCapability: video codec {codec.encoding_name}")
        for key, _value in codec.fmtp:
            if key not in SUPPORTED_VP8_FMTP:
                raise SdpError(f"UnsupportedCapability: vp8 fmtp {key}")
        for feedback in codec.rtcp_fb:
            if feedback not in SUPPORTED_VP8_RTCP_FB:
                raise SdpError(f"UnsupportedCapability: vp8 rtcp-fb {feedback}")


def validate_application(media: MediaSection) -> None:
    if media.protocol not in SUPPORTED_APPLICATION_PROTOCOLS:
        raise SdpError(f"UnsupportedCapability: application protocol {media.protocol}")
    has_datachannel_format = "webrtc-datachannel" in media.formats
    has_sctpmap = media.sctpmap is not None and media.sctpmap[1] == "webrtc-datachannel"
    if not has_datachannel_format and not has_sctpmap:
        raise SdpError("UnsupportedCapability: missing webrtc-datachannel application format")
    if media.sctp_port is None and media.sctpmap is None:
        raise SdpError("UnsupportedCapability: missing SCTP negotiation line")


def validate_webrtc_session(session: SessionDescription) -> None:
    if session.version != 0:
        raise SdpError(f"UnsupportedCapability: sdp version {session.version}")
    if not session.bundle_mids:
        raise SdpError("UnsupportedCapability: missing bundle group")
    mids = [media.mid for media in session.media_sections]
    if None in mids:
        raise SdpError("UnsupportedCapability: missing media mid")
    if session.bundle_mids != mids:
        raise SdpError("UnsupportedCapability: bundle mids do not match media order")

    for media in session.media_sections:
        if media.direction not in SUPPORTED_DIRECTIONS:
            raise SdpError(f"UnsupportedCapability: direction {media.direction}")
        if media.fingerprint is None and session.fingerprint is None:
            raise SdpError("MissingFingerprint")
        if not media.ice_ufrag:
            raise SdpError("MissingIceUfrag")
        if not media.ice_pwd:
            raise SdpError("MissingIcePwd")
        if len(set(media.formats)) != len(media.formats):
            raise SdpError("UnsupportedCapability: duplicate payload type")
        if media.kind != "application" and not media.rtcp_mux:
            raise SdpError("MissingRtcpMux")
        if media.kind == "audio":
            validate_audio(media)
        elif media.kind == "video":
            validate_video(media)
        elif media.kind == "application":
            validate_application(media)
        else:
            raise SdpError(f"UnsupportedCapability: media kind {media.kind}")


def run_roundtrip_test(name: str) -> None:
    text = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    parsed = parse_session_description(text)
    validate_webrtc_session(parsed)
    written = write_session_description(parsed)
    if written != text:
        raise AssertionError(f"{name}: canonical write mismatch")
    reparsed = parse_session_description(written)
    validate_webrtc_session(reparsed)
    rewritten = write_session_description(reparsed)
    if rewritten != written:
        raise AssertionError(f"{name}: second write changed the canonical form")
    if reparsed != parsed:
        raise AssertionError(f"{name}: parse/write/parse changed the semantic model")


def remove_line(text: str, exact_line: str) -> str:
    lines = text.splitlines()
    try:
        lines.remove(exact_line)
    except ValueError as exc:
        raise AssertionError(f"missing line for mutation: {exact_line}") from exc
    return "\n".join(lines) + "\n"


def replace_line(text: str, source: str, target: str) -> str:
    if source not in text:
        raise AssertionError(f"missing line for replacement: {source}")
    return text.replace(source, target, 1)


def expect_validation_error(name: str, text: str, expected: str) -> None:
    try:
        validate_webrtc_session(parse_session_description(text))
    except SdpError as exc:
        if expected not in str(exc):
            raise AssertionError(f"{name}: expected {expected}, got {exc}") from exc
        return
    raise AssertionError(f"{name}: expected validation failure {expected}")


def expect_parse_error(name: str, text: str, expected: str) -> None:
    try:
        parse_session_description(text)
    except SdpError as exc:
        if expected not in str(exc):
            raise AssertionError(f"{name}: expected {expected}, got {exc}") from exc
        return
    raise AssertionError(f"{name}: expected parse failure {expected}")


def run_parser_unit_tests() -> None:
    expect_parse_error(
        "invalid line scanner record",
        "v=0\nbroken-line\n",
        "invalid line",
    )
    expect_parse_error(
        "invalid candidate line",
        "v=0\no=- 1 1 IN IP4 127.0.0.1\ns=-\nt=0 0\nm=audio 9 UDP/TLS/RTP/SAVPF 111\na=mid:audio\na=sendrecv\na=ice-ufrag:u\na=ice-pwd:p\na=rtcp-mux\na=candidate:1 1 udp 2122260223 192.0.2.10 54400 host\n",
        "invalid candidate line",
    )
    expect_parse_error(
        "invalid extmap line",
        "v=0\no=- 1 1 IN IP4 127.0.0.1\ns=-\nt=0 0\nm=audio 9 UDP/TLS/RTP/SAVPF 111\na=mid:audio\na=sendrecv\na=ice-ufrag:u\na=ice-pwd:p\na=rtcp-mux\na=extmap:1\n",
        "invalid extmap line",
    )


def run_error_tests() -> None:
    chrome_text = (FIXTURE_DIR / "chrome_offer.sdp").read_text(encoding="utf-8")
    firefox_text = (FIXTURE_DIR / "firefox_offer.sdp").read_text(encoding="utf-8")

    expect_validation_error(
        "missing fingerprint",
        remove_line(
            firefox_text,
            "a=fingerprint:sha-256 60:88:79:AE:52:3B:2C:34:91:42:9E:77:57:14:3D:E8:B3:61:F0:47:1E:76:7D:6B:41:5A:CC:11:3D:27:92:FE",
        ),
        "MissingFingerprint",
    )
    expect_validation_error(
        "missing ice-pwd",
        remove_line(firefox_text, "a=ice-pwd:firefoxVideoPwd123456"),
        "MissingIcePwd",
    )
    expect_validation_error(
        "missing rtcp-mux",
        remove_line(chrome_text, "a=rtcp-mux"),
        "MissingRtcpMux",
    )
    expect_validation_error(
        "unsupported capability",
        replace_line(chrome_text, "a=rtpmap:100 VP8/90000", "a=rtpmap:100 H264/90000"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "missing ice-ufrag",
        remove_line(firefox_text, "a=ice-ufrag:firefoxVideo"),
        "MissingIceUfrag",
    )
    expect_validation_error(
        "unsupported direction",
        replace_line(firefox_text, "a=recvonly", "a=sendrecvonly"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "duplicate payload type",
        replace_line(chrome_text, "m=video 9 UDP/TLS/RTP/SAVPF 100", "m=video 9 UDP/TLS/RTP/SAVPF 100 100"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "unsupported vp8 fmtp",
        replace_line(chrome_text, "a=fmtp:100 max-fs=12288;max-fr=60", "a=fmtp:100 x-google-start-bitrate=800"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "missing datachannel negotiation",
        remove_line(firefox_text, "a=sctpmap:5000 webrtc-datachannel 256"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "missing mid",
        remove_line(chrome_text, "a=mid:audio"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "bundle mids mismatch",
        replace_line(
            chrome_text,
            "a=group:BUNDLE audio video data",
            "a=group:BUNDLE video audio data",
        ),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "duplicate payload type",
        replace_line(chrome_text, "m=video 9 UDP/TLS/RTP/SAVPF 100", "m=video 9 UDP/TLS/RTP/SAVPF 100 100"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "unsupported opus fmtp",
        replace_line(
            chrome_text,
            "a=fmtp:111 minptime=10;maxptime=60;useinbandfec=1;stereo=1;sprop-stereo=1;usedtx=1",
            "a=fmtp:111 minptime=10;foo=1",
        ),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "unsupported vp8 rtcp-fb",
        replace_line(chrome_text, "a=rtcp-fb:100 transport-cc", "a=rtcp-fb:100 goog-remb"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "unsupported application protocol",
        replace_line(chrome_text, "m=application 9 UDP/DTLS/SCTP webrtc-datachannel", "m=application 9 UDP/TLS/RTP/SAVPF webrtc-datachannel"),
        "UnsupportedCapability",
    )
    expect_validation_error(
        "missing datachannel negotiation line",
        remove_line(chrome_text, "a=sctp-port:5000"),
        "UnsupportedCapability",
    )


def main() -> None:
    run_parser_unit_tests()
    run_roundtrip_test("chrome_offer.sdp")
    run_roundtrip_test("firefox_offer.sdp")
    run_error_tests()


if __name__ == "__main__":
    main()
