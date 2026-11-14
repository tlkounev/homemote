"""Jednorázová instalace helperu přes ADB (adb z Android platform-tools).

ADB slouží jen k setupu: instalace APK + udělení přístupu k notifikacím
(nutné pro čtení MediaSession). Běžný provoz ADB nepotřebuje.
"""
from __future__ import annotations

import asyncio
import logging
import os

LOG = logging.getLogger(__name__)

HELPER_PACKAGE = "net.homemote.helper"
HELPER_LISTENER = f"{HELPER_PACKAGE}/{HELPER_PACKAGE}.MediaListenerService"


class AdbError(Exception):
    pass


async def _adb(*args: str, timeout: float = 60) -> str:
    proc = await asyncio.create_subprocess_exec(
        "adb", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise AdbError(f"adb {' '.join(args)}: timeout") from exc
    text = out.decode(errors="replace").strip()
    LOG.info("adb %s -> %s", " ".join(args), text)
    if proc.returncode != 0:
        raise AdbError(text)
    return text


async def _connect(host: str, connect_port: int, pair_port: int | None, pair_code: str | None, log: list[str]) -> str:
    target = f"{host}:{connect_port}"
    if pair_port and pair_code:
        log.append(await _adb("pair", f"{host}:{pair_port}", pair_code))
    out = await _adb("connect", target, timeout=20)
    log.append(out)
    if "connected" not in out or "failed" in out or "unable" in out:
        raise AdbError(f"ADB připojení selhalo: {out} (potvrďte dotaz na TV a zkuste znovu)")
    state = await _adb("-s", target, "get-state", timeout=10)
    if state != "device":
        await _disconnect(target)
        raise AdbError(f"zařízení ve stavu '{state}' – potvrďte ladění na TV")
    return target


async def _disconnect(target: str) -> None:
    try:
        await _adb("disconnect", target, timeout=10)
    except AdbError:
        pass


_CONNECTED: set[str] = set()


async def shell(host: str, port: int, command: str) -> str:
    """Příkaz přes trvalé ADB spojení (psaní textu – musí být rychlé, spojení se nechává otevřené)."""
    target = f"{host}:{port}"
    for attempt in (1, 2):
        if target not in _CONNECTED:
            out = await _adb("connect", target, timeout=6)
            if "connected" not in out or "failed" in out or "unable" in out:
                raise AdbError(out)
            _CONNECTED.add(target)
        try:
            return await _adb("-s", target, "shell", command, timeout=10)
        except AdbError:
            _CONNECTED.discard(target)
            if attempt == 2:
                raise
    return ""


async def exec_out(host: str, port: int, command: str, timeout: float = 15) -> bytes:
    """Binární výstup příkazu (např. screencap) přes trvalé ADB spojení."""
    target = f"{host}:{port}"
    for attempt in (1, 2):
        if target not in _CONNECTED:
            out = await _adb("connect", target, timeout=6)
            if "connected" not in out or "failed" in out or "unable" in out:
                raise AdbError(out)
            _CONNECTED.add(target)
        proc = await asyncio.create_subprocess_exec(
            "adb", "-s", target, "exec-out", command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise AdbError(f"adb exec-out {command}: timeout") from exc
        if proc.returncode == 0:
            LOG.info("adb exec-out %s -> %d B", command, len(out_b))
            return out_b
        _CONNECTED.discard(target)
        if attempt == 2:
            raise AdbError(err_b.decode(errors="replace").strip() or f"adb exec-out {command} selhalo")
    return b""


async def shell_once(host: str, port: int, *cmd: str) -> str:
    """Jeden příkaz přes už povolené ADB (bez párování). Krátké timeouty – jen když je ladění zapnuté."""
    target = f"{host}:{port}"
    out = await _adb("connect", target, timeout=6)
    if "connected" not in out or "failed" in out or "unable" in out:
        raise AdbError(out)
    try:
        if await _adb("-s", target, "get-state", timeout=5) != "device":
            raise AdbError("unauthorized")
        return await _adb("-s", target, "shell", *cmd, timeout=10)
    finally:
        _CONNECTED.discard(target)
        await _disconnect(target)


async def test(host: str, connect_port: int = 5555, pair_port: int | None = None, pair_code: str | None = None) -> dict:
    """Ověří přístup přes ADB: připojí se, přečte model a verzi Androidu a odpojí se."""
    try:
        await _adb("version", timeout=10)
    except (AdbError, FileNotFoundError) as exc:
        raise AdbError(f"ADB není dostupné: {exc}") from exc
    log: list[str] = []
    target = await _connect(host, connect_port, pair_port, pair_code, log)
    try:
        model = await _adb("-s", target, "shell", "getprop", "ro.product.model", timeout=10)
        release = await _adb("-s", target, "shell", "getprop", "ro.build.version.release", timeout=10)
        sdk = await _adb("-s", target, "shell", "getprop", "ro.build.version.sdk", timeout=10)
    finally:
        await _disconnect(target)
    return {"ok": True, "model": model, "android": release, "sdk": sdk, "log": log}


async def setup_helper(
    host: str,
    apk_path: str,
    connect_port: int = 5555,
    pair_port: int | None = None,
    pair_code: str | None = None,
) -> list[str]:
    """Nainstaluje helper a povolí mu přístup k notifikacím. Vrací log kroků.

    - Klasické síťové ladění: stačí connect_port (typicky 5555); TV zobrazí dotaz na povolení.
    - Bezdrátové ladění (Android 11+): pair_port + pair_code z obrazovky TV, connect_port
      je port zobrazený v sekci "IP adresa a port" (mění se).
    """
    if not os.path.exists(apk_path):
        raise AdbError(f"chybí {apk_path} – nahrajte helper.apk do /data")
    log: list[str] = []
    target = await _connect(host, connect_port, pair_port, pair_code, log)
    try:
        try:
            log.append(await _adb("-s", target, "install", "-r", "-g", apk_path, timeout=180))
        except AdbError as exc:
            # Nainstalovaný pomocník je podepsaný jiným klíčem (např. nové klíče v data/keys).
            # Pomocník nemá žádná data kromě tokenu, takže ho lze bez ztráty odinstalovat a nainstalovat znovu.
            if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" not in str(exc):
                raise
            log.append(str(exc))
            log.append("pomocník je podepsaný jiným klíčem – odinstaluji ho a nainstaluji znovu")
            log.append(await _adb("-s", target, "uninstall", HELPER_PACKAGE, timeout=60))
            log.append(await _adb("-s", target, "install", "-g", apk_path, timeout=180))
        log.append(await _adb("-s", target, "shell", "cmd", "notification", "allow_listener", HELPER_LISTENER))
        # Overlay oprávnění = výjimka z omezení spouštění aktivit z pozadí (spouštění aplikací helperem)
        log.append(await _adb("-s", target, "shell", "appops", "set", HELPER_PACKAGE, "SYSTEM_ALERT_WINDOW", "allow"))
    finally:
        await _disconnect(target)
    return log
