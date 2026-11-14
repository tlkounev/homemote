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
import android.widget.Toast;

import java.io.IOException;
import java.lang.ref.WeakReference;
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
    // aktualizace aplikace z backendu
    private static WeakReference<MainActivity> current = new WeakReference<MainActivity>(null);
    private Updater updater;
    private LinearLayout updateBar;
    private TextView updateText;
    private Button updateNow, updateLater;
    private Updater.Offer offer;
    private boolean updating, waitingForPermission;

    private final Runnable reconnect = new Runnable() {
        @Override public void run() { connect(false); }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        super.onCreate(savedInstanceState);
        store = new Store(this);
        updater = new Updater(this);
        current = new WeakReference<MainActivity>(this);
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
        if (waitingForPermission && offer != null) {
            waitingForPermission = false;
            if (Updater.canInstall(this)) startUpdate();
        }
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
        LinearLayout outer = new LinearLayout(this);
        outer.setOrientation(LinearLayout.VERTICAL);
        outer.setBackgroundColor(Ui.background(this));
        buildUpdateBar(outer);
        FrameLayout root = new FrameLayout(this);
        outer.addView(root, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
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
                    checkUpdate(base);
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

        Ui.applyInsets(outer);
        setContentView(outer);
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

    // --- aktualizace aplikace ----------------------------------------------------------------
    private void buildUpdateBar(LinearLayout parent) {
        updateBar = new LinearLayout(this);
        updateBar.setOrientation(LinearLayout.HORIZONTAL);
        updateBar.setGravity(Gravity.CENTER_VERTICAL);
        updateBar.setBackgroundColor(0xFF5B4BE0);
        updateBar.setPadding(dp(14), dp(6), dp(6), dp(6));
        updateText = new TextView(this);
        updateText.setTextColor(0xFFFFFFFF);
        updateText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        updateBar.addView(updateText, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        updateLater = smallButton(Texts.get(6));
        updateLater.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { if (offer != null) updater.snooze(offer); updateBar.setVisibility(View.GONE); }
        });
        updateBar.addView(updateLater);
        updateNow = smallButton(Texts.get(5));
        updateNow.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { startUpdate(); }
        });
        updateBar.addView(updateNow);
        updateBar.setVisibility(View.GONE);
        parent.addView(updateBar, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
    }

    private Button smallButton(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(0xFFFFFFFF);
        b.setBackgroundColor(0x00000000);
        b.setMinWidth(0);
        b.setMinimumWidth(0);
        b.setPadding(dp(12), 0, dp(12), 0);
        return b;
    }

    /** Po načtení webu: má backend novější verzi aplikace? (nejvýš jednou za hodinu) */
    private void checkUpdate(final String b) {
        if (updating || !updater.dueForCheck()) return;
        bg.execute(new Runnable() {
            @Override public void run() {
                final Updater.Offer o = updater.check(b);
                ui.post(new Runnable() {
                    @Override public void run() {
                        if (o == null || isFinishing() || updating) return;
                        offer = o;
                        updateText.setText(Texts.get(4).replace("{v}", o.version));
                        updateNow.setEnabled(true);
                        updateNow.setVisibility(View.VISIBLE);
                        updateLater.setVisibility(View.VISIBLE);
                        updateBar.setVisibility(View.VISIBLE);
                    }
                });
            }
        });
    }

    private void startUpdate() {
        if (offer == null || updating) return;
        if (!Updater.canInstall(this)) {
            waitingForPermission = true;
            Toast.makeText(this, Texts.get(10), Toast.LENGTH_LONG).show();
            Updater.openInstallPermission(this);
            return;
        }
        updating = true;
        updateNow.setVisibility(View.GONE);
        updateLater.setVisibility(View.GONE);
        updateText.setText(Texts.get(7).replace("{p}", "0"));
        final Updater.Offer o = offer;
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    Updater.downloadAndInstall(MainActivity.this, o, new Updater.Progress() {
                        @Override public void update(final int pct) {
                            ui.post(new Runnable() {
                                @Override public void run() {
                                    updateText.setText(pct >= 0 ? Texts.get(7).replace("{p}", String.valueOf(pct)) : Texts.get(8));
                                }
                            });
                        }
                    });
                    ui.post(new Runnable() { @Override public void run() { updateText.setText(Texts.get(8)); } });
                } catch (final Exception e) {
                    ui.post(new Runnable() {
                        @Override public void run() {
                            Toast.makeText(MainActivity.this, Texts.get(9) + e.getMessage(), Toast.LENGTH_LONG).show();
                            resetUpdateBar();
                        }
                    });
                }
            }
        }).start();
    }

    private void resetUpdateBar() {
        updating = false;
        if (offer == null) { updateBar.setVisibility(View.GONE); return; }
        updateText.setText(Texts.get(4).replace("{v}", offer.version));
        updateNow.setVisibility(View.VISIBLE);
        updateLater.setVisibility(View.VISIBLE);
    }

    /** Instalace skončila jinak než úspěchem (zrušeno / chyba) – lišta zpět do výchozího stavu. */
    static void updateFinished() {
        final MainActivity a = current.get();
        if (a != null) a.ui.post(new Runnable() { @Override public void run() { if (a.updateBar != null) a.resetUpdateBar(); } });
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
