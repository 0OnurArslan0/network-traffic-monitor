"""Rich-based live terminal dashboard. Read-only rendering of Stats."""
from __future__ import annotations

import time

from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .stats import Stats

REFRESH_PER_SECOND = 4


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_rate(bytes_per_sec: float) -> str:
    return f"{human_bytes(bytes_per_sec)}/s"


def _header_panel(iface_name: str, start_time: float) -> Panel:
    elapsed = time.time() - start_time
    mm, ss = divmod(int(elapsed), 60)
    hh, mm = divmod(mm, 60)
    text = Text()
    text.append("Network Traffic Monitor  ", style="bold cyan")
    text.append(f"iface={iface_name}  ", style="white")
    text.append(f"uptime={hh:02d}:{mm:02d}:{ss:02d}  ", style="white")
    text.append("MODE: MONITORING ONLY (read-only, no packet blocking/injection)", style="bold green")
    return Panel(text, style="on grey11")


def _throughput_panel(stats: Stats) -> Panel:
    snap = stats.throughput()
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="bold")
    table.add_column()
    table.add_row("Throughput:", human_rate(snap.bytes_per_sec))
    table.add_row("Packets/sec:", f"{snap.packets_per_sec:.1f}")
    table.add_row("Total captured:", f"{snap.total_packets} packets / {human_bytes(snap.total_bytes)}")
    return Panel(table, title="Live Throughput", border_style="cyan")


def _protocol_panel(stats: Stats) -> Panel:
    breakdown = stats.protocol_breakdown()
    total = sum(breakdown.values()) or 1
    table = Table(box=None, expand=True)
    table.add_column("Protocol", style="bold")
    table.add_column("Packets", justify="right")
    table.add_column("Share", justify="right")
    for protocol, count in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True):
        table.add_row(protocol, str(count), f"{count / total * 100:.1f}%")
    return Panel(table, title="Protocol Breakdown", border_style="magenta")


def _devices_panel(stats: Stats) -> Panel:
    table = Table(box=None, expand=True)
    table.add_column("Device (IP)", style="bold")
    table.add_column("Sent", justify="right")
    table.add_column("Recv", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Packets", justify="right")
    for dev in stats.top_devices(10):
        table.add_row(
            dev.ip,
            human_bytes(dev.bytes_sent),
            human_bytes(dev.bytes_recv),
            human_bytes(dev.total_bytes),
            str(dev.packets),
        )
    return Panel(table, title="Active Devices (by bandwidth)", border_style="yellow")


def _connections_panel(stats: Stats) -> Panel:
    table = Table(box=None, expand=True)
    table.add_column("Source", style="bold")
    table.add_column("Destination", style="bold")
    table.add_column("Proto", justify="center")
    table.add_column("Bytes", justify="right")
    table.add_column("Packets", justify="right")
    for conn in stats.top_connections(12):
        src = f"{conn.src_ip}:{conn.src_port}" if conn.src_port else conn.src_ip
        dst = f"{conn.dst_ip}:{conn.dst_port}" if conn.dst_port else conn.dst_ip
        table.add_row(src, dst, conn.protocol, human_bytes(conn.bytes_total), str(conn.packets))
    return Panel(table, title="Top Connections", border_style="green")


def build_layout(stats: Stats, iface_name: str, start_time: float) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right", ratio=2),
    )
    layout["left"].split_column(
        Layout(name="throughput", size=6),
        Layout(name="protocols"),
    )
    layout["right"].split_column(
        Layout(name="devices"),
        Layout(name="connections"),
    )

    layout["header"].update(_header_panel(iface_name, start_time))
    layout["throughput"].update(_throughput_panel(stats))
    layout["protocols"].update(_protocol_panel(stats))
    layout["devices"].update(_devices_panel(stats))
    layout["connections"].update(_connections_panel(stats))
    return layout


def run_dashboard(stats: Stats, iface_name: str, stop_check) -> None:
    """Render until stop_check() returns True or the user hits Ctrl+C."""
    start_time = time.time()
    with Live(
        build_layout(stats, iface_name, start_time),
        refresh_per_second=REFRESH_PER_SECOND,
        screen=True,
    ) as live:
        while not stop_check():
            live.update(build_layout(stats, iface_name, start_time))
            time.sleep(1 / REFRESH_PER_SECOND)
