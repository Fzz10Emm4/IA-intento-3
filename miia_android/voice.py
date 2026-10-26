"""Control de la voz: botón de hablar, palabra «MIIA» en segundo plano (como «Oye Siri»), modo conversación y
respuesta anticipada. Toda la lógica de estados vive aquí; Android solo aporta eventos (bridge.poll()).

Estados: off (sin micrófono) · idle (esperando, solo botón) · wake (escuchando «MIIA») · listening (te escucha
una orden) · thinking · speaking.
"""

import re
import threading
import time

from .util import has_audio_permission, log, log_exc, request_audio_permissions

_WAKE = re.compile(
    r"^\W*(?:(?:hola|oye|hey|ok|okay|eh|ey|ola)\W+){0,2}"
    r"(?:m[ií][ií]?[yaá]|m[ií]\s?[ií]a|m[ií]\s?ya|m[ií]\s?[ií]\s?a)\b[\s,.:;!¡?¿\-]*(?P<rest>.*)$",
    re.I | re.S)

ACK = "Dime."


def find_wake(text: str):
    """(True, resto) si la frase empieza con «MIIA» (admite «oye MIIA», «hey mía», «Miya»...). El resto es la orden."""
    m = _WAKE.match(text or "")
    if not m:
        return False, ""
    return True, m.group("rest").strip(" ,.;:¡!¿?-\n\t")


# códigos de error de SpeechRecognizer
E_TIMEOUT, E_NO_MATCH, E_BUSY, E_PERM = 6, 7, 8, 9
E_NET = {1, 2, 4, 11}
E_LANG = {12, 13}


class VoiceController:
    def __init__(self, bridge, cfg, speaker, responder, spec, ui=None, sleep=time.sleep):
        self.bridge, self.cfg, self.speaker, self.responder, self.spec = bridge, cfg, speaker, responder, spec
        self.ui = ui or {}
        self.sleep = sleep
        self.state = "off"
        self.session = None                 # None | wake | command | follow
        self.background = False
        self._token = 0
        self._busy = False
        self._muted = (False, False)
        self._net_fail = 0
        self._noted_net = False
        self._lock = threading.RLock()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ UI
    def _ui(self, name, *args):
        fn = self.ui.get(name)
        if fn:
            try:
                fn(*args)
            except Exception:
                log_exc("ui " + name)

    def _set_state(self, state, detail=""):
        if state != self.state:
            self.state = state
        self._ui("state", state, detail)

    def _note(self, text):
        self._ui("note", text)

    def _lang(self):
        return self.cfg.get("voice_lang") or "es-AR"

    # ------------------------------------------------------------------ API pública
    def shutdown(self):
        self._running = False
        self.stop_all()

    def start_background(self):
        """Activa la escucha de «MIIA» (pide permisos, pone la notificación fija y empieza)."""
        def go(granted):
            if not granted:
                self._note("Sin permiso de micrófono: no puedo escuchar «MIIA». Actívalo en Ajustes de Android.")
                self.cfg.update(wake_enabled=False)
                self._ui("wake_changed", False)
                return
            if not self.bridge.available():
                self._note("Este teléfono no tiene reconocimiento de voz disponible (falta la app de Google).")
                self.cfg.update(wake_enabled=False)
                self._ui("wake_changed", False)
                return
            with self._lock:
                self.background = True
                self.cfg.update(wake_enabled=True)
            try:
                self.bridge.start_service("MIIA escuchando", "Di «MIIA» para hablar")
            except Exception:
                log_exc("start_service")
            self._ui("wake_changed", True)
            if not self._busy and self.session != "command":
                self._start_session("wake")
        request_audio_permissions(go)

    def stop_background(self):
        with self._lock:
            self.background = False
            self.cfg.update(wake_enabled=False)
        try:
            self.bridge.stop_service()
        except Exception:
            log_exc("stop_service")
        if self.session == "wake":
            self._end_session()
        self._ui("wake_changed", False)
        if not self._busy and self.session is None:
            self._set_state("idle")

    def talk_button(self):
        """Botón de hablar: corta a MIIA si está hablando, termina de escuchar si ya te escucha, o empieza a escuchar."""
        if self.speaker.speaking:
            self.speaker.stop()
        if self._busy and self.state == "thinking":
            self._note("Estoy pensando la respuesta…")
            return
        if self.session in ("command", "follow"):
            self.bridge.stop_listening()          # ya hablaste: entrega lo que oyó
            return
        if not has_audio_permission():
            request_audio_permissions(lambda ok: ok and self._start_session("command"))
            return
        self._start_session("command")

    def cancel_listening(self):
        self._end_session()
        self._after_idle()

    def stop_all(self):
        self.speaker.stop()
        self._end_session()
        self.spec.cancel()
        self._mute(False, False)

    def submit_typed(self, text, speak=True):
        """Mensaje escrito: misma ruta que el hablado (guarda, responde con streaming y habla si la voz está activa)."""
        if self._busy:
            return False
        self._end_session()
        self._reply(text, None, via_voice=False, speak=speak)
        return True

    # ------------------------------------------------------------------ silenciar pitidos
    def _mute(self, sys_on, music_on):
        want = (bool(sys_on and self.cfg.get("mute_beeps")), bool(music_on and self.cfg.get("mute_music")))
        if want != self._muted:
            self._muted = want
            try:
                self.bridge.set_mute(*want)
            except Exception:
                log_exc("mute")

    # ------------------------------------------------------------------ sesiones de escucha
    def _start_session(self, kind):
        with self._lock:
            if self._busy and kind != "wake":
                return
            self._token += 1
            self.session = kind
            token = self._token
        self.spec.begin_utterance()
        self._mute(True, True)
        try:
            self.bridge.listen(self._lang(), bool(self.cfg.get("wake_offline")), kind == "wake")
        except Exception:
            log_exc("listen")
            self.session = None
            self._note("No pude abrir el micrófono.")
            self._set_state("idle")
            return
        self._set_state("wake" if kind == "wake" else "listening")
        log("sesión", kind, "token", token)

    def _end_session(self):
        with self._lock:
            self._token += 1
            had = self.session
            self.session = None
        if had:
            try:
                self.bridge.cancel()
            except Exception:
                log_exc("cancel")
        self.spec.cancel()

    def _later(self, delay, fn):
        token = self._token

        def run():
            if self._running and token == self._token:
                fn()
        t = threading.Timer(delay, run)
        t.daemon = True
        t.start()

    def _after_idle(self):
        """Tras una respuesta: vuelve a esperar «MIIA» si está activado; si no, queda en reposo."""
        if not self._running:
            return
        if self.background and not self._busy:
            self._start_session("wake")
        else:
            self._mute(False, False)
            self._set_state("idle" if not self._busy else self.state)

    # ------------------------------------------------------------------ bucle de eventos
    def _loop(self):
        while self._running:
            try:
                ev = self.bridge.poll()
            except Exception:
                ev = None
            if ev is None:
                self.sleep(0.04)
                continue
            try:
                self.handle_event(ev)
            except Exception:
                log_exc("evento " + str(ev))

    def handle_event(self, ev: str):
        kind, _, arg = ev.partition(":")
        if kind == "ready":
            self._net_fail = 0
        elif kind == "partial":
            self._on_partial(arg)
        elif kind == "final":
            self._on_final(arg)
        elif kind == "error":
            self._on_error(int(arg) if arg.lstrip("-").isdigit() else -1)
        elif kind == "svcstop":
            self._note("Escucha de «MIIA» detenida desde la notificación.")
            self.stop_background()
        # speech / endspeech: sin acción (el resultado final llega solo)

    def _on_partial(self, text):
        if not text or self.session is None:
            return
        if self.session == "wake":
            found, rest = find_wake(text)
            if found and rest:
                self._ui("partial", rest)
                self.spec.on_partial(rest)
            return
        self._ui("partial", text)
        self.spec.on_partial(text)

    def _on_final(self, text):
        text = (text or "").strip()
        kind = self.session
        if kind is None or self._busy:
            return
        if kind == "wake":
            found, rest = find_wake(text)
            if not found:
                self._start_session("wake")
                return
            self._end_session_keep_spec()
            if rest:
                self._answer_voice(rest)
            else:
                self._ack_then_listen()
            return
        self._end_session_keep_spec()
        if text:
            self._answer_voice(text)
        else:
            self._after_idle()

    def _end_session_keep_spec(self):
        with self._lock:
            self._token += 1
            self.session = None

    def _on_error(self, code):
        kind = self.session
        if kind is None:
            return
        if code == E_PERM:
            self._note("Falta el permiso de micrófono.")
            self.stop_background()
            self._end_session()
            self._set_state("idle")
            return
        if code in E_LANG:
            self._note(f"El idioma de voz «{self._lang()}» no está disponible en este teléfono. Cámbialo en Ajustes.")
            self.stop_background()
            self._end_session()
            self._set_state("idle")
            return
        if kind in ("command", "follow"):
            self._end_session()
            if code in (E_TIMEOUT, E_NO_MATCH):
                if kind == "command":
                    self._note("No te escuché. Toca el micrófono y habla.")
            elif code in E_NET:
                self._note("El reconocimiento de voz necesita internet (o activa «reconocimiento sin internet» en Ajustes).")
            else:
                self._note(f"Error del reconocimiento de voz ({code}).")
            self._after_idle()
            return
        # sesión «wake»: errores normales (silencio) se reinician sin ruido; los demás, con espera creciente
        if code in (E_TIMEOUT, E_NO_MATCH):
            self._net_fail = 0
            delay = 0.25
        elif code == E_BUSY:
            delay = 1.2
            try:
                self.bridge.cancel()
            except Exception:
                pass
        elif code in E_NET:
            self._net_fail += 1
            delay = min(3.0 * self._net_fail, 20.0)
            if not self._noted_net and self._net_fail >= 3:
                self._noted_net = True
                self._note("Sin internet para reconocer «MIIA». Si quieres, activa «reconocimiento sin internet» en Ajustes.")
        else:
            self._net_fail += 1
            delay = min(1.0 * (self._net_fail + 1), 10.0)
        self._later(delay, lambda: self.background and not self._busy and self._start_session("wake"))

    # ------------------------------------------------------------------ responder
    def _ack_then_listen(self):
        def run():
            self._busy = True
            self._set_state("speaking", "Dime")
            try:
                self._mute(True, False)
                if self.speaker.enabled():
                    self.speaker.say(ACK)
                    self.speaker.wait_idle(8)
                    self.sleep(0.25)
            finally:
                self._busy = False
            self._start_session("command")
        threading.Thread(target=run, daemon=True).start()

    def _answer_voice(self, text):
        job = self.spec.take(text)
        self._reply(text, job, via_voice=True, speak=True)

    def _reply(self, text, job, via_voice, speak):
        self._busy = True
        self._set_state("thinking")
        self._ui("user_message", text, via_voice)

        def run():
            ok = True
            try:
                self._ui("stream_begin")
                reply, ok = self.responder.respond(
                    text, job,
                    on_text=lambda p: self._ui("chunk", p),
                    on_status=lambda s: self._ui("status", s),
                    speak=speak and self.speaker.enabled())
                self._ui("stream_end", reply, ok)
                if speak and self.speaker.enabled():
                    self._mute(True, False)
                    self._set_state("speaking")
                    self.speaker.wait_idle(180)
            except Exception:
                log_exc("responder")
            finally:
                self._busy = False
            self.sleep(0.35)                         # que no te oiga a ti misma
            if via_voice and ok and self.cfg.get("conversation_mode"):
                self._start_session("follow")
            else:
                self._after_idle()
        threading.Thread(target=run, daemon=True).start()
