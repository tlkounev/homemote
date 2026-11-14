# Aplikace pro Android (pomocník na TV + aplikace pro telefon)

**Hotová APK jsou součástí Docker image** – sestavuje je GitHub Actions (`.github/workflows/release.yml`) s klíči z repozitářových Secrets a ukládá do `/opt/homemote/apk` v image.

Bez nich (image sestavený ze zdrojáků) se **sestaví automaticky v kontejneru backendu** – nic se nespouští ručně. Při startu backend porovná verze
v `*/app.json` s tím, co je v `/data`, a chybějící nebo zastaralé APK sestaví na pozadí (první sestavení
trvá několik minut: doinstaluje JDK a stáhne nástroje). Stav ukazuje web (dialog Pomocník, Přidat telefon)
a `GET /api/android`. Vypnutí: proměnná `HM_BUILD_APKS=0`.

Co vznikne v `/data`:

| soubor | co to je |
|---|---|
| `helper.apk` | pomocník na TV (instaluje ho backend přes ADB) |
| `homemote.apk` | aplikace pro telefon (stahuje se z `/download/homemote.apk`, QR v „Přidat telefon“) |
| `keys/homemote-*.jks` | podpisové klíče – **zálohujte je**, bez nich nejdou aktualizace přes nainstalovanou verzi |
| `apk-tools/` | stažené nástroje (android.jar, dx, uber-apk-signer) |
| `apk-versions.json` | jaké verze jsou sestavené |

Bez Gradlu a Android SDK: `javac` proti `android.jar`, `dx` (classes.dex), vlastní kodér binárního
`AndroidManifest.xml` a `resources.arsc` (jen ikona), podpis v1–v3 přes uber-apk-signer.

## Ručně (vývoj)

```sh
python3 android/build.py            # obě aplikace
python3 android/build.py phone      # jen aplikace pro telefon
HM_OUT=/data HM_KEYS=/data/keys HM_TOOLS=/data/apk-tools HM_WORK=/tmp/apk python3 android/build.py
```

Každá aplikace má složku s `app.json` (balíček, verze, min. SDK, název APK, volitelně ikona),
`AndroidManifest.xml`, `src/` a volitelně `assets/`. Nová verze = zvýšit `version_name` a `version_code`
v `app.json`; backend ji po restartu sestaví sám.
