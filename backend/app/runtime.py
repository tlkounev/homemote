"""Sdílený stav běžícího backendu: nastavení, adresy pro aplikaci, přihlášení."""
from __future__ import annotations

import os

from typing import Any

from .auth import Auth
from .bus import Bus
from .store import Store
from .tv import Manager


class Runtime:
    def __init__(self, store: Store, auth: Auth, mgr: Manager, bus: Bus, port: int, local_ip: str, helper_apk: str) -> None:
        self.store = store
        self.auth = auth
        self.mgr = mgr
        self.bus = bus
        self.port = port
        self.local_ip = local_ip
        self.helper_apk = helper_apk
        self.phone_apk = os.path.join(os.path.dirname(helper_apk) or ".", "homemote.apk")
        self.android: Any = None  # AndroidBuilder (nastaví main)
        self.discovery = None
        self.store.data.setdefault("settings", {})

    @property
    def settings(self) -> dict[str, Any]:
        return self.store.data["settings"]

    def endpoints(self) -> dict[str, Any]:
        return {
            "instance_id": self.store.instance_id,
            "local": self.settings.get("local_url") or f"http://{self.local_ip}:{self.port}",
            "public": self.settings.get("public_url") or None,
        }

    def txt(self) -> dict[str, str]:
        e = self.endpoints()
        txt = {"id": e["instance_id"], "local": e["local"]}
        if e["public"]:
            txt["public"] = e["public"]
        return txt

    async def update_settings(self, changes: dict[str, Any]) -> dict[str, Any]:
        for key in ("public_url", "local_url"):
            if key not in changes:
                continue
            val = (changes[key] or "").strip().rstrip("/")
            if val and not val.startswith(("http://", "https://")):
                raise ValueError(f"{key}: adresa musí začínat http:// nebo https://")
            self.settings[key] = val or None
        self.store.save()
        if self.discovery:
            await self.discovery.update_txt(self.txt())
        self.bus.publish({"type": "endpoints", "endpoints": self.endpoints()})
        return self.public_settings()

    def public_settings(self) -> dict[str, Any]:
        return {
            "public_url": self.settings.get("public_url") or "",
            "local_url": self.settings.get("local_url") or "",
            "local_url_auto": f"http://{self.local_ip}:{self.port}",
        }
