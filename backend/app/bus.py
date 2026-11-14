"""Rozesílání událostí připojeným klientům (WebSocket)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiohttp import web

LOG = logging.getLogger(__name__)


class Bus:
    def __init__(self) -> None:
        self.clients: set[web.WebSocketResponse] = set()
        self.owners: dict[web.WebSocketResponse, str] = {}  # socket -> id přihlášeného zařízení

    def close_device(self, dev_id: str) -> None:
        """Odhlášené zařízení: okamžitě ukončit jeho živá spojení."""
        for ws, owner in list(self.owners.items()):
            if owner == dev_id:
                self.clients.discard(ws)
                self.owners.pop(ws, None)
                asyncio.ensure_future(ws.close(code=4401, message=b"odhlaseno"))

    @property
    def has_clients(self) -> bool:
        return bool(self.clients)

    def publish(self, event: dict[str, Any]) -> None:
        if not self.clients:
            return
        msg = json.dumps(event, ensure_ascii=False)
        for ws in list(self.clients):
            asyncio.ensure_future(self._send(ws, msg))

    async def _send(self, ws: web.WebSocketResponse, msg: str) -> None:
        try:
            await ws.send_str(msg)
        except Exception:  # klient odpadl
            self.clients.discard(ws)
            self.owners.pop(ws, None)
