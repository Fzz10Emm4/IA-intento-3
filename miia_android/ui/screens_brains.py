"""Pantallas de Cerebros (lista, formulario y selector de modelos)."""

import os
import threading
import time

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.progressbar import ProgressBar

import miia_core as core

from . import theme
from .kit import (Dialog, Panel, WLabel, ask_yes_no, button, field, hrow, rowlabel, small, spacer, spinner,
                  title, toggle)


def _state_color(state):
    return {"listo": theme.OK, "agotado": theme.WARN, "pausa": theme.WARN}.get(state, theme.ERR)


def when_text(r):
    if r["state"] in ("agotado", "pausa") and r["until"]:
        return f"vuelve a las {core.fmt_clock(r['until'])} (en {core.fmt_remaining(r['until'] - time.time())})"
    if r["reset_at"] and r["state"] == "listo":
        return f"se renueva a las {core.fmt_clock(r['reset_at'])}"
    return ""


def open_model_picker(app, base_url, key_fn, target):
    """Busca modelos del proveedor y vuelca el elegido en el campo `target`."""
    eng = app.engine
    base = (base_url or "").strip()
    if not base:
        app.note("Primero indica la URL base del proveedor.")
        return
    dlg = Dialog("Elegir modelo")
    is_or = "openrouter.ai" in base
    state = {"free": is_or, "tools": True}
    search = field("Buscar: llama, gemini, deepseek, qwen...")
    dlg.add(search)
    free_row, free_sw = toggle("Solo gratuitos", state["free"], lambda v: (state.update(free=v), render()))
    tools_row, tools_sw = toggle("Solo con herramientas", state["tools"], lambda v: (state.update(tools=v), render()))
    dlg.add(free_row)
    dlg.add(tools_row)
    info = small("")
    dlg.add(info)
    lst = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
    lst.bind(minimum_height=lst.setter("height"))
    dlg.add(lst)

    def render(*_):
        lst.clear_widgets()
        items = eng.catalog.search(base, search.text, state["free"], state["tools"], 40)
        if not items:
            lst.add_widget(WLabel("Sin resultados. Toca «Actualizar lista» o quita algún filtro.", color=theme.TEXT_DIM))
        for m in items:
            tag = "GRATIS" if m.get("free") else ("de pago" if m.get("free") is False else "")
            ctx = f" · {m['ctx'] // 1000}k contexto" if m.get("ctx") else ""
            tl = " · herramientas" if m.get("tools") else ""

            def choose(mid=m["id"]):
                target.text = mid
                dlg.close()
            lst.add_widget(button(f"{m['name']}\n{m['id']} · {tag}{ctx}{tl}", choose, "neutral", height=58, size=13))
        n = len(eng.catalog.models(base))
        info.set_text((f"{n} modelos en la lista local." if n else
                       "Lista vacía: toca «Actualizar lista» (necesita internet y, en algunos proveedores, la API key).")
                      + " Mostrando hasta 40.")

    def refresh():
        info.set_text("Descargando lista de modelos...")
        key = key_fn()

        def work():
            try:
                eng.catalog.refresh(eng.client_for(base, key), base)
                app.ui(render)
            except Exception as e:
                msg = eng.brain.friendly_error(e)
                app.ui(lambda: info.set_text("Error: " + msg, theme.ERR))
        threading.Thread(target=work, daemon=True).start()

    search.bind(text=lambda *_: render())
    dlg.add(button("Actualizar lista", refresh, "secondary"))
    render()
    dlg.open()
    if eng.catalog.stale(base):
        refresh()


def open_brains(app):
    eng = app.engine
    dlg = Dialog("Cerebros")
    ui = {"sig": None, "countdowns": []}
    form = {"editing": None, "quota_group": ""}

    dlg.add(small("El orden es la prioridad: MIIA usa el primero que tenga cuota y, cuando se agota, guarda la "
                  "charla y la memoria y sigue con el siguiente. Las cuotas se renuevan solas cada día."))
    list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
    list_box.bind(minimum_height=list_box.setter("height"))
    dlg.add(list_box)

    # ---------- lista ----------
    def refresh_list(force=False):
        rows = eng.pool.status()
        sig = tuple((r["id"], r["state"], r["used"], r["active"], r["enabled"], r["model"], r["name"]) for r in rows)
        if sig == ui["sig"] and not force:
            for lbl, r in ui["countdowns"]:
                lbl.text = when_text(r)
            return
        ui["sig"] = sig
        ui["countdowns"] = []
        list_box.clear_widgets()
        if not rows:
            list_box.add_widget(WLabel("Aún no hay cerebros. Añade uno abajo.", color=theme.TEXT_DIM))
        for r in rows:
            card = Panel(bg=theme.SURFACE, orientation="vertical", size_hint_y=None, padding=dp(8), spacing=dp(4))
            star = "[principal] " if r["active"] else ""
            card.add_widget(WLabel(f"{star}{r['name']} · {eng.short_model(r['model'], 30)}", bold=True))
            card.add_widget(WLabel(r["state_text"], size=13, color=_state_color(r["state"])))
            if r["limit"]:
                bar = ProgressBar(max=max(1, r["limit"]), value=min(r["used"], r["limit"]), size_hint_y=None,
                                  height=dp(10))
                card.add_widget(bar)
                card.add_widget(small(f"{r['used']}/{r['limit']} hoy"))
            else:
                card.add_widget(small(f"{r['used']} peticiones hoy · sin tope local"))
            lbl = small(when_text(r), theme.INFO)
            card.add_widget(lbl)
            ui["countdowns"].append((lbl, r))
            if r["reason"] and r["state"] in ("agotado", "pausa", "key_mala"):
                card.add_widget(small(str(r["reason"])[:140], theme.TEXT_FAINT))

            def rm(bid=r["id"], name=r["name"]):
                def ans(yes):
                    if yes:
                        eng.registry.remove(bid)
                        eng.secrets.drop_brain(bid)
                        refresh_list(True)
                        app.refresh_brain_label()
                ask_yes_no("Quitar cerebro", f"¿Quitar «{name}» y su API key guardada?", ans, "Quitar", "Cancelar")

            def mv(d, bid=r["id"]):
                eng.registry.move(bid, d)
                refresh_list(True)

            def tog(v, bid=r["id"]):
                eng.registry.update(bid, enabled=bool(v))
                refresh_list(True)
                app.refresh_brain_label()

            en_row, _sw = toggle("Activado", r["enabled"], tog, height=36)
            card.add_widget(en_row)
            card.add_widget(hrow(button("Subir", lambda f=mv: f(-1), "neutral", height=38, size=13),
                                 button("Bajar", lambda f=mv: f(1), "neutral", height=38, size=13),
                                 button("Editar", lambda bid=r["id"]: load_form(bid), "secondary", height=38, size=13),
                                 button("Quitar", rm, "danger", height=38, size=13), height=38, spacing=6))
            card.bind(minimum_height=card.setter("height"))
            list_box.add_widget(card)

    tick_ev = Clock.schedule_interval(lambda dt: refresh_list(), 1.0)
    dlg.on_close = tick_ev.cancel
    dlg.bind(on_dismiss=lambda *_: tick_ev.cancel())
    app.brains_refresh = lambda: refresh_list(True)

    # ---------- formulario ----------
    form_title = title("Añadir cerebro")
    dlg.add(spacer(6))
    dlg.add(form_title)
    presets = list(core.PROVIDER_PRESETS.keys())
    preset_sp = spinner(presets, "OpenRouter (gratis)")
    name_e = field("Nombre (ej. Groq rápido)")
    url_e = field("URL base (https://.../v1)")
    model_e = field("Modelo (usa «Elegir modelo»)")
    key_e = field("API key de este proveedor (vacío = dejar la guardada)", password=True)
    limit_e = field("Tope diario", text="0")
    tz_e = field("Zona (ej. UTC)", text="UTC")
    hour_e = field("Hora", text="0")
    env_e = field("Secreto en GitHub (nube)")
    chat_only_row, chat_only_sw = toggle("Solo chat (no gastarlo en tareas)", False)
    note_lbl = small("", theme.INFO)
    msg = WLabel("", size=13, color=theme.ERR)

    def apply_preset(name):
        p = core.PROVIDER_PRESETS.get(name)
        if not p:
            return
        if not form["editing"] and not name_e.text.strip():
            name_e.text = name.split(" (")[0]
        url_e.text = p["base_url"]
        model_e.text = p["model"]
        limit_e.text = str(p["daily_requests"])
        tz_e.text = p["reset_tz"]
        hour_e.text = str(p["reset_hour"])
        env_e.text = p["key_env"]
        form["quota_group"] = p["quota_group"]
        hint = f"Key gratis en: {p['key_url']}\n" if p.get("key_url") else ""
        note_lbl.set_text(hint + p["note"], theme.INFO)

    preset_sp.bind(text=lambda _w, v: apply_preset(v))
    dlg.add(hrow(rowlabel("Proveedor:", size_hint_x=0.35), preset_sp, height=44))
    for w in (name_e, url_e):
        dlg.add(w)
    dlg.add(model_e)
    dlg.add(button("Elegir modelo...", lambda: open_model_picker(app, url_e.text, current_key, model_e)))
    dlg.add(key_e)
    dlg.add(small("Tope diario (0 = sin tope) · zona horaria de renovación · hora de renovación"))
    dlg.add(hrow(limit_e, tz_e, hour_e))
    dlg.add(env_e)
    dlg.add(chat_only_row)
    dlg.add(note_lbl)
    dlg.add(msg)

    def current_key():
        k = key_e.text.strip()
        if k:
            return k
        if form["editing"]:
            b = eng.registry.get(form["editing"])
            if b:
                return eng.secrets.brain_key(b)
        env = env_e.text.strip()
        return os.environ.get(env, "") if env else ""

    save_btn = button("Añadir cerebro", None, "primary")
    cancel_btn = button("Cancelar edición", None, "neutral")

    def reset_form():
        form["editing"] = None
        form_title.text = "Añadir cerebro"
        name_e.text = ""
        key_e.text = ""
        chat_only_sw.active = False
        preset_sp.text = "OpenRouter (gratis)"
        apply_preset("OpenRouter (gratis)")
        save_btn.text = "Añadir cerebro"
        cancel_btn.disabled = True

    def load_form(bid):
        b = eng.registry.get(bid)
        if not b:
            return
        form["editing"] = bid
        form["quota_group"] = b.get("quota_group", "")
        form_title.text = f"Editando: {b['name']}"
        preset_sp.text = b["preset"] if b["preset"] in core.PROVIDER_PRESETS else "Personalizado"
        # al cambiar el spinner se aplicó el preset; se vuelven a poner los datos reales del cerebro
        name_e.text, url_e.text, model_e.text = b["name"], b["base_url"], b["model"]
        limit_e.text, tz_e.text, hour_e.text = str(b["daily_requests"]), b["reset_tz"], str(b["reset_hour"])
        env_e.text = b["key_env"]
        form["quota_group"] = b.get("quota_group", "")
        key_e.text = ""
        chat_only_sw.active = bool(b["chat_only"])
        note_lbl.set_text("API key guardada: " + ("sí" if eng.secrets.has_stored_key(bid) else "no (pégala arriba)"),
                          theme.INFO)
        save_btn.text = "Guardar cambios"
        cancel_btn.disabled = False

    def save():
        name, url, model = name_e.text.strip(), url_e.text.strip(), model_e.text.strip()
        if not url:
            msg.set_text("Falta la URL base del proveedor.", theme.ERR)
            return
        try:
            limit, hour = int(limit_e.text or 0), int(hour_e.text or 0)
        except ValueError:
            msg.set_text("El tope diario y la hora deben ser números.", theme.ERR)
            return
        fields = dict(name=name or "Cerebro", preset=preset_sp.text, base_url=url, model=model,
                      key_env=env_e.text.strip(), daily_requests=limit, reset_tz=tz_e.text.strip() or "UTC",
                      reset_hour=hour, quota_group=form["quota_group"], chat_only=bool(chat_only_sw.active))
        if form["editing"]:
            bid = form["editing"]
            eng.registry.update(bid, **fields)
        else:
            bid = eng.registry.add(**fields)["id"]
        key = key_e.text.strip()
        if key:
            err = eng.secrets.set_brain_key(bid, key)
            if err:
                msg.set_text(err, theme.ERR)
                return
        msg.set_text("")
        reset_form()
        refresh_list(True)
        app.refresh_brain_label()

    def test():
        url = url_e.text.strip()
        key = current_key()
        if not url:
            msg.set_text("Falta la URL base.", theme.ERR)
            return
        msg.set_text("Probando conexión...", theme.INFO)

        def work():
            ok, text = eng.brain.ping(url, key)
            app.ui(lambda: msg.set_text(("OK: " if ok else "Error: ") + text, theme.OK if ok else theme.ERR))
        threading.Thread(target=work, daemon=True).start()

    save_btn.bind(on_release=lambda *_: save())
    cancel_btn.bind(on_release=lambda *_: reset_form())
    dlg.add(save_btn)
    dlg.add(button("Probar conexión", test, "secondary"))
    dlg.add(cancel_btn)
    dlg.add(small("Las API keys se guardan solo en este teléfono (almacenamiento privado de la app) y nunca se suben "
                  "a GitHub.", theme.TEXT_FAINT))

    apply_preset("OpenRouter (gratis)")
    cancel_btn.disabled = True
    refresh_list(True)
    dlg.open()
