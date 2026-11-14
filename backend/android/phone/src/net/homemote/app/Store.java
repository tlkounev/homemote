package net.homemote.app;

import android.content.Context;
import android.content.SharedPreferences;

/** Uložená vazba na backend (z párování QR kódem) nebo ručně zadaná adresa. */
public final class Store {
    private final SharedPreferences p;

    public Store(Context ctx) {
        p = ctx.getApplicationContext().getSharedPreferences("homemote", Context.MODE_PRIVATE);
    }

    public String instanceId() { return p.getString("instance_id", null); }
    public String localUrl() { return p.getString("local", null); }
    public String publicUrl() { return p.getString("public", null); }
    public String token() { return p.getString("token", null); }
    /** Ručně zadaná adresa webu (bez párování – přihlášení heslem přímo ve webu). */
    public String manualUrl() { return p.getString("manual", null); }

    public boolean bound() {
        return (token() != null && (localUrl() != null || publicUrl() != null)) || manualUrl() != null;
    }

    public void savePairing(String instanceId, String local, String pub, String token) {
        p.edit().clear()
                .putString("instance_id", instanceId)
                .putString("local", emptyToNull(local))
                .putString("public", emptyToNull(pub))
                .putString("token", token)
                .apply();
    }

    public void saveEndpoints(String local, String pub) {
        SharedPreferences.Editor e = p.edit();
        if (local != null) e.putString("local", emptyToNull(local));
        if (pub != null) e.putString("public", emptyToNull(pub));
        e.apply();
    }

    public void saveManual(String url) { p.edit().clear().putString("manual", url).apply(); }

    public void clear() { p.edit().clear().apply(); }

    static String emptyToNull(String s) {
        if (s == null) return null;
        s = s.trim();
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        return s.isEmpty() ? null : s;
    }
}
