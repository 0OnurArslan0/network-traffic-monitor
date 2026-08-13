"""Background, read-only packet capture.

STRICTLY MONITORING: capture uses `store=False` (scapy never buffers
packets in memory beyond the current callback) and nothing in this module
ever sends, injects, or modifies traffic — only scapy's passive sniff()
is used.
"""
from __future__ import annotations

from collections.abc import Callable

from scapy.all import AsyncSniffer, sniff

from .parser import PacketInfo, parse_packet
from .stats import Stats


def check_capture_permissions(iface: str) -> None:
    """Fail fast with a clear message if we can't open the interface,
    instead of letting the background sniffer thread die silently."""
    try:
        sniff(iface=iface, count=0, timeout=0.5, store=False)
    except PermissionError as exc:
        raise PermissionError(
            f"No permission to capture on '{iface}'. Either run with sudo, "
            f"or grant the venv's python capabilities, e.g.:\n"
            f"  sudo setcap cap_net_raw,cap_net_admin=eip "
            f"$(readlink -f venv/bin/python3)"
        ) from exc
    except OSError as exc:
        raise OSError(f"Failed to open interface '{iface}': {exc}") from exc


class TrafficSniffer:
    """Wraps scapy's AsyncSniffer to feed parsed packets into a Stats object
    (and optionally a callback) from a background thread."""

    def __init__(
        self,
        iface: str,
        stats: Stats,
        on_packet: Callable[[PacketInfo], None] | None = None,
        bpf_filter: str | None = None,
    ) -> None:
        self.iface = iface
        self.stats = stats
        self._on_packet = on_packet
        self._sniffer = AsyncSniffer(
            iface=iface,
            prn=self._handle_packet,
            store=False,          # never retain captured packets in memory
            filter=bpf_filter,    # optional BPF filter, e.g. "tcp or udp"
        )

    def _handle_packet(self, pkt) -> None:
        try:
            info = parse_packet(pkt)
        except Exception:
            # A single malformed/unsupported packet must never take capture down.
            return
        if info is None:
            return
        self.stats.record(info)
        if self._on_packet is not None:
            self._on_packet(info)

    def start(self) -> None:
        check_capture_permissions(self.iface)
        self._sniffer.start()

    def stop(self, timeout: float = 2.0) -> None:
        if self._sniffer.running:
            self._sniffer.stop(join=True)

    @property
    def running(self) -> bool:
        return bool(self._sniffer.running)
