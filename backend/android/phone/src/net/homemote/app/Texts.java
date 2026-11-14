package net.homemote.app;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** Pár nativních textů aplikace (zbytek rozhraní je web backendu a úvodní stránka v assets). */
public final class Texts {
    // klíče: 0 = backend nedostupný, 1 = zkusit znovu, 2 = odpojit, 3 = připojuji,
    // 4–10 = aktualizace aplikace (nabídka, aktualizovat, později, stahuji, instaluji, selhala, povolit instalaci)
    private static final Map<String, String[]> T = new HashMap<String, String[]>();
    static {
        T.put("cs", new String[]{"Backend Homemote teď není dostupný. Zkontrolujte připojení k síti.", "Zkusit znovu", "Odpojit od backendu", "Připojuji…", "Je dostupná nová verze aplikace {v}", "Aktualizovat", "Později", "Stahuji aktualizaci… {p} %", "Instaluji…", "Aktualizace selhala: ", "Povolte aplikaci Homemote instalovat aplikace a vraťte se zpět."});
        T.put("sk", new String[]{"Backend Homemote teraz nie je dostupný. Skontrolujte pripojenie k sieti.", "Skúsiť znova", "Odpojiť od backendu", "Pripájam…", "Je dostupná nová verzia aplikácie {v}", "Aktualizovať", "Neskôr", "Sťahujem aktualizáciu… {p} %", "Inštalujem…", "Aktualizácia zlyhala: ", "Povoľte aplikácii Homemote inštalovať aplikácie a vráťte sa späť."});
        T.put("en", new String[]{"The Homemote backend isn't reachable right now. Check your network connection.", "Try again", "Disconnect from backend", "Connecting…", "A new app version {v} is available", "Update", "Later", "Downloading update… {p} %", "Installing…", "Update failed: ", "Allow Homemote to install apps, then come back."});
        T.put("de", new String[]{"Das Homemote-Backend ist gerade nicht erreichbar. Prüfe die Netzwerkverbindung.", "Erneut versuchen", "Vom Backend trennen", "Verbinde…", "Neue App-Version {v} verfügbar", "Aktualisieren", "Später", "Update wird geladen… {p} %", "Wird installiert…", "Update fehlgeschlagen: ", "Erlaube Homemote, Apps zu installieren, und kehre dann zurück."});
        T.put("es", new String[]{"El backend de Homemote no está disponible ahora. Comprueba la conexión de red.", "Reintentar", "Desconectar del backend", "Conectando…", "Hay una nueva versión de la app {v}", "Actualizar", "Más tarde", "Descargando actualización… {p} %", "Instalando…", "Error al actualizar: ", "Permite que Homemote instale apps y vuelve."});
        T.put("fr", new String[]{"Le backend Homemote est injoignable pour le moment. Vérifiez la connexion réseau.", "Réessayer", "Se déconnecter du backend", "Connexion…", "Nouvelle version de l’app {v} disponible", "Mettre à jour", "Plus tard", "Téléchargement… {p} %", "Installation…", "Échec de la mise à jour : ", "Autorisez Homemote à installer des applis, puis revenez."});
        T.put("it", new String[]{"Il backend Homemote non è raggiungibile ora. Controlla la connessione di rete.", "Riprova", "Disconnetti dal backend", "Connessione…", "È disponibile la nuova versione dell’app {v}", "Aggiorna", "Più tardi", "Download aggiornamento… {p} %", "Installazione…", "Aggiornamento non riuscito: ", "Consenti a Homemote di installare app, poi torna qui."});
        T.put("nl", new String[]{"De Homemote-backend is nu niet bereikbaar. Controleer de netwerkverbinding.", "Opnieuw proberen", "Loskoppelen van backend", "Verbinden…", "Nieuwe app-versie {v} beschikbaar", "Bijwerken", "Later", "Update downloaden… {p} %", "Installeren…", "Bijwerken mislukt: ", "Sta Homemote toe apps te installeren en kom dan terug."});
        T.put("pl", new String[]{"Backend Homemote jest teraz niedostępny. Sprawdź połączenie z siecią.", "Spróbuj ponownie", "Odłącz od backendu", "Łączenie…", "Dostępna jest nowa wersja aplikacji {v}", "Aktualizuj", "Później", "Pobieranie aktualizacji… {p} %", "Instalowanie…", "Aktualizacja nie powiodła się: ", "Zezwól aplikacji Homemote na instalowanie aplikacji i wróć."});
        T.put("pt", new String[]{"O backend Homemote não está acessível agora. Verifique a ligação à rede.", "Tentar novamente", "Desligar do backend", "A ligar…", "Há uma nova versão da app {v}", "Atualizar", "Mais tarde", "A transferir atualização… {p} %", "A instalar…", "A atualização falhou: ", "Permita que a Homemote instale apps e volte."});
        T.put("uk", new String[]{"Бекенд Homemote зараз недоступний. Перевірте підключення до мережі.", "Спробувати ще раз", "Від’єднатися від бекенду", "Підключення…", "Доступна нова версія застосунку {v}", "Оновити", "Пізніше", "Завантаження оновлення… {p} %", "Встановлення…", "Не вдалося оновити: ", "Дозвольте Homemote встановлювати застосунки й поверніться."});
        T.put("hi", new String[]{"Homemote बैकएंड अभी उपलब्ध नहीं है। नेटवर्क कनेक्शन जाँचें।", "फिर से कोशिश करें", "बैकएंड से डिस्कनेक्ट करें", "कनेक्ट हो रहा है…", "ऐप का नया संस्करण {v} उपलब्ध है", "अपडेट करें", "बाद में", "अपडेट डाउनलोड हो रहा है… {p} %", "इंस्टॉल हो रहा है…", "अपडेट विफल: ", "Homemote को ऐप इंस्टॉल करने की अनुमति दें, फिर वापस आएँ।"});
        T.put("zh", new String[]{"暂时无法连接 Homemote 后端。请检查网络连接。", "重试", "与后端断开", "正在连接…", "有新版本应用 {v}", "更新", "稍后", "正在下载更新… {p}%", "正在安装…", "更新失败：", "请允许 Homemote 安装应用，然后返回。"});
        T.put("ja", new String[]{"Homemote バックエンドに接続できません。ネットワーク接続を確認してください。", "再試行", "バックエンドから切断", "接続中…", "新しいアプリのバージョン {v} があります", "更新", "後で", "更新をダウンロード中… {p}%", "インストール中…", "更新に失敗しました：", "Homemote にアプリのインストールを許可してから戻ってください。"});
        T.put("ko", new String[]{"지금 Homemote 백엔드에 연결할 수 없습니다. 네트워크 연결을 확인하세요.", "다시 시도", "백엔드 연결 해제", "연결 중…", "새 앱 버전 {v}이(가) 있습니다", "업데이트", "나중에", "업데이트 다운로드 중… {p}%", "설치 중…", "업데이트 실패: ", "Homemote의 앱 설치를 허용한 후 돌아오세요."});
    }

    private Texts() { }

    public static String get(int i) {
        String[] t = T.get(Locale.getDefault().getLanguage());
        if (t == null) t = T.get("en");
        return t[i];
    }
}
