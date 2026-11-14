"""Přihlášení: heslo (nastavené při prvním spuštění jen z LAN) a tokeny jednotlivých zařízení.

Data jsou v /data/auth.json. Zapomenuté heslo: smazat auth.json a restartovat kontejner
(odhlásí se všechna zařízení a heslo se nastaví znovu).
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from typing import Any

from aiohttp import web

PAIR_CODE_TTL = 300  # s
LOGIN_MAX_FAILS = 5
LOGIN_LOCK = 600  # s


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_local_request(request: web.Request) -> bool:
    """Požadavek přímo z lokální sítě – ne přes reverzní proxy (ta přidává hlavičky)."""
    if any(h in request.headers for h in ("X-Forwarded-For", "Forwarded", "X-Real-IP")):
        return False
    try:
        ip = ipaddress.ip_address(request.remote or "")
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def client_key(request: web.Request) -> str:
    """Klíč pro omezení pokusů – za proxy první adresa z X-Forwarded-For (jen pro počítání, ne pro důvěru)."""
    fwd = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return fwd or request.remote or "?"


class AuthError(Exception):
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


class Auth:
    def __init__(self, path: str) -> None:
        self.path = path
        self.data: dict[str, Any] = {"password": None, "devices": {}}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        self.data.setdefault("devices", {})
        self._pair_codes: dict[str, float] = {}
        self._fails: dict[str, list[float]] = {}

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    # --- stav ----------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self.data.get("password"))

    def device_for(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        th = _hash_token(token)
        for dev in self.data["devices"].values():
            if hmac.compare_digest(dev["token_hash"], th):
                return dev
        return None

    def touch(self, dev: dict[str, Any]) -> None:
        now = int(time.time())
        if now - dev.get("last_seen", 0) > 300:  # neukládat při každém požadavku
            dev["last_seen"] = now
            self._save()

    # --- heslo ---------------------------------------------------------------
    def _set_password(self, password: str) -> None:
        if len(password) < 8:
            raise AuthError(400, "heslo musí mít aspoň 8 znaků")
        salt = secrets.token_bytes(16)
        self.data["password"] = {"salt": salt.hex(), "hash": _hash_password(password, salt)}

    def _check_password(self, password: str) -> bool:
        pw = self.data.get("password")
        if not pw:
            return False
        return hmac.compare_digest(pw["hash"], _hash_password(password, bytes.fromhex(pw["salt"])))

    def _rate_check(self, key: str) -> None:
        now = time.time()
        fails = [t for t in self._fails.get(key, []) if now - t < LOGIN_LOCK]
        self._fails[key] = fails
        if len(fails) >= LOGIN_MAX_FAILS:
            raise AuthError(429, "příliš mnoho neúspěšných pokusů, zkuste to za 10 minut")

    def _fail(self, key: str) -> None:
        self._fails.setdefault(key, []).append(time.time())

    # --- zařízení ------------------------------------------------------------
    def _new_device(self, name: str, kind: str) -> tuple[str, dict[str, Any]]:
        token = secrets.token_urlsafe(32)
        dev_id = secrets.token_hex(6)
        dev = {
            "id": dev_id,
            "name": (name or "Zařízení").strip()[:60],
            "kind": kind,
            "token_hash": _hash_token(token),
            "created": int(time.time()),
            "last_seen": int(time.time()),
        }
        self.data["devices"][dev_id] = dev
        self._save()
        return token, dev

    def setup(self, password: str, device_name: str, local: bool) -> str:
        if self.configured:
            raise AuthError(409, "heslo už je nastavené – přihlaste se")
        if not local:
            raise AuthError(403, "první nastavení je možné jen z domácí sítě, ne přes internet")
        self._set_password(password)
        token, _ = self._new_device(device_name, "browser")
        return token

    def login(self, password: str, device_name: str, key: str, kind: str = "browser") -> str:
        if not self.configured:
            raise AuthError(409, "nejdřív je potřeba nastavit heslo")
        self._rate_check(key)
        if not self._check_password(password):
            self._fail(key)
            raise AuthError(401, "nesprávné heslo")
        token, _ = self._new_device(device_name, kind)
        return token

    def change_password(self, old: str, new: str) -> None:
        if not self._check_password(old):
            raise AuthError(401, "současné heslo nesouhlasí")
        self._set_password(new)
        self._save()

    def pair_code(self) -> str:
        now = time.time()
        self._pair_codes = {c: t for c, t in self._pair_codes.items() if now - t < PAIR_CODE_TTL}
        code = secrets.token_urlsafe(18)
        self._pair_codes[code] = now
        return code

    def redeem(self, code: str, device_name: str, key: str) -> str:
        self._rate_check(key)
        t = self._pair_codes.pop(code, None)
        if t is None or time.time() - t > PAIR_CODE_TTL:
            self._fail(key)
            raise AuthError(401, "kód je neplatný nebo vypršel – vygenerujte nový")
        token, _ = self._new_device(device_name, "phone")
        return token

    def devices(self) -> list[dict[str, Any]]:
        return sorted(
            ({k: v for k, v in d.items() if k != "token_hash"} for d in self.data["devices"].values()),
            key=lambda d: -d.get("last_seen", 0),
        )

    def revoke(self, dev_id: str) -> None:
        if self.data["devices"].pop(dev_id, None) is None:
            raise AuthError(404, "zařízení nenalezeno")
        self._save()
