"""Motor de MIIA: junta el núcleo (miia_core.py, sin cambios de fondo respecto al PC) con la voz de Android.
No depende de Kivy: la interfaz solo le pide cosas y le pasa callbacks."""

import os
import threading

import miia_core as core

from .bridge import AndroidBridge, FakeBridge
from .spec import Responder, SpecEngine
from .tts import build_speaker
from .util import IS_ANDROID, log, log_exc, setup_ssl
from .voice import VoiceController


class Engine:
    def __init__(self, data_dir, confirm_cb):
        setup_ssl()
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.cache_dir = os.path.join(data_dir, "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.paths = core.Paths(data_dir)
        # la interfaz rellena estos callbacks; hasta entonces no hacen nada
        self.on_pool = None          # (kind, kwargs)
        self.on_cloud = None         # (kind, kwargs)
        self.on_task_note = None     # (texto)
        self.on_change = None        # () cuando cambia algo que conviene sincronizar
        self.on_speaking = None      # (bool)
        self.on_voice_note = None    # (texto)

        self.cfg = core.Config(self.paths.config)
        self.secrets = core.Secrets(self.paths.secrets)
        self.registry = core.BrainRegistry(self.paths.brains)
        self.seed_notice = self.registry.seed(self.cfg.legacy, self.secrets)
        self.memory = core.MemoryManager(self.paths.memory)
        self.platforms = core.PlatformManager(confirm_cb, self.paths.platforms)
        self.scheduler = None
        self.toolbox = core.ToolBox(self.memory, self.platforms,
                                    schedule_fn=lambda **kw: self.scheduler.add_task(**kw),
                                    confirm_cb=confirm_cb)
        self.pool = core.BrainPool(self.registry, self.secrets, state_path=self.paths.pool_state,
                                   on_event=lambda kind, **kw: self._call(self.on_pool, kind, kw))
        self.handoff = core.Handoff(self.paths.handoff, self.memory, self.pool)
        self.pool.handoff_cb = self.handoff.save
        self.catalog = core.ModelCatalog(self.paths.models_cache)
        self.brain = core.Brain(self.cfg, self.memory, self.platforms, self.toolbox, self.pool)
        self.scheduler = core.TaskScheduler(self.brain, self.memory,
                                            lambda note: self._call(self.on_task_note, note),
                                            tasks_path=self.paths.tasks, log_path=self.paths.task_log)
        self.sync = core.GitHubSync(self.cfg, self.secrets, self.memory, self.registry,
                                    handoff_path=self.paths.handoff, tasks_api=self.scheduler,
                                    on_event=lambda kind, **kw: self._call(self.on_cloud, kind, kw))
        self.handoff.sync = self.sync
        for obj in (self.memory, self.registry, self.scheduler):
            obj.on_change = self.request_cloud_sync

        # ---- voz ----
        self.speaker = build_speaker(self.cfg, self.cache_dir,
                                     on_state=lambda s: self._call(self.on_speaking, s == "speaking"),
                                     on_note=lambda t: self._call(self.on_voice_note, t))
        self.bridge = AndroidBridge() if IS_ANDROID else FakeBridge()
        self.spec = SpecEngine(self.brain, self.cfg)
        self.responder = Responder(self.brain, self.memory, self.speaker)
        self.voice = VoiceController(self.bridge, self.cfg, self.speaker, self.responder, self.spec, ui={})
        self._closed = False

    # ---- utilidades ----
    @staticmethod
    def _call(fn, *args):
        if fn:
            try:
                fn(*args)
            except Exception:
                log_exc("callback del motor")

    def request_cloud_sync(self):
        try:
            self.sync.request_sync()
        except Exception:
            pass
        self._call(self.on_change)

    @staticmethod
    def client_for(base_url, key):
        return core.LLMClient(lambda: base_url, lambda: key)

    # ---- ciclo de vida ----
    def start(self):
        self.pool.start_clock()
        self.scheduler.start()
        self.sync.start()
        threading.Thread(target=self._startup_background, daemon=True).start()

    def _startup_background(self):
        """Lista de modelos (una por proveedor) y, si la nube está activa, baja lo que haya en ella."""
        try:
            seen = set()
            for b in self.registry.list():
                host = b["base_url"]
                if not host or host in seen:
                    continue
                seen.add(host)
                if self.catalog.stale(host):
                    try:
                        self.catalog.refresh(self.client_for(host, self.secrets.brain_key(b)), host)
                    except Exception as e:
                        log(f"No pude actualizar la lista de modelos de {host}: {e}")
        except Exception as e:
            log(f"Error en el arranque: {e}")
        if self.sync.enabled():
            try:
                res = self.sync.pull()
                if res and any(res.values()):
                    self._call(self.on_task_note, "Memoria al día con la nube.")
                self.sync.request_sync()
            except Exception as e:
                self._call(self.on_task_note, "Nube: " + self.brain.friendly_error(e))

    def close(self):
        if self._closed:
            return
        self._closed = True
        for fn in (self.voice.shutdown, self.scheduler.stop, self.pool.stop, self.speaker.stop, self.sync.stop):
            try:
                fn()
            except Exception:
                log_exc("cerrar")
        t = threading.Thread(target=self.sync.flush, daemon=True)
        t.start()
        t.join(6)
        try:
            self.bridge.stop_service()
        except Exception:
            pass

    # ---- resumen de cerebros (encabezado) ----
    @staticmethod
    def short_model(model: str, n=24) -> str:
        model = (model or "").replace(":free", "").split("/")[-1]
        return model if len(model) <= n else model[:n - 1] + "…"

    def brain_summary(self):
        """(texto del encabezado, texto de cuota)."""
        rows = self.pool.status()
        if not rows or not self.pool.any_configured():
            return "Sin cerebro: abre el menú > Cerebros", ""
        act = next((r for r in rows if r["active"] and r["available"]), None) \
            or next((r for r in rows if r["available"]), None)
        if not act:
            nxt = self.pool.next_renewal()
            if nxt:
                return "Sin cuota por ahora", f"Todos los cerebros descansan. El primero vuelve a las {core.fmt_clock(nxt)}."
            return "Ningún cerebro disponible", "Revisa Cerebros en el menú."
        model = (self.pool.last_model if act["active"] and self.pool.last_model else act["model"]) or ""
        head = f"{act['name']} · {self.short_model(model, 20)}"
        parts = [f"Hoy: {act['used']}/{act['limit']} peticiones" if act["limit"] else f"Hoy: {act['used']} peticiones"]
        if act["reset_at"]:
            parts.append(f"se renueva a las {core.fmt_clock(act['reset_at'])}")
        ready = len([r for r in rows if r["available"]])
        return head, " · ".join(parts) + f"\nCerebros listos: {ready} de {len(rows)}"
