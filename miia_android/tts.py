"""Voz de MIIA: corta lo que va llegando del modelo en frases, las sintetiza con Edge (Elvira) una por delante de la
que suena, y las reproduce. Si Edge no responde, habla con la voz nativa de Android."""

import queue
import re
import threading
import time

import miia_core as core

from .edge import EdgeError, EdgeTTS
from .util import IS_ANDROID, autoclass, log, log_exc

_ABBREV = re.compile(r"(?:\b(?:sr|sra|srta|dr|dra|ud|uds|etc|vs|pág|pags|av|núm|tel)\.)$", re.I)
_SENT = re.compile(r"(.+?(?:[.!?…]+|:)[\"”')\]]*(?=\s)|.+?\n)", re.S)


class SentenceSplitter:
    """Primer trozo corto (≥ first_min caracteres) para que MIIA arranque pronto; el resto, en grupos más largos
    (≥ group_min) para que la voz suene fluida y haya menos peticiones a Edge."""

    def __init__(self, first_min=12, group_min=70, max_buf=240):
        self.first_min, self.group_min, self.max_buf = first_min, group_min, max_buf
        self.buf = ""
        self.pending = ""
        self.first = True

    def _need(self):
        return self.first_min if self.first else self.group_min

    def _take(self):
        out = self.pending.strip()
        self.pending = ""
        if out:
            self.first = False
        return out

    def feed(self, piece: str):
        out = []
        self.buf += piece or ""
        while True:
            m = _SENT.match(self.buf)
            if not m:
                break
            sent, end = m.group(1), m.end()
            while _ABBREV.search(sent.strip()):             # «Sr.», «Dra.»...: no es fin de frase
                nxt = _SENT.match(self.buf, end + 1)
                if not nxt:
                    sent = None
                    break
                sent, end = sent + self.buf[end:nxt.start()] + nxt.group(1), nxt.end()
            if sent is None:
                break
            self.buf = self.buf[end:].lstrip(" \t")
            self.pending += (" " if self.pending else "") + sent.strip()
            if len(self.pending) >= self._need():
                out.append(self._take())
        if len(self.buf) > self.max_buf:                    # texto largo sin puntuación
            cut = max(self.buf.rfind(",", 0, self.max_buf), self.buf.rfind(" ", 0, self.max_buf))
            cut = cut if cut > 40 else self.max_buf
            self.pending += (" " if self.pending else "") + self.buf[:cut].strip()
            self.buf = self.buf[cut:].lstrip(" ,")
            if len(self.pending) >= self._need():
                out.append(self._take())
        return [o for o in out if o]

    def flush(self):
        if self.buf.strip():
            self.pending += (" " if self.pending else "") + self.buf.strip()
        self.buf = ""
        out = self._take()
        return [out] if out else []


# ------------------------------------------------------------------ reproductores
class NullPlayer:
    """Para pruebas en PC: no suena nada, solo espera un poco."""

    def __init__(self):
        self._stop = threading.Event()
        self.played = []

    def play(self, audio: bytes):
        self._stop.clear()
        self.played.append(len(audio))
        end = time.time() + 0.03
        while time.time() < end and not self._stop.is_set():
            time.sleep(0.005)

    def stop(self):
        self._stop.set()


class AndroidPlayer:
    """Reproduce el MP3 de Edge con android.media.MediaPlayer (interrumpible)."""

    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._mp = None
        self._n = 0
        self.MediaPlayer = autoclass("android.media.MediaPlayer")

    def play(self, audio: bytes):
        import os
        self._stop.clear()
        self._n = (self._n + 1) % 4
        path = os.path.join(self.cache_dir, f"voz_{self._n}.mp3")
        with open(path, "wb") as f:
            f.write(audio)
        mp = self.MediaPlayer()
        with self._lock:
            self._mp = mp
        try:
            mp.setDataSource(path)
            mp.prepare()
            if self._stop.is_set():
                return
            mp.start()
            time.sleep(0.12)
            while not self._stop.is_set() and mp.isPlaying():
                time.sleep(0.04)
        finally:
            with self._lock:
                self._mp = None
            for fn in (mp.stop, mp.release):
                try:
                    fn()
                except Exception:
                    pass

    def stop(self):
        self._stop.set()
        with self._lock:
            mp = self._mp
        if mp is not None:
            try:
                mp.stop()
            except Exception:
                pass


class NativeVoice:
    """Voz nativa de Android (TextToSpeech) a través de MiiaVoice."""

    def __init__(self, lang_fn, rate_fn):
        self.V = autoclass("org.miia.voice.MiiaVoice")
        self.lang_fn, self.rate_fn = lang_fn, rate_fn
        self._stop = threading.Event()

    def speak(self, text: str):
        self._stop.clear()
        self.V.nativeSpeak(text, self.lang_fn(), float(self.rate_fn()))
        t0 = time.time()
        while not self._stop.is_set() and time.time() - t0 < 90:
            time.sleep(0.05)
            if not self.V.nativeSpeaking():
                break

    def stop(self):
        self._stop.set()
        try:
            self.V.nativeStop()
        except Exception:
            pass


def rate_to_float(rate: str) -> float:
    m = re.match(r"^([+-])(\d+)%$", rate or "")
    if not m:
        return 1.0
    v = 1.0 + (int(m.group(2)) / 100.0) * (1 if m.group(1) == "+" else -1)
    return max(0.5, min(2.0, v))


# ------------------------------------------------------------------ orquestador de la voz
class Speaker:
    """begin() → feed(trozos)* → end_stream(). stop() corta todo al instante. on_state('speaking'|'idle')."""

    def __init__(self, cfg, player, edge=None, native=None, on_state=None, on_note=None):
        self.cfg, self.player, self.native = cfg, player, native
        self.edge = edge or EdgeTTS(cfg)
        self.on_state, self.on_note = on_state, on_note
        self._gen = 0
        self._lock = threading.RLock()
        self._split = SentenceSplitter()
        self._texts = queue.Queue()
        self._audio = queue.Queue(maxsize=3)
        self._speaking = False
        self._active = 0                      # trozos pendientes de sonar
        self._idle = threading.Event()
        self._idle.set()
        self._edge_down_until = 0.0
        self._noted = False
        self.spoken = []                      # (para pruebas) texto de cada trozo que se dijo
        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()

    # ---- API ----
    @property
    def speaking(self) -> bool:
        return self._speaking

    def enabled(self) -> bool:
        return bool(self.cfg.get("voice_enabled"))

    def begin(self):
        self.stop()
        with self._lock:
            self._split = SentenceSplitter()
            self._noted = False

    def feed(self, piece: str):
        if not self.enabled():
            return
        with self._lock:
            chunks = self._split.feed(piece)
        for c in chunks:
            self._enqueue(c)

    def end_stream(self):
        if not self.enabled():
            return
        with self._lock:
            chunks = self._split.flush()
        for c in chunks:
            self._enqueue(c)

    def say(self, text: str):
        self.begin()
        self.feed(text)
        self.end_stream()

    def stop(self):
        with self._lock:
            self._gen += 1
            self._split = SentenceSplitter()
        self._drain(self._texts)
        self._drain(self._audio)
        try:
            self.player.stop()
        except Exception:
            pass
        if self.native:
            self.native.stop()
        with self._lock:
            self._active = 0
        self._set_speaking(False)

    def wait_idle(self, timeout=60.0) -> bool:
        return self._idle.wait(timeout)

    # ---- internos ----
    @staticmethod
    def _drain(q):
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass

    def _set_speaking(self, v: bool):
        if v == self._speaking:
            return
        self._speaking = v
        if v:
            self._idle.clear()
        else:
            self._idle.set()
        if self.on_state:
            try:
                self.on_state("speaking" if v else "idle")
            except Exception:
                log_exc("on_state")

    def _enqueue(self, text: str):
        clean = core.clean_for_speech(text)
        if not re.search(r"\w", clean):
            return
        with self._lock:
            self._active += 1
            gen = self._gen
        self._set_speaking(True)
        self._texts.put((gen, clean))

    def _done_one(self, gen):
        with self._lock:
            if gen != self._gen:
                return
            self._active = max(0, self._active - 1)
            idle = self._active == 0
        if idle:
            self._set_speaking(False)

    def _note(self, msg):
        if not self._noted and self.on_note:
            self._noted = True
            try:
                self.on_note(msg)
            except Exception:
                pass

    def _synth_loop(self):
        while True:
            gen, text = self._texts.get()
            if gen != self._gen:
                continue
            audio, err = None, ""
            if time.time() >= self._edge_down_until:
                try:
                    audio = self.edge.synth(text, self.cfg.get("voice"), self.cfg.get("voice_rate"))
                except EdgeError as e:
                    err = str(e)
                except Exception as e:
                    err = f"{type(e).__name__}: {e}"
                if err:
                    log("Edge falló:", err)
                    self._edge_down_until = time.time() + 45
            if gen != self._gen:
                continue
            if audio is None and self.native and self.cfg.get("voice_native_fallback"):
                self._note("Edge no responde: hablo con la voz de Android por un rato.")
            self._audio.put((gen, text, audio))

    def _play_loop(self):
        while True:
            gen, text, audio = self._audio.get()
            if gen != self._gen:
                continue
            try:
                self.spoken.append(text)
                if audio is not None:
                    self.player.play(audio)
                elif self.native and self.cfg.get("voice_native_fallback"):
                    self.native.speak(text)
            except Exception:
                log_exc("reproducir")
            self._done_one(gen)


def build_speaker(cfg, cache_dir, on_state=None, on_note=None) -> Speaker:
    if IS_ANDROID:
        player = AndroidPlayer(cache_dir)
        native = NativeVoice(lambda: cfg.get("voice_lang") or "es-AR",
                             lambda: rate_to_float(cfg.get("voice_rate")))
    else:
        player, native = NullPlayer(), None
    return Speaker(cfg, player, EdgeTTS(cfg), native, on_state, on_note)
