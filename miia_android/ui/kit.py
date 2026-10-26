"""Piezas de interfaz reutilizables (botones, campos, diálogos). Sin emojis: la fuente de Kivy no los dibuja."""

from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from . import theme
from .theme import rgba


class Panel(BoxLayout):
    """BoxLayout con fondo de color y esquinas redondeadas."""

    def __init__(self, bg=theme.SURFACE, radius=10, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            self._color = Color(*rgba(bg))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def set_bg(self, bg):
        self._color.rgba = rgba(bg)


class WLabel(Label):
    """Texto que se ajusta al ancho y crece en alto (para párrafos)."""

    def __init__(self, text="", size=14, color=theme.TEXT, bold=False, halign="left", **kw):
        kw.setdefault("size_hint_y", None)
        super().__init__(text=text, font_size=sp(size), color=rgba(color), bold=bold, halign=halign,
                         valign="top", **kw)
        self.bind(width=self._wrap, texture_size=self._fit)
        self._wrap()

    def _wrap(self, *_):
        self.text_size = (max(1, self.width), None)

    def _fit(self, *_):
        self.height = max(dp(18), self.texture_size[1] + dp(2))

    def set_text(self, text, color=None):
        self.text = text
        if color:
            self.color = rgba(color)


_KINDS = {
    "primary": (theme.ACCENT, theme.ACCENT_PRESSED),
    "secondary": (theme.BLUE, theme.BLUE_PRESSED),
    "neutral": (theme.NEUTRAL, theme.NEUTRAL_PRESSED),
    "danger": (theme.DANGER, theme.DANGER_PRESSED),
    "flat": (theme.PANEL, theme.NEUTRAL),
}


class RButton(ButtonBehavior, Label):
    def __init__(self, text="", kind="secondary", on_press=None, height=44, **kw):
        kw.setdefault("size_hint_y", None)
        super().__init__(text=text, font_size=sp(kw.pop("size", 15)), color=(1, 1, 1, 1), halign="center",
                         valign="middle", height=dp(height), **kw)
        self.kind = kind
        with self.canvas.before:
            self._color = Color(*rgba(_KINDS[kind][0]))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._sync, size=self._sync, state=self._state)
        if on_press:
            self.bind(on_release=lambda *_: on_press())

    def _sync(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self.text_size = (max(1, self.width - dp(12)), max(1, self.height))

    def _state(self, *_):
        normal, pressed = _KINDS[self.kind]
        self._color.rgba = rgba(pressed if self.state == "down" else normal)

    def set_kind(self, kind):
        self.kind = kind
        self._state()


def button(text, on_press=None, kind="secondary", height=44, **kw):
    return RButton(text=text, kind=kind, on_press=on_press, height=height, **kw)


def field(hint="", text="", password=False, multiline=False, height=44, **kw):
    ti = TextInput(hint_text=hint, text=text, password=password, multiline=multiline,
                   size_hint_y=None, height=dp(height), font_size=sp(15),
                   background_normal="", background_active="", background_color=rgba(theme.SURFACE2),
                   foreground_color=(1, 1, 1, 1), hint_text_color=(1, 1, 1, 0.4),
                   cursor_color=rgba(theme.ACCENT_TEXT), selection_color=rgba(theme.ACCENT, 0.5),
                   padding=[dp(10), dp(12), dp(10), dp(8)], write_tab=False, **kw)
    return ti


def spinner(values, text="", **kw):
    kw.setdefault("size_hint_y", None)
    kw.setdefault("height", dp(44))
    return Spinner(text=text or (values[0] if values else ""), values=values, font_size=sp(14),
                   background_normal="", background_color=rgba(theme.BLUE), color=(1, 1, 1, 1), **kw)


def hrow(*widgets, height=44, spacing=8, **kw):
    r = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(height), spacing=dp(spacing), **kw)
    for w in widgets:
        r.add_widget(w)
    return r


def toggle(text, value=False, on_change=None, height=40):
    """(fila, interruptor). La etiqueta ocupa el ancho disponible."""
    sw = Switch(active=bool(value), size_hint_x=None, width=dp(90))
    if on_change:
        sw.bind(active=lambda _w, v: on_change(v))
    lbl = Label(text=text, font_size=sp(14), color=rgba(theme.TEXT), halign="left", valign="middle")
    lbl.bind(size=lambda w, _s: setattr(w, "text_size", (w.width, w.height)))
    return hrow(lbl, sw, height=height), sw


def rowlabel(text, size=14, color=theme.TEXT, **kw):
    """Etiqueta centrada en vertical para usar dentro de una fila (hrow)."""
    lbl = Label(text=text, font_size=sp(size), color=rgba(color), halign="left", valign="middle", **kw)
    lbl.bind(size=lambda w, _s: setattr(w, "text_size", (w.width, w.height)))
    return lbl


def spacer(h=8):
    return Widget(size_hint_y=None, height=dp(h))


def title(text):
    return WLabel(text, size=16, color=theme.ACCENT_TEXT, bold=True)


def small(text, color=theme.TEXT_DIM):
    return WLabel(text, size=12, color=color)


class ScrollColumn(ScrollView):
    """Columna desplazable: `.add(widget)` y `.clear()`."""

    def __init__(self, spacing=8, padding=10, **kw):
        super().__init__(do_scroll_x=False, bar_width=dp(4), **kw)
        self.box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(spacing), padding=dp(padding))
        self.box.bind(minimum_height=self.box.setter("height"))
        super().add_widget(self.box)

    def add(self, w):
        self.box.add_widget(w)
        return w

    def clear(self):
        self.box.clear_widgets()

    def scroll_bottom(self, *_):
        Clock.schedule_once(lambda dt: setattr(self, "scroll_y", 0), 0.05)


class Dialog(ModalView):
    """Ventana casi a pantalla completa con título, botón Cerrar y cuerpo desplazable."""

    def __init__(self, title_text, **kw):
        super().__init__(size_hint=(0.98, 0.95), auto_dismiss=False, background="",
                         background_color=(0, 0, 0, 0.7), **kw)
        self.on_close = None
        root = Panel(bg=theme.PANEL, radius=14, orientation="vertical", padding=dp(6), spacing=dp(4))
        bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(6))
        t = Label(text=title_text, font_size=sp(18), bold=True, color=rgba(theme.ACCENT_TEXT), halign="left",
                  valign="middle")
        t.bind(size=lambda w, _s: setattr(w, "text_size", (w.width, w.height)))
        bar.add_widget(t)
        bar.add_widget(RButton("Cerrar", kind="neutral", on_press=self.close, size_hint_x=None, width=dp(90),
                               height=40, pos_hint={"center_y": 0.5}))
        root.add_widget(bar)
        self.body = ScrollColumn()
        root.add_widget(self.body)
        self.add_widget(root)

    def add(self, w):
        return self.body.add(w)

    def close(self, *_):
        cb, self.on_close = self.on_close, None
        self.dismiss()
        if cb:
            try:
                cb()
            except Exception:
                pass


def ask_yes_no(title_text, text, on_answer, yes="Sí", no="No"):
    """Pregunta con dos botones. on_answer(bool)."""
    v = ModalView(size_hint=(0.9, None), height=dp(260), auto_dismiss=False, background="",
                  background_color=(0, 0, 0, 0.7))
    box = Panel(bg=theme.PANEL, radius=14, orientation="vertical", padding=dp(14), spacing=dp(10))
    box.add_widget(WLabel(title_text, size=17, color=theme.ACCENT_TEXT, bold=True))
    sc = ScrollColumn(padding=0)
    sc.add(WLabel(text, size=14))
    box.add_widget(sc)

    def answer(val):
        v.dismiss()
        try:
            on_answer(val)
        except Exception:
            pass
    box.add_widget(hrow(button(no, lambda: answer(False), "neutral"), button(yes, lambda: answer(True), "primary")))
    v.add_widget(box)
    v.open()
    return v


def ask_text(title_text, hint, on_text, multiline=False, ok="Guardar"):
    """Pide una línea de texto. on_text(str) solo si se acepta."""
    v = ModalView(size_hint=(0.92, None), height=dp(300 if multiline else 230), auto_dismiss=False,
                  background="", background_color=(0, 0, 0, 0.7))
    box = Panel(bg=theme.PANEL, radius=14, orientation="vertical", padding=dp(14), spacing=dp(10))
    box.add_widget(WLabel(title_text, size=16, color=theme.ACCENT_TEXT, bold=True))
    ti = field(hint, multiline=multiline, height=110 if multiline else 44)
    box.add_widget(ti)

    def done(accept):
        v.dismiss()
        if accept and ti.text.strip():
            try:
                on_text(ti.text.strip())
            except Exception:
                pass
    box.add_widget(hrow(button("Cancelar", lambda: done(False), "neutral"), button(ok, lambda: done(True), "primary")))
    v.add_widget(box)
    v.open()
    Clock.schedule_once(lambda dt: setattr(ti, "focus", True), 0.3)
    return v
