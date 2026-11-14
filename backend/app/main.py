"""Vstupní bod backendu."""
from __future__ import annotations

import asyncio
import logging
import os
import signal

from aiohttp import web

from .android_build import AndroidBuilder
from .updates import UpdateChecker
from .api import build_app
from .auth import Auth
from .bus import Bus
from .discovery import Discovery, local_ip
from .logbuf import RING
from .runtime import Runtime
from .store import Store
from .tv import Manager


async def run() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger().addHandler(RING)
    log = logging.getLogger(__name__)
    data_dir = os.environ.get("DATA_DIR", "/data")
    port = int(os.environ.get("PORT", "888"))
    os.makedirs(data_dir, exist_ok=True)

    store = Store(os.path.join(data_dir, "state.json"))
    auth = Auth(os.path.join(data_dir, "auth.json"))
    bus = Bus()
    mgr = Manager(store, bus, data_dir)
    await mgr.start()

    ip = os.environ.get("ADVERTISE_IP") or local_ip()
    # Hotová APK z Docker image (sestavená v GitHub Actions); jinak se sestaví sama do data_dir.
    prebuilt = os.environ.get("HM_APK_DIR", "/opt/homemote/apk")
    if not os.path.isfile(os.path.join(prebuilt, "apk-versions.json")):
        prebuilt = ""
    apk_dir = prebuilt or data_dir
    rt = Runtime(store, auth, mgr, bus, port, ip, os.environ.get("HELPER_APK", os.path.join(apk_dir, "helper.apk")))

    rt.updates = UpdateChecker(publish=bus.publish)
    rt.android = AndroidBuilder(data_dir, publish=bus.publish, prebuilt_dir=prebuilt or None)
    disc = Discovery(mgr, port, ip, rt.txt())
    mgr.discovery = disc
    rt.discovery = disc
    await disc.start()

    runner = web.AppRunner(build_app(rt))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Web a API běží na http://%s:%s/", ip, port)
    rt.updates.start()  # kontrola nové verze na GitHubu (každých 6 h)
    rt.android.start()  # hotová APK z image, jinak se chybějící / zastaralá sestaví na pozadí
    if not auth.configured:
        log.info("Heslo zatím není nastavené – otevřete web z domácí sítě a nastavte ho.")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    await rt.updates.stop()
    await runner.cleanup()
    await disc.stop()
    await mgr.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
