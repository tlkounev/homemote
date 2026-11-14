package net.homemote.app;

import android.net.Uri;
import android.os.Build;

import org.json.JSONObject;

import java.io.IOException;

/**
 * Párování a volba adresy backendu.
 * Doma (adresa v domácí síti odpoví se stejným instance_id) se používá lokální adresa,
 * jinak adresa přes internet. Router tak nemusí umět NAT loopback.
 */
public final class Backend {
    private Backend() { }

    public static final class PairingException extends Exception {
        public PairingException(String msg) { super(msg); }
    }

    /** Důvod posledního neúspěchu (pro zobrazení uživateli – SSL, DNS, HTTP stav …). */
    public static volatile String lastError;

    private static boolean healthy(String base, String instanceId, int timeoutMs) {
        if (base == null) return false;
        try {
            JSONObject h = Net.get(base + "/api/health", null, timeoutMs);
            if (!h.optBoolean("ok")) { lastError = base + ": odpověď není Homemote"; return false; }
            if (instanceId != null && !instanceId.equals(h.optString("instance_id"))) {
                lastError = base + ": jiný backend (instance_id nesouhlasí)";
                return false;
            }
            return true;
        } catch (org.json.JSONException e) {
            lastError = base + ": odpověď není JSON (přesměrování / přihlašovací stránka proxy?)";
            return false;
        } catch (Exception e) {
            lastError = base + ": " + describe(e);
            return false;
        }
    }

    static String describe(Throwable e) {
        String name = e.getClass().getSimpleName();
        String msg = e.getMessage();
        Throwable c = e.getCause();
        if (c != null && c.getMessage() != null && (msg == null || !msg.contains(c.getMessage()))) msg = (msg != null ? msg + " – " : "") + c.getMessage();
        return name + (msg != null ? " (" + msg + ")" : "");
    }

    /** Vrátí adresu, na které backend právě odpovídá, nebo null. */
    public static String choose(Store s) {
        if (s.manualUrl() != null) return s.manualUrl();
        if (healthy(s.localUrl(), s.instanceId(), 1500)) return s.localUrl();
        String localErr = lastError;
        if (healthy(s.publicUrl(), s.instanceId(), 8000)) return s.publicUrl();
        if (s.publicUrl() == null) lastError = localErr + "\n(adresa z internetu není nastavená)";
        return null;
    }

    /** Ověří, že token pořád platí (zařízení nebylo ve webu odhlášeno). */
    public static boolean tokenValid(String base, String token) throws IOException {
        try {
            return Net.get(base + "/api/auth/status", token, 6000).optBoolean("authenticated");
        } catch (org.json.JSONException e) {
            throw new IOException(e);
        }
    }

    /** Párování z URI homemote://pair?v=1&id=…&code=…&local=…&public=… (QR kód z „Přidat telefon“). */
    public static String pair(Store s, Uri uri) throws PairingException {
        if (uri == null || !"homemote".equals(uri.getScheme()) || !"pair".equals(uri.getHost())) {
            throw new PairingException("bad-qr");
        }
        String id = uri.getQueryParameter("id");
        String code = uri.getQueryParameter("code");
        String local = Store.emptyToNull(uri.getQueryParameter("local"));
        String pub = Store.emptyToNull(uri.getQueryParameter("public"));
        if (code == null || (local == null && pub == null)) throw new PairingException("bad-qr");
        String base = healthy(local, id, 2000) ? local : healthy(pub, id, 8000) ? pub : null;
        if (base == null) throw new PairingException("unreachable|" + (pub == null ? "QR kód neobsahuje adresu z internetu; " : "") + lastError);
        try {
            JSONObject body = new JSONObject().put("code", code).put("device_name", "Homemote – " + Build.MODEL);
            JSONObject r = Net.post(base + "/api/auth/redeem", null, body, 10000);
            String token = r.getString("token");
            JSONObject ep = r.optJSONObject("endpoints");
            if (ep != null) {
                String l = Store.emptyToNull(ep.optString("local", null));
                String p = Store.emptyToNull(ep.optString("public", null));
                if (l != null) local = l;
                if (p != null) pub = p;
                if (id == null) id = ep.optString("instance_id", null);
            }
            s.savePairing(id, local, pub, token);
            return base;
        } catch (Net.HttpError e) {
            throw new PairingException(e.status == 400 || e.status == 401 || e.status == 404 ? "code" : e.getMessage());
        } catch (Exception e) {
            throw new PairingException(String.valueOf(e.getMessage()));
        }
    }
}
