# Homemote helper (APK pro Google TV)

Malá aplikace na TV, kterou backend volá na portu 8765 (kontrakt v `../API.md`, část „Pomocník na TV“).

- HTTP server bez knihoven, ohlášení přes mDNS `_homemote-helper._tcp`.
- Token backendu se uloží při prvním `POST /v1/claim` (TOFU). Reset: otevřít aplikaci na TV → „Odpojit od backendu“.
- Seznam aplikací a ikon (banner), spuštění aplikace, co hraje + přesný posun (MediaSession přes NotificationListenerService), HDMI vstupy (TvInputManager), otevření Nastavení.
- Běh drží systém přes navázanou NotificationListenerService (povoluje ji backend při instalaci přes ADB, spolu s „zobrazením přes aplikace“ kvůli spouštění aplikací z pozadí).

## Sestavení

Společně s aplikací pro telefon skriptem `../build.py`, viz `../README.md` (v CI GitHub Actions, jinak v kontejneru backendu). Podpisový klíč musí zůstat stejný, jinak Android aktualizaci (`adb install -r`) odmítne.

Hotový `helper.apk` patří do složky `data` backendu, instaluje se z webu: Aplikace → ⋯ → Pomocník na zařízení.
