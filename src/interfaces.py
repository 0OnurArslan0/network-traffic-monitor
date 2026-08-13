"""Network interface discovery and selection.

Uses `ip -j addr` (iproute2 JSON output) for interface metadata, since it's
already present on any Ubuntu/Xubuntu system and needs no extra Python deps.
Cross-checked against scapy.get_if_list() to make sure a given interface is
actually something scapy can open for capture.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

from scapy.all import get_if_list


@dataclass
class Interface:
    name: str
    is_up: bool
    mac: str | None
    ipv4_addrs: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        state = "UP" if self.is_up else "DOWN"
        ip = self.ipv4_addrs[0] if self.ipv4_addrs else "no IPv4"
        return f"{self.name:<10} [{state:<4}] {ip}"


def list_interfaces(include_loopback: bool = False) -> list[Interface]:
    """Return interfaces known to both the OS and scapy."""
    try:
        raw = subprocess.run(
            ["ip", "-j", "addr", "show"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        entries = json.loads(raw.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError) as exc:
        raise RuntimeError(f"Failed to query interfaces via `ip`: {exc}") from exc

    scapy_ifaces = set(get_if_list())

    interfaces: list[Interface] = []
    for entry in entries:
        name = entry.get("ifname", "")
        if not include_loopback and "LOOPBACK" in entry.get("flags", []):
            continue
        if name not in scapy_ifaces:
            # scapy can't open it (e.g. some virtual/tunnel ifaces) — skip
            continue

        ipv4_addrs = [
            addr["local"]
            for addr in entry.get("addr_info", [])
            if addr.get("family") == "inet"
        ]
        interfaces.append(
            Interface(
                name=name,
                is_up="UP" in entry.get("flags", []),
                mac=entry.get("address"),
                ipv4_addrs=ipv4_addrs,
            )
        )
    return interfaces


def default_interface() -> Interface | None:
    """Best-guess default interface: first UP interface with an IPv4 address."""
    for iface in list_interfaces():
        if iface.is_up and iface.ipv4_addrs:
            return iface
    return None


def select_interface(auto: bool = False) -> Interface:
    """Return an Interface, either auto-selected or via interactive prompt."""
    interfaces = list_interfaces()
    if not interfaces:
        raise RuntimeError(
            "No usable network interfaces found (scapy could not open any "
            "interface reported by `ip addr`). Are you connected to a network?"
        )

    if auto or len(interfaces) == 1:
        guess = default_interface() or interfaces[0]
        return guess

    print("Available network interfaces:\n")
    for i, iface in enumerate(interfaces):
        print(f"  [{i}] {iface.label}")
    print()

    while True:
        choice = input(f"Select interface [0-{len(interfaces) - 1}]: ").strip()
        if choice.isdigit() and 0 <= int(choice) < len(interfaces):
            return interfaces[int(choice)]
        print("Invalid choice, try again.")


if __name__ == "__main__":
    # Quick manual check: `venv/bin/python3 -m src.interfaces`
    for iface in list_interfaces():
        print(iface.label)
