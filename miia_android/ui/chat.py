"""Lista de mensajes con burbujas y respuesta en streaming."""

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from . import theme
from .kit import Panel, ScrollColumn
from .theme import rgba

MAX_WIDGETS = 120


class Bubble(Panel):
    def __init__(self, text, role, **kw):
        bg = theme.BUBBLE_USER if role == "user" else theme.BUBBLE_MIIA
        super().__init__(bg=bg, radius=14, orientation="vertical", size_hint_y=None,
                         padding=[dp(12), dp(8), dp(12), dp(8)], **kw)
        self.lbl = Label(text=text, font_size=sp(15), color=rgba("#ffffff" if role == "user" else theme.TEXT),
                         halign="left", valign="top", size_hint_y=None)
        self.lbl.bind(width=self._wrap, texture_size=self._fit)
        self.add_widget(self.lbl)

    def _wrap(self, *_):
        self.lbl.text_size = (max(1, self.lbl.width), None)

    def _fit(self, *_):
        self.lbl.height = self.lbl.texture_size[1]
        self.height = self.lbl.height + dp(16)


class Row(BoxLayout):
    """Una fila: la burbuja ocupa el 88 % y el resto queda de margen (derecha para ti, izquierda para MIIA)."""

    def __init__(self, bubble, role, **kw):
        super().__init__(orientation="horizontal", size_hint_y=None, **kw)
        self.bubble = bubble
        gap = Widget(size_hint_x=0.12)
        bubble.size_hint_x = 0.88
        if role == "user":
            self.add_widget(gap)
            self.add_widget(bubble)
        else:
            self.add_widget(bubble)
            self.add_widget(gap)
        bubble.bind(height=lambda _w, h: setattr(self, "height", h))
        self.height = bubble.height


class Note(Label):
    def __init__(self, text, **kw):
        super().__init__(text=text, font_size=sp(12), color=rgba(theme.INFO), halign="center", valign="top",
                         size_hint_y=None, **kw)
        self.bind(width=lambda *_: setattr(self, "text_size", (max(1, self.width - dp(16)), None)),
                  texture_size=lambda *_: setattr(self, "height", self.texture_size[1] + dp(6)))


class ChatView(ScrollColumn):
    def __init__(self, **kw):
        super().__init__(spacing=8, padding=8, **kw)
        self._stream = None
        self._buf = ""
        self._flush_ev = None

    def _trim(self):
        kids = self.box.children        # el más nuevo está primero
        while len(kids) > MAX_WIDGETS:
            self.box.remove_widget(kids[-1])

    def add_user(self, text):
        self.add(Row(Bubble(text, "user"), "user"))
        self._trim()
        self.scroll_bottom()

    def add_miia(self, text):
        self.add(Row(Bubble(text, "miia"), "miia"))
        self._trim()
        self.scroll_bottom()

    def add_note(self, text):
        self.add(Note(text))
        self._trim()
        self.scroll_bottom()

    # ---- streaming ----
    def stream_begin(self):
        self._buf = ""
        b = Bubble("", "miia")
        self._stream = b
        self.add(Row(b, "miia"))
        self._trim()

    def stream_chunk(self, piece):
        if self._stream is None:
            self.stream_begin()
        self._buf += piece
        if self._flush_ev is None:
            self._flush_ev = Clock.schedule_once(self._flush, 0.08)

    def _flush(self, *_):
        self._flush_ev = None
        if self._stream is not None:
            self._stream.lbl.text = self._buf
            self.scroll_bottom()

    def stream_end(self):
        self._flush()
        self._stream = None
        self._buf = ""

    def clear_all(self):
        self._stream = None
        self.clear()
