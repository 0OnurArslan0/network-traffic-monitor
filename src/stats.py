"""Thread-safe in-memory aggregation of parsed packets.

One Stats instance is shared between the sniffer thread (writer, via
`record()`) and the UI thread (reader, via the snapshot/query methods).
All access goes through a single lock — capture rates here (home network,
single interface) are nowhere near high enough for this to be a bottleneck.
"""
from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field

from .parser import PacketInfo

# How far back "current throughput" looks. Short enough to feel live,
# long enough to smooth out per-packet jitter.
THROUGHPUT_WINDOW_SECONDS = 3.0


@dataclass
class DeviceStats:
    ip: str
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets: int = 0
    last_seen: float = 0.0

    @property
    def total_bytes(self) -> int:
        return self.bytes_sent + self.bytes_recv


@dataclass
class ConnectionStats:
    src_ip: str
    dst_ip: str
    src_port: int | None
    dst_port: int | None
    protocol: str
    bytes_total: int = 0
    packets: int = 0
    last_seen: float = 0.0

    @property
    def key(self) -> tuple:
        return (self.src_ip, self.dst_ip, self.src_port, self.dst_port, self.protocol)


@dataclass
class ThroughputSnapshot:
    bytes_per_sec: float
    packets_per_sec: float
    total_packets: int
    total_bytes: int
    elapsed_seconds: float


class Stats:
    def __init__(self, window_seconds: float = THROUGHPUT_WINDOW_SECONDS) -> None:
        self._lock = threading.Lock()
        self._window = window_seconds
        self._start_time = time.time()

        self._total_packets = 0
        self._total_bytes = 0

        # (timestamp, length) pairs within the rolling window, oldest first.
        self._recent: deque[tuple[float, int]] = deque()

        self._devices: dict[str, DeviceStats] = {}
        self._connections: dict[tuple, ConnectionStats] = {}
        self._protocol_counts: Counter[str] = Counter()

    def record(self, pkt: PacketInfo) -> None:
        with self._lock:
            self._total_packets += 1
            self._total_bytes += pkt.length
            self._protocol_counts[pkt.protocol] += 1

            self._recent.append((pkt.timestamp, pkt.length))
            self._trim_window_locked()

            if pkt.src_ip:
                sender = self._devices.setdefault(pkt.src_ip, DeviceStats(ip=pkt.src_ip))
                sender.bytes_sent += pkt.length
                sender.packets += 1
                sender.last_seen = pkt.timestamp

            if pkt.dst_ip:
                receiver = self._devices.setdefault(pkt.dst_ip, DeviceStats(ip=pkt.dst_ip))
                receiver.bytes_recv += pkt.length
                receiver.last_seen = pkt.timestamp

            if pkt.src_ip and pkt.dst_ip:
                conn = ConnectionStats(
                    src_ip=pkt.src_ip, dst_ip=pkt.dst_ip,
                    src_port=pkt.src_port, dst_port=pkt.dst_port,
                    protocol=pkt.protocol,
                )
                existing = self._connections.setdefault(conn.key, conn)
                existing.bytes_total += pkt.length
                existing.packets += 1
                existing.last_seen = pkt.timestamp

    def _trim_window_locked(self) -> None:
        cutoff = time.time() - self._window
        while self._recent and self._recent[0][0] < cutoff:
            self._recent.popleft()

    def throughput(self) -> ThroughputSnapshot:
        with self._lock:
            self._trim_window_locked()
            window_bytes = sum(length for _, length in self._recent)
            window_packets = len(self._recent)
            elapsed = min(self._window, time.time() - self._start_time)
            elapsed = max(elapsed, 0.001)  # avoid div-by-zero in the first instant
            return ThroughputSnapshot(
                bytes_per_sec=window_bytes / elapsed,
                packets_per_sec=window_packets / elapsed,
                total_packets=self._total_packets,
                total_bytes=self._total_bytes,
                elapsed_seconds=time.time() - self._start_time,
            )

    def top_devices(self, n: int = 10) -> list[DeviceStats]:
        with self._lock:
            devices = list(self._devices.values())
        devices.sort(key=lambda d: d.total_bytes, reverse=True)
        return devices[:n]

    def top_connections(self, n: int = 10) -> list[ConnectionStats]:
        with self._lock:
            conns = list(self._connections.values())
        conns.sort(key=lambda c: c.bytes_total, reverse=True)
        return conns[:n]

    def protocol_breakdown(self) -> dict[str, int]:
        with self._lock:
            return dict(self._protocol_counts)
