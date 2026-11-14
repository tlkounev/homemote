# Změny

Projekt se od 0.9.0 jmenuje **Homemote for Google TV**, backend **homemote-backend**. Starší verze vyšly pod názvem GTV-Remote.

Verze backendu je v `backend/app/version.py`. Zobrazuje se ve webu dole pod deskou a vrací ji `/api/health`.

## 1.0.10 – 2026-11-15
- Kontrola nové verze na GitHubu **každou hodinu** (dřív 6 h, takže se nové vydání mohlo ukázat až po několika hodinách). Po chybě znovu za 15 min.
- **Klepnutí na zelenou / šedou verzi** v záhlaví zkontroluje GitHub hned (`POST /api/update/check`, nejvýš jednou za minutu).
- Popisek u verze ukazuje, kdy proběhla poslední kontrola.

## 1.0.9 – 2026-11-14
- **Aplikace v telefonu se aktualizuje z backendu** (aplikace 1.0.2). Backend v `/api/health` hlásí verzi aplikace, kterou má v image. Když je novější, aplikace ukáže nahoře lištu **Aktualizovat / Později** („Později“ připomene za 24 h). APK se stáhne z backendu a nainstaluje přes PackageInstaller; Android ukáže svůj potvrzovací dialog. Napoprvé je potřeba povolit Homemote „Instalovat neznámé aplikace“. Kontrola nejvýš jednou za hodinu.
- **Pomocník na TV se aktualizuje automaticky**: po připojení pomocníka backend porovná jeho verzi s verzí v image a novější nainstaluje přes ověřené ADB. Stav je v okně Pomocník (aktualizuji / selhalo); po chybě další pokus za hodinu.
- Aplikace 1.0.1 aktualizaci ještě neumí – na 1.0.2 je potřeba jednou aktualizovat ručně (QR v „Přidat telefon“ nebo odkaz v README).

## 1.0.8 – 2026-11-14
- README přepsané jako návod krok za krokem se snímky obrazovky a přímými odkazy na stažení aplikace pro telefon a pomocníka (vždy nejnovější Release). Vývojářské informace jsou v `docs/development.md`.
- Pole pro párovací kód je dost široké pro všech šest znaků (první znak se někdy nevešel).

## 1.0.7 – 2026-11-14
- Verze backendu je v záhlaví vedle názvu (dřív v patičce): **zelená** = aktuální, **červená** = na GitHubu je novější verze (odkaz na její Release), šedá = zatím neověřeno.
- Backend každých 6 hodin anonymně zjistí poslední Release na GitHubu (`GET /api/update`, WS událost `update`). Vypnutí: `HM_UPDATE_CHECK=0`; fork: `HM_UPDATE_REPO=vlastník/název`.

## 1.0.6 – 2026-11-14
- **Projekt je na GitHubu** (`tlkounev/homemote`, Apache-2.0). GitHub Actions při každé změně backendu sestaví APK pomocníka i aplikace pro telefon a Docker image `ghcr.io/tlkounev/homemote-backend` s nimi uvnitř. Nová verze vytvoří Release s oběma APK.
- Image obsahuje hotová APK (`/opt/homemote/apk`), při startu se nic nesestavuje a image už neobsahuje JDK. Image sestavený ze zdrojáků bez APK si je dál sestaví sám.
- APK se podepisují pevnými klíči z repozitářových Secrets (`HM_KEY_HELPER`, `HM_KEY_PHONE`), aby šly aktualizace přes nainstalované verze.
- Instalace odkudkoli s Dockerem: `docker-compose.yml` v kořeni repozitáře (nebo `docker run`) s hotovým image; aktualizace `docker compose pull && docker compose up -d`. Žádné nahrávání ZIPu.
- Ukázková IP ve formuláři pro přidání zařízení je obecná (`192.168.1.50`).

## 1.0.5 – 2026-10-30
- **Rychlejší návrat TV po zapnutí:** když se TV ohlásí v síti (mDNS – služba ovladače nebo pomocníka), backend se připojí hned a nečeká na další pokus podle prodlevy. Nejdelší prodleva mezi pokusy je 30 s (dřív 60 s).
- **Wake-on-LAN:** tlačítko napájení u nedostupného zařízení (a nové tlačítko „Zkusit probudit“ na obrazovce Nedostupné) pošle magický paket na všechny broadcasty a poslední IP. Další minutu se pak připojení zkouší každé 3 s. Funguje jen u zařízení, které to umí a má to zapnuté (Philips Google TV: Nastavení → Síť a internet → Switch On with Wi-Fi (WoWLAN)).
- Backend si pamatuje skutečnou MAC síťového rozhraní TV z ARP tabulky (`hw_mac`); paket jde na ni i na MAC z certifikátu.

## 1.0.4 – 2026-10-28
- Barva stavu zařízení (tečka v záložce, stav v záhlaví i v nastavení): **zelená** zapnuté, **oranžová** v pohotovosti, **červená** nedostupné, šedá nespárované.
- Pořadí záložek zařízení jde měnit přetažením: myší rovnou, na dotyk po podržení záložky (krátký posun dál posouvá záložky), z klávesnice Alt+šipka vlevo/vpravo. Pořadí se ukládá v backendu (`PUT /api/tvs/order`), takže platí ve všech prohlížečích i v aplikaci.
- Popisek záložky ukazuje stav zařízení.

## 1.0.3 – 2026-10-28
- Nedostupný pomocník (TV vypnutá, v hlubokém spánku, mimo síť) už v logu nevypisuje „neošetřená chyba“ s výpisem zásobníku. API vrátí 504 „zařízení neodpovídá – je vypnuté nebo mimo síť“ (15 jazyků).
- Log „helper přestal odpovídat“ uvádí typ chyby i u timeoutu (dřív prázdné závorky).
- Instalace pomocníka: když je na TV pomocník podepsaný jiným klíčem (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`), backend ho odinstaluje a nainstaluje znovu. Pomocník nemá žádná data kromě tokenu, nic se neztratí.

## 1.0.2 – 2026-10-28
- **Pomocník i aplikace pro telefon se sestavují přímo v kontejneru backendu.** Samostatný kontejner `homemote-apk-build` už není potřeba.
  - Při startu backend porovná verze v `backend/android/*/app.json` s tím, co je v `data`, a chybějící nebo zastaralá APK sestaví na pozadí. Web mezitím běží; první sestavení trvá několik minut (doinstaluje JDK přes apt, stáhne nástroje do `data/apk-tools`).
  - Podpisové klíče jsou nově v `data/keys/`, sestavené verze v `data/apk-versions.json`. Vypnutí: `HM_BUILD_APKS=0`.
  - Stav sestavení: `GET /api/android`, WS událost `android`, ve webu v okně Pomocník a v „Přidat telefon“. Instalace pomocníka během sestavování vrátí srozumitelnou chybu.
- Zdrojáky aplikací se přesunuly: `helper/`, `phone/`, `apk/build.py` → `backend/android/`.
- `Dockerfile` obsahuje JDK a složku `android/`.

## 1.0.1 – 2026-10-28
- Způsob psaní se volí automaticky, přepínač „Psát přes ADB“ zmizel:
  - TV otevřela systémové textové pole (Google klávesnice) → IME přes Remote protocol,
  - jinak (aplikace s vlastní klávesnicí – Netflix, Oneplay, Prima+ …) a je-li ověřené ADB → přes ADB: šipkami po klávesnici aplikace, když ji najde na obrazovce, jinak jako fyzická klávesnice,
  - bez ADB vždy IME.
- Okno klávesnice bez vysvětlujícího textu pod klávesami.

## 1.0.0 – 2026-10-28
- Backend se od této verze čísluje 1.0.x.
- Ovladač: hlasitost, ztlumení se vstupem a kanály mají stejnou šířku (třetina řádku). Tlačítka hlasitosti a kanálů jsou širší, ztlumení a vstup užší.

## Aplikace pro telefon 1.0.1 – 2026-10-28 (backend beze změny)
- Při nedostupném backendu aplikace ukáže přesný důvod pro každou adresu: chyba certifikátu (SSL), DNS, HTTP stav, přesměrování na přihlašovací stránku proxy, jiný backend. Text jde označit a zkopírovat.
- WebView: chyba certifikátu, HTTP chyba (4xx/5xx) i síťová chyba hlavní stránky se zobrazí místo prázdné modré obrazovky. Chyba certifikátu se nikdy neobchází.
- Přesměrování (např. přihlášení u reverzní proxy) zůstává ve WebView, do prohlížeče se otevírají jen odkazy, na které uživatel klepne.

## 0.9.10 – 2026-10-28
- **Aplikace Homemote pro Android** (`phone/`, verze 1.0.0, min. Android 10): obal kolem webu backendu.
  - Při prvním spuštění nebo bez vazby na backend ukáže návod (Nastavení → Přihlášené telefony a prohlížeče → Přidat telefon) a vlastní čtečku QR kódu (BarcodeDetector, jinak jsQR – funguje bez Google služeb). Lze i ručně zadat adresu a přihlásit se heslem.
  - Párování: `POST /api/auth/redeem`, token se webu předá v `#hm_token=…`. Odkazy `homemote://pair?…` otevírají aplikaci přímo.
  - Volba adresy: domácí adresa, když odpoví se stejným `instance_id`, jinak internetová; při změně sítě přepne sama. Odhlášený telefon (token neplatí) vrátí na návod.
  - Tlačítka hlasitosti telefonu ovládají hlasitost TV, tlačítko Zpět zavírá okna webu.
  - 15 jazyků úvodní obrazovky, světlý/tmavý režim podle systému, ikona Homemote.
- Backend: `GET /download/homemote.apk` (aplikace ze složky `data`), v „Přidat telefon“ dva kroky – QR ke stažení aplikace a QR k přihlášení.
- Sestavení: `apk/build.py` sestaví pomocníka i aplikaci, na NASu `apk/container-station-build.yml` (nahrazuje `helper/container-station-build.yml`). Pomocník se nemění (1.0.1).

## 0.9.9 – 2026-10-28
- Ovladač: dole vlevo hlasitost (+ nahoře, − dole), uprostřed ztlumení a pod ním vstup, vpravo přepínání kanálů (+/−, `ch_up` / `ch_down` = KEYCODE_CHANNEL_UP/DOWN).
- Úchyty pro přesun bloků jsou skryté. Objeví se, když myš najede k hornímu okraji bloku; na dotyk po klepnutí do pruhu u horního okraje (na 4 s); z klávesnice při zaměření.
- Aplikace: bez nadpisu a bez čáry nad blokem. Místo tlačítek Upravit a Pomocník je tlačítko „⋯“ s nabídkou (Upravit / Pomocník na zařízení). V režimu úprav je u nápovědy tlačítko Hotovo.
- Záhlaví zařízení zůstává na telefonu na jednom řádku (stav a „⋯“ se nezalamují).

## 0.9.8 – 2026-10-28
- Pořadí aplikací lze měnit přetažením v režimu **Upravit**: myší rovnou, na telefonu po podržení dlaždice (krátký posun prstem dál posouvá stránku). Z klávesnice šipky vlevo/vpravo na zaměřené dlaždici. Klepnutí dál skrývá a zobrazuje.
- Pořadí se ukládá na backendu u zařízení (`app_order`, `PUT /api/tvs/{id}/apps/order`), takže platí i pro telefon a další prohlížeče. Nově nainstalované aplikace přibudou na konec podle abecedy.

## 0.9.7 – 2026-10-28
- Tlačítko OK umí podržení (kontextová nabídka aplikace na TV): krátký stisk = `SHORT`, podržení déle než 450 ms = `START_LONG`, puštění = `END_LONG`. Sjetí prstem z OK krátký stisk zruší; při ztrátě okna se dlouhý stisk vždy ukončí.

## 0.9.6 – 2026-10-28
- Psaní šipkami: polohu zvýraznění backend převezme jen při plynulém psaní (do 1,5 s od posledního stisku). Jinak vždy vezme nový snímek obrazovky, takže nevadí, když mezitím někdo pohne klasickým ovladačem.
- Pomocník 1.0.1: `targetSdkVersion` 36 (Play Protect varoval, že je aplikace pro starší Android).

## 0.9.5 – 2026-10-28
- Ověřeno z logu: Oneplay klepnutí (`input tap`) ignoruje – klávesy jeho webové klávesnice nejsou klikatelné, aplikace se ovládá jen šipkami.
- Psaní přes ADB do klávesnice aplikace teď jde **šipkami + OK**: z `uiautomator` se zjistí rozložení kláves (řady, mezerník, další klávesy bez textu), ze snímku obrazovky (`screencap`) zvýrazněná klávesa (nejvíc odlišný jas okraje klávesy) a backend k písmenu dojede šipkami přes Remote protocol. Polohu zvýraznění si pak pamatuje (30 s), snímek se bere jen na začátku.
- Když zvýrazněnou klávesu nenajde, web napíše, ať se na TV ovladačem vybere některé písmeno. Do logu jde jas nejodlišnějších kláves (pro doladění).

## 0.9.4 – 2026-10-28
- **Pomocník na TV** (`helper/`, verze 1.0.0): Java bez knihoven, HTTP na portu 8765, mDNS `_homemote-helper._tcp`, token TOFU. Umí seznam aplikací s bannery, spuštění aplikace, co hraje + přesný posun (MediaSession), vstupy HDMI a otevření Nastavení. Stavová obrazovka na TV s tlačítkem „Odpojit od backendu“.
  - Sestavení bez Gradlu: `helper/build.py` (javac → dx → vlastní binární manifest → podpis v1–v3). Na NASu jednorázovým kontejnerem `helper/container-station-build.yml`, výsledek jde rovnou do `data/helper.apk`.
- Psaní přes ADB umí klepat na klávesnici vykreslenou aplikací: backend přes `uiautomator` najde klávesy a–z, 0–9 a mezerník a klepne na ně (`input tap`). Ověřeno na výpisu obrazovky Oneplay (WebView, 36 kláves + mezerník). Když klávesnici nenajde, píše jako fyzická klávesnice (`input text`). Mazání vždy klávesou DEL.

## 0.9.3 – 2026-10-28
- Ověřeno na Oneplay (`net.cme.voyo.cz.tvapp`): písmena nepřijímá ani přes IME, ani jako klávesy z ADB (`input text`). Mazání (DEL) a Enter fungují.
- Diagnostika: v Nastavení zařízení tlačítko **Rozložení obrazovky** – přes ADB načte prvky aktuální obrazovky (`uiautomator dump`, `POST /api/tvs/{id}/adb/uidump`). Slouží k zjištění, jak je postavená vlastní klávesnice aplikace.

## 0.9.2 – 2026-10-28
- Přepínač psaní přes ADB je v okně klávesnice hned pod textovým polem (na telefonu byl až pod klávesnicí).
- Změna způsobu psaní se zapisuje do logu („způsob psaní v …“).
- Balíček `net.cme.voyo.cz.tvapp` se zobrazuje jako Oneplay (dřívější Voyo).

## 0.9.1 – 2026-10-28
- Psaní do aplikací s vlastní klávesnicí na obrazovce (Oneplay, Prima+ …), které IME z Remote protocolu nepřijímají. Ověřeno z logu: Voyo neotevírá systémové textové pole (`remote_ime_key_inject` bez `text_field_status`), takže vložený text nemá kam dopadnout.
  - V okně klávesnice je přepínač **Psát přes ADB jako klávesnice v aplikaci …**. Platí jen pro aktuální aplikaci a pamatuje se (`text_modes` u zařízení, `PUT /api/tvs/{id}/text_mode`).
  - Text jde přes ADB jako z fyzické klávesnice: `input keyevent 67` (mazání) a `input text`. Spojení ADB zůstává otevřené kvůli rychlosti.
  - Vyžaduje ověřené ADB (test u pomocníka). `input text` umí jen základní latinku: diakritika se odešle bez háčků a čárek.

## 0.9.0 – 2026-10-27
- Nový název **Homemote for Google TV**, backend **homemote-backend** (nový kontejner, složka `/share/Container/homemote`).
- Přejmenované identifikátory (telefonní aplikace a pomocník zatím neexistují, takže nic nerozbije):
  - mDNS: `_homemote._tcp` (backend), `_homemote-helper._tcp` (pomocník),
  - QR: `homemote://pair?…`,
  - balíček pomocníka `net.homemote.helper`,
  - jméno klienta při párování s TV: „Homemote“.
- Výběr jazyka: místo vlajek vedle sebe jedno tlačítko s vlajkou a kódem, kliknutím se otevře menu (ovládá se i šipkami a Esc).
- 15 jazyků seřazených podle abecedy vlastních názvů: čeština, Deutsch, English, Español, Français, Italiano, Nederlands, Polski, Português, slovenčina, українська, हिन्दी, 中文, 日本語, 한국어. Překládají se i chybové hlášky backendu.
- Výchozí jazyk podle prohlížeče (první podporovaný z jeho seznamu), jinak angličtina.
- Data se ukládají v prohlížeči pod novými klíči `hm.*`: po přechodu je potřeba se ve webu jednou znovu přihlásit.

## 0.8.3 – 2026-10-27
- Ikona aplikace (varianta D, nakloněný ovladač): favicon v záložce prohlížeče (SVG + PNG 32 px), ikona pro plochu iPhonu/Androidu (`apple-touch-icon`) a logo v záhlaví před názvem. Soubory jsou v `static/icons`, web je vrací na `/icons/…` bez přihlášení.

## 0.8.2 – 2026-10-27
- Nový název **GTV-Remote** (web, titulek stránky, přihlášení, QR text).
- Název zařízení jen v záložce. Přejmenování poklepáním na aktivní záložku, název se upraví přímo v ní (Enter nebo kliknutí mimo uloží, Esc zruší).
- Stav zařízení jen jednou, vpravo před tlačítkem „⋯“. Výrobce, model a IP adresa menším písmem.
- Verze backendu přesunuta do zápatí.
- Výchozí rozložení: ovladač vlevo, obrazovka vpravo, aplikace dole (uložené pořadí v prohlížeči zůstává).

## 0.8.1 – 2026-10-27
- Zařízení jako jedna skleněná deska: název, obrazovka, ovladač a aplikace na jedné průhledné ploše, za ní ambientní světlo v barvě běžící aplikace. Funguje v tmavém i světlém režimu.
- Záložky zařízení přecházejí do horní hrany desky a jsou vidět i u jediného zařízení. Název v záložce je výrazný, v desce menší.
- Přejmenování poklepáním na název (v desce i na aktivní záložce), bez samostatného tlačítka.
- Nastavení zařízení (dříve diagnostika) pod tlačítkem „⋯“ v rohu desky. Obsahuje údaje, odkaz na pomocníka, odebrání zařízení a záznamy backendu.
- Pořadí obrazovky, ovladače a aplikací lze měnit přetažením za úchyt (šest teček). Pořadí se pamatuje v prohlížeči. Z klávesnice posune úchyt část o jedno místo.

## 0.8.0 – 2026-10-27
- Pojmenování „zařízení“ místo „televize“ (Google TV může běžet i na boxu).
- Nově nalezená zařízení se neukazují mezi stávajícími. Tlačítko **+** v záhlaví bliká, když backend najde nové zařízení, a nabídne ho k přidání. Jinak otevře zadání IP adresy (`POST /api/tvs/{id}/adopt`, pole `adopted`).
- Pomocník na zařízení má vlastní okno (z části Aplikace), mimo nastavení backendu.
- Diagnostika zařízení (údaje, odebrání, záznamy backendu) je pod tlačítkem vedle přejmenování.
- Nastavení backendu obsahuje jen adresy, přihlášené telefony a prohlížeče, heslo a verzi.
- Tlačítko nastavení na ovladači otevírá Nastavení Androidu: přes pomocníka, nebo přes ADB (port se uloží po úspěšném testu klasického ladění). Jinak se pošle klávesa a web upozorní, že ji zařízení může ignorovat.
- Indikátor „Živě“ odstraněn. Zobrazí se jen upozornění při výpadku spojení s backendem.

## 0.7.0 – 2026-10-27
- Číslování verzí: verze ve webu, v `/api/health` a v Nastavení.
- Web v češtině a angličtině, přepínání vlajkami nahoře. Výchozí jazyk podle prohlížeče, volba se pamatuje. Chybové hlášky backendu se překládají podle hlavičky `X-Lang`.
- Návod k zapnutí ladění ADB na TV (Pro vývojáře) v Nastavení → Pomocník na TV.
- Tlačítko **Otestovat připojení ADB** (`POST /api/tvs/{id}/adb/test`). Ověří připojení a vrátí model a verzi Androidu.

## 0.6.x – 2026-10-27
- Psaní na TV přes IME podle funkční implementace (sofa-remote):
  - čítače z `remote_ime_key_inject` (`app_info.counter`, `counter_field`),
  - vkládání jen nového konce textu, mazání klávesou DEL,
  - čekání na ozvěnu `remote_ime_show_request`,
  - automatické otevření klávesnice ve webu, když TV otevře textové pole.
- Nulování čítačů IME po zavření pole nebo změně aplikace (oprava psaní v Netflixu).
- Diagnostika: log backendu ve webu s filtrem a kopírováním.

## 0.5.0
- Přihlášení heslem nastaveným při prvním spuštění (jen z LAN), tokeny pro zařízení, přidání telefonu QR kódem, seznam zařízení.
- Adresy backendu (internet / domácí síť) se nastavují ve webu.
- Záložky televizí, přejmenování a odebrání TV.
- Kolečko hlasitosti a velký ukazatel v obrazovce, výběr vstupu a otevření nastavení TV přes pomocníka.
- Výchozí síť `network_mode: host`.

## 0.4.0
- Webové rozhraní: obrazovka TV se světlem v barvě aplikace, ovladač, aplikace, párování.

## 0.1–0.3
- Backend: hledání TV přes mDNS, identita podle MAC z certifikátu, Remote protocol v2, API, WebSocket, instalace pomocníka přes ADB, port 888.
