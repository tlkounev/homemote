package net.homemote.helper;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.os.Bundle;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.net.Inet4Address;

/** Stavová obrazovka pomocníka (bez layoutů – APK nemá zdroje). */
public class MainActivity extends Activity {
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        HelperCore.get(this).ensureStarted();

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(Color.rgb(14, 22, 48));
        int pad = dp(48);
        root.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("Homemote helper");
        title.setTextColor(Color.WHITE);
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 32);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);

        status = new TextView(this);
        status.setTextColor(Color.rgb(200, 206, 230));
        status.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        status.setLineSpacing(0, 1.3f);
        status.setPadding(0, dp(20), 0, dp(28));
        root.addView(status);

        Button reset = new Button(this);
        reset.setText("Odpojit od backendu / Unpair from backend");
        reset.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                HelperCore.get(MainActivity.this).resetToken();
                refresh();
            }
        });
        root.addView(reset);

        setContentView(root);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    private void refresh() {
        HelperCore core = HelperCore.get(this);
        StringBuilder sb = new StringBuilder();
        sb.append("Verze / Version: ").append(core.version()).append('\n');
        sb.append("Server: ").append(core.serverRunning() ? "běží / running" : "neběží / stopped")
          .append(" – ").append(ipv4()).append(':').append(HelperCore.PORT).append('\n');
        sb.append("Backend: ").append(core.token() != null ? "přiřazen / paired" : "zatím nepřiřazen / not paired yet").append('\n');
        sb.append("Přístup k notifikacím / Notification access: ").append(core.listenerEnabled() ? "ano / yes" : "ne / no").append('\n');
        sb.append("Zobrazení přes aplikace / Overlay: ").append(Settings.canDrawOverlays(this) ? "ano / yes" : "ne / no");
        status.setText(sb.toString());
    }

    private String ipv4() {
        try {
            ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
            Network n = cm != null ? cm.getActiveNetwork() : null;
            LinkProperties lp = n != null ? cm.getLinkProperties(n) : null;
            if (lp != null) {
                for (LinkAddress la : lp.getLinkAddresses()) {
                    if (la.getAddress() instanceof Inet4Address) return la.getAddress().getHostAddress();
                }
            }
        } catch (Throwable ignored) { }
        return "?";
    }

    private int dp(int v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }
}
