# Homemote – API kontrakt

```
Telefon / web  ──HTTP/WS──►  Backend (Docker)  ──Remote protocol v2 (6466/6467)──►  Google TV
                                     └──────────HTTP──────────►  Pomocník na TV (8765)
```

Backend se ohlašuje přes mDNS jako `_homemote._tcp.local.`. TXT záznam obsahuje `path=/api`, `v=1`, `id`, `local` a `public`.

ID televize = MAC z TLS certifikátu TV (`aa:bb:cc:dd:ee:ff`). V URL lze psát i `aabbccddeeff`. IP se může libovolně měnit.

Chyby: `{"error": "..."}` + HTTP kód. Hláška je česky. S hlavičkou `X-Lang: <kód>` (u WebSocketu `?lang=<kód>`) přijde v daném jazyce: `en de es fr it nl pl pt sk uk hi zh ja ko`, jinak česky. 400 špatný požadavek, 401 nepřihlášeno, 404 neznámá TV, 409 TV/pomocník nepřipojen, 429 moc pokusů, 501 pomocník funkci neumí, 502 TV/ADB/pomocník selhal.

## Přihlášení

Každé zařízení má vlastní token: hlavička `Authorization: Bearer <token>`, u WebSocketu a obrázků i `?token=`.

| Metoda | Cesta | Tělo | Odpověď |
|---|---|---|---|
| GET | `/api/auth/status` | | `{"configured","setup_allowed","authenticated"}` |
| POST | `/api/auth/setup` | `{"password","device_name"}` | `{"token"}`. Jen jednou a jen z LAN. Požadavek s `X-Forwarded-For`/`Forwarded`/`X-Real-IP` se odmítne. |
| POST | `/api/auth/login` | `{"password","device_name","kind"}` | `{"token"}`. Po 5 chybách za 10 min vrací 429. |
| POST | `/api/auth/pair` | | `{"code","uri","svg","expires_in":300,"app"}`: jednorázový kód + QR (SVG); `app` = `{"url","svg"}` ke stažení aplikace pro Android, když je sestavená, jinak `null` |
| POST | `/api/auth/redeem` | `{"code","device_name"}` | `{"token","endpoints"}`: telefon po naskenování QR |
| GET | `/api/auth/devices` | | `[{"id","name","kind","created","last_seen","current"}]` |
| DELETE | `/api/auth/devices/{id}` | | odhlásí zařízení a ukončí jeho WebSocket (kód 4401) |
| POST | `/api/auth/logout` | | odhlásí volající zařízení |
| PUT | `/api/auth/password` | `{"old","new"}` | |

Aplikace pro telefon (`GET /download/homemote.apk`, bez přihlášení) předá webu token v URL `/#hm_token=<token>`; web si ho uloží a z adresy odstraní.

**QR kód** obsahuje URI `homemote://pair?v=1&id=<instance_id>&code=<kód>&local=<url>&public=<url>`. Aplikace z něj zná obě adresy i kód a zavolá `redeem` na první adresu, která odpoví.

## Volba adresy v telefonu (LAN vs. internet)

Adresy jsou v `/api/endpoints`, ve WS `snapshot`/`endpoints` a v mDNS TXT. Nastavují se ve webu (`PUT /api/settings`).

Při startu a při každé změně sítě aplikace:
1. Zkusí `local` + `/api/health` (timeout ~1,5 s). Adresu použije, jen když sedí `instance_id`.
2. Jinak použije `public`.

Router tak nemusí umět NAT loopback.

## Backend API (`/api`, s přihlášením)

| Metoda | Cesta | Tělo | Popis |
|---|---|---|---|
| GET | `/health` | | `{"ok":true,"instance_id":"…","version":"1.0.9","phone_app":{"version":"1.0.2","code":3,"url":"/download/homemote.apk"}}`, bez přihlášení. `phone_app` jen když je APK v image; podle `code` aplikace v telefonu nabídne aktualizaci. |
| GET | `/endpoints` | | `{"instance_id","local","public"}` |
| GET | `/update` | | kontrola nové verze: `{"current","latest","update":bool,"url","checked","enabled","error"}` (poslední Release na GitHubu, kontrola každou hodinu) |
| POST | `/update/check` | | zkontrolovat GitHub hned (nejvýš jednou za minutu), vrací totéž co `GET /update` |
| GET | `/android` | | stav sestavení APK: `{"state":"idle|ready|installing-jdk|building|error|unavailable","error","apps":{"helper":{"version","code","built","ready"},"phone":{…}}}` |
| GET/PUT | `/settings` | `{"public_url","local_url"}` | prázdné `local_url` = automaticky `http://<IP>:<PORT>` |
| GET | `/tvs` | | seznam TV (objekt `TV`) |
| POST | `/tvs` | `{"host":"192.168.1.50"}` | ruční přidání, když mDNS nefunguje |
| PUT | `/tvs/order` | `{"order":["<id>",…]}` | pořadí záložek zařízení; TV mimo seznam jdou na konec. Každá TV pak má v objektu `order` (0, 1, …; `null` = zatím neřazeno) |
| GET | `/tvs/{id}` | | jedna TV |
| PUT | `/tvs/{id}` | `{"name":"Obývák"}` | přejmenování |
| POST | `/tvs/{id}/adopt` | | přidá nalezené zařízení do ovladače (`adopted: true`) |
| DELETE | `/tvs/{id}` | | odebrání (párování, název, skryté aplikace). Zapnutá TV se přes mDNS hned objeví znovu jako nespárovaná. |
| POST | `/tvs/{id}/pair/start` | | TV zobrazí 6místný kód |
| POST | `/tvs/{id}/pair/finish` | `{"code":"A1B2C3"}` | při chybě znovu `start` |
| POST | `/tvs/{id}/key` | `{"key":"ok","direction":"SHORT"}` (`SHORT` / `START_LONG` / `END_LONG` – podržení) | `{"ok":true,"via":…}`. `settings` otevře Nastavení Androidu: pomocník → ADB (po úspěšném testu) → klávesa (`via`: `helper`/`adb`/`remote`) | `power` u nedostupné spárované TV pošle Wake-on-LAN a vrátí `via: "wol"` (i ve WS `key_result`).
| POST | `/tvs/{id}/text` | `{"text":"…"}` | požadovaný **celý obsah** aktivního pole. Backend z rozdílu pošle DEL a vložení nového konce (TV text vždy vkládá na kurzor) a čeká na ozvěnu z TV. |
| POST | `/tvs/{id}/volume` | `{"level":25}` | backend pošle potřebný počet kroků ±; TV pak hlásí skutečnou hodnotu |
| GET | `/tvs/{id}/inputs` | | `[{"id","label"}]` (pomocník) |
| POST | `/tvs/{id}/inputs/select` | `{"id":"…"}` | přepnutí vstupu (pomocník) |
| POST | `/tvs/{id}/launch` | `{"package":"…"}` / `{"link":"https://…"}` | `{"ok":true,"via":"helper"|"remote"}` |
| GET | `/tvs/{id}/apps[?include_hidden=1]` | | `[{"package","label","hidden"}]` |
| GET | `/tvs/{id}/apps/{package}/icon` | | PNG |
| PUT | `/tvs/{id}/apps/{package}/hidden` | `{"hidden":true}` | skrytí jen v ovladači |
| PUT | `/tvs/{id}/apps/order` | `{"order":["pkg", …]}` | uživatelské pořadí aplikací; `GET /apps` vrací seznam v tomto pořadí (neuvedené aplikace na konci podle názvu) |
| PUT | `/tvs/{id}/text_mode` | `{"package","mode":"keys"\|"ime"}` | způsob psaní pro aplikaci: `keys` = ADB `input` (aplikace s vlastní klávesnicí), `ime` = výchozí. `keys` vyžaduje ověřené ADB. |
| GET | `/tvs/{id}/nowplaying` | | `NowPlaying` |
| POST | `/tvs/{id}/seek` | `{"position_ms":5025000}` | přesný skok |
| POST | `/tvs/{id}/helper/setup` | `{"connect_port":5555}` nebo `{"pair_port","pair_code","connect_port"}` | instalace pomocníka přes ADB |
| POST | `/tvs/{id}/helper/connect` | | ruční pokus o spojení s pomocníkem |
| POST | `/tvs/{id}/adb/test` | jako `helper/setup` | ověří ADB: `{"ok","model","android","sdk","log"}` |
| POST | `/tvs/{id}/adb/uidump` | | `{"xml"}`: rozložení aktuální obrazovky (`uiautomator dump`), vyžaduje ověřené ADB |
| WS | `/ws` | | události (níže) |

**Aliasy kláves:** `up down left right ok back home guide vol_up vol_down mute ch_up ch_down play_pause play pause stop rewind forward power menu settings input`. Přijímá se i jakýkoli `KEYCODE_*`.

**Zařízení** (`TV`) – zařízení s Google TV / Android TV (televize nebo box). Nově nalezená zařízení mají `adopted: false`; web i aplikace je ukazují jen v nabídce „Přidat zařízení“, dokud je uživatel nepřidá.
```json
{"id":"aa:bb:cc:dd:ee:ff","name":"Obývák","host":"192.168.1.50","paired":true,"adopted":true,"online":true,
 "is_on":true,"current_app":"com.netflix.ninja","volume":{"level":12,"max":60,"muted":false},
 "device_info":{"manufacturer":"Philips","model":"…","sw_version":"…"},
 "helper":{"connected":true,"version":"1.0","listener_enabled":true,"update":null},
 "ime":{"active":false,"value":"","label":""},
 "adb":true,"text_modes":{"net.cme.voyo.cz.tvapp":"keys"}}
```

**NowPlaying:**
```json
{"active":true,"package":"com.netflix.ninja","title":"Název","subtitle":"S1:E3 …",
 "state":"playing","duration_ms":7200000,"position_ms":1234567,"speed":1.0,
 "can_seek":true,"fetched_at_ms":1793123818759}
```
`state`: `playing | paused | buffering | stopped | none`. Aktuální pozice = `position_ms + (teď − čas přijetí) * speed`, když `playing`. Posuvník jen při `can_seek`.

**WebSocket `/api/ws`:**
- Server → klient:
  - `snapshot` (`tvs`, `endpoints`, `android`, `update`) po připojení,
  - `android` (`android` = stav jako `GET /api/android`) při změně stavu sestavení APK,
  - `update` (`update` = stav jako `GET /api/update`) při zjištění nové verze,
  - `tv` (`tv`) při změně,
  - `tv_removed` (`id`),
  - `endpoints` (`endpoints`),
  - `nowplaying` (`tv_id`, `data`),
  - `ime` (`tv_id`, `ime`: `{"active","value","label"}`): TV otevřela klávesnici nebo se změnil obsah pole. Aplikace má otevřít svou klávesnici s tímto textem.
  - `error`.
- Klient → server: `{"tv_id","key","direction"?}` nebo `{"tv_id","text"}` (celý obsah pole).

## Pomocník na TV (port 8765)

Balíček `net.homemote.helper`, služba `net.homemote.helper.MediaListenerService`.

NotificationListenerService, ohlašuje se jako `_homemote-helper._tcp.local.`. Kromě `/v1/claim` vyžaduje hlavičku `X-Token`.

| Metoda | Cesta | Tělo / odpověď |
|---|---|---|
| POST | `/v1/claim` | `{"token"}`. První token se uloží (TOFU). Stejný → 200, jiný → 403. |
| GET | `/v1/info` | `{"version","sdk","listener_enabled"}` |
| GET | `/v1/apps` | `[{"package","label"}]`: launcher aplikace (LEANBACK_LAUNCHER i LAUNCHER) |
| GET | `/v1/apps/{package}/icon` | PNG (banner nebo ikona) |
| POST | `/v1/launch` | `{"package"}`. Potřebuje SYSTEM_ALERT_WINDOW (výjimka ze zákazu startu z pozadí). |
| GET | `/v1/nowplaying` | `NowPlaying` bez `fetched_at_ms`, pozice přepočtená na okamžik odpovědi |
| POST | `/v1/seek` | `{"position_ms"}`. 409 bez session, 501 bez ACTION_SEEK_TO. |
| GET | `/v1/inputs` | `[{"id","label"}]`: TvInputManager, jen fyzické vstupy (HDMI apod.) |
| POST | `/v1/inputs/select` | `{"id"}` → ACTION_VIEW na `TvContract.buildChannelUriForPassthroughInput(id)` |
| POST | `/v1/settings/open` | spustí systémové nastavení (`android.settings.SETTINGS`) |

Výběr session: první ve stavu PLAYING, jinak první z `getActiveSessions()`.

`helper.update` (u TV): automatická aktualizace pomocníka na verzi z image – `null`, nebo `{"version","from","state":"updating|done|failed","error"}`. Spouští se po připojení pomocníka, když je u TV ověřené ADB (`adb_port`) a pomocník v image je novější; po chybě další pokus nejdřív za hodinu.
