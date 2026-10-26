"""Pantalla principal: esfera arriba, chat debajo, botón de hablar y menú lateral."""

import threading
import time

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView

import miia_core as core

from ..util import log, log_exc, move_task_to_back
from . import screens_brains, screens_other, theme
from .chat import ChatView
from .kit import Panel, RButton, ScrollColumn, ask_yes_no, button, field, small, spacer
from .orb import Orb
from .theme import rgba

STATE_TEXT = {
    "off": "Lista",
    "idle": "Lista",
    "wake": "Esperando «MIIA»",
    "listening": "Te escucho...",
    "thinking": "Pensando...",
    "speaking": "Hablando...",
}


class Shell(BoxLayout):
    def __init__(self, engine, **kw):
        super().__init__(orientation="vertical", **kw)
        self.engine = engine
        self.brains_refresh = None
        self.vstate = "idle"
        self.speaking = False
        self.partial = ""
        self.busy_text = ""
        self._overlay_token = 0
        self._overlay_since = 0.0
        self.overlay = screens_other.SwitchOverlay()
        self.menu = None
        self.wake_btn = None
        self._build()
        self._wire()
        Window.bind(on_keyboard=self._on_key)

    # ------------------------------------------------------------------ construcción
    def _build(self):
        with self.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*rgba(theme.BG))
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._bg, "pos", self.pos),
                  size=lambda *_: setattr(self._bg, "size", self.size))

        header = Panel(bg=theme.HEADER, radius=0, orientation="horizontal", size_hint_y=None, height=dp(52),
                       padding=[dp(8), dp(6), dp(8), dp(6)], spacing=dp(8))
        header.add_widget(RButton("Menú", kind="neutral", on_press=self.open_menu, size_hint_x=None, width=dp(80),
                                  height=40, size=14))
        title = Label(text="MIIA", font_size=sp(22), bold=True, color=rgba(theme.ACCENT_TEXT), halign="left",
                      valign="middle", size_hint_x=None, width=dp(70))
        title.bind(size=lambda w, _s: setattr(w, "text_size", (w.width, w.height)))
        header.add_widget(title)
        self.brain_label = Label(text="", font_size=sp(12), color=rgba(theme.TEXT_DIM), halign="right",
                                 valign="middle")
        self.brain_label.bind(size=lambda w, _s: setattr(w, "text_size", (w.width, w.height)))
        header.add_widget(self.brain_label)
        self.add_widget(header)

        orb_area = FloatLayout(size_hint_y=None, height=dp(190))
        self.orb = Orb(size_hint=(1, 1))
        orb_area.add_widget(self.orb)
        self.status_label = Label(text="Lista", font_size=sp(13), color=rgba("#9aa4ad"), size_hint=(1, None),
                                  height=dp(22), pos_hint={"x": 0, "y": 0}, halign="center", valign="middle")
        self.status_label.bind(size=lambda w, _s: setattr(w, "text_size", (w.width, w.height)))
        orb_area.add_widget(self.status_label)
        self.add_widget(orb_area)

        self.quota_label = Label(text="", font_size=sp(11), color=rgba("#557799"), size_hint_y=None, height=dp(30),
                                 halign="center", valign="middle")
        self.quota_label.bind(size=lambda w, _s: setattr(w, "text_size", (w.width, w.height)))
        self.add_widget(self.quota_label)

        chat_panel = Panel(bg=theme.SURFACE, radius=12, orientation="vertical", padding=dp(4))
        self.chat = ChatView()
        chat_panel.add_widget(self.chat)
        wrap = BoxLayout(orientation="vertical", padding=[dp(8), 0, dp(8), dp(4)])
        wrap.add_widget(chat_panel)
        self.add_widget(wrap)

        bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(58), spacing=dp(6),
                        padding=[dp(8), dp(4), dp(8), dp(6)])
        self.entry = field("Escribe tu mensaje aquí...", height=46)
        self.entry.bind(on_text_validate=lambda *_: self.send())
        self.entry.size_hint_y = 1
        self.talk_btn = RButton("Hablar", kind="primary", on_press=self.on_talk, size_hint_x=None, width=dp(92),
                                height=46, size=15)
        self.talk_btn.size_hint_y = 1
        send = RButton("Enviar", kind="secondary", on_press=self.send, size_hint_x=None, width=dp(78), height=46,
                       size=14)
        send.size_hint_y = 1
        for w in (self.entry, send, self.talk_btn):
            bar.add_widget(w)
        self.add_widget(bar)

    def _wire(self):
        eng = self.engine
        eng.on_pool = lambda kind, kw: self.ui(lambda: self._pool_event(kind, kw))
        eng.on_cloud = lambda kind, kw: self.ui(lambda: self._cloud_event(kind, kw))
        eng.on_task_note = lambda text: self.ui(lambda: self.note(text))
        eng.on_voice_note = lambda text: self.ui(lambda: self.note(text))
        eng.on_speaking = lambda v: self.ui(lambda: self._set_speaking(v))
        eng.voice.ui.update({
            "state": lambda s, d="": self.ui(lambda: self._voice_state(s, d)),
            "partial": lambda t: self.ui(lambda: self._partial(t)),
            "user_message": lambda t, v: self.ui(lambda: self._user_message(t, v)),
            "stream_begin": lambda: self.ui(self.chat.stream_begin),
            "chunk": lambda p: self.ui(lambda: self.chat.stream_chunk(p)),
            "stream_end": lambda r, ok: self.ui(self._stream_end),
            "status": lambda s: self.ui(lambda: self._set_busy_text(s)),
            "note": lambda t: self.ui(lambda: self.note(t)),
            "wake_changed": lambda on: self.ui(lambda: self._wake_changed(on)),
        })

    def start(self):
        """Se llama cuando la ventana ya existe."""
        self.orb.start()
        self.refresh_brain_label()
        Clock.schedule_interval(lambda dt: self.refresh_brain_label(), 5)
        eng = self.engine
        name = eng.memory.memory["facts"].get("nombre", "")
        if eng.brain.available:
            self.chat.add_miia(f"Hola{', ' + name if name else ''}. Soy MIIA. ¿En qué te ayudo?")
        else:
            self.chat.add_miia("Hola. Soy MIIA. Para activar mi cerebro, abre el menú > Cerebros y pega una API key "
                               "gratuita.")
        if eng.seed_notice:
            self.note(eng.seed_notice)
        if not eng.brain.available:
            Clock.schedule_once(lambda dt: self.open_brains(), 0.8)
        if eng.cfg.get("wake_enabled"):
            Clock.schedule_once(lambda dt: eng.voice.start_background(), 1.5)

    def pause(self):
        self.orb.stop()

    def resume(self):
        self.orb.start()
        self.refresh_brain_label()

    # ------------------------------------------------------------------ utilidades para las pantallas
    @staticmethod
    def ui(fn):
        Clock.schedule_once(lambda dt: _safe(fn), 0)

    def note(self, text):
        self.chat.add_note(text)

    def refresh_brain_label(self):
        try:
            head, quota = self.engine.brain_summary()
            self.brain_label.text = head
            self.quota_label.text = quota
        except Exception:
            log_exc("brain label")

    def ask_confirm(self, text) -> bool:
        """Pide permiso desde cualquier hilo y espera la respuesta (hasta 90 s)."""
        ev = threading.Event()
        res = {"ok": False}

        def show():
            def ans(v):
                res["ok"] = v
                ev.set()
            ask_yes_no("MIIA pide permiso", text, ans, "Permitir", "Rechazar")
        self.ui(show)
        ev.wait(90)
        return res["ok"]

    # ------------------------------------------------------------------ estado
    def _status(self):
        if self.speaking:
            return "Hablando..."
        if self.vstate == "listening" and self.partial:
            return "Te escucho: " + self.partial[-48:]
        if self.vstate in ("thinking",) and self.busy_text:
            return self.busy_text
        return STATE_TEXT.get(self.vstate, "Lista")

    def _refresh_status(self):
        self.status_label.text = self._status()
        v = self.vstate
        self.orb.set_state(speaking=self.speaking or v == "speaking", thinking=v == "thinking",
                           listening=v == "listening")
        if self.speaking or v == "speaking":
            self.talk_btn.text = "Callar"
        elif v == "listening":
            self.talk_btn.text = "Listo"
        else:
            self.talk_btn.text = "Hablar"

    def _voice_state(self, state, detail=""):
        self.vstate = state
        if state != "listening":
            self.partial = ""
        if state != "thinking":
            self.busy_text = ""
        self._refresh_status()

    def _set_speaking(self, v):
        self.speaking = v
        self._refresh_status()

    def _set_busy_text(self, text):
        self.busy_text = text
        self._refresh_status()

    def _partial(self, text):
        self.partial = text
        self._refresh_status()

    def _user_message(self, text, via_voice):
        self.chat.add_user(text)

    def _stream_end(self):
        self.chat.stream_end()
        self.refresh_brain_label()

    def _wake_changed(self, on):
        if self.wake_btn is not None:
            self._style_wake_btn()

    # ------------------------------------------------------------------ acciones
    def send(self, *_):
        text = self.entry.text.strip()
        if not text:
            return
        if self.engine.voice.submit_typed(text):
            self.entry.text = ""
        else:
            self.note("Un momento: todavía estoy respondiendo.")

    def on_talk(self):
        try:
            self.engine.voice.talk_button()
        except Exception:
            log_exc("talk")
            self.note("No pude abrir el micrófono.")

    def open_menu(self):
        if self.menu is not None:
            try:
                self.menu.open()
                self._style_wake_btn()
                return
            except Exception:
                self.menu = None
        m = ModalView(size_hint=(0.8, 1), pos_hint={"x": 0, "y": 0}, background="", background_color=(0, 0, 0, 0.55),
                      auto_dismiss=True)
        panel = Panel(bg=theme.PANEL, radius=0, orientation="vertical", padding=dp(10), spacing=dp(6))
        col = ScrollColumn(padding=0)
        col.add(Label(text="MIIA", font_size=sp(24), bold=True, color=rgba(theme.ACCENT_TEXT), size_hint_y=None,
                      height=dp(44), halign="left"))
        self.wake_btn = button("", self._toggle_wake, "primary")
        col.add(self.wake_btn)
        col.add(small("Con «MIIA» activado, di «MIIA» en voz alta (aunque la pantalla esté apagada) y te respondo."))
        col.add(spacer(4))
        entries = [
            ("Cerebros", self.open_brains, "secondary"),
            ("Nube (GitHub)", lambda: screens_other.open_cloud(self), "secondary"),
            ("Tareas / Entrenar", lambda: screens_other.open_tasks(self), "secondary"),
            ("Plataformas", lambda: screens_other.open_platforms(self), "secondary"),
            ("Enseñar a MIIA", lambda: screens_other.teach(self), "neutral"),
            ("Detener voz", self.stop_voice, "neutral"),
            ("Limpiar chat", self.clear_chat, "neutral"),
            ("Ajustes", lambda: screens_other.open_settings(self), "neutral"),
            ("Segundo plano (dejar escuchando)", self._to_background, "neutral"),
        ]
        for text, fn, kind in entries:
            def go(f=fn):
                m.dismiss()
                Clock.schedule_once(lambda dt: _safe(f), 0.15)
            col.add(button(text, go, kind))
        col.add(small(f"MIIA {core.VERSION} · Android", theme.TEXT_FAINT))
        panel.add_widget(col)
        m.add_widget(panel)
        self.menu = m
        self._style_wake_btn()
        m.open()

    def _style_wake_btn(self):
        if self.wake_btn is None:
            return
        on = bool(self.engine.cfg.get("wake_enabled")) and self.engine.voice.background
        self.wake_btn.text = "Escuchar «MIIA»: ACTIVADO (tocar para apagar)" if on else \
            "Escuchar «MIIA»: apagado (tocar para activar)"
        self.wake_btn.set_kind("primary" if on else "secondary")

    def _toggle_wake(self):
        v = self.engine.voice
        if v.background:
            v.stop_background()
            self.note("Dejé de escuchar «MIIA». El botón Hablar sigue funcionando.")
        else:
            v.start_background()
            self.note("Activando la escucha de «MIIA». Acepta el permiso de micrófono si te lo pide.")
        self._style_wake_btn()

    def _to_background(self):
        if not self.engine.voice.background:
            self.note("Primero activa «Escuchar MIIA» para que siga escuchando en segundo plano.")
            return
        move_task_to_back()

    def stop_voice(self):
        self.engine.voice.stop_all()
        self.note("Voz detenida.")

    def clear_chat(self):
        self.chat.clear_all()
        self.engine.memory.clear_conversations()

    def open_brains(self):
        screens_brains.open_brains(self)

    # ------------------------------------------------------------------ eventos del núcleo
    def _pool_event(self, kind, kw):
        eng = self.engine
        if kind == "switch_start":
            self.busy_text = "Cambiando de cerebro..."
            self._refresh_status()
            if eng.cfg.get("show_switch_screen"):
                self._overlay_token += 1
                token = self._overlay_token
                self._overlay_since = time.time()
                self.overlay.show(kw.get("from_name", "-"), kw.get("to_name", "-"), kw.get("reason", ""))
                Clock.schedule_once(lambda dt: self._overlay_safety(token), 20)
        elif kind == "switch_step":
            if self.overlay.visible:
                self.overlay.step(kw.get("text", ""))
        elif kind == "switch_done":
            self.busy_text = "Pensando..."
            self._refresh_status()
            if self.overlay.visible:
                token = self._overlay_token
                wait = max(0.0, 1.0 - (time.time() - self._overlay_since))
                Clock.schedule_once(lambda dt: self._close_overlay(token), wait + 0.05)
            if not kw.get("ok", True):
                self.note("No pude pasar a otro cerebro. Revisa Cerebros en el menú.")
            self.refresh_brain_label()
        elif kind == "renewed":
            self.note(f"Tokens renovados: «{', '.join(kw.get('names') or [])}» vuelve a estar disponible.")
            self.refresh_brain_label()
        elif kind == "brain_exhausted":
            until = kw.get("until")
            when = f" Vuelve a las {core.fmt_clock(until)}." if until else ""
            self.note(f"«{kw.get('name')}» llegó al límite de hoy ({kw.get('reason')}).{when}")
            self.refresh_brain_label()
        if self.brains_refresh:
            try:
                self.brains_refresh()
            except Exception:
                self.brains_refresh = None

    def _close_overlay(self, token):
        if token == self._overlay_token:
            self.overlay.hide()

    def _overlay_safety(self, token):
        if token == self._overlay_token and self.overlay.visible:
            self.overlay.hide()

    def _cloud_event(self, kind, kw):
        if kind == "cloud_error":
            self.note("Nube: " + kw.get("message", ""))
        elif kind == "cloud_synced" and kw.get("pulled"):
            self.note("Nube: recibí novedades (lecciones o tareas hechas por el servidor).")

    # ------------------------------------------------------------------ botón «atrás» de Android
    def _on_key(self, window, key, *args):
        if key != 27:
            return False
        for w in list(Window.children):
            if isinstance(w, ModalView):
                try:
                    (w.close if hasattr(w, "close") else w.dismiss)()
                except Exception:
                    w.dismiss()
                return True
        if self.engine.voice.background:
            move_task_to_back()          # sigue escuchando «MIIA»
            return True
        move_task_to_back()
        return True


def _safe(fn):
    try:
        fn()
    except Exception:
        log_exc("UI")
        log("falló una acción de la interfaz")
