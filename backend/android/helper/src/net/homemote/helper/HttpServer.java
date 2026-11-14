package net.homemote.helper;

import android.util.Log;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.Charset;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Minimální HTTP/1.1 server (bez knihoven): jeden požadavek na spojení, odpověď s Connection: close. */
public final class HttpServer {
    private static final Charset UTF8 = Charset.forName("UTF-8");
    private static final int MAX_BODY = 64 * 1024;

    public static final class Request {
        public String method;
        public String path;
        public final Map<String, String> headers = new HashMap<String, String>();
        public byte[] body = new byte[0];
        public String remote;
        public String header(String name) { return headers.get(name.toLowerCase(Locale.ROOT)); }
        public String bodyText() { return new String(body, UTF8); }
    }

    public static final class Response {
        public final int status;
        public final String contentType;
        public final byte[] body;
        public Response(int status, String contentType, byte[] body) {
            this.status = status; this.contentType = contentType; this.body = body;
        }
        public static Response json(int status, String json) { return new Response(status, "application/json", json.getBytes(UTF8)); }
        public static Response text(int status, String text) { return new Response(status, "text/plain; charset=utf-8", text.getBytes(UTF8)); }
    }

    public interface Handler { Response handle(Request req); }

    private final int port;
    private final Handler handler;
    private final ExecutorService pool = Executors.newCachedThreadPool();
    private volatile ServerSocket socket;
    private volatile boolean running;

    public HttpServer(int port, Handler handler) {
        this.port = port;
        this.handler = handler;
    }

    public boolean isRunning() { return running; }

    public void start() {
        running = true;
        Thread t = new Thread(new Runnable() {
            @Override public void run() { loop(); }
        }, "homemote-http");
        t.setDaemon(true);
        t.start();
    }

    private void loop() {
        while (running) {
            try {
                ServerSocket ss = new ServerSocket();
                ss.setReuseAddress(true);
                ss.bind(new InetSocketAddress(port));
                socket = ss;
                Log.i(HelperCore.TAG, "HTTP server běží na portu " + port);
                while (running) {
                    final Socket s = ss.accept();
                    pool.execute(new Runnable() {
                        @Override public void run() { serve(s); }
                    });
                }
            } catch (IOException e) {
                Log.w(HelperCore.TAG, "HTTP server: " + e);
                try { Thread.sleep(3000); } catch (InterruptedException ignored) { return; }
            }
        }
    }

    private void serve(Socket s) {
        try {
            s.setSoTimeout(10000);
            InputStream in = new BufferedInputStream(s.getInputStream());
            Request req = parse(in);
            Response res;
            if (req == null) {
                res = Response.text(400, "bad request");
            } else {
                req.remote = s.getInetAddress() != null ? s.getInetAddress().getHostAddress() : "";
                try {
                    res = handler.handle(req);
                } catch (Throwable t) {
                    Log.w(HelperCore.TAG, "chyba při " + req.method + " " + req.path, t);
                    res = Response.text(500, String.valueOf(t));
                }
            }
            write(s.getOutputStream(), res);
        } catch (IOException ignored) {
        } finally {
            try { s.close(); } catch (IOException ignored) { }
        }
    }

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int c;
        while ((c = in.read()) != -1) {
            if (c == '\n') break;
            if (c != '\r') b.write(c);
            if (b.size() > 8192) throw new IOException("line too long");
        }
        if (c == -1 && b.size() == 0) return null;
        return new String(b.toByteArray(), UTF8);
    }

    private static Request parse(InputStream in) throws IOException {
        String line = readLine(in);
        if (line == null) return null;
        String[] parts = line.split(" ");
        if (parts.length < 2) return null;
        Request r = new Request();
        r.method = parts[0].toUpperCase(Locale.ROOT);
        String p = parts[1];
        int q = p.indexOf('?');
        r.path = java.net.URLDecoder.decode(q >= 0 ? p.substring(0, q) : p, "UTF-8");
        String h;
        while ((h = readLine(in)) != null && h.length() > 0) {
            int i = h.indexOf(':');
            if (i > 0) r.headers.put(h.substring(0, i).trim().toLowerCase(Locale.ROOT), h.substring(i + 1).trim());
        }
        String cl = r.header("content-length");
        if (cl != null) {
            int n = Integer.parseInt(cl.trim());
            if (n < 0 || n > MAX_BODY) return null;
            byte[] body = new byte[n];
            int off = 0;
            while (off < n) {
                int k = in.read(body, off, n - off);
                if (k < 0) break;
                off += k;
            }
            r.body = body;
        }
        return r;
    }

    private static String reason(int status) {
        switch (status) {
            case 200: return "OK";
            case 400: return "Bad Request";
            case 403: return "Forbidden";
            case 404: return "Not Found";
            case 409: return "Conflict";
            case 500: return "Internal Server Error";
            case 501: return "Not Implemented";
            default: return "Status";
        }
    }

    private static void write(OutputStream out, Response res) throws IOException {
        String head = "HTTP/1.1 " + res.status + " " + reason(res.status) + "\r\n"
                + "Content-Type: " + res.contentType + "\r\n"
                + "Content-Length: " + res.body.length + "\r\n"
                + "Connection: close\r\n\r\n";
        out.write(head.getBytes(UTF8));
        out.write(res.body);
        out.flush();
    }
}
