"""Ejecuta el código de la interfaz con un Kivy falso para detectar errores de nombres y argumentos."""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
import kivy_stub                                           # noqa: E402

Window = kivy_stub.install()

from miia_android.engine import Engine                    # noqa: E402
from miia_android.ui import screens_brains, screens_other  # noqa: E402
from miia_android.ui.shell import Shell                    # noqa: E402


def main():
    d = tempfile.mkdtemp()
    holder = {}
    eng = Engine(d, lambda t: True)
    shell = Shell(eng)
    holder["shell"] = shell
    shell.start()
    eng.start()
    eng.registry.add(name="Prueba", base_url="https://x.invalid/v1", model="m/modelo:free", daily_requests=5)
    shell.refresh_brain_label()
    shell.open_menu()
    shell.open_menu()
    shell._toggle_wake()
    shell._style_wake_btn()
    screens_brains.open_brains(shell)
    bid = eng.registry.list()[0]["id"]
    screens_other.open_cloud(shell)
    screens_other.open_tasks(shell)
    screens_other.open_platforms(shell)
    screens_other.open_settings(shell)
    screens_other.teach(shell)
    shell.overlay.show("A", "B", "agotado")
    shell.overlay.step("x")
    shell.overlay.hide()
    # eventos del motor hacia la interfaz
    for ev in (("switch_start", {"from_name": "A", "to_name": "B", "reason": "agotado"}),
               ("switch_step", {"text": "paso"}), ("switch_done", {"ok": True}),
               ("renewed", {"names": ["A"]}), ("brain_exhausted", {"name": "A", "until": time.time() + 99, "reason": "cuota"})):
        shell._pool_event(*ev)
    shell._cloud_event("cloud_error", {"message": "falla"})
    # voz → interfaz
    vui = eng.voice.ui
    vui["state"]("listening", "")
    vui["partial"]("hola que tal")
    vui["user_message"]("hola", True)
    vui["stream_begin"]()
    vui["chunk"]("Hola ")
    vui["chunk"]("mundo")
    vui["stream_end"]("Hola mundo", True)
    vui["state"]("speaking", "")
    shell._set_speaking(True)
    shell._set_speaking(False)
    vui["state"]("idle", "")
    shell.on_talk()
    time.sleep(0.2)
    shell.entry.text = "hola"
    shell.send()
    time.sleep(0.5)
    shell.stop_voice()
    shell.clear_chat()
    shell._on_key(Window, 27)
    shell.pause()
    shell.resume()
    eng.close()
    print("UI SMOKE OK; chat rows:", len(shell.chat.box.children))


if __name__ == "__main__":
    main()
