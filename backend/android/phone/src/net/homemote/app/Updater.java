package net.homemote.app;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Aktualizace aplikace z backendu: backend má v image aktuální homemote.apk a v /api/health hlásí
 * jeho verzi. Aplikace ji porovná se svou, nabídne lištu „Aktualizovat / Později“ a APK nainstaluje
 * přes PackageInstaller (Android ukáže svůj potvrzovací dialog). Podpis je stejný, takže jde o aktualizaci.
 */
final class Updater {
    static final long SNOOZE_MS = 24L * 3600 * 1000;   // „Později“ = připomenout zítra
    static final long CHECK_EVERY_MS = 3600L * 1000;    // kontrola nejvýš jednou za hodinu

    /** Nabízená verze z backendu. */
    static final class Offer {
        final String version; final int code; final String url;
        Offer(String version, int code, String url) { this.version = version; this.code = code; this.url = url; }
    }

    interface Progress { void update(int percent); }

    private final SharedPreferences p;

    Updater(Context ctx) {
        p = ctx.getApplicationContext().getSharedPreferences("homemote_update", Context.MODE_PRIVATE);
    }

    boolean dueForCheck() {
        return System.currentTimeMillis() - p.getLong("checked", 0) > CHECK_EVERY_MS;
    }

    /** Volat mimo hlavní vlákno. Vrací nabídku, jen když je novější a uživatel ji neodložil. */
    Offer check(String base) {
        p.edit().putLong("checked", System.currentTimeMillis()).apply();
        try {
            JSONObject h = Net.get(base + "/api/health", null, 8000);
            JSONObject app = h.optJSONObject("phone_app");
            if (app == null) return null;
            int code = app.optInt("code", 0);
            if (code <= BuildInfo.VERSION_CODE) return null;
            if (p.getInt("snooze_code", -1) == code && System.currentTimeMillis() < p.getLong("snooze_until", 0)) return null;
            String url = app.optString("url", "/download/homemote.apk");
            return new Offer(app.optString("version", "?"), code, url.startsWith("http") ? url : base + url);
        } catch (Exception e) {
            return null;
        }
    }

    void snooze(Offer o) {
        p.edit().putInt("snooze_code", o.code).putLong("snooze_until", System.currentTimeMillis() + SNOOZE_MS).apply();
    }

    /** Smí aplikace instalovat? Jinak je potřeba jednou povolit „Instalovat neznámé aplikace“. */
    static boolean canInstall(Context ctx) {
        return ctx.getPackageManager().canRequestPackageInstalls();
    }

    static void openInstallPermission(Activity a) {
        Intent i = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + a.getPackageName()));
        try { a.startActivity(i); } catch (Exception e) { a.startActivity(new Intent(Settings.ACTION_SETTINGS)); }
    }

    /** Stáhne APK rovnou do instalační relace a odešle ji. Volat mimo hlavní vlákno. */
    static void downloadAndInstall(Context ctx, Offer o, Progress progress) throws IOException {
        PackageInstaller installer = ctx.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(ctx.getPackageName());
        if (Build.VERSION.SDK_INT >= 31) {
            // Bez dialogu jen tam, kde to Android dovolí (aplikace je sama instalátorem); jinak se dialog ukáže.
            params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
        }
        int id = installer.createSession(params);
        PackageInstaller.Session session = installer.openSession(id);
        HttpURLConnection c = (HttpURLConnection) new URL(o.url).openConnection();
        boolean ok = false;
        try {
            c.setConnectTimeout(10000);
            c.setReadTimeout(30000);
            int status = c.getResponseCode();
            if (status != 200) throw new IOException("HTTP " + status);
            long total = c.getContentLengthLong();
            InputStream in = c.getInputStream();
            OutputStream out = session.openWrite("homemote.apk", 0, total > 0 ? total : -1);
            byte[] buf = new byte[64 * 1024];
            long done = 0;
            int n, last = -1;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                done += n;
                int pct = total > 0 ? (int) (done * 100 / total) : -1;
                if (pct != last) { last = pct; progress.update(pct); }
            }
            session.fsync(out);
            out.close();
            in.close();
            Intent result = new Intent(ctx, UpdateReceiver.class).setAction(UpdateReceiver.ACTION);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
            PendingIntent pi = PendingIntent.getBroadcast(ctx, id, result, flags);
            session.commit(pi.getIntentSender());
            ok = true;
        } finally {
            c.disconnect();
            if (!ok) session.abandon();
            session.close();
        }
    }
}
