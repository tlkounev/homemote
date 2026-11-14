"""Trvalý stav backendu (JSON v /data)."""
from __future__ import annotations

import json
import os
import secrets
from typing import Any


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        self.data: dict[str, Any] = {"devices": {}}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        self.data.setdefault("devices", {})
        # Token, kterým se backend prokazuje helperu na TV (TOFU "claim").
        changed = False
        if "helper_token" not in self.data:
            self.data["helper_token"] = secrets.token_urlsafe(24)
            changed = True
        # Stabilní ID backendu – telefon podle něj pozná, že na lokální IP je opravdu jeho backend.
        if "instance_id" not in self.data:
            self.data["instance_id"] = secrets.token_hex(8)
            changed = True
        if changed:
            self.save()

    @property
    def instance_id(self) -> str:
        return self.data["instance_id"]

    @property
    def helper_token(self) -> str:
        return self.data["helper_token"]

    def device(self, dev_id: str) -> dict[str, Any]:
        rec = self.data["devices"].setdefault(dev_id, {"id": dev_id})
        rec.setdefault("hidden_apps", [])
        rec.setdefault("paired", False)
        # "adopted" = uživatel zařízení přidal do ovladače; nově objevená zařízení čekají v nabídce +
        rec.setdefault("adopted", bool(rec.get("paired")))
        return rec

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
