"""Wake-on-LAN: magický paket pro TV v hlubokém spánku (síť vypnutá, neodpovídá ani na ARP).

Funguje jen tehdy, když to TV umí a má to zapnuté – u Philips Google TV
Nastavení → Síť a internet → Zapnout pomocí Wi-Fi (WoWLAN).
"""
from __future__ import annotations

import fcntl
import ipaddress
import logging
import re
import socket
import struct

LOG = logging.getLogger(__name__)
_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
SIOCGIFADDR, SIOCGIFNETMASK = 0x8915, 0x891B


def arp_mac(ip: str | None) -> str | None:
    """MAC adresa síťového rozhraní TV z ARP tabulky (platná, jen když byla TV nedávno v síti)."""
    if not ip:
        return None
    try:
        with open("/proc/net/arp", encoding="ascii") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip and parts[2] != "0x0":
                    mac = parts[3].lower()
                    return mac if _MAC.match(mac) and mac != "00:00:00:00:00:00" else None
    except OSError:
        pass
    return None


def _broadcasts() -> set[str]:
    """Broadcastové adresy všech IPv4 rozhraní (kromě loopbacku) + 255.255.255.255."""
    out = {"255.255.255.255"}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _, name in socket.if_nameindex():
            if name == "lo":
                continue
            req = struct.pack("256s", name.encode()[:15])
            try:
                addr = socket.inet_ntoa(fcntl.ioctl(s.fileno(), SIOCGIFADDR, req)[20:24])
                mask = socket.inet_ntoa(fcntl.ioctl(s.fileno(), SIOCGIFNETMASK, req)[20:24])
            except OSError:
                continue
            out.add(str(ipaddress.IPv4Network(f"{addr}/{mask}", strict=False).broadcast_address))
    finally:
        s.close()
    return out


def send(macs: list[str], host: str | None = None) -> list[str]:
    """Pošle magický paket na všechny broadcasty (porty 9 a 7) a na poslední známou IP. Vrací použité MAC."""
    used = [m for m in dict.fromkeys(macs) if m and _MAC.match(m)]
    if not used:
        return []
    targets = _broadcasts() | ({host} if host else set())
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        for mac in used:
            packet = b"\xff" * 6 + bytes.fromhex(mac.replace(":", "")) * 16
            for _ in range(3):
                for ip in targets:
                    for port in (9, 7):
                        try:
                            s.sendto(packet, (ip, port))
                        except OSError:
                            pass
    finally:
        s.close()
    LOG.info("Wake-on-LAN: %s → %s", ", ".join(used), ", ".join(sorted(targets)))
    return used
