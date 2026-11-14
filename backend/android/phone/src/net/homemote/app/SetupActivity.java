package net.homemote.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.ViewGroup;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.Charset;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Úvodní obrazovka (první spuštění / bez vazby na backend): návod, kde najít QR kód
 * (web Homemote → Nastavení → Přidat telefon), čtečka QR kódu a ruční zadání adresy.
 * Stránka je v assets/setup.html, s aplikací mluví přes most „HM“.
 */
public class SetupActivity extends Activity {
    private static final int REQ_CAMERA = 1;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService bg = Executors.newSingleThreadExecutor();
    private WebView web;
    private Store store;
    private String pendingPair;
    private boolean pageLoaded;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        super.onCreate(savedInstanceState);
        store = new Store(this);
        pendingPair = getIntent().getStringExtra("pair");

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Ui.background(this));
        getWindow().getDecorView().setBackgroundColor(Ui.background(this));
        web = new WebView(this);
        web.setBackgroundColor(Ui.background(this));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        web.addJavascriptInterface(new Bridge(), "HM");
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest req) {
                ui.post(new Runnable() {
                    @Override public void run() {
                        if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                            req.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                        } else {
                            req.deny();
                        }
                    }
                });
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                pageLoaded = true;
                if (pendingPair != null) {
                    String p = pendingPair;
                    pendingPair = null;
                    pair(p);
                }
            }
        });
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        Ui.applyInsets(root);
        setContentView(root);

        String html = asset("setup.html").replace("<!--JSQR-->", "<script>" + asset("jsQR.js") + "</script>");
        // https základ = bezpečný kontext (kamera přes getUserMedia), stránka nic nestahuje ze sítě.
        web.loadDataWithBaseURL("https://setup.homemote.invalid/", html, "text/html", "utf-8", null);
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        bg.shutdownNow();
        super.onDestroy();
    }

    private String asset(String name) {
        try {
            InputStream in = getAssets().open(name);
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
            in.close();
            return new String(b.toByteArray(), Charset.forName("UTF-8"));
        } catch (IOException e) {
            return "";
        }
    }

    private void js(String code) {
        if (web != null) web.evaluateJavascript(code, null);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode != REQ_CAMERA) return;
        boolean ok = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        js(ok ? "startCamera()" : "cameraDenied()");
    }

    private void openMain() {
        Intent i = new Intent(this, MainActivity.class);
        i.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(i);
        finish();
    }

    private void pair(final String uri) {
        js("pairing()");
        bg.execute(new Runnable() {
            @Override public void run() {
                String err = null;
                try {
                    Backend.pair(store, Uri.parse(uri));
                } catch (Backend.PairingException e) {
                    err = e.getMessage();
                }
                final String fe = err;
                ui.post(new Runnable() {
                    @Override public void run() {
                        if (fe == null) openMain();
                        else js("pairError(" + JSONObject.quote(fe) + ")");
                    }
                });
            }
        });
    }

    /** Most pro setup.html. */
    private final class Bridge {
        @JavascriptInterface
        public void scan() {
            ui.post(new Runnable() {
                @Override public void run() {
                    if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                        js("startCamera()");
                    } else {
                        requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAMERA);
                    }
                }
            });
        }

        @JavascriptInterface
        public void qr(final String text) {
            ui.post(new Runnable() {
                @Override public void run() { pair(text); }
            });
        }

        @JavascriptInterface
        public boolean manual(String url) {
            final String u = Store.emptyToNull(url);
            if (u == null || !(u.startsWith("http://") || u.startsWith("https://"))) return false;
            ui.post(new Runnable() {
                @Override public void run() {
                    store.saveManual(u);
                    openMain();
                }
            });
            return true;
        }

        @JavascriptInterface
        public String version() { return BuildInfo.VERSION_NAME; }
    }
}
