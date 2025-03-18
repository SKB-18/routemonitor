"""BGP Monitoring Protocol (BMP) binary parser.

RFC 7854: https://www.rfc-editor.org/rfc/rfc7854
"""
from __future__ import annotations

import math
import socket
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ─── Constants ────────────────────────────────────────────────────────────────

BMP_VERSION = 3
BMP_HEADER_LENGTH = 6

MSG_ROUTE_MONITORING = 0
MSG_STATS_REPORT = 1
MSG_PEER_DOWN = 2
MSG_PEER_UP = 3
MSG_INITIATION = 4
MSG_TERMINATION = 5
MSG_ROUTE_MIRRORING = 6

MSG_TYPE_NAMES = {
    MSG_ROUTE_MONITORING: "ROUTE_MONITORING",
    MSG_STATS_REPORT: "STATS_REPORT",
    MSG_PEER_DOWN: "PEER_DOWN",
    MSG_PEER_UP: "PEER_UP",
    MSG_INITIATION: "INITIATION",
    MSG_TERMINATION: "TERMINATION",
    MSG_ROUTE_MIRRORING: "ROUTE_MIRRORING",
}

BGP_OPEN = 1
BGP_UPDATE = 2
BGP_NOTIFICATION = 3
BGP_KEEPALIVE = 4

ATTR_ORIGIN = 1
ATTR_AS_PATH = 2
ATTR_NEXT_HOP = 3
ATTR_MED = 4
ATTR_LOCAL_PREF = 5
ATTR_COMMUNITY = 8
ATTR_MP_REACH_NLRI = 14
ATTR_MP_UNREACH_NLRI = 15

ORIGIN_NAMES = {0: "IGP", 1: "EGP", 2: "INCOMPLETE"}

PEER_HEADER_TYPES = {
    MSG_ROUTE_MONITORING,
    MSG_PEER_DOWN,
    MSG_PEER_UP,
    MSG_ROUTE_MIRRORING,
}


# ─── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class BMPCommonHeader:
    version: int
    message_length: int
    message_type: int


@dataclass
class BMPPeerHeader:
    peer_type: int
    peer_flags: int
    peer_distinguisher: bytes
    peer_address: str
    peer_asn: int
    peer_bgp_id: str
    timestamp_seconds: int
    timestamp_microseconds: int
    is_ipv6: bool = False


@dataclass
class BGPUpdate:
    withdrawn_prefixes: List[str] = field(default_factory=list)
    path_attributes: Dict[str, object] = field(default_factory=dict)
    nlri_prefixes: List[str] = field(default_factory=list)


@dataclass
class BMPRouteMonitoringMessage:
    peer_header: BMPPeerHeader
    bgp_update: BGPUpdate


# ─── Parser ───────────────────────────────────────────────────────────────────


class BMPParser:
    """RFC 7854 compliant BMP message parser."""

    def parse_message(self, data: bytes) -> dict:
        """Parse a complete BMP message from raw bytes."""
        if len(data) < BMP_HEADER_LENGTH:
            raise ValueError(f"BMP message too short: {len(data)} bytes")

        header = self._parse_common_header(data)
        offset = BMP_HEADER_LENGTH
        peer_header: Optional[BMPPeerHeader] = None
        body: object

        if header.message_type in PEER_HEADER_TYPES:
            peer_header, offset = self._parse_per_peer_header(data, offset)

        if header.message_type == MSG_ROUTE_MONITORING:
            body = self._parse_route_monitoring(data, offset)
        elif header.message_type == MSG_PEER_UP:
            body = self._parse_peer_up(data, offset)
        elif header.message_type == MSG_PEER_DOWN:
            body = self._parse_peer_down(data, offset)
        elif header.message_type == MSG_STATS_REPORT:
            body = self._parse_stats_report(data, offset)
        else:
            body = {"raw_length": len(data) - offset}

        return {
            "message_type": header.message_type,
            "message_type_name": MSG_TYPE_NAMES.get(
                header.message_type, f"UNKNOWN_{header.message_type}"
            ),
            "peer_header": peer_header,
            "body": body,
        }

    def _parse_common_header(self, data: bytes) -> BMPCommonHeader:
        if len(data) < BMP_HEADER_LENGTH:
            raise ValueError(f"BMP header requires {BMP_HEADER_LENGTH} bytes")
        version, length, msg_type = struct.unpack(">BIB", data[:6])
        if version != BMP_VERSION:
            raise ValueError(f"Expected BMP version {BMP_VERSION}, got {version}")
        return BMPCommonHeader(
            version=version, message_length=length, message_type=msg_type
        )

    def _parse_per_peer_header(
        self, data: bytes, offset: int = 0
    ) -> Tuple[BMPPeerHeader, int]:
        if len(data) < offset + 42:
            raise ValueError("Per-peer header requires 42 bytes")

        peer_type, peer_flags = struct.unpack_from(">BB", data, offset)
        distinguisher = data[offset + 2 : offset + 10]
        peer_addr_bytes = data[offset + 10 : offset + 26]
        peer_asn = struct.unpack_from(">I", data, offset + 26)[0]
        bgp_id = socket.inet_ntoa(data[offset + 30 : offset + 34])
        ts_sec, ts_usec = struct.unpack_from(">II", data, offset + 34)

        is_ipv6 = bool(peer_flags & 0x80)
        if is_ipv6:
            peer_address = socket.inet_ntop(socket.AF_INET6, peer_addr_bytes)
        else:
            peer_address = socket.inet_ntoa(peer_addr_bytes[12:16])

        header = BMPPeerHeader(
            peer_type=peer_type,
            peer_flags=peer_flags,
            peer_distinguisher=distinguisher,
            peer_address=peer_address,
            peer_asn=peer_asn,
            peer_bgp_id=bgp_id,
            timestamp_seconds=ts_sec,
            timestamp_microseconds=ts_usec,
            is_ipv6=is_ipv6,
        )
        return header, offset + 42

    def _parse_route_monitoring(self, data: bytes, offset: int = 0) -> BGPUpdate:
        # Skip 19-byte BGP header (marker + length + type)
        if len(data) < offset + 19:
            raise ValueError("Route monitoring body too short for BGP header")
        bgp_type = data[offset + 18]
        if bgp_type != BGP_UPDATE:
            raise ValueError(f"Expected BGP UPDATE (type 2), got {bgp_type}")
        return self._parse_bgp_update(data, offset + 19)

    def _parse_bgp_update(self, data: bytes, offset: int = 0) -> BGPUpdate:
        if len(data) < offset + 2:
            raise ValueError("BGP UPDATE too short")

        withdrawn_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        withdrawn_prefixes = self._parse_nlri(data, offset, withdrawn_len)
        offset += withdrawn_len

        if len(data) < offset + 2:
            raise ValueError("BGP UPDATE missing path attribute length")
        path_attr_len = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        path_attributes = self._parse_path_attributes(data, offset, path_attr_len)
        offset += path_attr_len

        nlri_prefixes = self._parse_nlri(data, offset, len(data) - offset)

        return BGPUpdate(
            withdrawn_prefixes=withdrawn_prefixes,
            path_attributes=path_attributes,
            nlri_prefixes=nlri_prefixes,
        )

    def _parse_path_attributes(
        self, data: bytes, offset: int, length: int
    ) -> Dict[str, object]:
        attrs: Dict[str, object] = {}
        end = offset + length

        while offset < end:
            if offset + 2 > end:
                break
            flags, attr_type = struct.unpack_from(">BB", data, offset)
            offset += 2

            extended = bool(flags & 0x10)
            if extended:
                if offset + 2 > end:
                    break
                attr_len = struct.unpack_from(">H", data, offset)[0]
                offset += 2
            else:
                attr_len = data[offset]
                offset += 1

            value = data[offset : offset + attr_len]
            offset += attr_len

            if attr_type == ATTR_ORIGIN and len(value) >= 1:
                attrs["origin"] = ORIGIN_NAMES.get(value[0], "UNKNOWN")
            elif attr_type == ATTR_AS_PATH:
                attrs["as_path"] = self._parse_as_path(value)
            elif attr_type == ATTR_NEXT_HOP and len(value) >= 4:
                attrs["next_hop"] = socket.inet_ntoa(value[:4])
            elif attr_type == ATTR_MED and len(value) >= 4:
                attrs["med"] = struct.unpack(">I", value[:4])[0]
            elif attr_type == ATTR_LOCAL_PREF and len(value) >= 4:
                attrs["local_pref"] = struct.unpack(">I", value[:4])[0]
            elif attr_type == ATTR_COMMUNITY:
                attrs["community"] = self._parse_communities(value)

        return attrs

    def _parse_as_path(self, data: bytes) -> List[int]:
        asns: List[int] = []
        offset = 0
        while offset + 2 <= len(data):
            seg_type, seg_len = struct.unpack_from(">BB", data, offset)
            offset += 2
            if seg_len == 0:
                continue

            remaining = len(data) - offset
            if remaining >= seg_len * 4:
                asn_size = 4
            elif remaining >= seg_len * 2:
                asn_size = 2
            else:
                break

            for _ in range(seg_len):
                if asn_size == 4:
                    asn = struct.unpack_from(">I", data, offset)[0]
                    offset += 4
                else:
                    asn = struct.unpack_from(">H", data, offset)[0]
                    offset += 2
                if seg_type == 2:  # AS_SEQUENCE
                    asns.append(asn)
        return asns

    def _parse_nlri(self, data: bytes, offset: int, length: int) -> List[str]:
        prefixes: List[str] = []
        end = offset + length
        while offset < end:
            prefix_len_bits = data[offset]
            offset += 1
            nbytes = math.ceil(prefix_len_bits / 8)
            if offset + nbytes > end:
                break
            raw = data[offset : offset + nbytes].ljust(4, b"\x00")
            ip = socket.inet_ntoa(raw)
            prefixes.append(f"{ip}/{prefix_len_bits}")
            offset += nbytes
        return prefixes

    def _parse_communities(self, data: bytes) -> List[str]:
        communities: List[str] = []
        for i in range(0, len(data) - 3, 4):
            asn, value = struct.unpack_from(">HH", data, i)
            communities.append(f"{asn}:{value}")
        return communities

    def _parse_peer_up(self, data: bytes, offset: int = 0) -> dict:
        return {"type": "PEER_UP", "raw_length": len(data) - offset}

    def _parse_peer_down(self, data: bytes, offset: int = 0) -> dict:
        return {"type": "PEER_DOWN", "raw_length": len(data) - offset}

    def _parse_stats_report(self, data: bytes, offset: int = 0) -> dict:
        return {"type": "STATS_REPORT", "raw_length": len(data) - offset}


def peer_header_to_dict(header: Optional[BMPPeerHeader]) -> dict:
    """Serialize BMPPeerHeader for Celery JSON transport."""
    if header is None:
        return {}
    return {
        "peer_type": header.peer_type,
        "peer_flags": header.peer_flags,
        "peer_address": header.peer_address,
        "peer_asn": header.peer_asn,
        "peer_bgp_id": header.peer_bgp_id,
        "timestamp_seconds": header.timestamp_seconds,
        "timestamp_microseconds": header.timestamp_microseconds,
        "is_ipv6": header.is_ipv6,
    }


def bgp_update_to_dict(update: BGPUpdate) -> dict:
    """Serialize BGPUpdate for Celery JSON transport."""
    return {
        "withdrawn_prefixes": update.withdrawn_prefixes,
        "path_attributes": update.path_attributes,
        "nlri_prefixes": update.nlri_prefixes,
    }


def parsed_message_to_dict(parsed: dict) -> dict:
    """Convert parse_message output to a JSON-serializable dict."""
    body = parsed.get("body")
    bgp_update = body if isinstance(body, BGPUpdate) else BGPUpdate()
    peer = parsed.get("peer_header")
    return {
        "message_type": parsed.get("message_type"),
        "message_type_name": parsed.get("message_type_name"),
        "peer_header": peer_header_to_dict(
            peer if isinstance(peer, BMPPeerHeader) else None
        ),
        "bgp_update": bgp_update_to_dict(bgp_update),
    }
