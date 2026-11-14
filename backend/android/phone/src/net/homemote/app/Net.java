package net.homemote.app;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.Charset;

/** Jednoduché HTTP volání backendu (běží mimo hlavní vlákno). */
public final class Net {
    private static final Charset UTF8 = Charset.forName("UTF-8");

    public static final class HttpError extends IOException {
        public final int status;
        HttpError(int status, String body) { super(status + ": " + body); this.status = status; }
    }

    private Net() { }

    public static JSONObject get(String url, String token, int timeoutMs) throws IOException, JSONException {
        return request("GET", url, token, null, timeoutMs);
    }

    public static JSONObject post(String url, String token, JSONObject body, int timeoutMs) throws IOException, JSONException {
        return request("POST", url, token, body, timeoutMs);
    }

    private static JSONObject request(String method, String url, String token, JSONObject body, int timeoutMs)
            throws IOException, JSONException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setRequestMethod(method);
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setRequestProperty("Accept", "application/json");
            if (token != null) c.setRequestProperty("Authorization", "Bearer " + token);
            if (body != null) {
                byte[] data = body.toString().getBytes(UTF8);
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                c.setFixedLengthStreamingMode(data.length);
                OutputStream out = c.getOutputStream();
                out.write(data);
                out.close();
            }
            int status = c.getResponseCode();
            InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
            String text = in != null ? read(in) : "";
            if (status >= 400) {
                String msg = text;
                try { msg = new JSONObject(text).optString("error", text); } catch (JSONException ignored) { }
                throw new HttpError(status, msg);
            }
            return text.isEmpty() ? new JSONObject() : new JSONObject(text);
        } finally {
            c.disconnect();
        }
    }

    private static String read(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
        in.close();
        return new String(b.toByteArray(), UTF8);
    }
}
