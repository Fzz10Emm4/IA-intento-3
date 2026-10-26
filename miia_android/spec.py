"""Respuesta anticipada: mientras el usuario todavía habla, MIIA ya empieza a pensar la respuesta con lo que lleva
dicho. Si lo que al final se entiende coincide con lo anticipado, la respuesta ya está (casi) lista; si no, se tira.

Reglas para no gastar de más:
  - solo cerebros SIN tope diario (BrainPool.candidates("spec")); nunca cambia de cerebro ni hace traspaso;
  - sin herramientas (no ejecuta nada en plataformas por una frase a medias);
  - se espera a que el usuario haga una pausa (settle) y a que lleve al menos `min_words` palabras;
  - máximo `max_launch` intentos por frase y un tope diario (`spec_max_per_day`).
"""

import difflib
import threading
import time
from datetime import date

from .util import log, log_exc, norm


class SpecJob:
    def __init__(self, text: str):
        self.text = text
        self.key = norm(text)
        self.chunks = []
        self.reply = ""
        self.error = None
        self.done = threading.Event()
        self.stale = False
        self.taken = False
        self._subs = []
        self._lock = threading.Lock()
        self.started = time.time()

    def push(self, piece: str):
        with self._lock:
            self.chunks.append(piece)
            subs = list(self._subs)
        for s in subs:
            try:
                s(piece)
            except Exception:
                log_exc("SpecJob.push")

    def attach(self, on_text):
        """Entrega lo ya generado y sigue entregando lo que llegue."""
        with self._lock:
            past = list(self.chunks)
            self._subs.append(on_text)
        if past:
            on_text("".join(past))

    def wait(self, timeout=90.0) -> bool:
        return self.done.wait(timeout)


class SpecEngine:
    def __init__(self, brain, cfg, settle=0.45, min_words=3, min_chars=14, max_launch=3, clock=time.time):
        self.brain, self.cfg = brain, cfg
        self.settle, self.min_words, self.min_chars, self.max_launch = settle, min_words, min_chars, max_launch
        self.clock = clock
        self._lock = threading.RLock()
        self._jobs = []
        self._timer = None
        self._latest = ""
        self._launched = 0
        self.launch_total = 0            # (estadística/pruebas)

    # ---- control ----
    def begin_utterance(self):
        with self._lock:
            self._cancel_timer()
            for j in self._jobs:
                j.stale = True
            self._jobs = []
            self._latest = ""
            self._launched = 0

    def cancel(self):
        self.begin_utterance()

    def _cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    # ---- tope diario ----
    def _today(self) -> str:
        return date.today().isoformat()

    def _count_today(self) -> int:
        return int(self.cfg.get("spec_count") or 0) if self.cfg.get("spec_day") == self._today() else 0

    def _bump(self):
        self.cfg.update(spec_day=self._today(), spec_count=self._count_today() + 1)

    def allowed(self) -> bool:
        if not self.cfg.get("speculate"):
            return False
        if self._count_today() >= int(self.cfg.get("spec_max_per_day") or 0):
            return False
        try:
            return bool(self.brain.pool.speculation_ok())
        except Exception:
            return False

    # ---- parciales ----
    def on_partial(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self._latest = text
            self._cancel_timer()
            if not self._worth(text):
                return
            t = threading.Timer(self.settle, self._settled, args=(text,))
            t.daemon = True
            self._timer = t
            t.start()

    def _worth(self, text: str) -> bool:
        words = len(text.split())
        if words < self.min_words and len(text) < self.min_chars * 2:
            return False
        if len(text) < self.min_chars:
            return False
        if self._launched >= self.max_launch:
            return False
        if self._jobs and self._jobs[-1].key == norm(text):
            return False
        return True

    def _settled(self, text: str):
        with self._lock:
            if text != self._latest or not self._worth(text) or not self.allowed():
                return
            for j in self._jobs:
                j.stale = True
            job = SpecJob(text)
            self._jobs.append(job)
            self._launched += 1
            self.launch_total += 1
        try:
            self._bump()
        except Exception:
            log_exc("spec bump")
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        log("Respuesta anticipada para:", text[:60])

    def _run(self, job: SpecJob):
        try:
            job.reply = self.brain.reply_to(job.text, on_text=job.push, purpose="spec")
        except Exception as e:
            job.error = e
        finally:
            job.done.set()

    # ---- resultado final ----
    @staticmethod
    def matches(spec_text: str, final_text: str) -> bool:
        a, b = norm(spec_text), norm(final_text)
        if not a or not b:
            return False
        if a == b:
            return True
        if abs(len(a.split()) - len(b.split())) > 1:
            return False
        return difflib.SequenceMatcher(None, a, b).ratio() >= 0.92

    def take(self, final_text: str):
        """Devuelve el trabajo anticipado que sirve para `final_text` (o None). Lo demás se descarta."""
        with self._lock:
            self._cancel_timer()
            found = None
            for j in reversed(self._jobs):
                if j.error is None and self.matches(j.text, final_text):
                    found = j
                    break
            for j in self._jobs:
                if j is not found:
                    j.stale = True
            self._jobs = []
            self._latest = ""
            self._launched = 0
        if found:
            found.taken = True
        return found


class Responder:
    """Responde un mensaje (escrito o hablado): guarda la charla, hace streaming y, si hay voz, habla."""

    def __init__(self, brain, memory, speaker=None):
        self.brain, self.memory, self.speaker = brain, memory, speaker

    def respond(self, text, spec=None, on_text=None, on_status=None, speak=True):
        """Devuelve (respuesta, ok). Nunca lanza: los errores se convierten en un mensaje amable."""
        brain, speaker = self.brain, self.speaker if speak else None
        self.memory.add_conversation("user", text)
        if speaker:
            speaker.begin()
        sent = {"n": 0}

        def emit(piece):
            if not piece:
                return
            sent["n"] += 1
            if on_text:
                on_text(piece)
            if speaker:
                speaker.feed(piece)

        reply, ok = "", True
        try:
            if not brain.available:
                reply = brain.fallback_reply(text)
                emit(reply)
            else:
                if spec is not None:
                    spec.attach(emit)
                    spec.wait()
                    if spec.error is not None and sent["n"] == 0:
                        reply = brain.chat(on_text=emit, on_status=on_status)       # la anticipada falló: se hace normal
                    elif spec.error is not None:
                        raise spec.error
                    else:
                        reply = spec.reply
                else:
                    reply = brain.chat(on_text=emit, on_status=on_status)
                if not reply:
                    reply = "(Sin respuesta)"
                    emit(reply)
        except Exception as e:
            ok = False
            msg = brain.friendly_error(e)
            emit(msg)
            reply = msg
        finally:
            if speaker:
                speaker.end_stream()
        if ok and reply:
            self.memory.add_conversation("assistant", reply)
        return reply, ok
