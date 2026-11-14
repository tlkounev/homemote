"""Posledních N řádků logu v paměti – pro zobrazení ve webu (Nastavení → Diagnostika)."""
from __future__ import annotations

import logging
from collections import deque


class RingHandler(logging.Handler):
    def __init__(self, size: int = 1000) -> None:
        super().__init__()
        self.lines: deque[str] = deque(maxlen=size)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == "aiohttp.access":  # přístupy k API by zahltily výpis
            return
        try:
            self.lines.append(self.format(record))
        except Exception:
            pass

    def get(self, contains: str = "", limit: int = 400) -> list[str]:
        lines = [l for l in self.lines if contains.lower() in l.lower()] if contains else list(self.lines)
        return lines[-limit:]


RING = RingHandler()
