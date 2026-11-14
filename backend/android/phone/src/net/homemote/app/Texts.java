package net.homemote.app;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** Pár nativních textů aplikace (zbytek rozhraní je web backendu a úvodní stránka v assets). */
public final class Texts {
    // klíče: 0 = backend nedostupný, 1 = zkusit znovu, 2 = odpojit, 3 = připojuji
    private static final Map<String, String[]> T = new HashMap<String, String[]>();
    static {
        T.put("cs", new String[]{"Backend Homemote teď není dostupný. Zkontrolujte připojení k síti.", "Zkusit znovu", "Odpojit od backendu", "Připojuji…"});
        T.put("sk", new String[]{"Backend Homemote teraz nie je dostupný. Skontrolujte pripojenie k sieti.", "Skúsiť znova", "Odpojiť od backendu", "Pripájam…"});
        T.put("en", new String[]{"The Homemote backend isn't reachable right now. Check your network connection.", "Try again", "Disconnect from backend", "Connecting…"});
        T.put("de", new String[]{"Das Homemote-Backend ist gerade nicht erreichbar. Prüfe die Netzwerkverbindung.", "Erneut versuchen", "Vom Backend trennen", "Verbinde…"});
        T.put("es", new String[]{"El backend de Homemote no está disponible ahora. Comprueba la conexión de red.", "Reintentar", "Desconectar del backend", "Conectando…"});
        T.put("fr", new String[]{"Le backend Homemote est injoignable pour le moment. Vérifiez la connexion réseau.", "Réessayer", "Se déconnecter du backend", "Connexion…"});
        T.put("it", new String[]{"Il backend Homemote non è raggiungibile ora. Controlla la connessione di rete.", "Riprova", "Disconnetti dal backend", "Connessione…"});
        T.put("nl", new String[]{"De Homemote-backend is nu niet bereikbaar. Controleer de netwerkverbinding.", "Opnieuw proberen", "Loskoppelen van backend", "Verbinden…"});
        T.put("pl", new String[]{"Backend Homemote jest teraz niedostępny. Sprawdź połączenie z siecią.", "Spróbuj ponownie", "Odłącz od backendu", "Łączenie…"});
        T.put("pt", new String[]{"O backend Homemote não está acessível agora. Verifique a ligação à rede.", "Tentar novamente", "Desligar do backend", "A ligar…"});
        T.put("uk", new String[]{"Бекенд Homemote зараз недоступний. Перевірте підключення до мережі.", "Спробувати ще раз", "Від’єднатися від бекенду", "Підключення…"});
        T.put("hi", new String[]{"Homemote बैकएंड अभी उपलब्ध नहीं है। नेटवर्क कनेक्शन जाँचें।", "फिर से कोशिश करें", "बैकएंड से डिस्कनेक्ट करें", "कनेक्ट हो रहा है…"});
        T.put("zh", new String[]{"暂时无法连接 Homemote 后端。请检查网络连接。", "重试", "与后端断开", "正在连接…"});
        T.put("ja", new String[]{"Homemote バックエンドに接続できません。ネットワーク接続を確認してください。", "再試行", "バックエンドから切断", "接続中…"});
        T.put("ko", new String[]{"지금 Homemote 백엔드에 연결할 수 없습니다. 네트워크 연결을 확인하세요.", "다시 시도", "백엔드 연결 해제", "연결 중…"});
    }

    private Texts() { }

    public static String get(int i) {
        String[] t = T.get(Locale.getDefault().getLanguage());
        if (t == null) t = T.get("en");
        return t[i];
    }
}
