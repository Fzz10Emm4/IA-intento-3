"""MIIA para Android (Kivy). Punto de entrada que usa python-for-android."""

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kivy.config import Config as KivyConfig          # noqa: E402

KivyConfig.set("kivy", "exit_on_escape", "0")

from kivy.app import App                              # noqa: E402
from kivy.core.window import Window                   # noqa: E402
from kivy.uix.label import Label                      # noqa: E402

from miia_android.util import IS_ANDROID, desktop_data_dir, log   # noqa: E402


class MiiaApp(App):
    title = "MIIA"

    def build(self):
        Window.clearcolor = (0.04, 0.04, 0.04, 1)
        try:
            Window.softinput_mode = "below_target"
        except Exception:
            pass
        try:
            from miia_android.engine import Engine
            from miia_android.ui.shell import Shell
            data_dir = self.user_data_dir if IS_ANDROID else desktop_data_dir()
            holder = {}
            self.engine = Engine(data_dir, lambda text: holder["shell"].ask_confirm(text))
            self.shell = Shell(self.engine)
            holder["shell"] = self.shell
            return self.shell
        except Exception:
            err = traceback.format_exc()
            log("ERROR al arrancar:", err)
            self.engine = None
            self.shell = None
            return Label(text="MIIA no pudo arrancar:\n\n" + err[-1500:], halign="left", valign="top",
                         text_size=(Window.width - 40, None))

    def on_start(self):
        if self.shell is not None:
            self.shell.start()
            self.engine.start()

    def on_pause(self):
        if self.shell is not None:
            self.shell.pause()
        return True            # no cerrar: la escucha de «MIIA» sigue en segundo plano

    def on_resume(self):
        if self.shell is not None:
            self.shell.resume()

    def on_stop(self):
        if self.engine is not None:
            self.engine.close()


if __name__ == "__main__":
    MiiaApp().run()
