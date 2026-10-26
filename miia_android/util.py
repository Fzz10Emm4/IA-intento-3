"""Utilidades comunes. Todo lo de Android se importa de forma perezosa para poder probar la lógica en un PC."""

import os
import re
import sys
import traceback
import unicodedata

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ


def log(*args):
    try:
        print("[MIIA]", *args, flush=True)
    except Exception:
        pass


def log_exc(where=""):
    log(where, traceback.format_exc())


def norm(text) -> str:
    """Minúsculas, sin tildes ni signos: sirve para comparar lo que dice el usuario."""
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def setup_ssl():
    """Android no trae certificados que Python encuentre solo: se usan los de certifi."""
    try:
        import certifi
        ca = certifi.where()
        os.environ["SSL_CERT_FILE"] = ca
        os.environ["REQUESTS_CA_BUNDLE"] = ca
        return ca
    except Exception:
        log_exc("setup_ssl")
        return None


# ---------------------------------------------------------------- Android (pyjnius)
def autoclass(name):
    from jnius import autoclass as _ac
    return _ac(name)


def activity():
    return autoclass("org.kivy.android.PythonActivity").mActivity


def api_level() -> int:
    if not IS_ANDROID:
        return 0
    try:
        return int(autoclass("android.os.Build$VERSION").SDK_INT)
    except Exception:
        return 0


def has_audio_permission() -> bool:
    if not IS_ANDROID:
        return True
    try:
        from android.permissions import check_permission, Permission
        return bool(check_permission(Permission.RECORD_AUDIO))
    except Exception:
        log_exc("has_audio_permission")
        return False


def request_audio_permissions(callback):
    """Pide micrófono (y notificaciones en Android 13+). callback(bool) con True si el micrófono quedó concedido."""
    if not IS_ANDROID:
        callback(True)
        return
    try:
        from android.permissions import request_permissions, check_permission, Permission
        if check_permission(Permission.RECORD_AUDIO):
            callback(True)
            return
        perms = [Permission.RECORD_AUDIO]
        if api_level() >= 33:
            perms.append("android.permission.POST_NOTIFICATIONS")

        def done(permissions, grants):
            try:
                callback(bool(grants) and bool(grants[0]))
            except Exception:
                log_exc("permission callback")
        request_permissions(perms, done)
    except Exception:
        log_exc("request_audio_permissions")
        callback(False)


def move_task_to_back():
    """Manda la app al fondo SIN cerrarla (así la escucha de «MIIA» sigue viva)."""
    if not IS_ANDROID:
        return False
    try:
        activity().moveTaskToBack(True)
        return True
    except Exception:
        log_exc("move_task_to_back")
        return False


def desktop_data_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), ".miia_android")
    os.makedirs(d, exist_ok=True)
    return d


def app_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_path(*parts) -> str:
    return os.path.join(app_dir(), "assets", *parts)


if __name__ == "__main__":
    print(norm("¡Oye, Mía! ¿Qué tal?"), file=sys.stdout)
