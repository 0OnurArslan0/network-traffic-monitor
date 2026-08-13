"""Entry point: wires interface selection, sniffer, stats, and UI together.

Usage:
    venv/bin/python3 -m src.main               # interactive interface picker
    venv/bin/python3 -m src.main -i wlp2s0      # explicit interface
    venv/bin/python3 -m src.main --auto         # auto-pick first UP interface
"""
from __future__ import annotations

import argparse
import platform
import sys
import threading

from . import interfaces
from .sniffer import TrafficSniffer
from .stats import Stats
from .ui import run_dashboard


def check_environment() -> None:
    if platform.system() != "Linux":
        print(
            f"Warning: this tool targets Linux (Ubuntu/Xubuntu). "
            f"Detected: {platform.system()}. Capture may not work.",
            file=sys.stderr,
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only network traffic monitor")
    p.add_argument("-i", "--iface", help="Network interface to capture on (e.g. wlp2s0)")
    p.add_argument("--auto", action="store_true", help="Auto-select the first UP interface, no prompt")
    return p.parse_args()


def main() -> int:
    check_environment()
    args = parse_args()

    try:
        if args.iface:
            iface_name = args.iface
        else:
            iface_name = interfaces.select_interface(auto=args.auto).name
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    stats = Stats()
    sniffer = TrafficSniffer(iface=iface_name, stats=stats)

    try:
        sniffer.start()
    except (PermissionError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    stop_event = threading.Event()
    try:
        run_dashboard(stats, iface_name, stop_check=stop_event.is_set)
    except KeyboardInterrupt:
        pass
    finally:
        sniffer.stop()

    snap = stats.throughput()
    print(f"\nCapture stopped. Total: {snap.total_packets} packets, "
          f"{snap.total_bytes} bytes on interface '{iface_name}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
