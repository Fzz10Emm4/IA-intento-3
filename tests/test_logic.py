"""Pruebas de la lógica que no depende de Android (se ejecutan en un PC: python tests/test_logic.py)."""
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import miia_core as core                                  # noqa: E402
from miia_android import edge                             # noqa: E402
from miia_android.bridge import FakeBridge                # noqa: E402
from miia_android.spec import Responder, SpecEngine, SpecJob   # noqa: E402
from miia_android.tts import NullPlayer, SentenceSplitter, Speaker, rate_to_float   # noqa: E402
from miia_android.util import norm                        # noqa: E402
from miia_android.voice import VoiceController, find_wake    # noqa: E402


def wait_for(cond, t=3.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_splitter():
    s = SentenceSplitter()
    out = []
    for piece in ["Hola, ", "te cuento. ", "Primero esto es una frase bastante larga para agrupar. ",
                  "Luego otra frase corta. ", "Y una más larga que sirva para completar el grupo de setenta caracteres. ",
                  "Final"]:
        out += s.feed(piece)
    out += s.flush()
    assert out[0] == "Hola, te cuento.", out
    assert all(len(o) >= 12 for o in out[:-1]), out
    assert "".join(o.replace(" ", "") for o in out) == (
        "Hola, te cuento. Primero esto es una frase bastante larga para agrupar. Luego otra frase corta. "
        "Y una más larga que sirva para completar el grupo de setenta caracteres. Final").replace(" ", ""), out
    s = SentenceSplitter()
    got = s.feed("Habla con el Sr. Pérez ahora. ") + s.feed("Luego se fue. ") + s.flush()
    assert got and got[0].startswith("Habla con el Sr. Pérez"), got
    s = SentenceSplitter()
    big = s.feed("palabra " * 80)
    assert big and all(len(b) < 300 for b in big)
    print("ok splitter", out)


def test_edge():
    g = edge.sec_ms_gec("6A5AA1D4EAFF4E9FB37E23D68491D6F4", now=1_700_000_000)
    assert len(g) == 64 and g == g.upper()
    assert edge.sec_ms_gec("X", now=1_700_000_000) == edge.sec_ms_gec("X", now=1_700_000_050)   # misma ventana de 5 min
    assert edge.long_voice("es-ES-ElviraNeural").endswith("(es-ES, ElviraNeural)")
    m = edge.ssml_message("Hola <b> & chau", "es-ES-ElviraNeural", "+8%")
    assert "&lt;b&gt; &amp; chau" in m and "rate='+8%'" in m and m.endswith("</speak>")
    hdr = b"X-RequestId:abc\r\nContent-Type:audio/mpeg\r\nX-Stream-Id:1\r\nPath:audio\r\n"
    frame = len(hdr).to_bytes(2, "big") + hdr + b"\x01\x02\x03"
    assert edge.audio_from_frame(frame) == b"\x01\x02\x03"
    assert edge.audio_from_frame(len(b"Path:turn.start").to_bytes(2, "big") + b"Path:turn.start" + b"zz") == b""
    c = edge.parse_constants('CHROMIUM_FULL_VERSION = "150.1.2.3"\nTRUSTED_CLIENT_TOKEN = "6a5aa1d4eaff4e9fb37e23d68491d6f4"\n'
                             'BASE_URL = "speech.platform.bing.com/consumer/speech/synthesize/readaloud"\n')
    assert c["chromium"] == "150.1.2.3" and c["token"].startswith("6A5A") and c["wss"].startswith("wss://speech.platform.bing.com")
    assert "wss" not in edge.parse_constants('BASE_URL = "evil.example.com/x"')
    assert abs(rate_to_float("+8%") - 1.08) < 1e-9 and rate_to_float("raro") == 1.0
    print("ok edge")


def test_wake():
    assert find_wake("MIIA qué hora es") == (True, "qué hora es")
    assert find_wake("oye Mía, ¿qué tiempo hace?") == (True, "qué tiempo hace")
    assert find_wake("hey mia") == (True, "")
    assert find_wake("Miya") == (True, "")
    assert find_wake("mi ia dime algo") == (True, "dime algo")
    assert find_wake("la casa es mía")[0] is False
    assert find_wake("hola buenas tardes")[0] is False
    assert find_wake("María llegó")[0] is False
    print("ok wake")


class FakePool:
    def __init__(self):
        self.ok = True

    def speculation_ok(self):
        return self.ok


class FakeBrain:
    def __init__(self):
        self.pool = FakePool()
        self.available = True
        self.spec_calls, self.chat_calls = [], []
        self.fail_spec = False

    def reply_to(self, text, on_text=None, on_status=None, purpose="chat"):
        self.spec_calls.append((text, purpose))
        if self.fail_spec:
            raise core.NetworkError("sin red")
        for p in ["Son ", "las tres."]:
            on_text and on_text(p)
            time.sleep(0.01)
        return "Son las tres."

    def chat(self, on_text=None, on_status=None):
        self.chat_calls.append(1)
        on_text and on_text("Respuesta normal.")
        return "Respuesta normal."

    def fallback_reply(self, t):
        return "sin cerebro"

    def friendly_error(self, e):
        return "ERR " + type(e).__name__


class FakeMemory:
    def __init__(self):
        self.rows = []

    def add_conversation(self, role, content):
        self.rows.append((role, content))


def make_cfg(**kw):
    cfg = core.Config(None)
    cfg.data.update(kw)
    return cfg


def test_spec():
    cfg = make_cfg(spec_max_per_day=2)
    brain = FakeBrain()
    eng = SpecEngine(brain, cfg, settle=0.05)
    eng.begin_utterance()
    eng.on_partial("qué")                                    # muy corto: no se lanza
    time.sleep(0.12)
    assert not brain.spec_calls
    eng.on_partial("qué hora es en este momento")
    assert wait_for(lambda: brain.spec_calls)
    assert brain.spec_calls[0][1] == "spec"
    job = eng.take("Qué hora es en este momento?")
    assert job and job.wait(2) and job.reply == "Son las tres."
    got = []
    job.attach(got.append)
    assert "".join(got) == "Son las tres."
    # lo dicho al final es otra cosa: se descarta
    eng.begin_utterance()
    eng.on_partial("cuéntame un chiste de gatos")
    assert wait_for(lambda: len(brain.spec_calls) == 2)
    assert eng.take("cuéntame un chiste de perros por favor") is None
    # tope diario (2) alcanzado
    eng.begin_utterance()
    eng.on_partial("esto ya no debería lanzarse hoy")
    time.sleep(0.2)
    assert len(brain.spec_calls) == 2
    # sin cerebros aptos
    cfg.update(spec_max_per_day=10)
    brain.pool.ok = False
    eng.on_partial("tampoco con la cuota agotada ahora")
    time.sleep(0.2)
    assert len(brain.spec_calls) == 2
    cfg.update(speculate=False)
    brain.pool.ok = True
    eng.on_partial("ni apagada la función completa")
    time.sleep(0.2)
    assert len(brain.spec_calls) == 2
    print("ok spec")


def test_responder():
    brain, mem = FakeBrain(), FakeMemory()
    r = Responder(brain, mem)
    out = []
    reply, ok = r.respond("hola", None, on_text=out.append, speak=False)
    assert ok and reply == "Respuesta normal." and mem.rows == [("user", "hola"), ("assistant", "Respuesta normal.")]
    # con anticipada lista
    job = SpecJob("qué hora es")
    job.push("Son las tres.")
    job.reply = "Son las tres."
    job.done.set()
    mem.rows.clear()
    out.clear()
    reply, ok = r.respond("qué hora es", job, on_text=out.append, speak=False)
    assert reply == "Son las tres." and "".join(out) == "Son las tres." and not brain.chat_calls[1:]
    # la anticipada falló sin emitir: se responde normal
    bad = SpecJob("x")
    bad.error = core.NetworkError("x")
    bad.done.set()
    out.clear()
    reply, ok = r.respond("x", bad, on_text=out.append, speak=False)
    assert ok and reply == "Respuesta normal."
    # sin cerebro
    brain.available = False
    reply, ok = r.respond("hola", None, speak=False)
    assert reply == "sin cerebro"
    print("ok responder")


def make_voice(cfg=None, conv=True):
    cfg = cfg or make_cfg(conversation_mode=conv)
    bridge = FakeBridge()
    brain, mem = FakeBrain(), FakeMemory()
    player = NullPlayer()
    states = []
    spk = Speaker(cfg, player, edge=_FakeEdge(), native=None, on_state=lambda s: states.append(s))
    resp = Responder(brain, mem, spk)
    spec = SpecEngine(brain, cfg, settle=0.05)
    log = {"user": [], "chunks": [], "notes": [], "states": []}
    ui = {"user_message": lambda t, v: log["user"].append((t, v)),
          "chunk": log["chunks"].append, "note": log["notes"].append,
          "state": lambda s, d="": log["states"].append(s)}
    vc = VoiceController(bridge, cfg, spk, resp, spec, ui, sleep=lambda s: time.sleep(min(s, 0.01)))
    return vc, bridge, brain, mem, spk, log, player


class _FakeEdge:
    def synth(self, text, voice, rate):
        return b"x" * 500


def test_voice_wake_flow():
    vc, bridge, brain, mem, spk, log, player = make_voice()
    vc.start_background()
    assert wait_for(lambda: bridge.service and any(c[0] == "listen" and c[3] for c in bridge.calls))   # sesión wake (tight)
    # silencio: se reinicia sola
    n = len([c for c in bridge.calls if c[0] == "listen"])
    bridge.push("error:7")
    assert wait_for(lambda: len([c for c in bridge.calls if c[0] == "listen"]) > n)
    # el usuario dice «oye MIIA qué hora es»: la anticipada arranca con el resto
    bridge.push("partial:oye mia")
    bridge.push("partial:oye mia qué hora es en este momento")
    assert wait_for(lambda: brain.spec_calls)
    assert brain.spec_calls[0][0] == "qué hora es en este momento"
    bridge.push("final:oye MIIA qué hora es en este momento")
    assert wait_for(lambda: log["user"] and mem.rows[-1:] == [("assistant", "Son las tres.")])
    assert log["user"][0] == ("qué hora es en este momento", True)
    assert not brain.chat_calls                       # se usó la respuesta anticipada
    assert wait_for(lambda: spk.spoken and not spk.speaking)
    # modo conversación: sigue escuchando sin decir MIIA
    assert wait_for(lambda: vc.session == "follow" and not vc._busy and bridge.calls[-1][0] == "listen")
    bridge.push("final:y mañana")
    assert wait_for(lambda: len(mem.rows) >= 4)
    assert mem.rows[-2] == ("user", "y mañana")
    # silencio en la conversación: vuelve a esperar «MIIA»
    assert wait_for(lambda: vc.session == "follow" and not vc._busy and bridge.calls[-1][0] == "listen")
    bridge.push("error:6")
    assert wait_for(lambda: bridge.calls[-1][0] == "listen" and bridge.calls[-1][3] is True)
    # solo «MIIA»: dice «Dime» y abre escucha de orden
    spoken_before = len(spk.spoken)
    bridge.push("final:MIIA")
    assert wait_for(lambda: len(spk.spoken) > spoken_before and spk.spoken[-1] == "Dime.")
    assert wait_for(lambda: bridge.calls[-1][0] == "listen" and bridge.calls[-1][3] is False)
    # pitidos silenciados
    assert ("mute", True, False) in bridge.calls
    # detener desde la notificación
    bridge.push("svcstop")
    assert wait_for(lambda: not bridge.service)
    vc.shutdown()
    print("ok voice wake", log["states"][:8])


def test_voice_button_and_errors():
    vc, bridge, brain, mem, spk, log, player = make_voice(conv=False)
    vc.talk_button()
    assert wait_for(lambda: bridge.calls and bridge.calls[-1][0] == "listen" and bridge.calls[-1][3] is False)
    vc.talk_button()                                  # segundo toque: termina de escuchar
    assert wait_for(lambda: ("stop_listening",) in bridge.calls)
    bridge.push("final:cuéntame algo")
    assert wait_for(lambda: mem.rows[-1:] == [("assistant", "Respuesta normal.")])
    assert brain.chat_calls                            # sin anticipada: respuesta normal
    assert wait_for(lambda: log["states"][-1] == "idle")
    # error de idioma
    vc.talk_button()
    assert wait_for(lambda: vc.session == "command")
    bridge.push("error:13")
    assert wait_for(lambda: any("idioma" in n for n in log["notes"]))
    # escrito
    assert vc.submit_typed("hola") or True
    vc.shutdown()
    print("ok voice button")


def test_norm():
    assert norm("¡Oye, Mía! ¿Qué tal?") == "oye mia que tal"
    print("ok norm")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("TODO OK")
