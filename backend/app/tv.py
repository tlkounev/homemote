"""Správa televizí: identita podle MAC, připojení přes Remote protocol v2, helper na TV."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import struct
import time
import unicodedata
from typing import Any

import aiohttp
from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth

from . import keys, wol
from .ime import Remote
from .bus import Bus
from .helper_client import HelperClient, HelperError
from .store import Store

LOG = logging.getLogger(__name__)

CLIENT_NAME = "Homemote"
REMOTE_TYPE = "_androidtvremote2._tcp.local."
DEFAULT_HELPER_PORT = 8765
HELPER_ERRORS = (HelperError, aiohttp.ClientError, asyncio.TimeoutError, OSError)


class NotConnected(Exception):
    pass


class HelperUnavailable(Exception):
    pass


def norm_mac(mac: str) -> str:
    """"AA-BB-..", "aa:bb:.." i "aabb.." -> "aa:bb:cc:dd:ee:ff"."""
    raw = mac.strip().lower().replace("-", "").replace(":", "")
    if len(raw) == 12:
        return ":".join(raw[i : i + 2] for i in range(0, 12, 2))
    return mac.strip().lower()


_NODE_RX = re.compile(r"<node\b([^>]*)>")
_ATTR_RX = re.compile(r'([\w-]+)="([^"]*)"')
_BOUNDS_RX = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


Rect = tuple[int, int, int, int]


def parse_screen_keyboard(xml: str) -> dict[str, Any]:
    """Z výpisu uiautomator najde klávesnici vykreslenou aplikací.

    Klávesy = prvky s jedním znakem a–z/0–9. Prvky bez textu ve stejné oblasti a velikosti klávesy
    jsou speciální klávesy (nejširší = mezerník " ", ostatní "#1", "#2" … – jen kvůli navigaci).
    Vrací {"keys": {znak: rect}, "rows": [[znak, …], …], "screen": (šířka, výška)} nebo {}.
    """
    keys: dict[str, Rect] = {}
    blanks: list[Rect] = []
    sw = sh = 0
    for m in _NODE_RX.finditer(xml):
        a = dict(_ATTR_RX.findall(m.group(1)))
        b = _BOUNDS_RX.search(a.get("bounds", ""))
        if not b:
            continue
        x1, y1, x2, y2 = map(int, b.groups())
        sw, sh = max(sw, x2), max(sh, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        text = (a.get("text") or a.get("content-desc") or "").strip()
        if len(text) == 1 and text.isascii() and text.isalnum():
            keys.setdefault(text.lower(), (x1, y1, x2, y2))
        elif not text:
            blanks.append((x1, y1, x2, y2))
    if len([k for k in keys if k.isalpha()]) < 20:
        return {}
    kx1 = min(v[0] for v in keys.values()); kx2 = max(v[2] for v in keys.values())
    ky1 = min(v[1] for v in keys.values()); ky2 = max(v[3] for v in keys.values())
    kw = sorted(v[2] - v[0] for v in keys.values())[len(keys) // 2]
    kh = sorted(v[3] - v[1] for v in keys.values())[len(keys) // 2]
    specials = [r for r in blanks
                if r[0] >= kx1 - kw // 2 and r[2] <= kx2 + kw // 2 and r[1] >= ky1 - kh // 2 and r[3] <= ky2 + 2 * kh
                and 0.6 * kh <= (r[3] - r[1]) <= 1.5 * kh and (r[2] - r[0]) >= 0.6 * kw]
    specials = sorted(set(specials), key=lambda r: (r[1], r[0]))
    if specials:
        widest = max(specials, key=lambda r: r[2] - r[0])
        if widest[2] - widest[0] >= 2.5 * kw:
            keys[" "] = widest
        n = 0
        for r in specials:
            if r != keys.get(" "):
                n += 1
                keys[f"#{n}"] = r
    # řádky podle středu na ose y
    rows: list[list[str]] = []
    for ch in sorted(keys, key=lambda k: ((keys[k][1] + keys[k][3]) / 2, keys[k][0])):
        cy = (keys[ch][1] + keys[ch][3]) / 2
        if rows and abs(cy - (keys[rows[-1][0]][1] + keys[rows[-1][0]][3]) / 2) <= kh / 2:
            rows[-1].append(ch)
        else:
            rows.append([ch])
    for row in rows:
        row.sort(key=lambda k: keys[k][0])
    return {"keys": keys, "rows": rows, "screen": (sw, sh)}


def keyboard_path(kb: dict[str, Any], start: str, target: str) -> list[str]:
    """Šipky z klávesy `start` na `target`: nejdřív svisle (do nejbližší klávesy podle osy x), pak vodorovně."""
    keys, rows = kb["keys"], kb["rows"]
    where = {ch: (ri, row.index(ch)) for ri, row in enumerate(rows) for ch in row}
    cx = lambda ch: (keys[ch][0] + keys[ch][2]) / 2  # noqa: E731
    ri, _ = where[start]
    tr, _ = where[target]
    cur, moves = start, []
    while ri != tr:
        ri += 1 if tr > ri else -1
        x = cx(cur)
        cur = min(rows[ri], key=lambda k: abs(cx(k) - x))
        moves.append("KEYCODE_DPAD_DOWN" if tr > where[start][0] else "KEYCODE_DPAD_UP")
    ci, tc = rows[ri].index(cur), rows[ri].index(target)
    moves += ["KEYCODE_DPAD_RIGHT" if tc > ci else "KEYCODE_DPAD_LEFT"] * abs(tc - ci)
    return moves


def focused_key(kb: dict[str, Any], raw: bytes, debug: list[str] | None = None) -> str | None:
    """Zvýrazněná klávesa ze snímku obrazovky (screencap bez -p: hlavička + RGBA).
    Hledá klávesu, jejíž okraj (bez znaku uprostřed) se jasem nejvíc liší od ostatních."""
    if len(raw) < 16:
        return None
    w, h, _fmt = struct.unpack_from("<III", raw)
    hdr = len(raw) - w * h * 4
    if w <= 0 or h <= 0 or hdr not in (12, 16):
        return None
    sw, sh = kb["screen"]
    sx, sy = w / max(sw, 1), h / max(sh, 1)
    lum: dict[str, float] = {}
    for ch, (x1, y1, x2, y2) in kb["keys"].items():
        vals = []
        for fx, fy in ((.1, .15), (.5, .1), (.9, .15), (.08, .5), (.92, .5), (.1, .85), (.5, .9), (.9, .85)):
            px = min(w - 1, max(0, int((x1 + (x2 - x1) * fx) * sx)))
            py = min(h - 1, max(0, int((y1 + (y2 - y1) * fy) * sy)))
            o = hdr + (py * w + px) * 4
            vals.append((raw[o] + raw[o + 1] + raw[o + 2]) / 3)
        lum[ch] = sum(vals) / len(vals)
    med = sorted(lum.values())[len(lum) // 2]
    dev = sorted(((abs(v - med), ch) for ch, v in lum.items()), reverse=True)
    if debug is not None:
        debug.append(f"snímek {w}x{h}, medián jasu {med:.0f}, nejvíc odlišné: "
                     + ", ".join(f"{ch!r}={lum[ch]:.0f}" for _d, ch in dev[:4]))
    if dev[0][0] >= 30 and (len(dev) < 2 or dev[1][0] <= dev[0][0] / 2):
        return dev[0][1]
    return None


class TV:
    def __init__(self, mgr: Manager, rec: dict[str, Any]) -> None:
        self.mgr = mgr
        self.rec = rec
        self.remote: AndroidTVRemote | None = None
        self.available = False
        self._connect_task: asyncio.Task | None = None
        self._poke = asyncio.Event()           # okamžitý nový pokus o připojení (mDNS, buzení)
        self._fast_until = 0.0                 # po buzení zkoušet připojení častěji
        self._pairing: AndroidTVRemote | None = None
        self.helper: HelperClient | None = None
        self.helper_info: dict[str, Any] | None = None
        self.helper_update: dict[str, Any] = {}  # automatická aktualizace pomocníka (stav pro web)
        self._helper_failures = 0
        self._icons: dict[str, bytes] = {}
        self.nowplaying: dict[str, Any] | None = None
        self._np_sent_at = 0.0
        self._volume_task: asyncio.Task | None = None
        self.ime: dict[str, Any] = {"active": False, "value": "", "label": ""}
        self._typed = ""                       # co je podle nás v poli na TV (bez ozvěny z TV)
        self._kbd_cache: dict[str, dict[str, Any]] = {}  # klávesnice aplikace na obrazovce
        self._kbd_focus: tuple[str, str, float] | None = None  # (aplikace, klávesa, čas) – kde je podle nás zvýraznění
        self._ime_target: str | None = None    # nejnovější požadovaný obsah pole od klienta
        self._ime_wake = asyncio.Event()       # nový požadavek k odeslání
        self._ime_echo = asyncio.Event()       # TV potvrdila obsah pole
        self._ime_task: asyncio.Task | None = None
        self._echo_seen = False

    # --- základní vlastnosti -------------------------------------------------
    @property
    def id(self) -> str:
        return self.rec["id"]

    @property
    def host(self) -> str | None:
        return self.rec.get("host")

    def snapshot(self) -> dict[str, Any]:
        r = self.remote if self.available else None
        return {
            "id": self.id,
            "name": self.rec.get("name") or self.id,
            "host": self.host,
            "paired": self.rec.get("paired", False),
            "adopted": self.rec.get("adopted", False),
            "order": self.rec.get("order"),
            "online": self.available,
            "is_on": r.is_on if r else None,
            "current_app": r.current_app if r else None,
            "volume": dict(r.volume_info) if r and r.volume_info else None,
            "device_info": dict(r.device_info) if r and r.device_info else None,
            "helper": {"connected": self.helper is not None, **(self.helper_info or {}),
                       "update": {k: v for k, v in self.helper_update.items() if k != "at"} or None},
            "ime": self.ime,
            "adb": bool(self.rec.get("adb_port")),
            "text_modes": dict(self.rec.get("text_modes") or {}),
        }

    def publish(self) -> None:
        self.mgr.bus.publish({"type": "tv", "tv": self.snapshot()})

    def _save(self) -> None:
        self.mgr.store.save()

    # --- připojení -----------------------------------------------------------
    def _new_remote(self) -> Remote:
        return Remote(CLIENT_NAME, self.mgr.certfile, self.mgr.keyfile, self.host or "", ime_callback=self._on_ime)

    def _on_ime(self, ev: dict[str, Any]) -> None:
        """TV hlásí otevřené pole (open), jeho skutečný obsah po úpravě (echo) nebo zavření (close)."""
        kind = ev["event"]
        if kind == "close":
            self.ime = {"active": False, "value": "", "label": ""}
            self._typed = ""
        else:
            label = ev.get("label") or self.ime.get("label", "")
            self.ime = {"active": True, "value": ev.get("value", ""), "label": label}
            self._typed = self.ime["value"]
            self._echo_seen = True
            self._ime_echo.set()
        self.mgr.bus.publish({"type": "ime", "tv_id": self.id, "ime": self.ime})

    def _on_app_change(self) -> None:
        self._typed = ""
        self._kbd_cache = {}
        self._kbd_focus = None
        if self.ime.get("active"):
            self.ime = {"active": False, "value": "", "label": ""}
            self.mgr.bus.publish({"type": "ime", "tv_id": self.id, "ime": self.ime})
        self.publish()

    def _teardown(self) -> None:
        if self._connect_task:
            self._connect_task.cancel()
            self._connect_task = None
        if self.remote:
            self.remote.disconnect()
            self.remote = None
        self.available = False

    async def restart(self) -> None:
        self._teardown()
        if self.rec.get("paired") and self.host:
            self._connect_task = asyncio.create_task(self._connect_loop())
        self.publish()

    async def set_host(self, host: str) -> None:
        if host == self.host and (self.remote or self._connect_task or not self.rec.get("paired")):
            return
        if host != self.host:
            LOG.info("TV %s: nová IP %s (předtím %s)", self.id, host, self.host)
            self.rec["host"] = host
            self._save()
            self.helper = None
            self.helper_info = None
        await self.restart()

    async def _connect_loop(self) -> None:
        delay = 5
        while True:
            r = self._new_remote()
            try:
                await r.async_connect()
            except InvalidAuth:
                r.disconnect()
                LOG.warning("TV %s: párování zneplatněno, je nutné spárovat znovu", self.id)
                self.rec["paired"] = False
                self._save()
                self.publish()
                return
            except (CannotConnect, ConnectionClosed) as exc:
                r.disconnect()
                wait = 3 if time.monotonic() < self._fast_until else delay
                LOG.info("TV %s (%s) nedostupná: %s; zkusím znovu za %ss", self.id, self.host, exc, wait)
                self.mgr.request_rediscovery(self)
                self._poke.clear()
                try:
                    await asyncio.wait_for(self._poke.wait(), wait)
                    LOG.info("TV %s: nový pokus o připojení hned (mDNS / buzení)", self.id)
                    delay = 5
                except asyncio.TimeoutError:
                    delay = min(delay * 2, 30)
                continue
            except asyncio.CancelledError:
                r.disconnect()
                raise
            break

        self.remote = r
        self.available = True
        self._connect_task = None
        self._fast_until = 0.0
        hw = wol.arp_mac(self.host)  # skutečná MAC rozhraní (pro Wake-on-LAN), může se lišit od MAC v certifikátu
        if hw and hw != self.rec.get("hw_mac"):
            self.rec["hw_mac"] = hw
            self._save()
        r.add_is_on_updated_callback(lambda _: self.publish())
        r.add_current_app_updated_callback(lambda _: self._on_app_change())
        r.add_volume_info_updated_callback(lambda _: self.publish())
        r.add_is_available_updated_callback(self._on_available)
        r.keep_reconnecting(self._on_invalid_auth)
        LOG.info("TV %s připojena (%s)", self.id, self.host)
        self.publish()
        asyncio.create_task(self.ensure_helper())

    def _on_available(self, available: bool) -> None:
        self.available = available
        if not available:
            self.mgr.request_rediscovery(self)
        self.publish()

    def _on_invalid_auth(self) -> None:
        self.rec["paired"] = False
        self._save()
        self._teardown()
        self.publish()

    # --- párování ------------------------------------------------------------
    async def start_pairing(self) -> None:
        self._teardown()
        if self._pairing:
            self._pairing.disconnect()
        self._pairing = self._new_remote()
        await self._pairing.async_start_pairing()

    async def finish_pairing(self, code: str) -> None:
        if not self._pairing:
            raise RuntimeError("párování nebylo zahájeno")
        try:
            await self._pairing.async_finish_pairing(code.strip().upper())
        finally:
            self._pairing.disconnect()
            self._pairing = None
        self.rec["paired"] = True
        self._save()
        await self.restart()

    # --- příkazy -------------------------------------------------------------
    def _r(self) -> AndroidTVRemote:
        if not self.remote or not self.available:
            raise NotConnected("TV není připojena")
        return self.remote

    def poke(self) -> None:
        """TV se ohlásila v síti (mDNS) – nečekat na další pokus podle prodlevy."""
        if self._connect_task and not self.available:
            self._poke.set()

    def wake(self) -> list[str]:
        """Wake-on-LAN na TV, která je mimo síť; další minutu pak zkouší připojení každé 3 s."""
        used = wol.send([self.rec.get("hw_mac") or "", self.id], self.host)
        self._fast_until = time.monotonic() + 60
        self.poke()
        return used

    def send_key(self, key: str, direction: str = "SHORT") -> None:
        self._r().send_key_command(keys.resolve(key), direction)

    def send_text(self, text: str) -> None:
        """Klient posílá požadovaný CELÝ obsah pole. Úpravy se na TV posílají postupně:
        smazání koncové části klávesou DEL + vložení nového konce, mezi nimi se čeká na ozvěnu z TV."""
        self._r()
        self._ime_target = text
        self._ime_wake.set()
        if not self._ime_task or self._ime_task.done():
            self._ime_task = asyncio.create_task(self._ime_worker())

    async def _await_echo(self, value: str) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 1.0
        while self._typed != value and self.ime.get("active"):
            self._ime_echo.clear()
            left = deadline - loop.time()
            if left <= 0:
                return
            try:
                await asyncio.wait_for(self._ime_echo.wait(), left)
            except asyncio.TimeoutError:
                return

    async def _ime_worker(self) -> None:
        while True:
            await self._ime_wake.wait()
            self._ime_wake.clear()
            target = self._ime_target
            if target is None:
                continue
            try:
                r = self._r()
            except NotConnected:
                return
            assert isinstance(r, Remote)
            # Automaticky: když TV otevřela systémové textové pole -> IME (Remote protocol).
            # Jinak (aplikace s vlastní klávesnicí: Netflix, Oneplay, Prima+ …) přes ADB, pokud je ověřené.
            if self.rec.get("adb_port") and not self.ime.get("active"):
                await self._type_keys(target)
                continue
            base = self._typed  # skutečný obsah pole z ozvěny TV, když ji TV posílá
            i = 0
            while i < len(base) and i < len(target) and base[i] == target[i]:
                i += 1
            dels, add = len(base) - i, target[i:]
            LOG.info("IME: pole %r -> %r: smazat %d, vložit %r", base, target, dels, add)
            for _ in range(dels):
                r.send_key_command("KEYCODE_DEL")
            if dels and add:
                await self._await_echo(target[:i])
            self._echo_seen = False
            r.insert_text(add)
            if self.ime.get("active") and (dels or add):
                await self._await_echo(target)
            if not self._echo_seen:
                # TV obsah pole nepotvrdila (např. vlastní klávesnice aplikace) -> počítáme sami
                self._typed = target

    def set_text_mode(self, package: str, mode: str) -> None:
        """Způsob psaní pro jednu aplikaci: "ime" (výchozí, Remote protocol) nebo "keys"
        (ADB `input` – pro aplikace s vlastní klávesnicí, které IME nepřijímají)."""
        if not package:
            raise ValueError("chybí package nebo link")
        modes = self.rec.setdefault("text_modes", {})
        if mode == "keys":
            if not self.rec.get("adb_port"):
                raise ValueError("psaní přes ADB vyžaduje ověřené ADB – otestujte připojení u pomocníka na zařízení")
            modes[package] = "keys"
        else:
            modes.pop(package, None)
        self._kbd_cache = {}
        self._kbd_focus = None
        LOG.info("TV %s: způsob psaní v %s: %s", self.id, package, "ADB (klávesnice)" if mode == "keys" else "IME")
        self._save()
        self.publish()

    async def _type_keys(self, target: str) -> None:
        """Psaní jako z fyzické klávesnice přes ADB: DEL + `input text`.
        `input text` umí jen znaky z mapy kláves – diakritika se odešle bez háčků a čárek."""
        from . import adb  # pozdní import kvůli cyklu
        base = self._typed
        i = 0
        while i < len(base) and i < len(target) and base[i] == target[i]:
            i += 1
        dels, add = len(base) - i, target[i:]
        plain = "".join(c for c in unicodedata.normalize("NFKD", add) if not unicodedata.combining(c) and c.isascii() and (c.isprintable()))
        port = self.rec.get("adb_port")
        if not (self.host and port):
            self.mgr.bus.publish({"type": "text_error", "tv_id": self.id, "error": "no-adb"})
            return
        parts = []
        if dels:
            parts.append("input keyevent " + " ".join(["67"] * dels))
        try:
            kb = await self._screen_keyboard(int(port)) if plain else {}
            if dels:
                await adb.shell(self.host or "", int(port), parts.pop(0))
            if kb:
                # Klávesnice aplikace na obrazovce (Oneplay …): šipkami na písmeno a OK.
                done = await self._type_dpad(int(port), kb, plain)
                how = f"šipkami na klávesnici aplikace ({done}/{len(plain)} znaků)"
                LOG.info("Psaní přes ADB %s: pole %r -> %r: smazat %d, vložit %r", how, base, target, dels, plain)
                if done < len(plain):
                    self.mgr.bus.publish({"type": "text_error", "tv_id": self.id, "error": "no-focus"})
                    return
            else:
                if plain:
                    parts.append("input text " + shlex.quote(plain.replace(" ", "%s")))
                how = "jako klávesnice" if plain else "jen mazání"
                LOG.info("Psaní přes ADB %s: pole %r -> %r: smazat %d, vložit %r", how, base, target, dels, plain)
                if parts:
                    await adb.shell(self.host, int(port), "; ".join(parts))
            self._typed = target
        except (adb.AdbError, NotConnected) as exc:
            LOG.warning("TV %s: psaní přes ADB selhalo: %s", self.id, exc)
            self.mgr.bus.publish({"type": "text_error", "tv_id": self.id, "error": str(exc)})

    async def _type_dpad(self, port: int, kb: dict[str, Any], text: str) -> int:
        """Napíše `text` na klávesnici aplikace šipkami + OK. Vrací počet napsaných znaků."""
        from . import adb  # pozdní import kvůli cyklu
        r = self._r()
        app = (self.remote.current_app if self.remote else None) or ""
        loop = asyncio.get_running_loop()
        cur = None
        # Polohu zvýraznění převzít jen při plynulém psaní (< 1,5 s od posledního stisku). Jinak mohl někdo
        # pohnout klasickým ovladačem -> nový snímek obrazovky.
        if self._kbd_focus and self._kbd_focus[0] == app and loop.time() - self._kbd_focus[2] < 1.5:
            cur = self._kbd_focus[1]
        if cur is None:
            raw = await adb.exec_out(self.host or "", port, "screencap")
            dbg: list[str] = []
            cur = focused_key(kb, raw, dbg)
            LOG.info("TV %s: zvýrazněná klávesa podle snímku obrazovky: %r (%s)", self.id, cur, "; ".join(dbg))
            if cur is None:
                return 0
        done = 0
        for ch in text.lower():
            if ch not in kb["keys"]:
                done += 1  # znak klávesnice nemá (interpunkce …) – vynechat
                continue
            for key in keyboard_path(kb, cur, ch):
                r.send_key_command(key)
                await asyncio.sleep(0.07)
            r.send_key_command("KEYCODE_DPAD_CENTER")
            await asyncio.sleep(0.15)
            cur = ch
            done += 1
            self._kbd_focus = (app, cur, loop.time())
        return done

    async def _screen_keyboard(self, port: int) -> dict[str, Any]:
        """Najde klávesnici vykreslenou aplikací (prvky s jedním znakem a–z, 0–9) přes uiautomator.
        Výsledek se pamatuje pro aktuální aplikaci do změny aplikace."""
        from . import adb  # pozdní import kvůli cyklu
        app = (self.remote.current_app if self.remote else None) or ""
        cached = self._kbd_cache.get(app)
        if cached is not None:
            return cached
        xml = await adb.shell(self.host or "", port,
                              "uiautomator dump /sdcard/hm_ui.xml >/dev/null 2>&1; cat /sdcard/hm_ui.xml; rm -f /sdcard/hm_ui.xml")
        keymap = parse_screen_keyboard(xml)
        LOG.info("TV %s: klávesnice na obrazovce v %s: %s", self.id, app or "?",
                 f"{len(keymap['keys'])} kláves v {len(keymap['rows'])} řadách" if keymap else "nenalezena (psaní jako klávesnice)")
        self._kbd_cache[app] = keymap
        return keymap

    async def ui_dump(self) -> str:
        """Rozložení aktuální obrazovky (uiautomator) – diagnostika aplikací s vlastní klávesnicí."""
        from . import adb  # pozdní import kvůli cyklu
        port = self.rec.get("adb_port")
        if not (self.host and port):
            raise ValueError("ADB není nastavené – otestujte připojení u pomocníka na zařízení")
        out = await adb.shell(self.host, int(port),
                              "uiautomator dump /sdcard/hm_ui.xml >/dev/null 2>&1; cat /sdcard/hm_ui.xml; rm -f /sdcard/hm_ui.xml")
        return out

    async def launch(self, package_or_link: str) -> str:
        """Spustí aplikaci. Vrací použitou cestu ("helper" / "remote").

        Balíček: přednostně přes helper (od srpna 2026 řada TV odmítá market://launch?id=…),
        jinak Remote protocol. URL (deep link): vždy Remote protocol.
        """
        is_link = "://" in package_or_link
        if not is_link and self.helper:
            try:
                await self.helper.launch(package_or_link)
                return "helper"
            except HELPER_ERRORS as exc:
                LOG.info("TV %s: spuštění přes helper selhalo (%s), zkouším Remote protocol", self.id, exc)
        self._r().send_launch_app_command(package_or_link)
        return "remote"

    def adopt(self) -> None:
        self.rec["adopted"] = True
        self._save()
        self.publish()

    def rename(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("název nesmí být prázdný")
        self.rec["name"] = name[:60]
        self._save()
        self.publish()

    async def set_volume(self, level: int) -> None:
        """Remote protocol umí jen kroky nahoru/dolů – dopočítá a pošle potřebný počet kroků."""
        r = self._r()
        vi = r.volume_info
        if not vi:
            raise NotConnected("TV zatím nehlásí hlasitost")
        level = max(0, min(int(level), int(vi["max"])))
        if self._volume_task and not self._volume_task.done():
            self._volume_task.cancel()
        self._volume_task = asyncio.create_task(self._volume_steps(level))

    async def _volume_steps(self, target: int) -> None:
        for _attempt in range(2):  # druhý průchod opraví případně ztracené kroky
            r = self._r()
            current = int((r.volume_info or {}).get("level", target))
            diff = target - current
            if diff == 0:
                return
            key = "KEYCODE_VOLUME_UP" if diff > 0 else "KEYCODE_VOLUME_DOWN"
            for _ in range(abs(diff)):
                r.send_key_command(key)
                await asyncio.sleep(0.06)
            await asyncio.sleep(0.8)  # počkat na hlášení skutečné hodnoty z TV

    # --- helper ----------------------------------------------------------------
    async def ensure_helper(self, port: int | None = None) -> bool:
        if not self.host:
            return False
        port = port or self.rec.get("helper_port") or DEFAULT_HELPER_PORT
        hc = HelperClient(self.mgr.session, self.host, port, self.mgr.store.helper_token)
        try:
            await hc.claim()
            info = await hc.info()
        except HELPER_ERRORS as exc:
            msg = str(exc) or exc.__class__.__name__
            if isinstance(exc, HelperError) and exc.status == 403:
                msg = "helper patří jinému backendu (token nesouhlasí) – reset dat helperu na TV"
            self.helper = None
            self.helper_info = {"error": msg}
            self.publish()
            return False
        self.helper = hc
        self.helper_info = info
        self._helper_failures = 0
        if self.rec.get("helper_port") != port:
            self.rec["helper_port"] = port
            self._save()
        LOG.info("TV %s: helper připojen (%s:%s) %s", self.id, self.host, port, info)
        self.publish()
        self._maybe_update_helper()
        return True

    def _maybe_update_helper(self) -> None:
        """Automatická aktualizace pomocníka na verzi z image backendu (přes ověřené ADB)."""
        bundle = self.mgr.helper_bundle() if self.mgr.helper_bundle else None
        running = (self.helper_info or {}).get("version")
        port = self.rec.get("adb_port")
        if not bundle or not running or not port or not self.host:
            return
        version, apk = bundle
        if not _ver(version) or not _ver(running) or _ver(version) <= _ver(running):
            if self.helper_update.get("state") == "updating":
                return
            if self.helper_update:
                self.helper_update = {}
                self.publish()
            return
        last = self.helper_update
        if last.get("version") == version and (last.get("state") == "updating"
                                               or time.monotonic() - last.get("at", 0) < 3600):
            return  # běží, nebo nedávno selhala – další pokus nejdřív za hodinu
        self.helper_update = {"version": version, "from": running, "state": "updating", "at": time.monotonic()}
        self.publish()
        asyncio.create_task(self._update_helper(version, apk, int(port)))

    async def _update_helper(self, version: str, apk: str, port: int) -> None:
        from . import adb  # pozdní import kvůli cyklu
        LOG.info("TV %s: aktualizuji pomocníka %s → %s", self.id, self.helper_update.get("from"), version)
        try:
            for line in await adb.setup_helper(self.host or "", apk, connect_port=port):
                LOG.info("TV %s: helper update: %s", self.id, line)
            self.helper_update = {**self.helper_update, "state": "done", "at": time.monotonic()}
            LOG.info("TV %s: pomocník aktualizován na %s", self.id, version)
        except Exception as exc:  # noqa: BLE001 – zkusí se znovu za hodinu, ručně z okna Pomocník
            err = str(exc) or exc.__class__.__name__
            self.helper_update = {**self.helper_update, "state": "failed", "error": err, "at": time.monotonic()}
            LOG.warning("TV %s: aktualizace pomocníka selhala: %s", self.id, err)
        self.publish()
        await asyncio.sleep(3)
        await self.ensure_helper()

    def _h(self) -> HelperClient:
        if not self.helper:
            raise HelperUnavailable("helper na TV není dostupný")
        return self.helper

    async def apps(self) -> list[dict[str, Any]]:
        apps = await self._h().apps()
        hidden = set(self.rec["hidden_apps"])
        out = [{**a, "hidden": a["package"] in hidden} for a in apps]
        out.sort(key=lambda a: (a.get("label") or a["package"]).lower())
        # Uživatelské pořadí (přetažením ve webu); nově nainstalované aplikace na konec podle názvu.
        rank = {pkg: i for i, pkg in enumerate(self.rec.get("app_order") or [])}
        out.sort(key=lambda a: rank.get(a["package"], len(rank)))
        return out

    def set_app_order(self, order: list[Any]) -> None:
        if not isinstance(order, list) or not all(isinstance(p, str) and p for p in order):
            raise ValueError("chybí pole order")
        seen: list[str] = []
        for pkg in order:
            if pkg not in seen:
                seen.append(pkg[:200])
        self.rec["app_order"] = seen[:500]
        self._save()

    async def icon(self, package: str) -> bytes:
        if package not in self._icons:
            self._icons[package] = await self._h().icon(package)
        return self._icons[package]

    def set_hidden(self, package: str, hidden: bool) -> None:
        lst: list[str] = self.rec["hidden_apps"]
        if hidden and package not in lst:
            lst.append(package)
        elif not hidden and package in lst:
            lst.remove(package)
        self._save()

    async def inputs(self) -> list[dict[str, Any]]:
        return await self._h().inputs()

    async def select_input(self, input_id: str) -> None:
        await self._h().select_input(input_id)

    async def open_settings(self) -> str:
        """Nastavení Androidu na zařízení. Pořadí: pomocník → ADB (když už bylo jednou ověřené)
        → klávesa SETTINGS (část zařízení ji přes Remote protocol ignoruje)."""
        if self.helper:
            try:
                await self.helper.open_settings()
                return "helper"
            except HELPER_ERRORS as exc:
                LOG.info("TV %s: otevření nastavení přes helper selhalo (%s)", self.id, exc)
        if self.host and self.rec.get("adb_port"):
            from . import adb  # pozdní import kvůli cyklu
            try:
                await adb.shell_once(self.host, int(self.rec["adb_port"]), "am", "start", "-a", "android.settings.SETTINGS")
                return "adb"
            except adb.AdbError as exc:
                LOG.info("TV %s: otevření nastavení přes ADB selhalo (%s)", self.id, exc)
        self._r().send_key_command("KEYCODE_SETTINGS")
        return "remote"

    async def fetch_nowplaying(self) -> dict[str, Any]:
        np = await self._h().nowplaying()
        np["fetched_at_ms"] = int(time.time() * 1000)
        return np

    async def seek(self, position_ms: int) -> None:
        await self._h().seek(position_ms)
        await self.poll_nowplaying(force=True)

    async def poll_nowplaying(self, force: bool = False) -> None:
        """Načte stav přehrávání a rozešle ho jen při změně (pozici si klient dopočítává)."""
        if not self.helper:
            return
        try:
            np = await self.fetch_nowplaying()
        except HELPER_ERRORS as exc:
            self._helper_failures += 1
            if self._helper_failures >= 3:
                LOG.info("TV %s: helper přestal odpovídat (%s)", self.id, str(exc) or exc.__class__.__name__)
                self.helper = None
                self.helper_info = {"error": str(exc) or exc.__class__.__name__}
                self.publish()
            return
        self._helper_failures = 0
        if force or self._np_changed(self.nowplaying, np):
            self.mgr.bus.publish({"type": "nowplaying", "tv_id": self.id, "data": np})
            self._np_sent_at = time.monotonic()
        self.nowplaying = np

    def _np_changed(self, old: dict[str, Any] | None, new: dict[str, Any]) -> bool:
        if old is None:
            return True
        fields = ("active", "package", "title", "subtitle", "state", "duration_ms", "can_seek", "speed")
        if any(old.get(f) != new.get(f) for f in fields):
            return True
        if time.monotonic() - self._np_sent_at > 10:
            return True
        # skok v pozici (seek z TV/ovladače) – porovnání s extrapolací
        if new.get("state") == "playing" and old.get("position_ms") is not None:
            elapsed = new["fetched_at_ms"] - old["fetched_at_ms"]
            expected = old["position_ms"] + elapsed * (old.get("speed") or 1.0)
        else:
            expected = old.get("position_ms") or 0
        return abs((new.get("position_ms") or 0) - expected) > 2000


def _ver(v: Any) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", str(v or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


class Manager:
    def set_order(self, order: list[Any]) -> None:
        """Pořadí záložek zařízení (přetažením ve webu); zařízení mimo seznam jdou na konec."""
        if not isinstance(order, list) or not all(isinstance(i, str) for i in order):
            raise ValueError("chybí pole order")
        ids = [i for i in dict.fromkeys(order) if i in self.tvs]
        rest = sorted((tv for tv in self.tvs.values() if tv.id not in ids),
                      key=lambda tv: (tv.rec.get("order") is None, tv.rec.get("order") or 0))
        for i, tv in enumerate([self.tvs[i] for i in ids] + rest):
            tv.rec["order"] = i
        self.store.save()
        for tv in self.tvs.values():
            tv.publish()

    def __init__(self, store: Store, bus: Bus, data_dir: str) -> None:
        self.store = store
        self.bus = bus
        self.data_dir = data_dir
        self.certfile = os.path.join(data_dir, "cert.pem")
        self.keyfile = os.path.join(data_dir, "key.pem")
        self.tvs: dict[str, TV] = {}
        self.session: aiohttp.ClientSession | None = None
        self.discovery = None  # nastaví main
        self.helper_bundle: Any = None  # () -> (verze, cesta k helper.apk) | None – nastaví main
        self._tasks: list[asyncio.Task] = []
        self._identify_lock = asyncio.Lock()

    async def start(self) -> None:
        self.session = aiohttp.ClientSession()
        await AndroidTVRemote(CLIENT_NAME, self.certfile, self.keyfile, "").async_generate_cert_if_missing()
        for rec in list(self.store.data["devices"].values()):
            tv = TV(self, self.store.device(rec["id"]))
            self.tvs[tv.id] = tv
            await tv.restart()  # zkusí poslední známou IP, mDNS případně opraví
        self._tasks = [asyncio.create_task(self._poll_loop()), asyncio.create_task(self._watchdog())]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for tv in self.tvs.values():
            tv._teardown()
        if self.session:
            await self.session.close()

    def get(self, tv_id: str) -> TV:
        return self.tvs[norm_mac(tv_id)]

    def _get_or_create(self, tv_id: str) -> TV:
        if tv_id not in self.tvs:
            self.tvs[tv_id] = TV(self, self.store.device(tv_id))
            self.store.save()
        return self.tvs[tv_id]

    async def identify(self, host: str) -> tuple[str, str]:
        """Jméno a MAC z TLS certifikátu TV (port 6467) – nevyžaduje párování."""
        probe = AndroidTVRemote(CLIENT_NAME, self.certfile, self.keyfile, host)
        name, mac = await probe.async_get_name_and_mac()
        return name, norm_mac(mac)

    async def on_tv_seen(self, service_name: str, host: str) -> None:
        known = next((t for t in self.tvs.values() if t.rec.get("service_name") == service_name), None)
        if known and known.host == host:
            if known.rec.get("paired") and not known.available:
                if known._connect_task:
                    known.poke()
                else:
                    await known.restart()
            return
        async with self._identify_lock:
            try:
                cert_name, tv_id = await self.identify(host)
            except CannotConnect:
                LOG.info("mDNS: %s (%s) nelze identifikovat", service_name, host)
                return
            tv = self._get_or_create(tv_id)
            tv.rec["service_name"] = service_name
            if not tv.rec.get("name"):
                tv.rec["name"] = service_name.removesuffix("." + REMOTE_TYPE) or cert_name
            self.store.save()
        await tv.set_host(host)
        tv.publish()

    async def add_manual(self, host: str) -> TV:
        cert_name, tv_id = await self.identify(host)
        tv = self._get_or_create(tv_id)
        if not tv.rec.get("name"):
            tv.rec["name"] = cert_name
        tv.rec["adopted"] = True  # zadáno ručně = uživatel ho chce
        self.store.save()
        await tv.set_host(host)
        tv.publish()
        return tv

    async def remove(self, tv_id: str) -> None:
        """Odebere TV z backendu (párování, název, skryté aplikace). Zapnutou TV mDNS hned najde znovu."""
        tv = self.get(tv_id)
        tv._teardown()
        if tv._pairing:
            tv._pairing.disconnect()
        service = tv.rec.get("service_name")
        del self.tvs[tv.id]
        self.store.data["devices"].pop(tv.id, None)
        self.store.save()
        self.bus.publish({"type": "tv_removed", "id": tv.id})
        if self.discovery and service:
            self.discovery.resolve_now(REMOTE_TYPE, service)

    async def on_helper_seen(self, host: str, port: int) -> None:
        for tv in self.tvs.values():
            if tv.host == host and not tv.available:
                tv.poke()  # pomocník se ohlásil = TV je v síti
            if tv.host == host and (not tv.helper or tv.rec.get("helper_port") != port):
                await tv.ensure_helper(port)

    def request_rediscovery(self, tv: TV) -> None:
        if self.discovery and tv.rec.get("service_name"):
            self.discovery.resolve_soon(REMOTE_TYPE, tv.rec["service_name"])

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(30)
            for tv in list(self.tvs.values()):
                if tv.available and not tv.helper:
                    await tv.ensure_helper()

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            if not self.bus.has_clients:
                continue
            tvs = [tv for tv in self.tvs.values() if tv.helper and tv.available]
            if tvs:
                await asyncio.gather(*(tv.poll_nowplaying() for tv in tvs), return_exceptions=True)
