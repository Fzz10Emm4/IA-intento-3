[app]
title = MIIA
package.name = miia
package.domain = org.miia
source.dir = .
source.include_exts = py,png,json,txt
source.exclude_dirs = tests, tools, .github, signing, java_src, bin, .buildozer, p4a_src, __pycache__
source.exclude_patterns = *.keystore, miia_secrets.json, miia_*.json
version = 4.1.0

# websocket-client y certifi son Python puro; pyjnius y android dan acceso a las APIs de Android
requirements = python3,kivy==2.3.0,pyjnius,android,certifi,websocket-client

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
presplash.color = #0a0a0a
icon.adaptive_foreground.filename = %(source.dir)s/assets/icon_fg.png
icon.adaptive_background.filename = %(source.dir)s/assets/icon_bg.png

android.permissions = INTERNET, RECORD_AUDIO, FOREGROUND_SERVICE, FOREGROUND_SERVICE_MICROPHONE, POST_NOTIFICATIONS, WAKE_LOCK, MODIFY_AUDIO_SETTINGS, REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

android.api = 34
android.minapi = 24
android.ndk = 25b
# El Galaxy A02s suele traer Android de 32 bits: se compilan las dos arquitecturas
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.private_storage = True
android.debug_artifact = apk

# python-for-android se descarga y se parchea en el workflow (tools/patch_p4a.py) para declarar el servicio de escucha
p4a.source_dir = ./p4a_src

[buildozer]
log_level = 2
warn_on_root = 1
