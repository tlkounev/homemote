"""HTTP klient pro helper APK běžící na TV (kontrakt viz API.md, část Helper)."""
from __future__ import annotations

from typing import Any

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=4)


class HelperError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status


class HelperClient:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, token: str) -> None:
        self.session = session
        self.base = f"http://{host}:{port}"
        self.token = token

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Token": self.token}

    async def _req(self, method: str, path: str, json: Any = None) -> Any:
        async with self.session.request(
            method, self.base + path, json=json, headers=self._headers, timeout=TIMEOUT
        ) as r:
            if r.status >= 400:
                raise HelperError(r.status, await r.text())
            if r.content_type == "application/json":
                return await r.json()
            return await r.read()

    async def claim(self) -> None:
        """Předá helperu token. Helper si uloží první token (TOFU); jiný token odmítne 403."""
        await self._req("POST", "/v1/claim", {"token": self.token})

    async def info(self) -> dict[str, Any]:
        return await self._req("GET", "/v1/info")

    async def apps(self) -> list[dict[str, Any]]:
        return await self._req("GET", "/v1/apps")

    async def icon(self, package: str) -> bytes:
        return await self._req("GET", f"/v1/apps/{package}/icon")

    async def nowplaying(self) -> dict[str, Any]:
        return await self._req("GET", "/v1/nowplaying")

    async def inputs(self) -> list[dict[str, Any]]:
        return await self._req("GET", "/v1/inputs")

    async def select_input(self, input_id: str) -> None:
        await self._req("POST", "/v1/inputs/select", {"id": input_id})

    async def open_settings(self) -> None:
        await self._req("POST", "/v1/settings/open")

    async def launch(self, package: str) -> None:
        await self._req("POST", "/v1/launch", {"package": package})

    async def seek(self, position_ms: int) -> None:
        await self._req("POST", "/v1/seek", {"position_ms": int(position_ms)})
