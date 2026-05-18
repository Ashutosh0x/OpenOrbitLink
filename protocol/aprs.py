from __future__ import annotations

"""
APRS and AX.25 helpers based on the APRS Protocol Reference 1.0.1.

The goal is not to turn OpenOrbitLink into a full APRS client; it is to make
received APRS packets structured enough for routing, display, gateway policy,
and testable interoperability with ISS/terrestrial APRS traffic.

ISS APRS constraint: the ISS digipeater relays ordinary AX.25 UI APRS frames
only. It is not a general store-and-forward chat service, and amateur-band APRS
traffic must be unencrypted, non-commercial, and transmitted only by licensed
operators using their callsign.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .bpv7 import crc16_x25


AX25_FLAG = 0x7E
AX25_UI_CONTROL = 0x03
AX25_NO_LAYER3_PID = 0xF0


class APRSParseError(ValueError):
    """Raised when APRS or AX.25 bytes are malformed."""


@dataclass(frozen=True)
class AX25Address:
    callsign: str
    ssid: int = 0
    repeated: bool = False

    @property
    def display(self) -> str:
        return self.callsign if self.ssid == 0 else f"{self.callsign}-{self.ssid}"


@dataclass(frozen=True)
class AX25Frame:
    destination: AX25Address
    source: AX25Address
    digipeaters: list[AX25Address]
    control: int
    pid: int
    information: bytes
    fcs_valid: Optional[bool] = None


@dataclass(frozen=True)
class APRSCoordinate:
    raw: str
    value: float
    ambiguity_digits: int = 0


@dataclass(frozen=True)
class APRSPosition:
    latitude: APRSCoordinate
    longitude: APRSCoordinate
    symbol_table: str
    symbol_code: str
    compressed: bool = False
    extension: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class APRSPacket:
    raw: str
    data_type: str
    kind: str
    fields: dict[str, Any]


def ax25_fcs(frame_without_flags_or_fcs: bytes) -> int:
    """Return AX.25 FCS as the reflected CRC-16/X-25 value."""
    return crc16_x25(frame_without_flags_or_fcs)


def encode_ax25_address(address: AX25Address, last: bool = False) -> bytes:
    if not (0 <= address.ssid <= 15):
        raise ValueError("AX.25 SSID must be in the range 0..15")
    call = address.callsign.upper().ljust(6)[:6]
    encoded = bytearray((ord(char) << 1) & 0xFE for char in call)
    ssid = 0x60 | ((address.ssid & 0x0F) << 1)
    if address.repeated:
        ssid |= 0x80
    if last:
        ssid |= 0x01
    encoded.append(ssid)
    return bytes(encoded)


def decode_ax25_address(data: bytes) -> tuple[AX25Address, bool]:
    if len(data) != 7:
        raise APRSParseError("AX.25 address fields are exactly 7 bytes")
    callsign = "".join(chr(byte >> 1) for byte in data[:6]).strip()
    ssid_byte = data[6]
    ssid = (ssid_byte >> 1) & 0x0F
    repeated = bool(ssid_byte & 0x80)
    last = bool(ssid_byte & 0x01)
    if not callsign:
        raise APRSParseError("AX.25 callsign is empty")
    return AX25Address(callsign=callsign, ssid=ssid, repeated=repeated), last


def build_ax25_ui_frame(
    source: str,
    destination: str,
    information: bytes,
    digipeaters: Optional[list[str]] = None,
    include_flags: bool = True,
    include_fcs: bool = True,
) -> bytes:
    """Build a standards-shaped AX.25 UI frame for APRS information bytes."""
    src = parse_callsign(source)
    dest = parse_callsign(destination)
    digis = [parse_callsign(item) for item in (digipeaters or [])]
    body = bytearray()
    body.extend(encode_ax25_address(dest, last=False))
    body.extend(encode_ax25_address(src, last=not digis))
    for index, digi in enumerate(digis):
        body.extend(encode_ax25_address(digi, last=index == len(digis) - 1))
    body.append(AX25_UI_CONTROL)
    body.append(AX25_NO_LAYER3_PID)
    body.extend(information)
    if include_fcs:
        body.extend(ax25_fcs(bytes(body)).to_bytes(2, "little"))
    if include_flags:
        return bytes([AX25_FLAG]) + bytes(body) + bytes([AX25_FLAG])
    return bytes(body)


def decode_ax25_ui_frame(raw: bytes, validate_fcs: bool = True) -> AX25Frame:
    data = raw
    if len(data) >= 2 and data[0] == AX25_FLAG and data[-1] == AX25_FLAG:
        data = data[1:-1]
    if len(data) < 16:
        raise APRSParseError("AX.25 frame too short")

    fcs_valid: Optional[bool] = None
    if len(data) >= 18:
        body, supplied_fcs = data[:-2], data[-2:]
        expected = ax25_fcs(body).to_bytes(2, "little")
        fcs_valid = supplied_fcs == expected
        if validate_fcs and not fcs_valid:
            raise APRSParseError("AX.25 FCS check failed")
        if fcs_valid or validate_fcs:
            data = body

    offset = 0
    destination, last = decode_ax25_address(data[offset:offset + 7])
    offset += 7
    source, last = decode_ax25_address(data[offset:offset + 7])
    offset += 7
    digipeaters: list[AX25Address] = []
    while not last:
        if offset + 7 > len(data):
            raise APRSParseError("AX.25 digipeater address truncated")
        digi, last = decode_ax25_address(data[offset:offset + 7])
        digipeaters.append(digi)
        offset += 7
    if offset + 2 > len(data):
        raise APRSParseError("AX.25 control/PID fields missing")
    control = data[offset]
    pid = data[offset + 1]
    if control != AX25_UI_CONTROL:
        raise APRSParseError("APRS uses AX.25 UI frames")
    if pid != AX25_NO_LAYER3_PID:
        raise APRSParseError("APRS UI frames must use no-layer-3 PID")
    return AX25Frame(
        destination=destination,
        source=source,
        digipeaters=digipeaters,
        control=control,
        pid=pid,
        information=data[offset + 2:],
        fcs_valid=fcs_valid,
    )


def parse_callsign(value: str) -> AX25Address:
    match = re.fullmatch(r"([A-Za-z0-9]{1,6})(?:-(\d{1,2}))?", value.strip())
    if not match:
        raise ValueError(f"invalid AX.25 callsign: {value!r}")
    ssid = int(match.group(2) or 0)
    return AX25Address(match.group(1).upper(), ssid)


def parse_aprs_info(info: bytes | str) -> APRSPacket:
    raw = info.decode("ascii", errors="replace") if isinstance(info, bytes) else info
    if not raw:
        raise APRSParseError("empty APRS information field")

    data_type = raw[0]
    if data_type in ("!", "="):
        return _parse_position_packet(raw, data_type, pos_start=1, timestamp=None)
    if data_type in ("/", "@"):
        if len(raw) < 8:
            raise APRSParseError("timestamped position packet is too short")
        return _parse_position_packet(raw, data_type, pos_start=8, timestamp=raw[1:8])
    if data_type == ":":
        return _parse_message(raw)
    if data_type == ";":
        return _parse_object(raw)
    if data_type == ")":
        return _parse_item(raw)
    if data_type == ">":
        return _parse_status(raw)
    if data_type == "T":
        return _parse_telemetry(raw)
    if data_type == "_":
        return APRSPacket(
            raw=raw,
            data_type=data_type,
            kind="weather_positionless",
            fields={"timestamp_mdhm": raw[1:9], "weather": raw[9:]},
        )
    if data_type == "$":
        return APRSPacket(raw=raw, data_type=data_type, kind="nmea", fields={"sentence": raw})
    if data_type == "{":
        return APRSPacket(
            raw=raw,
            data_type=data_type,
            kind="user_defined",
            fields={"user_id": raw[1:2], "packet_type": raw[2:3], "data": raw[3:]},
        )
    if data_type == ",":
        return APRSPacket(raw=raw, data_type=data_type, kind="invalid_or_test", fields={"data": raw[1:]})
    if data_type == "}":
        header, sep, rest = raw[1:].partition(":")
        return APRSPacket(
            raw=raw,
            data_type=data_type,
            kind="third_party",
            fields={"header": header, "payload": rest if sep else ""},
        )

    x1j_pos = raw.find("!")
    if 0 < x1j_pos <= 39:
        return _parse_position_packet(raw, "!", pos_start=x1j_pos + 1, timestamp=None, prefix=raw[:x1j_pos])

    return APRSPacket(raw=raw, data_type=data_type, kind="other", fields={"data": raw})


def _parse_position_packet(
    raw: str,
    data_type: str,
    pos_start: int,
    timestamp: Optional[str],
    prefix: str = "",
) -> APRSPacket:
    position, next_index = _parse_position(raw, pos_start)
    fields: dict[str, Any] = {
        "messaging": data_type in ("=", "@"),
        "timestamp": timestamp,
        "position": position,
        "comment": raw[next_index:],
    }
    if prefix:
        fields["prefix"] = prefix
    return APRSPacket(raw=raw, data_type=data_type, kind="position", fields=fields)


def _parse_position(raw: str, start: int) -> tuple[APRSPosition, int]:
    if len(raw) < start + 13:
        raise APRSParseError("position field is too short")
    first = raw[start]
    if not first.isdigit() and first != " ":
        return _parse_compressed_position(raw, start)
    lat_raw = raw[start:start + 8]
    symbol_table = raw[start + 8]
    lon_raw = raw[start + 9:start + 18]
    symbol_code = raw[start + 18]
    lat = _parse_latitude(lat_raw)
    lon = _parse_longitude(lon_raw)
    extension_start = start + 19
    extension: dict[str, Any] = {}
    if len(raw) >= extension_start + 7:
        ext = raw[extension_start:extension_start + 7]
        extension = _parse_data_extension(ext)
        if extension:
            extension_start += 7
    return (
        APRSPosition(
            latitude=lat,
            longitude=lon,
            symbol_table=symbol_table,
            symbol_code=symbol_code,
            compressed=False,
            extension=extension,
        ),
        extension_start,
    )


def _parse_latitude(raw: str) -> APRSCoordinate:
    match = re.fullmatch(r"([0-9 ]{2})([0-9 ]{2})\.([0-9 ]{2})([NS])", raw)
    if not match:
        raise APRSParseError(f"invalid APRS latitude: {raw!r}")
    cleaned = raw[:-1].replace(" ", "0")
    degrees = int(cleaned[:2])
    minutes = int(cleaned[2:4]) + int(cleaned[5:7]) / 100.0
    value = degrees + minutes / 60.0
    if raw[-1] == "S":
        value = -value
    return APRSCoordinate(raw=raw, value=value, ambiguity_digits=raw[:-1].count(" "))


def _parse_longitude(raw: str) -> APRSCoordinate:
    match = re.fullmatch(r"([0-9 ]{3})([0-9 ]{2})\.([0-9 ]{2})([EW])", raw)
    if not match:
        raise APRSParseError(f"invalid APRS longitude: {raw!r}")
    cleaned = raw[:-1].replace(" ", "0")
    degrees = int(cleaned[:3])
    minutes = int(cleaned[3:5]) + int(cleaned[6:8]) / 100.0
    value = degrees + minutes / 60.0
    if raw[-1] == "W":
        value = -value
    return APRSCoordinate(raw=raw, value=value, ambiguity_digits=raw[:-1].count(" "))


def _base91(chars: str) -> int:
    value = 0
    for char in chars:
        ordinal = ord(char)
        if ordinal < 33 or ordinal > 124:
            raise APRSParseError("compressed APRS base-91 character out of range")
        value = value * 91 + (ordinal - 33)
    return value


def _parse_compressed_position(raw: str, start: int) -> tuple[APRSPosition, int]:
    if len(raw) < start + 13:
        raise APRSParseError("compressed position field is too short")
    symbol_table = raw[start]
    lat_chars = raw[start + 1:start + 5]
    lon_chars = raw[start + 5:start + 9]
    symbol_code = raw[start + 9]
    cs = raw[start + 10:start + 12]
    comp_type = raw[start + 12]
    lat_value = 90.0 - (_base91(lat_chars) / 380926.0)
    lon_value = -180.0 + (_base91(lon_chars) / 190463.0)
    extension = _parse_compressed_extension(cs, comp_type)
    return (
        APRSPosition(
            latitude=APRSCoordinate(raw=lat_chars, value=lat_value),
            longitude=APRSCoordinate(raw=lon_chars, value=lon_value),
            symbol_table=symbol_table,
            symbol_code=symbol_code,
            compressed=True,
            extension=extension,
        ),
        start + 13,
    )


def _parse_compressed_extension(cs: str, comp_type: str) -> dict[str, Any]:
    if len(cs) != 2 or cs[0] == " ":
        return {}
    c_value = ord(cs[0]) - 33
    s_value = ord(cs[1]) - 33
    t_value = ord(comp_type) - 33
    if not (0 <= c_value <= 90 and 0 <= s_value <= 90 and 0 <= t_value <= 90):
        return {}
    nmea_source = (t_value >> 3) & 0x03
    if nmea_source == 0x02:
        return {"altitude_ft": 1.002 ** (c_value * 91 + s_value), "compression_type": t_value}
    if cs[0] == "{":
        return {"radio_range_miles": 2.0 * (1.08 ** s_value), "compression_type": t_value}
    if 0 <= c_value <= 89:
        return {
            "course_deg": c_value * 4,
            "speed_knots": (1.08 ** s_value) - 1.0,
            "compression_type": t_value,
        }
    return {"compression_type": t_value}


def _parse_data_extension(ext: str) -> dict[str, Any]:
    if re.fullmatch(r"(\d{3}|\.{3}| {3})/(\d{3}|\.{3}| {3})", ext):
        left, right = ext.split("/")
        if left.strip(". ") and right.strip(". "):
            return {"course_deg": int(left), "speed_knots": int(right)}
        return {"course_deg": None, "speed_knots": None}
    if ext.startswith("PHG") and len(ext) == 7:
        return {"phg": ext[3:]}
    if ext.startswith("RNG") and len(ext) == 7:
        return {"radio_range_miles": int(ext[3:])}
    if ext.startswith("DFS") and len(ext) == 7:
        return {"df_signal": ext[3:]}
    if len(ext) == 7 and ext[0].isdigit() and ext[3] == "/":
        return {"area_object": ext}
    return {}


def _parse_message(raw: str) -> APRSPacket:
    if len(raw) < 11 or raw[10] != ":":
        raise APRSParseError("message packet has invalid addressee field")
    addressee = raw[1:10].strip()
    text = raw[11:]
    message_id = None
    if "{" in text:
        text, message_id = text.rsplit("{", 1)
    kind = "message"
    if text.startswith("ack"):
        kind = "message_ack"
        message_id = text[3:] or message_id
        text = ""
    elif text.startswith("rej"):
        kind = "message_reject"
        message_id = text[3:] or message_id
        text = ""
    elif addressee.startswith("BLN"):
        kind = "bulletin"
    return APRSPacket(
        raw=raw,
        data_type=":",
        kind=kind,
        fields={"addressee": addressee, "text": text, "message_id": message_id},
    )


def _parse_object(raw: str) -> APRSPacket:
    if len(raw) < 29:
        raise APRSParseError("object report too short")
    name = raw[1:10].rstrip()
    state = raw[10]
    if state not in ("*", "_"):
        raise APRSParseError("object report missing live/killed marker")
    timestamp = raw[11:18]
    position, next_index = _parse_position(raw, 18)
    return APRSPacket(
        raw=raw,
        data_type=";",
        kind="object",
        fields={
            "name": name,
            "alive": state == "*",
            "timestamp": timestamp,
            "position": position,
            "comment": raw[next_index:],
        },
    )


def _parse_item(raw: str) -> APRSPacket:
    separator = -1
    for index in range(4, min(len(raw), 11)):
        if raw[index] in ("!", "_"):
            separator = index
            break
    if separator == -1:
        raise APRSParseError("item report missing live/killed marker")
    name = raw[1:separator]
    position, next_index = _parse_position(raw, separator + 1)
    return APRSPacket(
        raw=raw,
        data_type=")",
        kind="item",
        fields={
            "name": name,
            "alive": raw[separator] == "!",
            "position": position,
            "comment": raw[next_index:],
        },
    )


def _parse_status(raw: str) -> APRSPacket:
    text = raw[1:]
    timestamp = None
    if re.match(r"^\d{6}z", text):
        timestamp = text[:7]
        text = text[7:]
    return APRSPacket(raw=raw, data_type=">", kind="status", fields={"timestamp": timestamp, "text": text})


def _parse_telemetry(raw: str) -> APRSPacket:
    if not raw.startswith("T#"):
        raise APRSParseError("telemetry report must start with T#")
    parts = raw[2:].split(",")
    if not parts:
        raise APRSParseError("telemetry report missing sequence")
    sequence = parts[0]
    values = parts[1:]
    analog = values[:5]
    digital = values[5] if len(values) >= 6 else ""
    return APRSPacket(
        raw=raw,
        data_type="T",
        kind="telemetry",
        fields={"sequence": sequence, "analog": analog, "digital": digital},
    )
