"""Kivy falso, solo para ejecutar el código de la interfaz en este PC y cazar errores de nombres/argumentos.
No dibuja nada: no sustituye una prueba real en el teléfono."""
import sys
import types


class _Noop:
    def __getattr__(self, name):
        return _Noop()

    def __call__(self, *a, **k):
        return _Noop()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class StubBase:
    canvas = _Noop()
    x = y = 0
    width = height = 100
    size = (100, 100)
    pos = (0, 0)
    center_x = center_y = 50
    top = right = 100
    text = ""
    hint_text = ""
    texture_size = (10, 10)
    state = "normal"
    active = False
    disabled = False
    focus = False
    value = 0
    max = 100
    minimum_height = 0
    scroll_y = 1
    values = ()
    color = (1, 1, 1, 1)
    children = ()

    def __init__(self, *a, **kw):
        self.children = []
        self._binds = {}
        for k, v in kw.items():
            setattr(self, k, v)

    def bind(self, **kw):
        for k, v in kw.items():
            self._binds.setdefault(k, []).append(v)

    def unbind(self, **kw):
        pass

    def fire(self, name, *args):
        for cb in self._binds.get(name, []):
            cb(self, *args)

    def setter(self, name):
        return lambda *a: None

    def add_widget(self, w, *a, **k):
        self.children.insert(0, w)

    def remove_widget(self, w):
        if w in self.children:
            self.children.remove(w)

    def clear_widgets(self):
        self.children = []

    def open(self, *a, **k):
        self.is_open = True
        Window.children.insert(0, self)

    def dismiss(self, *a, **k):
        self.is_open = False
        if self in Window.children:
            Window.children.remove(self)
        self.fire("on_dismiss")


class _Ev:
    def cancel(self):
        pass


class _ClockClass:
    def schedule_once(self, fn, t=0):
        self.last = fn
        try:
            fn(0)
        except Exception:
            import traceback
            traceback.print_exc()
            raise
        return _Ev()

    def schedule_interval(self, fn, t):
        return _Ev()


class _Window(StubBase):
    clearcolor = None
    softinput_mode = ""


Window = _Window()
Window.children = []


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


def install():
    classes = {n: type(n, (StubBase,), {}) for n in (
        "Label", "BoxLayout", "FloatLayout", "ModalView", "ScrollView", "Spinner", "Switch", "TextInput",
        "Widget", "ProgressBar", "RoundedRectangle", "Rectangle", "Ellipse", "Mesh", "Color")}
    kivy = _mod("kivy")
    kivy.__path__ = []
    _mod("kivy.clock", Clock=_ClockClass())
    _mod("kivy.metrics", dp=lambda v: v, sp=lambda v: v)
    _mod("kivy.graphics", Color=classes["Color"], Rectangle=classes["Rectangle"],
         RoundedRectangle=classes["RoundedRectangle"], Ellipse=classes["Ellipse"], Mesh=classes["Mesh"])
    _mod("kivy.core")
    _mod("kivy.core.window", Window=Window)
    _mod("kivy.uix")
    _mod("kivy.uix.behaviors", ButtonBehavior=type("ButtonBehavior", (), {}))
    _mod("kivy.uix.boxlayout", BoxLayout=classes["BoxLayout"])
    _mod("kivy.uix.floatlayout", FloatLayout=classes["FloatLayout"])
    _mod("kivy.uix.label", Label=classes["Label"])
    _mod("kivy.uix.modalview", ModalView=classes["ModalView"])
    _mod("kivy.uix.scrollview", ScrollView=classes["ScrollView"])
    _mod("kivy.uix.spinner", Spinner=classes["Spinner"])
    _mod("kivy.uix.switch", Switch=classes["Switch"])
    _mod("kivy.uix.textinput", TextInput=classes["TextInput"])
    _mod("kivy.uix.widget", Widget=classes["Widget"])
    _mod("kivy.uix.progressbar", ProgressBar=classes["ProgressBar"])
    return Window
