"""Puente con Android (clase Java org.miia.voice.MiiaVoice) y un puente falso para probar la lógica en un PC."""

import collections

from .util import autoclass, activity, log_exc


class AndroidBridge:
    def __init__(self):
        self.V = autoclass("org.miia.voice.MiiaVoice")
        self.V.init(activity())

    def available(self) -> bool:
        try:
            return bool(self.V.recognitionAvailable())
        except Exception:
            log_exc("available")
            return False

    def poll(self):
        try:
            e = self.V.poll()
            return str(e) if e is not None else None
        except Exception:
            log_exc("poll")
            return None

    def listen(self, lang, offline=False, tight=False):
        self.V.listen(lang, bool(offline), bool(tight))

    def stop_listening(self):
        self.V.stopListening()

    def cancel(self):
        self.V.cancel()

    def set_mute(self, sys_on, music_on):
        self.V.setMute(bool(sys_on), bool(music_on))

    def start_service(self, title, text):
        self.V.startService(title, text)

    def stop_service(self):
        self.V.stopService()

    def service_running(self) -> bool:
        return bool(self.V.serviceRunning())

    def battery_ok(self) -> bool:
        return bool(self.V.ignoringBatteryOptimizations())

    def open_battery_settings(self):
        self.V.openBatterySettings()


class FakeBridge:
    """Mismo contrato, sin Android. `events` se llena a mano en las pruebas."""

    def __init__(self):
        self.events = collections.deque()
        self.calls = []
        self.service = False
        self.can_listen = True

    def available(self):
        return self.can_listen

    def poll(self):
        return self.events.popleft() if self.events else None

    def push(self, ev):
        self.events.append(ev)

    def listen(self, lang, offline=False, tight=False):
        self.calls.append(("listen", lang, offline, tight))

    def stop_listening(self):
        self.calls.append(("stop_listening",))

    def cancel(self):
        self.calls.append(("cancel",))

    def set_mute(self, sys_on, music_on):
        self.calls.append(("mute", sys_on, music_on))

    def start_service(self, title, text):
        self.service = True
        self.calls.append(("start_service", title))

    def stop_service(self):
        self.service = False
        self.calls.append(("stop_service",))

    def service_running(self):
        return self.service

    def battery_ok(self):
        return True

    def open_battery_settings(self):
        self.calls.append(("battery",))
