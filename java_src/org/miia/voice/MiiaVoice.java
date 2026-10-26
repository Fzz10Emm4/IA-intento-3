package org.miia.voice;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;

import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Puente entre Python (pyjnius) y las APIs de voz de Android.
 *
 * Python NO recibe callbacks: consulta {@link #poll()} (una cola de eventos de texto) desde un hilo propio.
 * Eventos: ready, speech, endspeech, partial:TEXTO, final:TEXTO, error:CODIGO, svcstop.
 * El reconocedor de Android siempre se usa en el hilo principal (Looper) como exige el sistema.
 */
public class MiiaVoice {
    private static final String PREFS = "miia_voice";

    private static Context appCtx;
    private static Handler main;
    private static final ConcurrentLinkedQueue<String> events = new ConcurrentLinkedQueue<String>();
    private static final AtomicInteger session = new AtomicInteger(0);
    private static SpeechRecognizer recognizer;
    private static volatile float lastRms = 0f;

    // silenciado de pitidos
    private static boolean mutedSys = false;
    private static boolean mutedMusic = false;

    // voz nativa de Android (respaldo cuando Edge no puede hablar)
    private static TextToSpeech tts;
    private static volatile boolean ttsReady = false;
    private static volatile boolean ttsSpeaking = false;

    // ------------------------------------------------------------------ inicio

    public static synchronized void init(Context ctx) {
        if (appCtx != null) {
            return;
        }
        appCtx = ctx.getApplicationContext();
        main = new Handler(Looper.getMainLooper());
        // Si la app anterior se cerró con el sonido silenciado por nosotros, se restaura ahora.
        try {
            SharedPreferences sp = appCtx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            mutedSys = sp.getBoolean("m_sys", false);
            mutedMusic = sp.getBoolean("m_music", false);
        } catch (Throwable t) {
            // nada
        }
        applyMute(false, false);
    }

    public static void pushEvent(String e) {
        events.add(e);
    }

    public static String poll() {
        return events.poll();
    }

    public static float rms() {
        return lastRms;
    }

    public static boolean recognitionAvailable() {
        try {
            return appCtx != null && SpeechRecognizer.isRecognitionAvailable(appCtx);
        } catch (Throwable t) {
            return false;
        }
    }

    // ------------------------------------------------------------------ reconocimiento

    /** Empieza una sesión de escucha (parciales + final). Cancela la anterior si la hubiera. */
    public static void listen(final String lang, final boolean preferOffline, final boolean tightSilence) {
        final int id = session.incrementAndGet();
        main.post(new Runnable() {
            public void run() {
                startOnMain(id, lang, preferOffline, tightSilence);
            }
        });
    }

    /** Termina de escuchar ya: el reconocedor entrega lo que tenga como resultado final. */
    public static void stopListening() {
        main.post(new Runnable() {
            public void run() {
                try {
                    if (recognizer != null) {
                        recognizer.stopListening();
                    }
                } catch (Throwable t) {
                    // nada
                }
            }
        });
    }

    /** Aborta la escucha sin entregar resultados. */
    public static void cancel() {
        session.incrementAndGet();
        main.post(new Runnable() {
            public void run() {
                destroyOnMain();
            }
        });
    }

    private static void destroyOnMain() {
        if (recognizer != null) {
            try {
                recognizer.cancel();
            } catch (Throwable t) {
                // nada
            }
            try {
                recognizer.destroy();
            } catch (Throwable t) {
                // nada
            }
            recognizer = null;
        }
    }

    private static void startOnMain(int id, String lang, boolean offline, boolean tight) {
        if (id != session.get()) {
            return; // ya se pidió otra sesión más nueva
        }
        destroyOnMain();
        try {
            if (!SpeechRecognizer.isRecognitionAvailable(appCtx)) {
                events.add("error:unavailable");
                return;
            }
            recognizer = SpeechRecognizer.createSpeechRecognizer(appCtx);
            recognizer.setRecognitionListener(new Listener(id));
            Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang);
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, lang);
            i.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
            i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
            i.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, appCtx.getPackageName());
            if (offline) {
                i.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true);
            }
            if (tight) {
                // Cuanto menos silencio se espere, antes llega el resultado final (el reconocedor puede ignorarlo).
                i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 900L);
                i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 700L);
            }
            recognizer.startListening(i);
        } catch (Throwable t) {
            events.add("error:exception");
        }
    }

    private static String first(Bundle b) {
        try {
            if (b == null) {
                return "";
            }
            ArrayList<String> l = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
            if (l != null && !l.isEmpty() && l.get(0) != null) {
                return l.get(0).replace('\n', ' ').trim();
            }
        } catch (Throwable t) {
            // nada
        }
        return "";
    }

    private static class Listener implements RecognitionListener {
        private final int id;

        Listener(int id) {
            this.id = id;
        }

        private boolean live() {
            return id == session.get();
        }

        public void onReadyForSpeech(Bundle params) {
            if (live()) {
                events.add("ready");
            }
        }

        public void onBeginningOfSpeech() {
            if (live()) {
                events.add("speech");
            }
        }

        public void onRmsChanged(float rmsdB) {
            if (live()) {
                lastRms = rmsdB;
            }
        }

        public void onBufferReceived(byte[] buffer) {
        }

        public void onEndOfSpeech() {
            if (live()) {
                events.add("endspeech");
            }
        }

        public void onError(int error) {
            if (live()) {
                events.add("error:" + error);
            }
        }

        public void onResults(Bundle results) {
            if (live()) {
                events.add("final:" + first(results));
            }
        }

        public void onPartialResults(Bundle partialResults) {
            if (!live()) {
                return;
            }
            String t = first(partialResults);
            if (t.length() > 0) {
                events.add("partial:" + t);
            }
        }

        public void onEvent(int eventType, Bundle params) {
        }
    }

    // ------------------------------------------------------------------ silenciar pitidos

    /** sys = notificaciones + sistema (donde suelen sonar los pitidos). music = multimedia (apaga la música). */
    public static void setMute(final boolean sys, final boolean music) {
        if (main == null) {
            return;
        }
        main.post(new Runnable() {
            public void run() {
                applyMute(sys, music);
            }
        });
    }

    private static synchronized void applyMute(boolean sys, boolean music) {
        try {
            AudioManager am = (AudioManager) appCtx.getSystemService(Context.AUDIO_SERVICE);
            if (am == null) {
                return;
            }
            if (sys && !mutedSys) {
                boolean already = am.isStreamMute(AudioManager.STREAM_NOTIFICATION)
                        || am.isStreamMute(AudioManager.STREAM_SYSTEM);
                if (!already) {
                    am.adjustStreamVolume(AudioManager.STREAM_NOTIFICATION, AudioManager.ADJUST_MUTE, 0);
                    am.adjustStreamVolume(AudioManager.STREAM_SYSTEM, AudioManager.ADJUST_MUTE, 0);
                    mutedSys = true;
                    savePref("m_sys", true);
                }
            } else if (!sys && mutedSys) {
                am.adjustStreamVolume(AudioManager.STREAM_NOTIFICATION, AudioManager.ADJUST_UNMUTE, 0);
                am.adjustStreamVolume(AudioManager.STREAM_SYSTEM, AudioManager.ADJUST_UNMUTE, 0);
                mutedSys = false;
                savePref("m_sys", false);
            }
            if (music && !mutedMusic) {
                if (!am.isStreamMute(AudioManager.STREAM_MUSIC)) {
                    am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_MUTE, 0);
                    mutedMusic = true;
                    savePref("m_music", true);
                }
            } else if (!music && mutedMusic) {
                am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_UNMUTE, 0);
                mutedMusic = false;
                savePref("m_music", false);
            }
        } catch (Throwable t) {
            // p. ej. SecurityException con «No molestar»: no se puede silenciar y no pasa nada
        }
    }

    private static void savePref(String key, boolean value) {
        try {
            appCtx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(key, value).apply();
        } catch (Throwable t) {
            // nada
        }
    }

    // ------------------------------------------------------------------ voz nativa de Android

    public static void nativeSpeak(final String text, final String lang, final float rate) {
        if (main == null) {
            return;
        }
        ttsSpeaking = true;
        main.post(new Runnable() {
            public void run() {
                speakOnMain(text, lang, rate);
            }
        });
    }

    private static void speakOnMain(final String text, final String lang, final float rate) {
        try {
            if (tts == null) {
                tts = new TextToSpeech(appCtx, new TextToSpeech.OnInitListener() {
                    public void onInit(int status) {
                        ttsReady = (status == TextToSpeech.SUCCESS);
                        if (ttsReady) {
                            speakNow(text, lang, rate);
                        } else {
                            ttsSpeaking = false;
                        }
                    }
                });
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    public void onStart(String utteranceId) {
                    }

                    public void onDone(String utteranceId) {
                        ttsSpeaking = false;
                    }

                    public void onError(String utteranceId) {
                        ttsSpeaking = false;
                    }
                });
            } else if (ttsReady) {
                speakNow(text, lang, rate);
            } else {
                // todavía inicializando: se reintenta enseguida
                main.postDelayed(new Runnable() {
                    public void run() {
                        if (ttsReady) {
                            speakNow(text, lang, rate);
                        } else {
                            ttsSpeaking = false;
                        }
                    }
                }, 800);
            }
        } catch (Throwable t) {
            ttsSpeaking = false;
        }
    }

    private static void speakNow(String text, String lang, float rate) {
        try {
            int r = tts.setLanguage(Locale.forLanguageTag(lang));
            if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
                tts.setLanguage(new Locale("es"));
            }
            tts.setSpeechRate(rate);
            ttsSpeaking = true;
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "miia");
        } catch (Throwable t) {
            ttsSpeaking = false;
        }
    }

    public static void nativeStop() {
        ttsSpeaking = false;
        if (main == null) {
            return;
        }
        main.post(new Runnable() {
            public void run() {
                try {
                    if (tts != null) {
                        tts.stop();
                    }
                } catch (Throwable t) {
                    // nada
                }
            }
        });
    }

    public static boolean nativeSpeaking() {
        return ttsSpeaking;
    }

    // ------------------------------------------------------------------ servicio y batería

    public static void startService(String title, String text) {
        MiiaListenService.start(appCtx, title, text);
    }

    public static void stopService() {
        MiiaListenService.stop(appCtx);
    }

    public static boolean serviceRunning() {
        return MiiaListenService.running;
    }

    public static boolean ignoringBatteryOptimizations() {
        try {
            PowerManager pm = (PowerManager) appCtx.getSystemService(Context.POWER_SERVICE);
            return pm != null && pm.isIgnoringBatteryOptimizations(appCtx.getPackageName());
        } catch (Throwable t) {
            return false;
        }
    }

    /** Abre el permiso «sin restricciones de batería» (o, si ya lo tiene, la lista de ajustes de batería). */
    public static void openBatterySettings() {
        try {
            Intent i;
            if (!ignoringBatteryOptimizations()) {
                i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:" + appCtx.getPackageName()));
            } else {
                i = new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
            }
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            appCtx.startActivity(i);
        } catch (Throwable t) {
            try {
                Intent d = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.parse("package:" + appCtx.getPackageName()));
                d.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                appCtx.startActivity(d);
            } catch (Throwable t2) {
                // nada
            }
        }
    }
}
