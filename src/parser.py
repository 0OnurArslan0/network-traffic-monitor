"""Turn a raw scapy packet into a normalized, read-only PacketInfo record.

This module never mutates or re-injects packets — it only reads fields off
already-captured packet objects.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from scapy.layers.inet import ICMP, IP, TCP, UDP
from scapy.layers.inet6 import IPv6
from scapy.layers.l2 import ARP
from scapy.packet import Packet

# Well-known ports we bother labeling explicitly; anything else just shows
# the transport protocol (TCP/UDP) plus the raw port number.
_PORT_LABELS = {
    53: "DNS",
    67: "DHCP",
    68: "DHCP",
    80: "HTTP",
    443: "HTTPS",
    123: "NTP",
}


@dataclass
class PacketInfo:
    timestamp: float
    length: int
    protocol: str          # display protocol: DNS, HTTP, TCP, UDP, ICMP, ARP, OTHER
    transport: str | None   # TCP, UDP, ICMP, ARP, or None
    src_ip: str | None
    dst_ip: str | None
    src_port: int | None
    dst_port: int | None


def _label_for_ports(sport: int | None, dport: int | None, transport: str) -> str:
    for port in (sport, dport):
        if port in _PORT_LABELS:
            return _PORT_LABELS[port]
    return transport


def parse_packet(pkt: Packet) -> PacketInfo | None:
    """Return a PacketInfo, or None if the packet isn't something we track
    (e.g. raw L2 frames with no IP/ARP payload)."""
    timestamp = float(getattr(pkt, "time", time.time()))
    length = len(pkt)

    if ARP in pkt:
        arp = pkt[ARP]
        return PacketInfo(
            timestamp=timestamp,
            length=length,
            protocol="ARP",
            transport="ARP",
            src_ip=arp.psrc,
            dst_ip=arp.pdst,
            src_port=None,
            dst_port=None,
        )

    ip_layer = None
    if IP in pkt:
        ip_layer = pkt[IP]
    elif IPv6 in pkt:
        ip_layer = pkt[IPv6]

    if ip_layer is None:
        return None

    src_ip, dst_ip = ip_layer.src, ip_layer.dst

    if TCP in pkt:
        tcp = pkt[TCP]
        protocol = _label_for_ports(tcp.sport, tcp.dport, "TCP")
        return PacketInfo(
            timestamp=timestamp, length=length,
            protocol=protocol, transport="TCP",
            src_ip=src_ip, dst_ip=dst_ip,
            src_port=int(tcp.sport), dst_port=int(tcp.dport),
        )

    if UDP in pkt:
        udp = pkt[UDP]
        protocol = _label_for_ports(udp.sport, udp.dport, "UDP")
        return PacketInfo(
            timestamp=timestamp, length=length,
            protocol=protocol, transport="UDP",
            src_ip=src_ip, dst_ip=dst_ip,
            src_port=int(udp.sport), dst_port=int(udp.dport),
        )

    if ICMP in pkt:
        return PacketInfo(
            timestamp=timestamp, length=length,
            protocol="ICMP", transport="ICMP",
            src_ip=src_ip, dst_ip=dst_ip,
            src_port=None, dst_port=None,
        )

    return PacketInfo(
        timestamp=timestamp, length=length,
        protocol="OTHER", transport=None,
        src_ip=src_ip, dst_ip=dst_ip,
        src_port=None, dst_port=None,
    )
