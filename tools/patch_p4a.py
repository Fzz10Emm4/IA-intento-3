#!/usr/bin/env python3
"""Prepara una copia local de python-for-android para MIIA (la usa el workflow de GitHub Actions).

Hace dos cosas y, si alguna no se puede hacer, FALLA con un mensaje claro (para no producir un APK sin micrófono
en segundo plano sin darnos cuenta):
  1) copia el código Java de MIIA (puente de voz + servicio) dentro del proyecto Android que genera p4a;
  2) declara en el AndroidManifest el servicio MiiaListenService con foregroundServiceType="microphone"
     (obligatorio desde Android 14 para un servicio en primer plano que usa el micrófono).

Uso: python tools/patch_p4a.py <carpeta_de_python-for-android> <carpeta_java_src>
"""

import os
import re
import shutil
import sys

SERVICE_XML = """
        <!-- MIIA: escucha de la palabra «MIIA» en segundo plano (mismo proceso que la app) -->
        <service android:name="org.miia.voice.MiiaListenService"
                 android:exported="false"
                 android:foregroundServiceType="microphone" />
"""
MARK = "org.miia.voice.MiiaListenService"


def patch_manifest(text: str) -> str:
    if MARK in text:
        return text
    if text.count("</application>") != 1:
        raise SystemExit("patch_p4a: la plantilla del manifiesto no tiene exactamente un </application>; "
                         "python-for-android cambió y hay que revisar este script.")
    return text.replace("</application>", SERVICE_XML + "    </application>")


def find_bootstraps(p4a_dir: str):
    base = os.path.join(p4a_dir, "pythonforandroid", "bootstraps")
    if not os.path.isdir(base):
        raise SystemExit(f"patch_p4a: no existe {base}")
    out = []
    for name in sorted(os.listdir(base)):
        tmpl = os.path.join(base, name, "build", "templates", "AndroidManifest.tmpl.xml")
        if os.path.isfile(tmpl):
            out.append((name, os.path.join(base, name, "build")))
    return out


def copy_java(src_root: str, build_dir: str) -> int:
    dst_root = os.path.join(build_dir, "src", "main", "java")
    n = 0
    for dirpath, _dirs, files in os.walk(src_root):
        for f in files:
            if not f.endswith(".java"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), src_root)
            dst = os.path.join(dst_root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(dirpath, f), dst)
            n += 1
    return n


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    p4a_dir, java_src = argv[1], argv[2]
    if not os.path.isdir(java_src):
        raise SystemExit(f"patch_p4a: no existe la carpeta de Java {java_src}")
    boots = find_bootstraps(p4a_dir)
    if not boots:
        raise SystemExit("patch_p4a: no encontré ninguna plantilla AndroidManifest.tmpl.xml en p4a")
    done = 0
    for name, build_dir in boots:
        tmpl = os.path.join(build_dir, "templates", "AndroidManifest.tmpl.xml")
        with open(tmpl, "r", encoding="utf-8") as f:
            text = f.read()
        new = patch_manifest(text)
        with open(tmpl, "w", encoding="utf-8") as f:
            f.write(new)
        n = copy_java(java_src, build_dir)
        if n < 2:
            raise SystemExit(f"patch_p4a: solo se copiaron {n} archivos Java (se esperaban al menos 2)")
        if not re.search(r'android:foregroundServiceType="microphone"', new):
            raise SystemExit("patch_p4a: el servicio no quedó declarado en el manifiesto")
        print(f"patch_p4a: bootstrap «{name}»: servicio declarado y {n} archivos Java copiados")
        done += 1
    print(f"patch_p4a: listo ({done} bootstrap(s))")


if __name__ == "__main__":
    main(sys.argv)
