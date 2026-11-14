"""Sestavení APK (pomocník na TV + aplikace pro telefon) přímo v kontejneru backendu.

Při startu se porovnají verze v android/<aplikace>/app.json s tím, co je sestavené v /data.
Když APK chybí nebo je starší, spustí se na pozadí android/build.py. Chybí-li JDK
(čistý python image), doinstaluje se přes apt (jen když je co sestavovat).
Podpisové klíče jsou v /data/keys – stejné klíče = aktualizace na zařízeních projdou.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)
ANDROID_DIR = Path(__file__).resolve().parent.parent / "android"
APPS = ("helper", "phone")


class AndroidBuilder:
    def __init__(self, data_dir: str, publish: Any = None, prebuilt_dir: str | None = None) -> None:
        self.prebuilt = bool(prebuilt_dir)
        self.data = Path(prebuilt_dir or data_dir)  # kde APK jsou: v image (jen pro čtení), nebo v /data
        self.publish = publish  # callback(dict) – změna stavu pro web
        self.state = "idle"     # idle | ready | installing-jdk | building | error | unavailable
        self.error: str | None = None
        self.versions_file = self.data / "apk-versions.json"
        self._task: asyncio.Task | None = None

    # --- stav ---------------------------------------------------------------------------
    def _wanted(self) -> dict[str, dict[str, Any]]:
        out = {}
        for name in APPS:
            try:
                out[name] = json.loads((ANDROID_DIR / name / "app.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        return out

    def _built(self) -> dict[str, str]:
        try:
            return json.loads(self.versions_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _missing(self) -> list[str]:
        built = self._built()
        return [name for name, cfg in self._wanted().items()
                if not (self.data / cfg["apk"]).is_file() or built.get(name) != cfg["version_name"]]

    def status(self) -> dict[str, Any]:
        wanted, built = self._wanted(), self._built()
        apps = {name: {"version": cfg["version_name"], "built": built.get(name),
                       "ready": (self.data / cfg["apk"]).is_file()}
                for name, cfg in wanted.items()}
        return {"state": self.state, "error": self.error, "apps": apps}

    def _set(self, state: str, error: str | None = None) -> None:
        self.state, self.error = state, error
        if self.publish:
            try:
                self.publish({"type": "android", "android": self.status()})
            except Exception:  # noqa: BLE001 – web jen informujeme
                pass

    # --- sestavení ---------------------------------------------------------------------
    def start(self) -> None:
        if self.prebuilt:
            # APK jsou součástí image – nic se nesestavuje
            missing = self._missing()
            if missing:
                LOG.warning("Android aplikace: image neobsahuje aktuální APK (%s)", ", ".join(missing))
            self.state = "unavailable" if missing else "ready"
            return
        if os.environ.get("HM_BUILD_APKS", "1") in ("0", "false", "no"):
            self.state = "ready" if not self._missing() else "unavailable"
            return
        if not (ANDROID_DIR / "build.py").is_file():
            self.state = "unavailable"
            return
        if not self._missing():
            self.state = "ready"
            return
        self._task = asyncio.create_task(self._run())

    async def _exec(self, *cmd: str, env: dict[str, str] | None = None, tag: str = "apk") -> tuple[int, list[str]]:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env
        )
        tail: list[str] = []
        assert proc.stdout
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if not line or line.startswith("Picked up JAVA_TOOL_OPTIONS"):
                continue
            LOG.info("%s: %s", tag, line)
            tail = (tail + [line])[-12:]
        return await proc.wait(), tail

    async def _ensure_jdk(self) -> bool:
        if shutil.which("javac") and shutil.which("keytool"):
            return True
        if not shutil.which("apt-get"):
            self._set("error", "chybí JDK (javac) a nejde doinstalovat – použijte image s JDK")
            return False
        self._set("installing-jdk")
        LOG.info("Android aplikace: instaluji JDK (jednorázově, pár minut) …")
        env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
        rc, tail = await self._exec("sh", "-c", "apt-get update -qq && apt-get install -y -qq --no-install-recommends "
                                    "default-jdk-headless >/dev/null", env=env, tag="apt")
        if rc != 0 or not shutil.which("javac"):
            self._set("error", "instalace JDK selhala: " + " | ".join(tail[-3:]))
            return False
        return True

    async def _run(self) -> None:
        missing = self._missing()
        LOG.info("Android aplikace: je potřeba sestavit %s", ", ".join(missing))
        try:
            if not await self._ensure_jdk():
                return
            self._set("building")
            env = {
                **os.environ,
                "HM_OUT": str(self.data),
                "HM_WORK": str(self.data / "apk-build"),
                "HM_KEYS": str(self.data / "keys"),
                "HM_TOOLS": str(self.data / "apk-tools"),
                "PYTHONUNBUFFERED": "1",
            }
            rc, tail = await self._exec(sys.executable, str(ANDROID_DIR / "build.py"), *missing, env=env)
            if rc != 0:
                self._set("error", " | ".join(tail[-4:]) or f"build.py skončil kódem {rc}")
                return
            built = self._built()
            for name, cfg in self._wanted().items():
                if name in missing:
                    built[name] = cfg["version_name"]
            self.versions_file.write_text(json.dumps(built, indent=1), encoding="utf-8")
            shutil.rmtree(self.data / "apk-build", ignore_errors=True)
            LOG.info("Android aplikace: hotovo (%s)", ", ".join(f"{n} {built[n]}" for n in missing))
            self._set("ready")
        except Exception as exc:  # noqa: BLE001
            LOG.exception("Android aplikace: sestavení selhalo")
            self._set("error", str(exc) or exc.__class__.__name__)
