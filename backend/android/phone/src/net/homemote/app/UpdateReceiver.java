package net.homemote.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.widget.Toast;

/** Výsledek instalace aktualizace: ukáže potvrzovací dialog Androidu, nebo chybu. */
public class UpdateReceiver extends BroadcastReceiver {
    static final String ACTION = "net.homemote.app.UPDATE_RESULT";

    @Override
    @SuppressWarnings("deprecation")
    public void onReceive(Context ctx, Intent intent) {
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirm != null) {
                confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try { ctx.startActivity(confirm); } catch (Exception e) { toast(ctx, e.toString()); }
            }
        } else if (status != PackageInstaller.STATUS_SUCCESS) {
            String msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            // STATUS_FAILURE_ABORTED = uživatel instalaci zrušil – žádná chyba
            if (status != PackageInstaller.STATUS_FAILURE_ABORTED) toast(ctx, Texts.get(9) + (msg != null ? msg : String.valueOf(status)));
            MainActivity.updateFinished();
        }
    }

    private static void toast(Context ctx, String s) {
        Toast.makeText(ctx, s, Toast.LENGTH_LONG).show();
    }
}
