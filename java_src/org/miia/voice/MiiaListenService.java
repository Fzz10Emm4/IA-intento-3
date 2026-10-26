package org.miia.voice;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

/**
 * Servicio en primer plano (notificación fija) que mantiene viva la app mientras MIIA espera la palabra «MIIA».
 * Corre en el MISMO proceso que la app (no es un servicio de python-for-android en otro proceso), así el
 * reconocimiento de voz y Python siguen funcionando con la pantalla apagada.
 * Lo declara en el manifiesto el hook p4a_hook.py (tipo microphone).
 */
public class MiiaListenService extends Service {
    public static final String ACTION_STOP = "org.miia.voice.STOP";
    private static final String CHANNEL = "miia_escucha";
    private static final int NOTIF_ID = 4101;

    public static volatile boolean running = false;

    private PowerManager.WakeLock wakeLock;

    public static void start(Context ctx, String title, String text) {
        Intent i = new Intent(ctx, MiiaListenService.class);
        i.putExtra("title", title);
        i.putExtra("text", text);
        if (Build.VERSION.SDK_INT >= 26) {
            ctx.startForegroundService(i);
        } else {
            ctx.startService(i);
        }
    }

    public static void stop(Context ctx) {
        ctx.stopService(new Intent(ctx, MiiaListenService.class));
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            // Botón «Detener» de la notificación: se avisa a Python para que apague la escucha.
            MiiaVoice.pushEvent("svcstop");
            stopSelf();
            return START_NOT_STICKY;
        }
        String title = intent != null && intent.getStringExtra("title") != null
                ? intent.getStringExtra("title") : "MIIA escuchando";
        String text = intent != null && intent.getStringExtra("text") != null
                ? intent.getStringExtra("text") : "Di «MIIA» para hablar";
        Notification n = buildNotification(title, text);
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
            } else {
                startForeground(NOTIF_ID, n);
            }
        } catch (Throwable t) {
            try {
                startForeground(NOTIF_ID, n);
            } catch (Throwable t2) {
                stopSelf();
                return START_NOT_STICKY;
            }
        }
        running = true;
        try {
            if (wakeLock == null) {
                PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                if (pm != null) {
                    wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "miia:escucha");
                    wakeLock.setReferenceCounted(false);
                    wakeLock.acquire();
                }
            }
        } catch (Throwable t) {
            // sin wake lock: la escucha funciona igual, pero el sistema puede dormir la CPU antes
        }
        return START_NOT_STICKY;
    }

    private Notification buildNotification(String title, String text) {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26 && nm != null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "Escucha de MIIA",
                    NotificationManager.IMPORTANCE_LOW);
            ch.setDescription("Notificación fija mientras MIIA espera que digas «MIIA»");
            ch.setShowBadge(false);
            nm.createNotificationChannel(ch);
        }
        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        b.setContentTitle(title);
        b.setContentText(text);
        b.setSmallIcon(android.R.drawable.ic_btn_speak_now);
        b.setOngoing(true);

        int imm = Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0;
        Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (launch != null) {
            launch.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            b.setContentIntent(PendingIntent.getActivity(this, 0, launch, PendingIntent.FLAG_UPDATE_CURRENT | imm));
        }
        Intent stop = new Intent(this, MiiaListenService.class);
        stop.setAction(ACTION_STOP);
        PendingIntent sp = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_UPDATE_CURRENT | imm);
        b.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Detener", sp);
        return b.build();
    }

    @Override
    public void onDestroy() {
        running = false;
        try {
            if (wakeLock != null && wakeLock.isHeld()) {
                wakeLock.release();
            }
        } catch (Throwable t) {
            // nada
        }
        wakeLock = null;
        try {
            stopForeground(true);
        } catch (Throwable t) {
            // nada
        }
        super.onDestroy();
    }
}
