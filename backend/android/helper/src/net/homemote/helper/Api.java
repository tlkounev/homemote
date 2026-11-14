package net.homemote.helper;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.media.MediaMetadata;
import android.media.session.MediaController;
import android.media.session.MediaSessionManager;
import android.media.session.PlaybackState;
import android.media.tv.TvContract;
import android.media.tv.TvInputInfo;
import android.media.tv.TvInputManager;
import android.os.Build;
import android.os.SystemClock;
import android.provider.Settings;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Rozhraní pomocníka pro backend (kontrakt: API.md, část „Pomocník na TV“). */
public final class Api implements HttpServer.Handler {
    private final Context ctx;
    private final HelperCore core;

    public Api(Context ctx, HelperCore core) {
        this.ctx = ctx;
        this.core = core;
    }

    @Override
    public HttpServer.Response handle(HttpServer.Request r) {
        String m = r.method, p = r.path;
        try {
            if (m.equals("POST") && p.equals("/v1/claim")) return claim(r);
            if (m.equals("GET") && p.equals("/v1/ping")) return HttpServer.Response.json(200, "{\"ok\":true}");

            String token = core.token();
            String sent = r.header("x-token");
            if (token == null) return HttpServer.Response.text(403, "pomocník zatím nemá token – nejdřív POST /v1/claim");
            if (sent == null || !token.equals(sent)) return HttpServer.Response.text(403, "neplatný token");

            if (m.equals("GET") && p.equals("/v1/info")) return info();
            if (m.equals("GET") && p.equals("/v1/apps")) return apps();
            if (m.equals("GET") && p.startsWith("/v1/apps/") && p.endsWith("/icon")) {
                return icon(p.substring("/v1/apps/".length(), p.length() - "/icon".length()));
            }
            if (m.equals("POST") && p.equals("/v1/launch")) return launch(new JSONObject(r.bodyText()).optString("package"));
            if (m.equals("GET") && p.equals("/v1/nowplaying")) return HttpServer.Response.json(200, nowPlaying().toString());
            if (m.equals("POST") && p.equals("/v1/seek")) return seek(new JSONObject(r.bodyText()).optLong("position_ms", -1));
            if (m.equals("GET") && p.equals("/v1/inputs")) return inputs();
            if (m.equals("POST") && p.equals("/v1/inputs/select")) return selectInput(new JSONObject(r.bodyText()).optString("id"));
            if (m.equals("POST") && p.equals("/v1/settings/open")) return openSettings();
            return HttpServer.Response.text(404, "neznámá cesta " + m + " " + p);
        } catch (JSONException e) {
            return HttpServer.Response.text(400, "neplatný JSON: " + e.getMessage());
        }
    }

    private static HttpServer.Response ok() { return HttpServer.Response.json(200, "{\"ok\":true}"); }

    // --- přiřazení k backendu -------------------------------------------------------
    private HttpServer.Response claim(HttpServer.Request r) throws JSONException {
        String t = new JSONObject(r.bodyText()).optString("token");
        if (t.length() < 16) return HttpServer.Response.text(400, "chybí token");
        return core.claim(t) ? ok() : HttpServer.Response.text(403, "pomocník patří jinému backendu");
    }

    private HttpServer.Response info() throws JSONException {
        JSONObject o = new JSONObject();
        o.put("version", core.version());
        o.put("sdk", Build.VERSION.SDK_INT);
        o.put("listener_enabled", core.listenerEnabled());
        o.put("overlay_allowed", Settings.canDrawOverlays(ctx));
        o.put("model", Build.MODEL);
        o.put("manufacturer", Build.MANUFACTURER);
        return HttpServer.Response.json(200, o.toString());
    }

    // --- aplikace ---------------------------------------------------------------------
    private HttpServer.Response apps() throws JSONException {
        PackageManager pm = ctx.getPackageManager();
        Map<String, String> found = new LinkedHashMap<String, String>();
        for (String cat : new String[]{Intent.CATEGORY_LEANBACK_LAUNCHER, Intent.CATEGORY_LAUNCHER}) {
            Intent i = new Intent(Intent.ACTION_MAIN).addCategory(cat);
            List<ResolveInfo> list = pm.queryIntentActivities(i, 0);
            for (ResolveInfo ri : list) {
                String pkg = ri.activityInfo.packageName;
                if (pkg.equals(ctx.getPackageName()) || found.containsKey(pkg)) continue;
                CharSequence label = ri.activityInfo.applicationInfo.loadLabel(pm);
                found.put(pkg, label != null ? label.toString() : pkg);
            }
        }
        JSONArray a = new JSONArray();
        for (Map.Entry<String, String> e : found.entrySet()) {
            a.put(new JSONObject().put("package", e.getKey()).put("label", e.getValue()));
        }
        return HttpServer.Response.json(200, a.toString());
    }

    private HttpServer.Response icon(String pkg) {
        PackageManager pm = ctx.getPackageManager();
        Drawable d = null;
        try {
            Intent li = pm.getLeanbackLaunchIntentForPackage(pkg);
            if (li != null) d = pm.getActivityBanner(li);
            if (d == null) d = pm.getApplicationBanner(pkg);
            if (d == null) d = pm.getApplicationIcon(pkg);
        } catch (PackageManager.NameNotFoundException e) {
            return HttpServer.Response.text(404, "aplikace nenalezena");
        }
        if (d == null) return HttpServer.Response.text(404, "aplikace nemá ikonu");
        return new HttpServer.Response(200, "image/png", toPng(d));
    }

    private static byte[] toPng(Drawable d) {
        Bitmap bmp;
        if (d instanceof BitmapDrawable && ((BitmapDrawable) d).getBitmap() != null) {
            bmp = ((BitmapDrawable) d).getBitmap();
        } else {
            int w = d.getIntrinsicWidth() > 0 ? d.getIntrinsicWidth() : 192;
            int h = d.getIntrinsicHeight() > 0 ? d.getIntrinsicHeight() : 192;
            if (w > 640) { h = h * 640 / w; w = 640; }
            bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
            Canvas c = new Canvas(bmp);
            d.setBounds(0, 0, w, h);
            d.draw(c);
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        bmp.compress(Bitmap.CompressFormat.PNG, 100, out);
        return out.toByteArray();
    }

    private HttpServer.Response launch(String pkg) {
        if (pkg == null || pkg.length() == 0) return HttpServer.Response.text(400, "chybí package");
        PackageManager pm = ctx.getPackageManager();
        Intent i = pm.getLeanbackLaunchIntentForPackage(pkg);
        if (i == null) i = pm.getLaunchIntentForPackage(pkg);
        if (i == null) return HttpServer.Response.text(404, "aplikaci nelze spustit: " + pkg);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
        return start(i);
    }

    private HttpServer.Response start(Intent i) {
        try {
            ctx.startActivity(i);
            return ok();
        } catch (Throwable t) {
            return HttpServer.Response.text(500, "spuštění selhalo: " + t);
        }
    }

    // --- přehrávání (MediaSession) ----------------------------------------------------
    private MediaController pickController() {
        MediaSessionManager msm = (MediaSessionManager) ctx.getSystemService(Context.MEDIA_SESSION_SERVICE);
        if (msm == null) return null;
        List<MediaController> list = msm.getActiveSessions(core.listenerComponent());
        if (list == null || list.isEmpty()) return null;
        for (MediaController c : list) {
            PlaybackState s = c.getPlaybackState();
            if (s != null && s.getState() == PlaybackState.STATE_PLAYING) return c;
        }
        return list.get(0);
    }

    private static String stateName(int s) {
        switch (s) {
            case PlaybackState.STATE_PLAYING: return "playing";
            case PlaybackState.STATE_PAUSED: return "paused";
            case PlaybackState.STATE_BUFFERING:
            case PlaybackState.STATE_CONNECTING:
            case PlaybackState.STATE_FAST_FORWARDING:
            case PlaybackState.STATE_REWINDING: return "buffering";
            case PlaybackState.STATE_STOPPED:
            case PlaybackState.STATE_ERROR: return "stopped";
            default: return "none";
        }
    }

    private static String firstText(MediaMetadata md, String... keys) {
        if (md == null) return "";
        for (String k : keys) {
            CharSequence v = md.getText(k);
            if (v != null && v.length() > 0) return v.toString();
        }
        return "";
    }

    private JSONObject nowPlaying() throws JSONException {
        JSONObject o = new JSONObject();
        MediaController c;
        try {
            c = pickController();
        } catch (SecurityException e) {
            return o.put("active", false).put("state", "none").put("error", "chybí přístup k notifikacím");
        }
        if (c == null) return o.put("active", false).put("state", "none");
        MediaMetadata md = c.getMetadata();
        PlaybackState st = c.getPlaybackState();
        long duration = md != null ? md.getLong(MediaMetadata.METADATA_KEY_DURATION) : 0;
        long pos = 0;
        float speed = 1f;
        String state = "none";
        boolean canSeek = false;
        if (st != null) {
            state = stateName(st.getState());
            speed = st.getPlaybackSpeed();
            pos = st.getPosition();
            if (st.getState() == PlaybackState.STATE_PLAYING && st.getLastPositionUpdateTime() > 0) {
                pos += (long) ((SystemClock.elapsedRealtime() - st.getLastPositionUpdateTime()) * speed);
            }
            canSeek = (st.getActions() & PlaybackState.ACTION_SEEK_TO) != 0 && duration > 0;
        }
        if (duration > 0 && pos > duration) pos = duration;
        if (pos < 0) pos = 0;
        o.put("active", true);
        o.put("package", c.getPackageName());
        o.put("title", firstText(md, MediaMetadata.METADATA_KEY_DISPLAY_TITLE, MediaMetadata.METADATA_KEY_TITLE));
        o.put("subtitle", firstText(md, MediaMetadata.METADATA_KEY_DISPLAY_SUBTITLE, MediaMetadata.METADATA_KEY_ARTIST,
                MediaMetadata.METADATA_KEY_ALBUM));
        o.put("state", state);
        o.put("duration_ms", Math.max(duration, 0));
        o.put("position_ms", pos);
        o.put("speed", (double) speed);
        o.put("can_seek", canSeek);
        return o;
    }

    private HttpServer.Response seek(long posMs) {
        if (posMs < 0) return HttpServer.Response.text(400, "position_ms musí být >= 0");
        MediaController c;
        try {
            c = pickController();
        } catch (SecurityException e) {
            return HttpServer.Response.text(409, "chybí přístup k notifikacím");
        }
        if (c == null) return HttpServer.Response.text(409, "nic se nepřehrává");
        PlaybackState st = c.getPlaybackState();
        if (st == null || (st.getActions() & PlaybackState.ACTION_SEEK_TO) == 0) {
            return HttpServer.Response.text(501, "aplikace nepodporuje přesný skok");
        }
        c.getTransportControls().seekTo(posMs);
        return ok();
    }

    // --- vstupy (HDMI apod.) --------------------------------------------------------------
    private HttpServer.Response inputs() throws JSONException {
        TvInputManager tim = (TvInputManager) ctx.getSystemService(Context.TV_INPUT_SERVICE);
        JSONArray a = new JSONArray();
        if (tim != null) {
            for (TvInputInfo ti : tim.getTvInputList()) {
                if (!ti.isPassthroughInput()) continue;
                try { if (ti.isHidden(ctx)) continue; } catch (Throwable ignored) { }
                CharSequence label = null;
                try { label = ti.loadCustomLabel(ctx); } catch (Throwable ignored) { }
                if (label == null || label.length() == 0) label = ti.loadLabel(ctx);
                a.put(new JSONObject().put("id", ti.getId()).put("label", label != null ? label.toString() : ti.getId()));
            }
        }
        return HttpServer.Response.json(200, a.toString());
    }

    private HttpServer.Response selectInput(String id) {
        if (id == null || id.length() == 0) return HttpServer.Response.text(400, "chybí id");
        Intent i = new Intent(Intent.ACTION_VIEW, TvContract.buildChannelUriForPassthroughInput(id));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return start(i);
    }

    private HttpServer.Response openSettings() {
        Intent i = new Intent(Settings.ACTION_SETTINGS);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return start(i);
    }
}
