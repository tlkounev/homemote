package net.homemote.helper;

import android.service.notification.NotificationListenerService;
import android.util.Log;

/**
 * Přístup k notifikacím je potřeba pro MediaSessionManager.getActiveSessions (co hraje, posun).
 * Systém tuto službu drží navázanou, takže zároveň udržuje proces pomocníka (a HTTP server) při životě.
 */
public class MediaListenerService extends NotificationListenerService {
    @Override
    public void onCreate() {
        super.onCreate();
        HelperCore.get(this).ensureStarted();
    }

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        Log.i(HelperCore.TAG, "přístup k notifikacím aktivní");
        HelperCore.get(this).ensureStarted();
    }
}
