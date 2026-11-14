package net.homemote.helper;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Po startu TV / aktualizaci pomocníka hned spustí server (služba notifikací se naváže sama). */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        HelperCore.get(context).ensureStarted();
    }
}
