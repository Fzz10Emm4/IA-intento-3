"""Pantallas: Nube (GitHub), Tareas, Plataformas, Ajustes, Enseñar y la pantalla de cambio de cerebro."""

import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.progressbar import ProgressBar

import miia_core as core

from . import theme
from .kit import (Dialog, Panel, WLabel, ask_text, ask_yes_no, button, field, hrow, rowlabel, small, spacer, spinner,
                  title, toggle)


def _box():
    b = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
    b.bind(minimum_height=b.setter("height"))
    return b


# ====================================================================== NUBE
def open_cloud(app):
    eng = app.engine
    cfg, sync = eng.cfg, eng.sync
    dlg = Dialog("Nube (GitHub)")
    dlg.add(title("Qué hace (y qué no)"))
    dlg.add(small(
        "GitHub NO ejecuta modelos de IA ni aloja un servidor gratis. Lo que sí hace MIIA:\n"
        "- Guarda tu memoria, lecciones y charlas en un repositorio PRIVADO (se sincroniza solo).\n"
        "- GitHub Actions ejecuta cada ~6 h tus tareas marcadas como «en la nube» aunque el teléfono esté apagado, "
        "con los mismos cerebros gratuitos, y deja lo aprendido en el repositorio.\n"
        "Las API keys nunca se suben: en la nube van como «secretos» del repositorio."))
    repo_e = field("Repositorio privado: usuario/repositorio", cfg.get("github_repo") or "")
    token_e = field("Token guardado (pega otro para cambiarlo)" if eng.secrets.github_token
                    else "Token de GitHub (fine-grained)", password=True)
    branch_e = field("Rama (vacío = la principal)", cfg.get("github_branch") or "")
    sync_row, sync_sw = toggle("Sincronizar memoria con GitHub", bool(cfg.get("github_sync")))
    pub_row, pub_sw = toggle("Permitir repositorio PÚBLICO (no recomendado)", bool(cfg.get("github_allow_public")))
    msg = WLabel("", size=13)
    for w in (repo_e, token_e, branch_e, sync_row, pub_row, msg):
        dlg.add(w)

    def say(text, ok=None):
        color = theme.INFO if ok is None else (theme.OK if ok else theme.ERR)
        app.ui(lambda: msg.set_text(text, color))

    def save(quiet=False):
        cfg.update(github_repo=repo_e.text.strip().strip("/"), github_branch=branch_e.text.strip(),
                   github_sync=bool(sync_sw.active), github_allow_public=bool(pub_sw.active))
        tok = token_e.text.strip()
        if tok:
            eng.secrets.set_github_token(tok)
            token_e.text = ""
            token_e.hint_text = "Token guardado (pega otro para cambiarlo)"
        sync._info = None
        if not quiet:
            say("Guardado.", True)
        eng.request_cloud_sync()

    def run_bg(label, fn):
        save(quiet=True)
        say(label)

        def work():
            try:
                fn()
            except Exception as e:
                say("Error: " + eng.brain.friendly_error(e), False)
        threading.Thread(target=work, daemon=True).start()

    def do_check():
        info = sync.check()
        vis = "PRIVADO (bien)" if info["private"] else "PÚBLICO (no subiré nada salvo que lo permitas)"
        say(f"Conectado a {info['full_name']} · repositorio {vis} · escritura: {'sí' if info['push'] else 'NO'}",
            info["private"] and info["push"])

    def do_sync():
        res = sync.sync_now()
        say(f"Sincronizado. Bajé: {', '.join(k for k, v in res['pulled'].items() if v) or 'nada nuevo'}. "
            f"Subí: {len(res['pushed'])} archivo(s).", True)

    def do_install():
        src = Path(core.__file__).read_text(encoding="utf-8")
        done = sync.install_server(src)
        say("Servidor instalado en el repositorio." if done else "El servidor ya estaba al día en el repositorio.", True)
        app.ui(refresh_steps)

    dlg.add(button("Guardar", lambda: save(), "primary"))
    dlg.add(button("Probar conexión", lambda: run_bg("Probando...", do_check)))
    dlg.add(button("Sincronizar ahora", lambda: run_bg("Sincronizando...", do_sync)))
    dlg.add(button("Instalar servidor", lambda: run_bg("Instalando...", do_install)))
    dlg.add(spacer(4))
    dlg.add(title("Pasos para activarlo"))
    steps = small("", theme.TEXT)
    dlg.add(steps)

    def refresh_steps():
        names = sync.needed_secrets()
        steps.set_text(
            "1. En GitHub crea un repositorio PRIVADO vacío (con un README para que exista la rama).\n"
            "2. Settings > Developer settings > Fine-grained tokens: crea un token solo para ese repositorio con "
            "«Contents: Read and write» y «Workflows: Read and write».\n"
            "3. Pega aquí el repositorio y el token, activa la sincronización y toca «Guardar» y «Probar conexión».\n"
            "4. Toca «Instalar servidor»: sube el trabajador de la nube al repositorio.\n"
            "5. En el repositorio: Settings > Secrets and variables > Actions > New repository secret. Crea un secreto "
            "por cada proveedor que uses (el valor es tu API key):\n"
            + ("".join(f"      - {n}\n" for n in names) or "      (añade antes cerebros en Cerebros)\n")
            + "6. Marca «Ejecutar en la nube» al crear una tarea en Tareas.\n\n"
            "Notas: el cron de Actions puede retrasarse; en repositorios privados tienes 2.000 min/mes gratis.",
            theme.TEXT)
    refresh_steps()
    if sync._last_error:
        msg.set_text("Último error: " + sync._last_error, theme.ERR)
    dlg.open()


# ====================================================================== PLATAFORMAS
def open_platforms(app):
    eng = app.engine
    dlg = Dialog("Plataformas conectadas")
    lst = _box()
    dlg.add(lst)

    def refresh():
        lst.clear_widgets()
        if not eng.platforms.items:
            lst.add_widget(WLabel("Aún no hay plataformas.", color=theme.TEXT_DIM))
        for name, p in eng.platforms.items.items():
            card = Panel(bg=theme.SURFACE, orientation="horizontal", size_hint_y=None, height=dp(56),
                         padding=dp(8), spacing=dp(6))
            card.add_widget(rowlabel(f"{name}\n{p['base_url']}", size=13))

            def rm(n=name):
                eng.platforms.remove(n)
                refresh()
            card.add_widget(button("Quitar", rm, "danger", height=40, size=13, size_hint_x=None, width=dp(80)))
            lst.add_widget(card)
    refresh()

    dlg.add(title("Añadir plataforma"))
    name_e = field("Nombre (ej. Notion, MiCRM, Shopify)")
    url_e = field("URL base de la API (https://api.ejemplo.com/v1)")
    auth_sp = spinner(["bearer", "header", "query", "none"], "bearer")
    auth_name_e = field("Nombre del header/parámetro (opcional)")
    token_e = field("Token / API key (o env:NOMBRE_VARIABLE)", password=True)
    desc_e = field("Descripción para MIIA: qué es y qué endpoints útiles tiene", multiline=True, height=100)
    writes_row, writes_sw = toggle("Permitir escrituras (POST/PUT/DELETE) sin preguntarme", False)
    msg = WLabel("", size=13, color=theme.ERR)
    for w in (name_e, url_e, hrow(rowlabel("Autenticación:", size_hint_x=0.4), auth_sp), auth_name_e, token_e,
              desc_e, writes_row, msg):
        dlg.add(w)

    def add():
        err = eng.platforms.add(name_e.text, url_e.text, auth_sp.text, auth_name_e.text, token_e.text,
                                desc_e.text, bool(writes_sw.active))
        if err:
            msg.set_text(err, theme.ERR)
            return
        msg.set_text("")
        for e in (name_e, url_e, auth_name_e, token_e, desc_e):
            e.text = ""
        refresh()
    dlg.add(button("Añadir", add, "primary"))
    dlg.add(small("Los tokens se guardan solo en este teléfono (nunca se suben a GitHub).", theme.TEXT_FAINT))
    dlg.open()


# ====================================================================== TAREAS
def open_tasks(app):
    eng = app.engine
    dlg = Dialog("Tareas / Entrenar")
    dlg.add(small(f"Cada ejecución gasta cuota de tus cerebros (tope diario local: {eng.cfg.get('auto_runs_per_day')}). "
                  "Tras 3 fallos seguidos una tarea se pausa sola. Las tareas «en la nube» las ejecuta GitHub Actions "
                  "(cada ~6 h) aunque el teléfono esté apagado; necesitan la nube activada. Las tareas locales solo "
                  "corren mientras MIIA está abierta o escuchando."))
    lst = _box()
    log_lbl = small("", theme.TEXT)
    dlg.add(lst)

    def refresh_log():
        lines = []
        for e in reversed(eng.scheduler.recent_log()):
            mark = "[ok]" if e["ok"] else "[error]"
            lines.append(f"{mark} [{e['time']}] {e['task']}\n{e['result'][:300]}")
        log_lbl.set_text("\n\n".join(lines) or "Sin ejecuciones todavía.", theme.TEXT)

    def refresh():
        lst.clear_widgets()
        for t in eng.scheduler.list_tasks():
            card = Panel(bg=theme.SURFACE, orientation="vertical", size_hint_y=None, padding=dp(8), spacing=dp(4))
            reps = t["repetitions"] or "inf"
            cloud = "[nube] " if t.get("cloud") else ""
            card.add_widget(WLabel(f"{cloud}{t['name']}\ncada {t['every_minutes']} min · {t['runs']}/{reps}", size=14))
            row, _sw = toggle("Activada", t["enabled"], lambda v, tid=t["id"]: eng.scheduler.set_enabled(tid, v), 36)
            card.add_widget(row)

            def rm(tid=t["id"]):
                eng.scheduler.remove(tid)
                refresh()

            def run(tid=t["id"]):
                eng.scheduler.run_now(tid)
                app.note("Ejecutando tarea ahora...")
            card.add_widget(hrow(button("Ejecutar ahora", run, "secondary", height=38, size=13),
                                 button("Quitar", rm, "danger", height=38, size=13), height=38))
            card.bind(minimum_height=card.setter("height"))
            lst.add_widget(card)
        refresh_log()
    dlg.add(title("Nueva tarea"))
    name_e = field("Nombre (ej. Resumen diario de ventas)")
    prompt_e = field("Instrucción para MIIA", multiline=True, height=100)
    every_e = field("Cada (min)", text="60")
    reps_e = field("Repeticiones (0 = infinitas)", text="5")
    learn_row, learn_sw = toggle("Aprender una lección de cada ejecución", True)
    cloud_row, cloud_sw = toggle("Ejecutar en la nube (GitHub Actions)", False)
    msg = WLabel("", size=13, color=theme.ERR)
    for w in (name_e, prompt_e, hrow(every_e, reps_e), learn_row, cloud_row, msg):
        dlg.add(w)

    def create():
        name, prompt = name_e.text.strip(), prompt_e.text.strip()
        try:
            every, reps = int(every_e.text), int(reps_e.text)
        except ValueError:
            msg.set_text("Intervalo y repeticiones deben ser números.", theme.ERR)
            return
        if not name or not prompt:
            msg.set_text("Pon un nombre y una instrucción.", theme.ERR)
            return
        eng.scheduler.add_task(name, prompt, every, reps, bool(learn_sw.active), cloud=bool(cloud_sw.active))
        msg.set_text("")
        name_e.text = ""
        prompt_e.text = ""
        refresh()
    dlg.add(button("Crear tarea", create, "primary"))
    dlg.add(button("Actualizar registro", refresh, "neutral"))
    dlg.add(title("Registro reciente"))
    dlg.add(log_lbl)
    refresh()
    dlg.open()


# ====================================================================== AJUSTES
RATES = ["-10%", "+0%", "+8%", "+15%", "+25%"]
LANGS = ["es-AR", "es-ES", "es-MX", "es-US", "es-CO", "es-CL"]


def open_settings(app):
    eng = app.engine
    cfg, voice = eng.cfg, eng.voice
    dlg = Dialog("Ajustes")

    dlg.add(title("Voz de MIIA"))
    voice_row, voice_sw = toggle("MIIA habla las respuestas", bool(cfg.get("voice_enabled")))
    dlg.add(voice_row)
    names = list(dict.fromkeys(core.PREFERRED_VOICES + ["es-ES-AlvaroNeural", "es-AR-TomasNeural", cfg.get("voice")]))
    voice_sp = spinner(names, cfg.get("voice"))
    rate_sp = spinner(RATES, cfg.get("voice_rate") if cfg.get("voice_rate") in RATES else "+8%")
    dlg.add(hrow(rowlabel("Voz (Edge):", size_hint_x=0.4), voice_sp))
    dlg.add(hrow(rowlabel("Velocidad:", size_hint_x=0.4), rate_sp))
    native_row, native_sw = toggle("Si Edge falla, hablar con la voz de Android", bool(cfg.get("voice_native_fallback")))
    dlg.add(native_row)
    dlg.add(small("Elvira y las demás voces de Edge son gratis pero necesitan internet. Sin conexión, MIIA usa la voz "
                  "de tu teléfono para no quedarse muda."))

    dlg.add(title("Escuchar tu voz"))
    lang_sp = spinner(LANGS, cfg.get("voice_lang") if cfg.get("voice_lang") in LANGS else "es-AR")
    dlg.add(hrow(rowlabel("Idioma:", size_hint_x=0.4), lang_sp))
    offline_row, offline_sw = toggle("Preferir reconocimiento sin internet", bool(cfg.get("wake_offline")))
    conv_row, conv_sw = toggle("Modo conversación (sigue escuchando tras responder)", bool(cfg.get("conversation_mode")))
    beeps_row, beeps_sw = toggle("Silenciar el pitido del micrófono", bool(cfg.get("mute_beeps")))
    music_row, music_sw = toggle("Silenciar también multimedia mientras espero «MIIA»", bool(cfg.get("mute_music")))
    for w in (offline_row, conv_row, beeps_row, music_row):
        dlg.add(w)
    dlg.add(small("Si aún oyes pitidos al escuchar, activa «silenciar también multimedia» (apaga la música de otras apps "
                  "mientras esperas «MIIA»). El reconocimiento sin internet solo funciona si descargaste el idioma en "
                  "Ajustes de Android > Idioma / Google > Reconocimiento de voz sin conexión."))

    dlg.add(title("Respuesta anticipada"))
    spec_row, spec_sw = toggle("MIIA va pensando la respuesta mientras hablas", bool(cfg.get("speculate")))
    dlg.add(spec_row)
    spec_e = field("Tope diario de intentos", text=str(cfg.get("spec_max_per_day")))
    dlg.add(hrow(rowlabel("Máx. por día:", size_hint_x=0.5), spec_e))
    dlg.add(small("Solo usa cerebros SIN tope diario (así no gasta tu cuota limitada) y nunca ejecuta herramientas. "
                  "Si lo que terminas diciendo es distinto, descarta lo pensado."))

    dlg.add(title("Batería y segundo plano"))
    bat = small("")

    def bat_refresh():
        try:
            ok = eng.bridge.battery_ok()
        except Exception:
            ok = False
        bat.set_text("Batería: sin restricciones (bien)." if ok else
                     "Batería: Android puede dormir a MIIA. Pon «Sin restricciones» para que escuche «MIIA» con la "
                     "pantalla apagada.", theme.OK if ok else theme.WARN)
    bat_refresh()
    dlg.add(bat)
    dlg.add(button("Ajustes de batería de MIIA", lambda: (eng.bridge.open_battery_settings(), None)[1]))
    dlg.add(small("En Samsung: Ajustes > Aplicaciones > MIIA > Batería > Sin restricciones; y en Cuidado del "
                  "dispositivo > Batería > Límites de uso en segundo plano, quita a MIIA de «aplicaciones en suspensión»."))

    dlg.add(title("General"))
    switch_row, switch_sw = toggle("Mostrar pantalla al cambiar de cerebro", bool(cfg.get("show_switch_screen")))
    dlg.add(switch_row)
    tokens_e = field("Tokens máximos por respuesta", text=str(cfg.get("max_tokens")))
    runs_e = field("Tareas automáticas por día", text=str(cfg.get("auto_runs_per_day")))
    sync_e = field("Revisar la nube cada (min)", text=str(cfg.get("sync_minutes")))
    dlg.add(hrow(rowlabel("Tokens por respuesta:", size_hint_x=0.6), tokens_e))
    dlg.add(hrow(rowlabel("Tareas auto. por día:", size_hint_x=0.6), runs_e))
    dlg.add(hrow(rowlabel("Revisar nube (min):", size_hint_x=0.6), sync_e))
    msg = WLabel("", size=13, color=theme.ERR)
    dlg.add(msg)

    def save_all(close=True):
        try:
            tokens, runs, mins = int(tokens_e.text), int(runs_e.text), int(sync_e.text)
            spec_max = max(0, int(spec_e.text or 0))
        except ValueError:
            msg.set_text("Los valores numéricos deben ser números enteros.", theme.ERR)
            return False
        cfg.update(voice_enabled=bool(voice_sw.active), voice=voice_sp.text, voice_rate=rate_sp.text,
                   voice_native_fallback=bool(native_sw.active), voice_lang=lang_sp.text,
                   wake_offline=bool(offline_sw.active), conversation_mode=bool(conv_sw.active),
                   mute_beeps=bool(beeps_sw.active), mute_music=bool(music_sw.active),
                   speculate=bool(spec_sw.active), spec_max_per_day=spec_max,
                   max_tokens=max(50, min(tokens, 8000)), auto_runs_per_day=max(0, runs),
                   sync_minutes=max(1, mins), show_switch_screen=bool(switch_sw.active))
        if not voice_sw.active:
            eng.speaker.stop()
        if close:
            dlg.close()
        return True

    def test_voice():
        if not save_all(close=False):
            return
        msg.set_text("Probando la voz...", theme.INFO)
        eng.speaker.stop()
        eng.speaker.say("Hola, soy MIIA. Así sueno ahora.")

        def work():
            eng.speaker.wait_idle(20)
            err = eng.speaker.edge.last_error
            app.ui(lambda: msg.set_text("Listo." if not err else
                                        "Edge no respondió (" + err + "). Usé la voz de Android.",
                                        theme.OK if not err else theme.WARN))
        threading.Thread(target=work, daemon=True).start()

    def refresh_edge():
        msg.set_text("Buscando constantes nuevas de Edge...", theme.INFO)

        def work():
            changed = eng.speaker.edge.refresh_constants(force=True)
            err = eng.speaker.edge.last_error
            app.ui(lambda: msg.set_text("Actualizadas." if changed else
                                        ("No pude consultar: " + err if err else "Ya estaban al día."),
                                        theme.OK if changed or not err else theme.WARN))
        threading.Thread(target=work, daemon=True).start()

    dlg.add(button("Guardar", save_all, "primary"))
    dlg.add(button("Probar la voz", test_voice))
    dlg.add(button("Actualizar claves de Edge (si Elvira no suena)", refresh_edge, "neutral"))
    dlg.open()


# ====================================================================== ENSEÑAR
def teach(app):
    def done(text):
        if app.engine.memory.add_lesson(text):
            app.note(f"Lección guardada: {text}")
        else:
            app.note("Eso ya lo tenía anotado.")
    ask_text("Enseñar a MIIA", "Dime qué debo recordar o hacer distinto (una frase)", done, multiline=True)


# ====================================================================== CAMBIO DE CEREBRO
class SwitchOverlay(ModalView):
    REASONS = {
        "agotado": "«{a}» se quedó sin cuota por hoy.",
        "error": "«{a}» no respondió.",
        "renovado": "Tu cuota se renovó: vuelvo a mi cerebro principal.",
    }

    def __init__(self):
        super().__init__(size_hint=(0.88, None), height=dp(220), auto_dismiss=False, background="",
                         background_color=(0, 0, 0, 0.6))
        self.visible = False
        box = Panel(bg="#0b1620", radius=14, orientation="vertical", padding=dp(14), spacing=dp(6))
        self.title_lbl = WLabel("Cambiando de cerebro", size=17, color="#66d9ff", bold=True, halign="center")
        self.route_lbl = WLabel("", size=14, halign="center")
        self.step_lbl = WLabel("", size=12, color="#8fb8cc", halign="center")
        self.bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(8))
        for w in (self.title_lbl, self.route_lbl, self.step_lbl, self.bar):
            box.add_widget(w)
        self.add_widget(box)
        self._ev = None

    def show(self, from_name, to_name, reason):
        why = self.REASONS.get(reason, "").format(a=from_name)
        self.route_lbl.set_text((why + "\n" if why else "") + f"{from_name}  ->  {to_name}")
        self.step_lbl.set_text("Guardando la conversación y la memoria…")
        if not self.visible:
            self.open()
            self._ev = Clock.schedule_interval(self._anim, 0.05)
        self.visible = True

    def _anim(self, dt):
        self.bar.value = (self.bar.value + 4) % 100

    def step(self, text):
        self.step_lbl.set_text(text)

    def hide(self):
        if not self.visible:
            return
        self.visible = False
        if self._ev:
            self._ev.cancel()
            self._ev = None
        self.dismiss()
