"""Mock BGP telemetry generator for testing and simulation.

Generates RFC 7854-compliant BMP binary messages for:
  - Normal routing behavior (steady-state)
  - Route flapping (anomaly scenario)
  - Link failure (mass withdrawal)
  - Convergence events

Can also run as __main__ to send live BMP messages to a TCP target.

Usage:
    generator = MockBGPTelemetryGenerator(num_speakers=5, prefixes_per_speaker=1000)
    update_bytes = generator.generate_update("10.0.0.0/24", 65001)
    withdraw_bytes = generator.generate_withdraw("10.0.0.0/24")
    flap_messages = generator.simulate_route_flap("speaker-1", "10.0.0.0/24", num_flaps=20)
"""
from __future__ import annotations

import ipaddress
import random
import socket
import struct
import time
from typing import List, Optional


# ─── BMP / BGP constants ─────────────────────────────────────────────────────

BMP_VERSION = 3
BMP_MSG_ROUTE_MONITORING = 0

BGP_MARKER = b"\xff" * 16  # 16 bytes of 0xFF (BGP message marker)
BGP_UPDATE_TYPE = 2


class MockBGPTelemetryGenerator:
    """Generate realistic mock BGP BMP telemetry for testing.

    Args:
        num_speakers: Number of simulated BGP routers.
        prefixes_per_speaker: Number of prefixes each speaker advertises.
        seed: Random seed for reproducibility (default: 42).
    """

    def __init__(
        self,
        num_speakers: int = 5,
        prefixes_per_speaker: int = 1000,
        seed: int = 42,
    ) -> None:
        self.num_speakers = num_speakers
        self.prefixes_per_speaker = prefixes_per_speaker
        random.seed(seed)

        # Generate speaker identities
        self.speakers = [
            {
                "id": f"router-{i+1}",
                "router_id": f"10.0.{i}.1",
                "asn": 65000 + i,
                "peer_ip": f"10.1.{i}.1",
                "peer_asn": 65100 + i,
            }
            for i in range(num_speakers)
        ]

        # Generate prefix pool
        self.prefixes = self._generate_prefix_pool()

    # ─── Prefix pool ──────────────────────────────────────────────────────────

    def _generate_prefix_pool(self) -> List[str]:
        """Generate a realistic pool of IPv4 CIDR prefixes."""
        prefixes = []
        # /24 prefixes from various /16 blocks
        for block in [10, 172, 192]:
            for second in range(0, min(255, self.prefixes_per_speaker // 5)):
                prefixes.append(f"{block}.{second}.0.0/16")
        # /24 subnets
        for i in range(self.prefixes_per_speaker):
            a = random.randint(1, 223)
            b = random.randint(0, 255)
            c = random.randint(0, 255)
            prefixes.append(f"{a}.{b}.{c}.0/24")
        return list(set(prefixes))[: self.prefixes_per_speaker * self.num_speakers]

    # ─── Public API ───────────────────────────────────────────────────────────

    def generate_update(
        self,
        prefix: str,
        local_asn: int,
        as_path: Optional[List[int]] = None,
        next_hop: str = "10.0.0.1",
    ) -> bytes:
        """Generate a BMP Route Monitoring message containing a BGP UPDATE.

        Args:
            prefix: CIDR prefix being advertised (e.g. "10.0.0.0/24")
            local_asn: ASN of the originating speaker
            as_path: AS path list; random if None
            next_hop: Next hop IP address

        Returns:
            Raw BMP message bytes

        [CURSOR TO IMPLEMENT - Phase 1]:
            1. Build BGP UPDATE bytes:
               - 16-byte marker (all 0xFF)
               - length (2 bytes)
               - type=2 (1 byte)
               - withdrawn_routes_length=0 (2 bytes)
               - path_attributes (AS_PATH + NEXT_HOP + ORIGIN)
               - NLRI (prefix)
            2. Wrap in BMP per-peer header
            3. Wrap in BMP common header (version=3, type=0)
        """
        if as_path is None:
            as_path = [
                local_asn,
                random.randint(65000, 65100),
                random.randint(65100, 65200),
            ]

        bgp_update = self._build_bgp_update(
            nlri_prefixes=[prefix],
            as_path=as_path,
            next_hop=next_hop,
        )
        peer_header = self._build_per_peer_header(local_asn, "10.1.0.1", next_hop)
        return self._build_bmp_route_monitoring(peer_header, bgp_update)

    def generate_withdraw(self, prefix: str, local_asn: int = 65001) -> bytes:
        """Generate a BMP Route Monitoring message containing a BGP WITHDRAW.

        Args:
            prefix: CIDR prefix to withdraw

        Returns:
            Raw BMP message bytes

        [CURSOR TO IMPLEMENT - Phase 1]:
            Similar to generate_update but withdrawn_routes contains the prefix
            and NLRI is empty.
        """
        bgp_update = self._build_bgp_update(
            withdrawn_prefixes=[prefix],
            nlri_prefixes=[],
            as_path=[],
            next_hop="0.0.0.0",
        )
        peer_header = self._build_per_peer_header(local_asn, "10.1.0.1", "0.0.0.0")
        return self._build_bmp_route_monitoring(peer_header, bgp_update)

    def simulate_route_flap(
        self,
        speaker_id: str,
        prefix: str,
        num_flaps: int = 20,
        local_asn: int = 65001,
    ) -> List[bytes]:
        """Simulate a flapping route: alternating UPDATE and WITHDRAW messages.

        Args:
            speaker_id: Speaker identifier (for logging)
            prefix: The flapping prefix
            num_flaps: Number of flap cycles

        Returns:
            List of BMP messages (num_flaps * 2 messages)
        """
        messages = []
        for i in range(num_flaps):
            if i % 2 == 0:
                messages.append(self.generate_update(prefix, local_asn))
            else:
                messages.append(self.generate_withdraw(prefix, local_asn))
        return messages

    def simulate_link_failure(
        self,
        affected_prefix_count: int = 100,
        local_asn: int = 65001,
    ) -> List[bytes]:
        """Simulate a link failure: mass withdrawal of many prefixes simultaneously.

        This is the pattern that triggers CORRELATED_FAILURE anomaly detection.

        Args:
            affected_prefix_count: Number of prefixes to withdraw at once

        Returns:
            List of BMP WITHDRAW messages (one per prefix)
        """
        affected = random.sample(
            self.prefixes, min(affected_prefix_count, len(self.prefixes))
        )
        return [self.generate_withdraw(p, local_asn) for p in affected]

    def simulate_normal_traffic(
        self,
        num_messages: int = 1000,
        speaker_idx: int = 0,
    ) -> List[bytes]:
        """Simulate normal BGP traffic for a speaker.

        90% UPDATE messages, 10% WITHDRAW messages, random prefixes.

        Args:
            num_messages: Total messages to generate

        Returns:
            List of BMP messages
        """
        speaker = self.speakers[speaker_idx % len(self.speakers)]
        messages = []
        for _ in range(num_messages):
            prefix = random.choice(self.prefixes)
            if random.random() < 0.9:
                messages.append(self.generate_update(prefix, speaker["asn"]))
            else:
                messages.append(self.generate_withdraw(prefix, speaker["asn"]))
        return messages

    # ─── BMP / BGP binary builders ────────────────────────────────────────────

    def _build_per_peer_header(
        self,
        peer_asn: int,
        peer_ip: str,
        bgp_id: str,
    ) -> bytes:
        """Build a 42-byte BMP per-peer header (RFC 7854 section 4.2)."""
        ts = int(time.time())
        peer_addr_bytes = b"\x00" * 12 + socket.inet_aton(peer_ip)
        bgp_id_bytes = socket.inet_aton(bgp_id)
        return struct.pack(
            ">BB8s16sI4sII",
            0,  # peer_type: Global Instance
            0,  # peer_flags
            b"\x00" * 8,  # peer_distinguisher
            peer_addr_bytes,
            peer_asn,
            bgp_id_bytes,
            ts,
            0,  # timestamp_usec
        )

    def _build_bgp_update(
        self,
        nlri_prefixes: Optional[List[str]] = None,
        withdrawn_prefixes: Optional[List[str]] = None,
        as_path: Optional[List[int]] = None,
        next_hop: str = "10.0.0.1",
    ) -> bytes:
        """Build a minimal BGP UPDATE message (19-byte header + body)."""
        nlri_prefixes = nlri_prefixes or []
        withdrawn_prefixes = withdrawn_prefixes or []
        as_path = as_path or []

        withdrawn_bytes = self._encode_nlri(withdrawn_prefixes)
        path_attrs = self._encode_path_attributes(as_path, next_hop)
        nlri_bytes = self._encode_nlri(nlri_prefixes)

        update_body = (
            struct.pack(">H", len(withdrawn_bytes))
            + withdrawn_bytes
            + struct.pack(">H", len(path_attrs))
            + path_attrs
            + nlri_bytes
        )

        # BGP header: 16-byte marker + 2-byte length + 1-byte type
        total_len = 19 + len(update_body)
        bgp_header = BGP_MARKER + struct.pack(">HB", total_len, BGP_UPDATE_TYPE)
        return bgp_header + update_body

    def _build_bmp_route_monitoring(
        self, per_peer_header: bytes, bgp_message: bytes
    ) -> bytes:
        """Wrap per-peer header + BGP message in a BMP common header."""
        body = per_peer_header + bgp_message
        total_len = 6 + len(body)  # 6 = BMP common header length
        bmp_header = struct.pack(
            ">BIB", BMP_VERSION, total_len, BMP_MSG_ROUTE_MONITORING
        )
        return bmp_header + body

    def _encode_nlri(self, prefixes: List[str]) -> bytes:
        """Encode a list of CIDR prefixes as BGP NLRI bytes."""
        result = b""
        for cidr in prefixes:
            net = ipaddress.IPv4Network(cidr, strict=False)
            prefix_len = net.prefixlen
            prefix_bytes_count = (prefix_len + 7) // 8
            addr_bytes = net.network_address.packed[:prefix_bytes_count]
            result += struct.pack("B", prefix_len) + addr_bytes
        return result

    def _encode_path_attributes(self, as_path: List[int], next_hop: str) -> bytes:
        """Encode ORIGIN, AS_PATH, and NEXT_HOP path attributes."""
        attrs = b""

        # ORIGIN = IGP (0)
        attrs += struct.pack(">BBB", 0x40, 1, 1) + b"\x00"

        # AS_PATH (AS_SEQUENCE, 2-byte ASNs)
        if as_path:
            as_path_value = struct.pack("BB", 2, len(as_path))
            for asn in as_path:
                as_path_value += struct.pack(">H", asn)
            attrs += struct.pack(">BBB", 0x40, 2, len(as_path_value)) + as_path_value

        # NEXT_HOP
        nh_bytes = socket.inet_aton(next_hop)
        attrs += struct.pack(">BBB", 0x40, 3, 4) + nh_bytes

        return attrs


# ─── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Send mock BMP telemetry to RouteMonitor"
    )
    parser.add_argument(
        "--target", default="localhost:9179", help="host:port of BMP server"
    )
    parser.add_argument("--messages", type=int, default=100)
    parser.add_argument(
        "--scenario", choices=["normal", "flap", "failure"], default="normal"
    )
    args = parser.parse_args()

    host, port = args.target.rsplit(":", 1)
    gen = MockBGPTelemetryGenerator()

    if args.scenario == "flap":
        messages = gen.simulate_route_flap(
            "router-1", "10.0.0.0/24", num_flaps=args.messages // 2
        )
    elif args.scenario == "failure":
        messages = gen.simulate_link_failure(affected_prefix_count=args.messages)
    else:
        messages = gen.simulate_normal_traffic(num_messages=args.messages)

    print(
        f"Sending {len(messages)} BMP messages to {host}:{port} (scenario={args.scenario})"
    )
    try:
        sock = socket.create_connection((host, int(port)), timeout=5)
        for msg in messages:
            sock.sendall(msg)
        sock.close()
        print("Done.")
    except ConnectionRefusedError:
        print(f"Could not connect to {host}:{port} — is the BMP server running?")
        sys.exit(1)
