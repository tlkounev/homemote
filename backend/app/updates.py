"""Kontrola nové verze: poslední Release na GitHubu (každých 6 hodin).

Do GitHubu jde jen anonymní dotaz na veřejné API (bez údajů o instalaci).
Vypnutí: HM_UPDATE_CHECK=0. Jiný repozitář (fork): HM_UPDATE_REPO=vlastník/název.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

import aiohttp

from .version import VERSION

LOG = logging.getLogger(__name__)
INTERVAL = 6 * 3600
RETRY = 30 * 60


def parse(v: str | None) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", (v or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


class UpdateChecker:
    def __init__(self, publish: Any = None) -> None:
        self.publish = publish
        self.repo = os.environ.get("HM_UPDATE_REPO", "tlkounev/homemote")
        self.enabled = os.environ.get("HM_UPDATE_CHECK", "1").lower() not in ("0", "false", "no")
        self.latest: str | None = None
        self.url: str | None = None
        self.checked: float | None = None
        self.error: str | None = None
        self._task: asyncio.Task | None = None

    def status(self) -> dict[str, Any]:
        cur, new = parse(VERSION), parse(self.latest)
        return {
            "current": VERSION,
            "latest": self.latest,
            "update": bool(cur and new and new > cur),
            "url": self.url,
            "checked": self.checked,
            "enabled": self.enabled,
            "error": self.error,
        }

    def start(self) -> None:
        if self.enabled:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        await asyncio.sleep(20)  # nezdržovat start
        while True:
            ok = await self.check()
            await asyncio.sleep(INTERVAL if ok else RETRY)

    async def check(self) -> bool:
        before = (self.latest, self.error)
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            headers = {"Accept": "application/vnd.github+json", "User-Agent": f"homemote/{VERSION}"}
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as s:
                async with s.get(f"https://api.github.com/repos/{self.repo}/releases/latest") as r:
                    if r.status != 200:
                        raise RuntimeError(f"GitHub HTTP {r.status}")
                    data = await r.json()
            tag = str(data.get("tag_name") or "")
            if not parse(tag):
                raise RuntimeError(f"neznámý formát verze: {tag!r}")
            self.latest, self.url, self.error = tag.lstrip("v"), data.get("html_url"), None
            ok = True
        except Exception as exc:  # noqa: BLE001 – kontrola verze nesmí nic shodit
            self.error = str(exc) or exc.__class__.__name__
            LOG.info("Kontrola nové verze selhala: %s", self.error)
            ok = False
        self.checked = time.time()
        if (self.latest, self.error) != before:
            st = self.status()
            if st["update"]:
                LOG.info("Je dostupná nová verze %s (běží %s): %s", self.latest, VERSION, self.url)
            if self.publish:
                try:
                    self.publish({"type": "update", "update": st})
                except Exception:  # noqa: BLE001
                    pass
        return ok
