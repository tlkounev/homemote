# Homemote for Google TV – backend (homemote-backend)

Homemote je ovladač pro zařízení s Google TV / Android TV. Backend běží v Dockeru, najde televize v domácí síti a nabízí webové rozhraní a API pro aplikaci v telefonu.

- Televize hledá sám přes mDNS. Pozná je podle MAC adresy z certifikátu, takže jim IP může přidělovat DHCP.
- Ovládání (klávesy, hlasitost, psaní, spouštění aplikací) jde přes Android TV Remote protocol v2, stejný jako u oficiální aplikace Google TV.
- Seznam aplikací, stav přehrávání, posuvník, výběr vstupu a otevření nastavení TV zajišťuje volitelný pomocník na TV (APK).
- Hotová APK pomocníka i aplikace pro telefon jsou součástí Docker image `ghcr.io/tlkounev/homemote-backend` (sestavuje je GitHub Actions). Při sestavení image ze zdrojáků si je backend sestaví sám při prvním startu (viz `android/README.md`).

## Spuštění

Libovolný Linux s Dockerem. Hotový image `ghcr.io/tlkounev/homemote-backend` obsahuje vše včetně APK. Stačí `docker-compose.yml` z kořene repozitáře:

```sh
docker compose up -d                          # první spuštění
docker compose pull && docker compose up -d   # aktualizace
```

Pak otevřete `http://<IP počítače>:888/` **z domácí sítě** a nastavte heslo. Port změníte proměnnou `PORT`. Veškerý stav je ve složce připojené jako `/data`.

### Síť

Výchozí je `network_mode: host`. Automatické hledání televizí (mDNS) potřebuje, aby kontejner byl přímo v domácí síti. Výchozí NAT síť Dockeru multicast nepropustí.

Volitelně může kontejner dostat vlastní IP v LAN přes síť `macvlan` (příklad v `../README.md`). Hostitel se pak ke kontejneru nedostane, pokud na něm nepřidáte také macvlan rozhraní.

Docker Desktop (Windows, macOS) neposílá multicast do domácí sítě. Zařízení se tam přidávají ručně podle IP (tlačítko + v záhlaví).

### Vývoj ze zdrojáků

`docker build -t ghcr.io/tlkounev/homemote-backend:latest .` (v této složce) sestaví image z `Dockerfile`. Bez hotových APK v `apk-dist/` si je backend sestaví při prvním startu (doinstaluje JDK, pár minut). `start.sh` spouští backend v čistém `python:3.12-slim` s kódem připojeným do `/srv` (bez sestavování image).

## Jazyky

Web je v 15 jazycích (výběr přes vlajku vpravo nahoře). Čeština a angličtina jsou přímo v `static/index.html`, ostatní v `static/i18n/<kód>.json` (sekce `ui` pro web, `errors` pro chybové hlášky backendu). Chybějící text se zobrazí anglicky.

## První spuštění

1. Otevřete web z domácí sítě a nastavte heslo. Z internetu (přes reverzní proxy) to z bezpečnostních důvodů nejde.
2. Zapnuté zařízení najde backend sám. Tlačítko **+** v záhlaví pak bliká: přidejte zařízení, klepněte na **Spárovat** a zadejte kód z obrazovky. Zařízení lze přidat i podle IP adresy (také přes +).
3. Volitelně nainstalujte pomocníka na zařízení (Aplikace → ⋯ → Pomocník).
4. Pro přístup z internetu nastavte v Nastavení → Adresy backendu adresu reverzní proxy. Proxy musí propouštět WebSocket (`/api/ws`).

Telefon přidáte v Nastavení → Přihlášené telefony a prohlížeče → **Přidat telefon**. Ukáže se QR kód ke stažení aplikace; druhý QR kód pak naskenujete v aplikaci.

## Aplikace pro Android

Obal kolem webu backendu (`android/phone/`): při prvním spuštění ukáže návod a čtečku QR kódu, po spárování sama volí adresu (doma lokální, jinak internetová) a tlačítka hlasitosti telefonu ovládají hlasitost TV. APK se stahuje z `/download/homemote.apk`.

## Záloha

Vše důležité je ve složce `data`. Podpisové klíče aplikací jsou v GitHub Secrets (`HM_KEY_HELPER`, `HM_KEY_PHONE`, viz `../README.md`); při sestavení ze zdrojáků v `data/keys/` – bez nich nepůjde aktualizovat pomocníka ani aplikaci v telefonu přes nainstalovanou verzi.

## Zapomenuté heslo

Zastavte kontejner, smažte `data/auth.json` a spusťte ho znovu. Všechna zařízení se odhlásí a heslo nastavíte znovu z domácí sítě. Televize a jejich párování zůstanou.

## Data (`data/`)

| Soubor | Obsah |
|---|---|
| `state.json` | televize, názvy, skryté aplikace, adresy backendu |
| `auth.json` | hash hesla, přihlášená zařízení |
| `cert.pem`, `key.pem` | certifikát pro párování s TV. Po smazání je nutné všechny TV spárovat znovu. |
| `home/.android/` | ADB klíč pro instalaci pomocníka |

API: `../API.md`.
