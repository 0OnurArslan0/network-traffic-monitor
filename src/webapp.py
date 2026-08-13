"""FastAPI backend for the web dashboard.

Read-only monitoring, same as the terminal UI — this module only adds an
HTTP/JSON layer on top of the existing interfaces/sniffer/stats modules.
Nothing here sends, injects, or modifies network traffic.
"""
from __future__ import annotations

import pathlib
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import interfaces
from .sniffer import TrafficSniffer
from .stats import Stats

STATIC_DIR = pathlib.Path(__file__).parent / "static"


class CaptureState:
    """Owns the single active capture session, if any. One capture at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: Stats | None = None
        self._sniffer: TrafficSniffer | None = None
        self._iface: str | None = None
        self._start_time: float | None = None

    def start(self, iface: str) -> None:
        with self._lock:
            if self._sniffer is not None and self._sniffer.running:
                raise RuntimeError("Capture is already running; stop it first.")
            stats = Stats()
            sniffer = TrafficSniffer(iface=iface, stats=stats)
            sniffer.start()  # may raise PermissionError / OSError
            self._stats = stats
            self._sniffer = sniffer
            self._iface = iface
            self._start_time = time.time()

    def stop(self) -> None:
        with self._lock:
            if self._sniffer is not None:
                self._sniffer.stop()
            self._sniffer = None
            self._iface = None
            self._start_time = None

    def snapshot_refs(self) -> tuple[Stats | None, str | None, float | None, bool]:
        """Consistent (stats, iface, start_time, capturing) tuple under one lock."""
        with self._lock:
            capturing = self._sniffer is not None and self._sniffer.running
            return self._stats, self._iface, self._start_time, capturing


state = CaptureState()

app = FastAPI(title="Network Traffic Monitor")


class StartRequest(BaseModel):
    iface: str


@app.get("/api/interfaces")
def api_interfaces():
    return [
        {
            "name": iface.name,
            "label": iface.label,
            "is_up": iface.is_up,
            "ipv4": iface.ipv4_addrs,
        }
        for iface in interfaces.list_interfaces()
    ]


@app.post("/api/start")
def api_start(body: StartRequest):
    try:
        state.start(body.iface)
    except Exception as exc:
        # Covers permission errors, unknown/renamed interfaces (scapy raises
        # ValueError), and "already running" (RuntimeError) alike — any of
        # these is a client-facing 400, never a 500 with a stack trace.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/stop")
def api_stop():
    state.stop()
    return {"ok": True}


@app.get("/api/status")
def api_status():
    _, iface, start_time, capturing = state.snapshot_refs()
    return {
        "capturing": capturing,
        "iface": iface,
        "elapsed_seconds": (time.time() - start_time) if start_time else 0,
    }


@app.get("/api/stats")
def api_stats():
    stats, _, _, capturing = state.snapshot_refs()
    if not capturing or stats is None:
        raise HTTPException(status_code=409, detail="Not capturing")

    snap = stats.throughput()
    return {
        "throughput": {
            "bytes_per_sec": snap.bytes_per_sec,
            "packets_per_sec": snap.packets_per_sec,
            "total_packets": snap.total_packets,
            "total_bytes": snap.total_bytes,
        },
        "protocols": stats.protocol_breakdown(),
        "devices": [
            {
                "ip": d.ip,
                "bytes_sent": d.bytes_sent,
                "bytes_recv": d.bytes_recv,
                "total_bytes": d.total_bytes,
                "packets": d.packets,
            }
            for d in stats.top_devices(15)
        ],
        "connections": [
            {
                "src_ip": c.src_ip,
                "dst_ip": c.dst_ip,
                "src_port": c.src_port,
                "dst_port": c.dst_port,
                "protocol": c.protocol,
                "bytes_total": c.bytes_total,
                "packets": c.packets,
            }
            for c in stats.top_connections(25)
        ],
    }


@app.on_event("shutdown")
def _on_shutdown():
    state.stop()


# Must be mounted last: it's a catch-all for "/" and everything under it.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
