package net.homemote.app;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Insets;
import android.os.Build;
import android.view.View;
import android.view.WindowInsets;

/** Společné drobnosti obou aktivit: barvy podle režimu a okraje kolem systémových lišt (edge-to-edge). */
final class Ui {
    private Ui() { }

    static boolean dark(Activity a) {
        return (a.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
    }

    /** Barva pozadí shodná s webem (tmavý / světlý režim). */
    static int background(Activity a) {
        return dark(a) ? Color.rgb(14, 22, 48) : Color.rgb(233, 237, 246);
    }

    static int text(Activity a) {
        return dark(a) ? Color.rgb(232, 236, 247) : Color.rgb(22, 32, 58);
    }

    /** Obsah nepřekrývá stavovou lištu, navigaci ani klávesnici. */
    static void applyInsets(View root) {
        root.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override
            public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                if (Build.VERSION.SDK_INT >= 30) {
                    Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime()
                            | WindowInsets.Type.displayCutout());
                    v.setPadding(i.left, i.top, i.right, i.bottom);
                    return WindowInsets.CONSUMED;
                }
                v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                        insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
                return insets.consumeSystemWindowInsets();
            }
        });
    }
}
