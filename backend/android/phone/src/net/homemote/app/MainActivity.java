package net.homemote.app;

import android.app.Activity;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.net.http.SslError;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebResourceResponse;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Hlavní obrazovka: web backendu ve WebView.
 * - volí adresu (domácí síť / internet) a při změně sítě přepne,
 * - předá webu token z párování (#hm_token=…),
 * - tlačítka hlasitosti telefonu ovládají hlasitost TV.
 */
public class MainActivity extends Activity {
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService bg = Executors.newSingleThreadExecutor();
    private Store store;
    private WebView web;
    private LinearLayout overlay;
    private TextView overlayText;
    private ProgressBar overlaySpinner;
    private View overlayButtons;
    private String base;
    private boolean pageReady;
    private boolean connecting;
    private ConnectivityManager.NetworkCallback netCb;

    private final Runnable reconnect = new Runnable() {
        @Override public void run() { connect(false); }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        super.onCreate(savedInstanceState);
        store = new Store(this);
        if (handleDeepLink(getIntent())) return;
        if (!store.bound()) { openSetup(null); return; }
        buildUi();
        watchNetwork();
        connect(true);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleDeepLink(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) connect(false);  // mezitím se mohla změnit síť (Wi‑Fi doma / mobilní data)
    }

    @Override
    protected void onDestroy() {
        if (netCb != null) {
            try { ((ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE)).unregisterNetworkCallback(netCb); }
            catch (Exception ignored) { }
        }
        if (web != null) web.destroy();
        bg.shutdownNow();
        super.onDestroy();
    }

    private boolean handleDeepLink(Intent intent) {
        Uri d = intent != null ? intent.getData() : null;
        if (d != null && "homemote".equals(d.getScheme())) {
            openSetup(d.toString());
            return true;
        }
        return false;
    }

    private void openSetup(String pairUri) {
        Intent i = new Intent(this, SetupActivity.class);
        if (pairUri != null) i.putExtra("pair", pairUri);
        startActivity(i);
        finish();
    }

    // --- rozhraní ------------------------------------------------------------------------
    private int dp(int v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Ui.background(this));
        getWindow().getDecorView().setBackgroundColor(Ui.background(this));

        web = new WebView(this);
        web.setBackgroundColor(Ui.background(this));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setUserAgentString(s.getUserAgentString() + " HomemoteApp/" + BuildInfo.VERSION_NAME);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (base != null && u.toString().startsWith(base)) return false;
                if (req.isRedirect() || !req.hasGesture()) return false;  // přesměrování (např. přihlášení u proxy) nechat ve WebView
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (base != null && url.startsWith(base)) {
                    pageReady = true;
                    hideOverlay();
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) {
                    pageReady = false;
                    showOverlay(Texts.get(0) + "\n\n" + req.getUrl().getHost() + ": " + err.getDescription(), true);
                }
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest req, WebResourceResponse res) {
                if (req.isForMainFrame() && res.getStatusCode() >= 400) {
                    pageReady = false;
                    showOverlay(Texts.get(0) + "\n\n" + req.getUrl().getHost() + ": HTTP " + res.getStatusCode()
                            + " " + res.getReasonPhrase(), true);
                }
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();  // nikdy neobcházet – jen ukázat proč
                pageReady = false;
                showOverlay(Texts.get(0) + "\n\n" + sslReason(error), true);
            }
        });
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        overlay = new LinearLayout(this);
        overlay.setOrientation(LinearLayout.VERTICAL);
        overlay.setGravity(Gravity.CENTER);
        overlay.setBackgroundColor(Ui.background(this));
        int pad = dp(32);
        overlay.setPadding(pad, pad, pad, pad);
        overlaySpinner = new ProgressBar(this);
        overlay.addView(overlaySpinner);
        overlayText = new TextView(this);
        overlayText.setTextColor(Ui.text(this));
        overlayText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        overlayText.setTextIsSelectable(true);
        overlayText.setGravity(Gravity.CENTER);
        overlayText.setPadding(0, dp(16), 0, dp(20));
        overlay.addView(overlayText);
        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.VERTICAL);
        buttons.setGravity(Gravity.CENTER);
        Button retry = new Button(this);
        retry.setText(Texts.get(1));
        retry.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { connect(true); }
        });
        buttons.addView(retry);
        Button unpair = new Button(this);
        unpair.setText(Texts.get(2));
        unpair.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { store.clear(); openSetup(null); }
        });
        buttons.addView(unpair);
        overlayButtons = buttons;
        overlay.addView(buttons);
        root.addView(overlay, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        Ui.applyInsets(root);
        setContentView(root);
        showOverlay(Texts.get(3), false);
    }

    private static String sslReason(SslError e) {
        String why;
        switch (e.getPrimaryError()) {
            case SslError.SSL_UNTRUSTED: why = "certifikát nemá platný řetězec (chybí mezilehlý certifikát?)"; break;
            case SslError.SSL_EXPIRED: why = "certifikát vypršel"; break;
            case SslError.SSL_IDMISMATCH: why = "certifikát nepatří této adrese"; break;
            case SslError.SSL_NOTYETVALID: why = "certifikát ještě neplatí"; break;
            case SslError.SSL_DATE_INVALID: why = "neplatné datum certifikátu"; break;
            default: why = "chyba certifikátu " + e.getPrimaryError();
        }
        return "SSL: " + Uri.parse(e.getUrl()).getHost() + " – " + why;
    }

    private void showOverlay(String text, boolean error) {
        if (overlay == null) return;
        overlayText.setText(text);
        overlaySpinner.setVisibility(error ? View.GONE : View.VISIBLE);
        overlayButtons.setVisibility(error ? View.VISIBLE : View.GONE);
        overlay.setVisibility(View.VISIBLE);
    }

    private void hideOverlay() {
        if (overlay != null) overlay.setVisibility(View.GONE);
    }

    // --- připojení -----------------------------------------------------------------------
    private void watchNetwork() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        if (cm == null) return;
        netCb = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network n) { schedule(); }
            @Override public void onLost(Network n) { schedule(); }
        };
        try { cm.registerDefaultNetworkCallback(netCb); } catch (Exception e) { netCb = null; }
    }

    private void schedule() {
        ui.removeCallbacks(reconnect);
        ui.postDelayed(reconnect, 1500);
    }

    /** Zjistí, která adresa backendu odpovídá; když se liší od načtené (nebo force), načte web znovu. */
    private void connect(final boolean force) {
        if (connecting) return;
        connecting = true;
        if (!pageReady) showOverlay(Texts.get(3), false);
        bg.execute(new Runnable() {
            @Override public void run() {
                final String chosen = Backend.choose(store);
                boolean revoked = false;
                if (chosen != null && store.token() != null && store.manualUrl() == null) {
                    try { revoked = !Backend.tokenValid(chosen, store.token()); } catch (IOException ignored) { }
                }
                final boolean wasRevoked = revoked;
                ui.post(new Runnable() {
                    @Override public void run() {
                        connecting = false;
                        if (isFinishing()) return;
                        if (wasRevoked) { store.clear(); openSetup(null); return; }
                        if (chosen == null) {
                            if (!pageReady) showOverlay(Texts.get(0) + (Backend.lastError != null ? "\n\n" + Backend.lastError : ""), true);
                            return;
                        }
                        if (force || !pageReady || !chosen.equals(base)) load(chosen);
                    }
                });
            }
        });
    }

    private void load(String b) {
        base = b;
        pageReady = false;
        String token = store.token();
        String url = b + "/" + (token != null && store.manualUrl() == null ? "#hm_token=" + Uri.encode(token) : "");
        web.loadUrl(url);
    }

    // --- tlačítka --------------------------------------------------------------------------
    @Override
    public boolean dispatchKeyEvent(KeyEvent e) {
        int code = e.getKeyCode();
        if (web != null && pageReady && (code == KeyEvent.KEYCODE_VOLUME_UP || code == KeyEvent.KEYCODE_VOLUME_DOWN)) {
            if (e.getAction() == KeyEvent.ACTION_DOWN) {
                String key = code == KeyEvent.KEYCODE_VOLUME_UP ? "vol_up" : "vol_down";
                web.evaluateJavascript("window.sendKey && typeof cur === 'function' && cur() && sendKey('" + key + "')", null);
            }
            return true;
        }
        return super.dispatchKeyEvent(e);
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web == null || !pageReady) { super.onBackPressed(); return; }
        web.evaluateJavascript(
                "(function(){var d=document.querySelector('dialog[open]');if(d){d.close();return true}"
                        + "var m=document.querySelector('.lang-menu');if(m&&window.closeLangMenus){closeLangMenus();return true}"
                        + "var p=document.querySelector('.pop-menu:not(.hidden)');if(p&&window.closeAppsMenu){closeAppsMenu();return true}"
                        + "return false})()",
                new ValueCallback<String>() {
                    @Override public void onReceiveValue(String handled) {
                        if ("true".equals(handled)) return;
                        if (web.canGoBack()) web.goBack();
                        else finish();
                    }
                });
    }
}
