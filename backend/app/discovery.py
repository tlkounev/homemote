"""mDNS: hledání Google TV a helperu, ohlášení backendu pro telefonní aplikaci."""
from __future__ import annotations

import asyncio
import logging
import socket
import time

from zeroconf import IPVersion, ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from .tv import REMOTE_TYPE, Manager

LOG = logging.getLogger(__name__)

HELPER_TYPE = "_homemote-helper._tcp.local."
SELF_TYPE = "_homemote._tcp.local."


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("224.0.0.251", 5353))  # nic se neposílá, jen výběr rozhraní
        return s.getsockname()[0]
    finally:
        s.close()


class Discovery:
    def __init__(
        self, mgr: Manager, api_port: int, advertise_ip: str | None = None, txt: dict[str, str] | None = None
    ) -> None:
        self.txt = txt or {}
        self.mgr = mgr
        self.api_port = api_port
        self.advertise_ip = advertise_ip
        self.azc: AsyncZeroconf | None = None
        self.browser: AsyncServiceBrowser | None = None
        self._self_info: AsyncServiceInfo | None = None
        self._last_resolve: dict[str, float] = {}

    async def start(self) -> None:
        self.azc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        self.browser = AsyncServiceBrowser(
            self.azc.zeroconf, [REMOTE_TYPE, HELPER_TYPE], handlers=[self._on_change]
        )
        ip = self.advertise_ip or local_ip()
        self._self_info = AsyncServiceInfo(
            SELF_TYPE,
            f"Homemote backend.{SELF_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=self.api_port,
            properties={"path": "/api", "v": "1", **self.txt},
        )
        await self.azc.async_register_service(self._self_info)
        LOG.info("mDNS: backend ohlášen jako %s na %s:%s", SELF_TYPE, ip, self.api_port)

    async def update_txt(self, txt: dict[str, str]) -> None:
        """Změna ohlašovaných adres (např. po úpravě veřejné adresy ve webu)."""
        self.txt = txt
        if not (self.azc and self._self_info):
            return
        self._self_info = AsyncServiceInfo(
            SELF_TYPE,
            self._self_info.name,
            addresses=self._self_info.addresses,
            port=self.api_port,
            server=self._self_info.server,
            properties={"path": "/api", "v": "1", **txt},
        )
        await self.azc.async_update_service(self._self_info)

    def resolve_now(self, service_type: str, name: str) -> None:
        self._last_resolve.pop(name, None)
        self.resolve_soon(service_type, name)

    async def stop(self) -> None:
        if not self.azc:
            return
        if self.browser:
            await self.browser.async_cancel()
        if self._self_info:
            await self.azc.async_unregister_service(self._self_info)
        await self.azc.async_close()

    def _on_change(
        self, zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
    ) -> None:
        if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
            asyncio.ensure_future(self._resolve(service_type, name))

    def resolve_soon(self, service_type: str, name: str) -> None:
        """Znovu dotáže konkrétní službu (např. po výpadku spojení – mohla se změnit IP)."""
        now = time.monotonic()
        if now - self._last_resolve.get(name, 0) < 15:
            return
        self._last_resolve[name] = now
        asyncio.ensure_future(self._resolve(service_type, name))

    async def _resolve(self, service_type: str, name: str) -> None:
        assert self.azc
        info = AsyncServiceInfo(service_type, name)
        if not await info.async_request(self.azc.zeroconf, 3000):
            return
        addrs = info.parsed_addresses(IPVersion.V4Only)
        if not addrs or not info.port:
            return
        host = addrs[0]
        LOG.debug("mDNS: %s -> %s:%s", name, host, info.port)
        try:
            if service_type == REMOTE_TYPE:
                await self.mgr.on_tv_seen(name, host)
            elif service_type == HELPER_TYPE:
                await self.mgr.on_helper_seen(host, info.port)
        except Exception:  # discovery nesmí spadnout
            LOG.exception("mDNS: chyba při zpracování %s", name)
