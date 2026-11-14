"""Překlad chybových hlášek backendu (web posílá hlavičku X-Lang).

Zdrojem jsou české hlášky. Regexy je převedou na anglickou šablonu, ostatní jazyky
mají překlad šablon v static/i18n/<jazyk>.json (sekce "errors")."""
from __future__ import annotations

import json
import re
from pathlib import Path

_EN: list[tuple[str, str]] = [
    (r"chybí (\S+) – nahrajte helper\.apk do /data", "missing {0} – put helper.apk into the data folder"),
    (r"ADB připojení selhalo: (.*) \(potvrďte dotaz na TV a zkuste znovu\)", "ADB connection failed: {0} (confirm the prompt on the TV and try again)"),
    (r"zařízení ve stavu '(.*)' – potvrďte ladění na TV", "device is in state '{0}' – allow debugging on the TV"),
    (r"chybí pole (.*)", "missing field {0}"),
    (r"nepřipojeno", "not connected"),
    (r"neplatný kód / nespárováno", "invalid code / not paired"),
    (r"TV nedostupná: (.*)", "TV unreachable: {0}"),
    (r"tuto funkci nainstalovaný pomocník na TV neumí – aktualizujte ho", "the installed TV helper doesn't support this – update it"),
    (r"pomocník na TV: (.*)", "TV helper: {0}"),
    (r"ADB: (.*)", "ADB: {0}"),
    (r"interní chyba", "internal error"),
    (r"nepřihlášeno", "not signed in"),
    (r"nejdřív je potřeba nastavit heslo", "a password has to be set first"),
    (r"chybí IP adresa", "IP address is missing"),
    (r"chybí kód", "code is missing"),
    (r"chybí package nebo link", "package or link is missing"),
    (r"position_ms musí být >= 0", "position_ms must be >= 0"),
    (r"neznámá IP TV", "unknown TV IP address"),
    (r"neznámá TV", "unknown TV"),
    (r"heslo musí mít aspoň 8 znaků", "the password must have at least 8 characters"),
    (r"příliš mnoho neúspěšných pokusů, zkuste to za 10 minut", "too many failed attempts, try again in 10 minutes"),
    (r"heslo už je nastavené – přihlaste se", "a password is already set – sign in"),
    (r"první nastavení je možné jen z domácí sítě, ne přes internet", "the first setup is only possible from the home network, not over the internet"),
    (r"nesprávné heslo", "wrong password"),
    (r"současné heslo nesouhlasí", "the current password doesn't match"),
    (r"kód je neplatný nebo vypršel – vygenerujte nový", "the code is invalid or expired – generate a new one"),
    (r"zařízení nenalezeno", "device not found"),
    (r"TV není připojena", "the TV is not connected"),
    (r"neznámá klávesa: (.*)", "unknown key: {0}"),
    (r"(\S+): adresa musí začínat http:// nebo https://", "{0}: the address must start with http:// or https://"),
    (r"párování nebylo zahájeno", "pairing was not started"),
    (r"název nesmí být prázdný", "the name must not be empty"),
    (r"TV zatím nehlásí hlasitost", "the TV hasn't reported its volume yet"),
    (r"helper na TV není dostupný", "the TV helper is not available"),
    (r"helper patří jinému backendu \(token nesouhlasí\) – reset dat helperu na TV", "the TV helper belongs to another backend (token mismatch) – clear the helper's data on the TV"),
    (r"ADB není dostupné: (.*)", "ADB is not available: {0}"),
    (r"zařízení neodpovídá – je vypnuté nebo mimo síť", "the device is not responding – it is off or not on the network"),
    (r"aplikace pro Android se ještě sestavují – zkuste to za pár minut", "the Android apps are still being built – try again in a few minutes"),
    (r"ADB není nastavené – otestujte připojení u pomocníka na zařízení", "ADB is not set up – test the connection in the device helper"),
    (r"psaní přes ADB vyžaduje ověřené ADB – otestujte připojení u pomocníka na zařízení", "typing over ADB needs a verified ADB connection – test it in the device helper"),
]
_COMPILED = [(re.compile(rf"^{p}$", re.S), t) for p, t in _EN]


_DIR = Path(__file__).parent / "static" / "i18n"
_TABLES: dict[str, dict[str, str]] = {}


def _table(lang: str) -> dict[str, str]:
    if lang not in _TABLES:
        try:
            _TABLES[lang] = json.loads((_DIR / f"{lang}.json").read_text("utf-8")).get("errors", {})
        except (OSError, ValueError):
            _TABLES[lang] = {}
    return _TABLES[lang]


def translate(msg: str, lang: str | None) -> str:
    code = (lang or "cs").lower().split("-")[0]
    if code == "cs" or not re.fullmatch(r"[a-z]{2}", code):
        return msg
    for rx, tpl in _COMPILED:
        m = rx.match(msg)
        if m:
            if code != "en":
                tpl = _table(code).get(tpl, tpl)
            return tpl.format(*(translate(g, lang) for g in m.groups()))
    return msg
