package net.homemote.helper;

import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Build;
import android.provider.Settings;
import android.app.NotificationManager;
import android.util.Log;

/** Sdílený stav pomocníka: HTTP server, ohlášení přes mDNS a token backendu. */
public final class HelperCore {
    public static final String TAG = "HomemoteHelper";
    public static final int PORT = 8765;
    public static final String SERVICE_TYPE = "_homemote-helper._tcp";

    private static HelperCore instance;

    private final Context ctx;
    private final SharedPreferences prefs;
    private HttpServer server;
    private NsdManager.RegistrationListener nsdListener;

    private HelperCore(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        this.prefs = this.ctx.getSharedPreferences("homemote", Context.MODE_PRIVATE);
    }

    public static synchronized HelperCore get(Context ctx) {
        if (instance == null) instance = new HelperCore(ctx);
        return instance;
    }

    /** Spustí server a mDNS, pokud ještě neběží. Volá se ze služby, aktivity i po startu TV. */
    public synchronized void ensureStarted() {
        if (server == null || !server.isRunning()) {
            server = new HttpServer(PORT, new Api(ctx, this));
            server.start();
        }
        if (nsdListener == null) registerNsd();
    }

    public Context context() { return ctx; }

    public String version() { return BuildInfo.VERSION_NAME; }

    public boolean serverRunning() { return server != null && server.isRunning(); }

    // --- token (TOFU) -----------------------------------------------------------
    public synchronized String token() { return prefs.getString("token", null); }

    /** @return true = token přijat (první nebo shodný), false = pomocník patří jinému backendu. */
    public synchronized boolean claim(String token) {
        String cur = token();
        if (cur == null) {
            prefs.edit().putString("token", token).apply();
            Log.i(TAG, "pomocník přiřazen backendu");
            return true;
        }
        return cur.equals(token);
    }

    public synchronized void resetToken() { prefs.edit().remove("token").apply(); }

    // --- přístup k notifikacím (MediaSession) ------------------------------------
    public ComponentName listenerComponent() { return new ComponentName(ctx, MediaListenerService.class); }

    public boolean listenerEnabled() {
        ComponentName cn = listenerComponent();
        if (Build.VERSION.SDK_INT >= 27) {
            NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
            try { return nm != null && nm.isNotificationListenerAccessGranted(cn); } catch (Throwable ignored) { }
        }
        String s = Settings.Secure.getString(ctx.getContentResolver(), "enabled_notification_listeners");
        return s != null && s.contains(cn.flattenToString());
    }

    // --- mDNS ------------------------------------------------------------------------
    private void registerNsd() {
        try {
            NsdManager nsd = (NsdManager) ctx.getSystemService(Context.NSD_SERVICE);
            if (nsd == null) return;
            NsdServiceInfo info = new NsdServiceInfo();
            info.setServiceName("Homemote helper " + Build.MODEL);
            info.setServiceType(SERVICE_TYPE);
            info.setPort(PORT);
            info.setAttribute("v", "1");
            info.setAttribute("version", version());
            nsdListener = new NsdManager.RegistrationListener() {
                @Override public void onServiceRegistered(NsdServiceInfo i) { Log.i(TAG, "mDNS ohlášeno: " + i.getServiceName()); }
                @Override public void onRegistrationFailed(NsdServiceInfo i, int code) { Log.w(TAG, "mDNS selhalo: " + code); nsdListener = null; }
                @Override public void onServiceUnregistered(NsdServiceInfo i) { }
                @Override public void onUnregistrationFailed(NsdServiceInfo i, int code) { }
            };
            nsd.registerService(info, NsdManager.PROTOCOL_DNS_SD, nsdListener);
        } catch (Throwable t) {
            Log.w(TAG, "mDNS nelze ohlásit", t);
            nsdListener = null;
        }
    }
}
