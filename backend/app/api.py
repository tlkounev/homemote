"""REST + WebSocket API pro web a telefonní aplikaci (kontrakt viz API.md)."""
from __future__ import annotations

import asyncio
import io
import os
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import segno
import aiohttp
from aiohttp import web, WSMsgType
from androidtvremote2 import CannotConnect, ConnectionClosed, InvalidAuth

from . import adb
from .auth import AuthError, client_key, is_local_request
from .helper_client import HelperError
from .i18n import translate
from .version import VERSION
from .logbuf import RING
from .runtime import Runtime
from .tv import TV, HelperUnavailable, NotConnected

LOG = logging.getLogger(__name__)

RT = web.AppKey("rt", Runtime)
STATIC_DIR = Path(__file__).parent / "static"

# Cesty dostupné bez přihlášení
PUBLIC_PATHS = {"/api/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login", "/api/auth/redeem"}


def _lang(request: web.Request) -> str:
    return request.headers.get("X-Lang") or request.query.get("lang") or "cs"


def _err(status: int, msg: str, request: web.Request | None = None) -> web.Response:
    return web.json_response({"error": translate(msg, _lang(request) if request else None)}, status=status)


@web.middleware
async def errors_mw(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except AuthError as exc:
        return _err(exc.status, str(exc), request)
    except KeyError as exc:
        return _err(400, f"chybí pole {exc}", request)
    except (NotConnected, HelperUnavailable, ConnectionClosed) as exc:
        return _err(409, str(exc) or "nepřipojeno", request)
    except InvalidAuth:
        return _err(400, "neplatný kód / nespárováno", request)
    except CannotConnect as exc:
        return _err(502, f"TV nedostupná: {exc}", request)
    except HelperError as exc:
        if exc.status == 404:
            return _err(501, "tuto funkci nainstalovaný pomocník na TV neumí – aktualizujte ho", request)
        return _err(exc.status if exc.status < 500 else 502, f"pomocník na TV: {exc}", request)
    except adb.AdbError as exc:
        return _err(502, f"ADB: {exc}", request)
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        # pomocník na TV neodpovídá (TV vypnutá, v hlubokém spánku, mimo síť) – běžný stav, ne chyba backendu
        return _err(504, "zařízení neodpovídá – je vypnuté nebo mimo síť", request)
    except (ValueError, json.JSONDecodeError) as exc:
        return _err(400, str(exc), request)
    except Exception:
        LOG.exception("neošetřená chyba")
        return _err(500, "interní chyba", request)


@web.middleware
async def auth_mw(request: web.Request, handler):
    if request.path.startswith("/api") and request.path not in PUBLIC_PATHS:
        rt = request.app[RT]
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.query.get("token")
        dev = rt.auth.device_for(token)
        if not dev:
            return _err(401, "nepřihlášeno" if rt.auth.configured else "nejdřív je potřeba nastavit heslo", request)
        rt.auth.touch(dev)
        request["device"] = dev
    return await handler(request)


def _tv(request: web.Request) -> TV:
    try:
        return request.app[RT].mgr.get(request.match_info["tv_id"])
    except KeyError:
        raise web.HTTPNotFound(
            text=json.dumps({"error": translate("neznámá TV", _lang(request))}), content_type="application/json"
        ) from None


async def _body(request: web.Request) -> dict[str, Any]:
    if not request.can_read_body:
        return {}
    return await request.json()


def _ok(**extra: Any) -> web.Response:
    return web.json_response({"ok": True, **extra})


# --- přihlášení ------------------------------------------------------------------
async def auth_status(request: web.Request) -> web.Response:
    rt = request.app[RT]
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.query.get("token")
    return web.json_response(
        {
            "configured": rt.auth.configured,
            "setup_allowed": not rt.auth.configured and is_local_request(request),
            "authenticated": rt.auth.device_for(token) is not None,
        }
    )


async def auth_setup(request: web.Request) -> web.Response:
    b = await _body(request)
    token = request.app[RT].auth.setup(b.get("password", ""), b.get("device_name", ""), is_local_request(request))
    return _ok(token=token)


async def auth_login(request: web.Request) -> web.Response:
    b = await _body(request)
    token = request.app[RT].auth.login(
        b.get("password", ""), b.get("device_name", ""), client_key(request), b.get("kind", "browser")
    )
    return _ok(token=token)


async def auth_redeem(request: web.Request) -> web.Response:
    b = await _body(request)
    token = request.app[RT].auth.redeem(b.get("code", ""), b.get("device_name", ""), client_key(request))
    rt = request.app[RT]
    return _ok(token=token, endpoints=rt.endpoints())


async def auth_pair(request: web.Request) -> web.Response:
    """Jednorázový kód pro přihlášení telefonu + QR kód (SVG)."""
    rt = request.app[RT]
    code = rt.auth.pair_code()
    e = rt.endpoints()
    params = {"v": "1", "id": e["instance_id"], "code": code, "local": e["local"]}
    if e["public"]:
        params["public"] = e["public"]
    uri = "homemote://pair?" + urlencode(params)
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=6, border=2, omitsize=True, dark="#000", light="#fff", xmldecl=False)
    app = None
    if os.path.isfile(rt.phone_apk):
        url = (e["public"] or e["local"]).rstrip("/") + "/download/homemote.apk"
        abuf = io.BytesIO()
        segno.make(url, error="m").save(abuf, kind="svg", scale=5, border=2, omitsize=True, dark="#000", light="#fff", xmldecl=False)
        app = {"url": url, "svg": abuf.getvalue().decode()}
    return web.json_response({"code": code, "uri": uri, "svg": buf.getvalue().decode(), "expires_in": 300, "app": app})


async def android_status(request: web.Request) -> web.Response:
    rt = request.app[RT]
    return web.json_response(rt.android.status() if rt.android else {"state": "unavailable", "apps": {}})


async def download_phone_apk(request: web.Request) -> web.StreamResponse:
    """Aplikace Homemote pro Android (sestavená do složky data). Veřejné – APK neobsahuje žádná tajemství."""
    path = request.app[RT].phone_apk
    if not os.path.isfile(path):
        raise web.HTTPNotFound(text="homemote.apk zatím není sestavené")
    return web.FileResponse(path, headers={
        "Content-Type": "application/vnd.android.package-archive",
        "Content-Disposition": 'attachment; filename="homemote.apk"',
        "Cache-Control": "no-cache",
    })


async def auth_devices(request: web.Request) -> web.Response:
    me = request["device"]["id"]
    return web.json_response([{**d, "current": d["id"] == me} for d in request.app[RT].auth.devices()])


async def auth_revoke(request: web.Request) -> web.Response:
    dev_id = request.match_info["dev_id"]
    request.app[RT].auth.revoke(dev_id)
    request.app[RT].bus.close_device(dev_id)
    return _ok()


async def auth_logout(request: web.Request) -> web.Response:
    dev_id = request["device"]["id"]
    request.app[RT].auth.revoke(dev_id)
    request.app[RT].bus.close_device(dev_id)
    return _ok()


async def auth_password(request: web.Request) -> web.Response:
    b = await _body(request)
    request.app[RT].auth.change_password(b.get("old", ""), b.get("new", ""))
    return _ok()


# --- obecné ------------------------------------------------------------------------
async def health(request: web.Request) -> web.Response:
    # Bez přihlášení: telefon tím ověřuje dosažitelnost a že jde o "jeho" backend.
    return web.json_response({"ok": True, "instance_id": request.app[RT].store.instance_id, "version": VERSION})


async def logs(request: web.Request) -> web.Response:
    return web.json_response({"lines": RING.get(request.query.get("q", ""), int(request.query.get("limit", "400")))})


async def endpoints(request: web.Request) -> web.Response:
    return web.json_response(request.app[RT].endpoints())


async def get_settings(request: web.Request) -> web.Response:
    return web.json_response(request.app[RT].public_settings())


async def put_settings(request: web.Request) -> web.Response:
    return web.json_response(await request.app[RT].update_settings(await _body(request)))


# --- televize ------------------------------------------------------------------------
async def list_tvs(request: web.Request) -> web.Response:
    return web.json_response([tv.snapshot() for tv in request.app[RT].mgr.tvs.values()])


async def tv_order(request: web.Request) -> web.Response:
    request.app[RT].mgr.set_order((await _body(request)).get("order"))
    return _ok()


async def add_tv(request: web.Request) -> web.Response:
    host = (await _body(request)).get("host")
    if not host:
        raise ValueError("chybí IP adresa")
    tv = await request.app[RT].mgr.add_manual(host)
    return web.json_response(tv.snapshot())


async def get_tv(request: web.Request) -> web.Response:
    return web.json_response(_tv(request).snapshot())


async def update_tv(request: web.Request) -> web.Response:
    b = await _body(request)
    tv = _tv(request)
    if "name" in b:
        tv.rename(b["name"])
    return web.json_response(tv.snapshot())


async def remove_tv(request: web.Request) -> web.Response:
    await request.app[RT].mgr.remove(_tv(request).id)
    return _ok()


async def pair_start(request: web.Request) -> web.Response:
    await _tv(request).start_pairing()
    return _ok(hint="zadejte kód zobrazený na TV")


async def pair_finish(request: web.Request) -> web.Response:
    code = (await _body(request)).get("code", "")
    if not code:
        raise ValueError("chybí kód")
    tv = _tv(request)
    await tv.finish_pairing(code)
    return web.json_response(tv.snapshot())


async def _do_key(tv: TV, key: str, direction: str = "SHORT") -> str:
    if key == "settings":
        return await tv.open_settings()
    if key == "power" and not tv.available and tv.rec.get("paired"):
        if direction != "END_LONG":
            tv.wake()  # TV v hlubokém spánku: Wake-on-LAN, připojení se pak zkouší každé 3 s
        return "wol"
    tv.send_key(key, direction)
    return "remote"


async def key(request: web.Request) -> web.Response:
    b = await _body(request)
    via = await _do_key(_tv(request), b["key"], b.get("direction", "SHORT"))
    return _ok(via=via)


async def text(request: web.Request) -> web.Response:
    _tv(request).send_text((await _body(request))["text"])
    return _ok()


async def volume(request: web.Request) -> web.Response:
    await _tv(request).set_volume(int((await _body(request))["level"]))
    return _ok()


async def inputs(request: web.Request) -> web.Response:
    return web.json_response(await _tv(request).inputs())


async def select_input(request: web.Request) -> web.Response:
    await _tv(request).select_input((await _body(request))["id"])
    return _ok()


async def launch(request: web.Request) -> web.Response:
    b = await _body(request)
    target = b.get("package") or b.get("link")
    if not target:
        raise ValueError("chybí package nebo link")
    via = await _tv(request).launch(target)
    return _ok(via=via)


async def apps(request: web.Request) -> web.Response:
    lst = await _tv(request).apps()
    if request.query.get("include_hidden") not in ("1", "true"):
        lst = [a for a in lst if not a["hidden"]]
    return web.json_response(lst)


async def app_icon(request: web.Request) -> web.Response:
    data = await _tv(request).icon(request.match_info["package"])
    return web.Response(body=data, content_type="image/png", headers={"Cache-Control": "max-age=86400"})


async def app_hidden(request: web.Request) -> web.Response:
    hidden = bool((await _body(request)).get("hidden", True))
    _tv(request).set_hidden(request.match_info["package"], hidden)
    return _ok(hidden=hidden)


async def app_order(request: web.Request) -> web.Response:
    _tv(request).set_app_order((await _body(request)).get("order"))
    return _ok()


async def text_mode(request: web.Request) -> web.Response:
    body = await _body(request)
    mode = "keys" if body.get("mode") == "keys" else "ime"
    _tv(request).set_text_mode(str(body.get("package") or ""), mode)
    return _ok(mode=mode)


async def nowplaying(request: web.Request) -> web.Response:
    return web.json_response(await _tv(request).fetch_nowplaying())


async def seek(request: web.Request) -> web.Response:
    pos = int((await _body(request))["position_ms"])
    if pos < 0:
        raise ValueError("position_ms musí být >= 0")
    await _tv(request).seek(pos)
    return _ok()


async def helper_setup(request: web.Request) -> web.Response:
    b = await _body(request)
    tv = _tv(request)
    if not tv.host:
        raise NotConnected("neznámá IP TV")
    rt = request.app[RT]
    if not os.path.isfile(rt.helper_apk) and rt.android and rt.android.state in ("installing-jdk", "building"):
        raise ValueError("aplikace pro Android se ještě sestavují – zkuste to za pár minut")
    log = await adb.setup_helper(tv.host, rt.helper_apk, **_adb_args(b))
    ok = await tv.ensure_helper()
    return web.json_response({"ok": ok, "log": log, "tv": tv.snapshot()})


def _adb_args(b: dict[str, Any]) -> dict[str, Any]:
    return {
        "connect_port": int(b.get("connect_port") or 5555),
        "pair_port": int(b["pair_port"]) if b.get("pair_port") else None,
        "pair_code": (b.get("pair_code") or "").strip() or None,
    }


async def adb_test(request: web.Request) -> web.Response:
    tv = _tv(request)
    if not tv.host:
        raise NotConnected("neznámá IP TV")
    args = _adb_args(await _body(request))
    res = await adb.test(tv.host, **args)
    if not args["pair_port"]:  # klasické ladění má stálý port -> použít i pro otevírání nastavení
        tv.rec["adb_port"] = args["connect_port"]
        request.app[RT].store.save()
    return web.json_response(res)


async def ui_dump(request: web.Request) -> web.Response:
    return web.json_response({"xml": await _tv(request).ui_dump()})


async def adopt_tv(request: web.Request) -> web.Response:
    tv = _tv(request)
    tv.adopt()
    return web.json_response(tv.snapshot())


async def helper_connect(request: web.Request) -> web.Response:
    tv = _tv(request)
    ok = await tv.ensure_helper()
    return web.json_response({"ok": ok, "tv": tv.snapshot()})


async def ws(request: web.Request) -> web.WebSocketResponse:
    rt = request.app[RT]
    mgr = rt.mgr
    sock = web.WebSocketResponse(heartbeat=20)
    await sock.prepare(request)
    await sock.send_json({"type": "snapshot", "endpoints": rt.endpoints(), "tvs": [tv.snapshot() for tv in mgr.tvs.values()],
                          "android": rt.android.status() if rt.android else None})
    for tv in mgr.tvs.values():
        if tv.nowplaying:
            await sock.send_json({"type": "nowplaying", "tv_id": tv.id, "data": tv.nowplaying})
    rt.bus.clients.add(sock)
    rt.bus.owners[sock] = request["device"]["id"]
    try:
        async for msg in sock:
            # Klávesy a text i přes WS (nižší latence): {"tv_id":..,"key":"ok"} / {"tv_id":..,"text":"a"}
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
                tv = mgr.get(data["tv_id"])
                if "key" in data:
                    via = await _do_key(tv, data["key"], data.get("direction", "SHORT"))
                    if data["key"] in ("settings", "power"):
                        await sock.send_json({"type": "key_result", "key": data["key"], "via": via})
                elif "text" in data:
                    tv.send_text(data["text"])
            except Exception as exc:  # chyba jednoho příkazu neukončí spojení
                await sock.send_json({"type": "error", "error": translate(str(exc) or exc.__class__.__name__, _lang(request))})
    finally:
        rt.bus.clients.discard(sock)
        rt.bus.owners.pop(sock, None)
    return sock


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


def build_app(rt: Runtime) -> web.Application:
    app = web.Application(middlewares=[auth_mw, errors_mw])
    app[RT] = rt
    t = "/api/tvs/{tv_id}"
    app.add_routes(
        [
            web.get("/", index),
            web.get("/download/homemote.apk", download_phone_apk),
            web.get("/api/android", android_status),
            web.static("/icons", STATIC_DIR / "icons"),
            web.static("/i18n", STATIC_DIR / "i18n"),
            web.get("/api/health", health),
            web.get("/api/auth/status", auth_status),
            web.post("/api/auth/setup", auth_setup),
            web.post("/api/auth/login", auth_login),
            web.post("/api/auth/redeem", auth_redeem),
            web.post("/api/auth/pair", auth_pair),
            web.get("/api/auth/devices", auth_devices),
            web.delete("/api/auth/devices/{dev_id}", auth_revoke),
            web.post("/api/auth/logout", auth_logout),
            web.put("/api/auth/password", auth_password),
            web.get("/api/endpoints", endpoints),
            web.get("/api/logs", logs),
            web.get("/api/settings", get_settings),
            web.put("/api/settings", put_settings),
            web.get("/api/tvs", list_tvs),
            web.post("/api/tvs", add_tv),
            web.put("/api/tvs/order", tv_order),  # před {tv_id}, jinak by "order" bralo jako id
            web.get(t, get_tv),
            web.put(t, update_tv),
            web.post(t + "/adopt", adopt_tv),
            web.delete(t, remove_tv),
            web.post(t + "/pair/start", pair_start),
            web.post(t + "/pair/finish", pair_finish),
            web.post(t + "/key", key),
            web.post(t + "/text", text),
            web.post(t + "/volume", volume),
            web.get(t + "/inputs", inputs),
            web.post(t + "/inputs/select", select_input),
            web.post(t + "/launch", launch),
            web.get(t + "/apps", apps),
            web.get(t + "/apps/{package}/icon", app_icon),
            web.put(t + "/apps/{package}/hidden", app_hidden),
            web.put(t + "/text_mode", text_mode),
            web.put(t + "/apps/order", app_order),
            web.post(t + "/adb/uidump", ui_dump),
            web.get(t + "/nowplaying", nowplaying),
            web.post(t + "/seek", seek),
            web.post(t + "/helper/setup", helper_setup),
            web.post(t + "/helper/connect", helper_connect),
            web.post(t + "/adb/test", adb_test),
            web.get("/api/ws", ws),
        ]
    )
    return app
