"""Cliente mínimo de Edge TTS (voces neuronales gratuitas de Microsoft) con websocket-client.

Es el mismo servicio que usa la librería «edge-tts» del PC. Microsoft va rotando la versión de Edge que acepta
(si se queda vieja responde 403), así que este cliente:
  1) corrige el reloj si el 403 viene por desfase horario,
  2) si sigue el 403, baja de PyPI la última «edge-tts» SOLO para leer sus constantes (no la ejecuta) y reintenta,
  3) si nada funciona, lanza EdgeError y MIIA habla con la voz nativa de Android.
"""

import hashlib
import io
import json
import re
import ssl
import time
import urllib.request
import uuid
import zipfile
from email.utils import parsedate_to_datetime
from xml.sax.saxutils import escape

from .util import log

DEFAULTS = {
    "token": "6A5AA1D4EAFF4E9FB37E23D68491D6F4",
    "chromium": "143.0.3650.75",
    "wss": "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1",
}
ORIGIN = "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold"
WIN_EPOCH = 11644473600
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class EdgeError(Exception):
    pass


class _Forbidden(Exception):
    def __init__(self, date_header=""):
        super().__init__("Edge TTS respondió 403 (versión o reloj no aceptados)")
        self.date = date_header


def sec_ms_gec(token: str, skew: float = 0.0, now: float = None) -> str:
    """Token DRM de Edge: SHA-256 del instante (en intervalos de 100 ns desde 1601, redondeado a 5 min) + token."""
    t = int((time.time() if now is None else now) + skew) + WIN_EPOCH
    t -= t % 300
    return hashlib.sha256(f"{t * 10_000_000}{token}".encode("ascii")).hexdigest().upper()


def js_date(now: float = None) -> str:
    t = time.gmtime(now)
    return (f"{_DAYS[t.tm_wday]} {_MONTHS[t.tm_mon - 1]} {t.tm_mday:02d} {t.tm_year} "
            f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d} GMT+0000 (Coordinated Universal Time)")


def long_voice(name: str) -> str:
    m = re.match(r"^([a-z]{2,})-([A-Z]{2,})-(.+Neural)$", name or "")
    if not m:
        return name or "Microsoft Server Speech Text to Speech Voice (es-ES, ElviraNeural)"
    return f"Microsoft Server Speech Text to Speech Voice ({m.group(1)}-{m.group(2)}, {m.group(3)})"


def voice_lang(name: str) -> str:
    m = re.match(r"^([a-z]{2,}-[A-Z]{2,})-", name or "")
    return m.group(1) if m else "es-ES"


def config_message(now: float = None) -> str:
    return (f"X-Timestamp:{js_date(now)}\r\nContent-Type:application/json; charset=utf-8\r\nPath:speech.config\r\n\r\n"
            '{"context":{"synthesis":{"audio":{"metadataoptions":{"sentenceBoundaryEnabled":"false",'
            '"wordBoundaryEnabled":"true"},"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}\r\n')


def ssml_message(text: str, voice: str, rate: str = "+0%", now: float = None) -> str:
    rate = rate if re.match(r"^[+-]\d+%$", rate or "") else "+0%"
    ssml = (f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='{voice_lang(voice)}'>"
            f"<voice name='{long_voice(voice)}'><prosody pitch='+0Hz' rate='{rate}' volume='+0%'>"
            f"{escape(text)}</prosody></voice></speak>")
    return (f"X-RequestId:{uuid.uuid4().hex}\r\nContent-Type:application/ssml+xml\r\n"
            f"X-Timestamp:{js_date(now)}Z\r\nPath:ssml\r\n\r\n{ssml}")


def audio_from_frame(frame: bytes) -> bytes:
    """Un mensaje binario trae: 2 bytes (longitud de cabecera), cabecera de texto y el audio."""
    if len(frame) < 2:
        return b""
    hlen = int.from_bytes(frame[:2], "big")
    header = frame[2:2 + hlen]
    if b"Path:audio" not in header:
        return b""
    return frame[2 + hlen:]


def parse_constants(src: str) -> dict:
    """Lee (sin ejecutar nada) las constantes del constants.py de edge-tts. Valida el formato de cada una."""
    out = {}
    m = re.search(r'CHROMIUM_FULL_VERSION\s*=\s*"(\d+(?:\.\d+){3})"', src)
    if m:
        out["chromium"] = m.group(1)
    m = re.search(r'TRUSTED_CLIENT_TOKEN\s*=\s*"([0-9A-Fa-f]{32})"', src)
    if m:
        out["token"] = m.group(1).upper()
    m = re.search(r'BASE_URL\s*=\s*"([a-z0-9./-]+)"', src)
    if m and re.match(r"^[a-z0-9.-]+\.(bing|microsoft)\.com/", m.group(1)):
        out["wss"] = f"wss://{m.group(1)}/edge/v1"
    return out


def _ca_file():
    try:
        import certifi
        return certifi.where()
    except Exception:
        return None


def _http_get(url: str, timeout: float) -> bytes:
    ctx = ssl.create_default_context(cafile=_ca_file())
    req = urllib.request.Request(url, headers={"User-Agent": "MIIA-Android"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read(8_000_000)


class EdgeTTS:
    def __init__(self, cfg=None):
        self.cfg = cfg
        self.skew = 0.0
        self.const = dict(DEFAULTS)
        cached = (cfg.get("edge_const") if cfg else None) or {}
        if isinstance(cached, dict):
            self.const.update({k: v for k, v in cached.items() if k in DEFAULTS and v})
        self._last_refresh = 0.0
        self.last_error = ""

    # ---- constantes ----
    def refresh_constants(self, force=False) -> bool:
        """Devuelve True solo si encontró constantes DISTINTAS a las que ya se usaban."""
        if not force and time.time() - self._last_refresh < 900:
            return False
        self._last_refresh = time.time()
        try:
            info = json.loads(_http_get("https://pypi.org/pypi/edge-tts/json", 15).decode("utf-8"))
            url = next(u["url"] for u in info["urls"] if u.get("packagetype") == "bdist_wheel")
            z = zipfile.ZipFile(io.BytesIO(_http_get(url, 30)))
            name = next(n for n in z.namelist() if n.endswith("edge_tts/constants.py"))
            new = parse_constants(z.read(name).decode("utf-8", "replace"))
        except Exception as e:
            self.last_error = f"No pude actualizar las constantes de Edge: {e}"
            log(self.last_error)
            return False
        changed = any(self.const.get(k) != v for k, v in new.items())
        if changed:
            self.const.update(new)
            if self.cfg:
                self.cfg.update(edge_const=dict(self.const))
            log("Constantes de Edge actualizadas:", new)
        return changed

    def _apply_skew(self, date_header: str):
        try:
            server = parsedate_to_datetime(date_header).timestamp()
            self.skew = server - time.time()
        except Exception:
            pass

    # ---- síntesis ----
    def synth(self, text: str, voice: str, rate: str = "+8%") -> bytes:
        err = None
        for attempt in range(3):
            try:
                return self._synth_once(text, voice, rate)
            except _Forbidden as e:
                err = e
                if attempt == 0 and e.date:
                    self._apply_skew(e.date)
                    continue
                if attempt <= 1 and self.refresh_constants():
                    continue
                break
        self.last_error = str(err)
        raise EdgeError(str(err))

    def _synth_once(self, text: str, voice: str, rate: str) -> bytes:
        import websocket
        c = self.const
        major = c["chromium"].split(".")[0]
        url = (f"{c['wss']}?TrustedClientToken={c['token']}&ConnectionId={uuid.uuid4().hex}"
               f"&Sec-MS-GEC={sec_ms_gec(c['token'], self.skew)}&Sec-MS-GEC-Version=1-{c['chromium']}")
        headers = [
            "Pragma: no-cache",
            "Cache-Control: no-cache",
            "Accept-Language: en-US,en;q=0.9",
            (f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
             f"Chrome/{major}.0.0.0 Safari/537.36 Edg/{major}.0.0.0"),
        ]
        sslopt = {"cert_reqs": ssl.CERT_REQUIRED}
        ca = _ca_file()
        if ca:
            sslopt["ca_certs"] = ca
        try:
            ws = websocket.create_connection(url, timeout=12, origin=ORIGIN, header=headers,
                                             cookie=f"muid={uuid.uuid4().hex.upper()};", sslopt=sslopt)
        except websocket.WebSocketBadStatusException as e:
            if getattr(e, "status_code", 0) == 403:
                hdrs = getattr(e, "resp_headers", None) or {}
                raise _Forbidden(str(hdrs.get("date") or hdrs.get("Date") or ""))
            raise EdgeError(f"Edge TTS: HTTP {getattr(e, 'status_code', '?')}")
        except Exception as e:
            raise EdgeError(f"Edge TTS no conecta: {e}")
        audio = bytearray()
        try:
            ws.settimeout(12)
            ws.send(config_message())
            ws.send(ssml_message(text, voice, rate))
            deadline = time.time() + 30
            while time.time() < deadline:
                msg = ws.recv()
                if isinstance(msg, str):
                    if "Path:turn.end" in msg:
                        break
                    continue
                audio += audio_from_frame(msg)
            else:
                raise EdgeError("Edge TTS tardó demasiado")
        except EdgeError:
            raise
        except Exception as e:
            raise EdgeError(f"Edge TTS se cortó: {e}")
        finally:
            try:
                ws.close()
            except Exception:
                pass
        if len(audio) < 200:
            raise EdgeError("Edge TTS no devolvió audio")
        return bytes(audio)
