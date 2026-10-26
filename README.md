# MIIA para Android (v4.1.0)

MIIA con todas las funciones del PC (cerebros múltiples con traspaso de cuota, memoria y lecciones, plataformas,
tareas y entrenamiento, nube en GitHub) **menos las descargas** (quedan para una futura actualización), más:

- **Botón Hablar** y **palabra «MIIA»** en segundo plano (como «Oye Siri»): dices «MIIA…» y responde por voz.
- **Respuesta anticipada**: mientras hablas, MIIA ya va pensando la respuesta; si lo que terminas diciendo coincide,
  contesta casi al instante.
- Voz **Elvira** (Edge TTS, gratis, necesita internet) con respaldo a la voz de Android si Edge falla.
- Diseño oscuro con **azul oscuro** en lugar del rosa, esfera arriba, chat debajo y botones en el menú lateral.
- Ícono: el de los anillos azules.

No hay Fish Audio ni ElevenLabs en esta versión.

> **Importante:** este proyecto NO trae ninguna API key. Tampoco copies `miia_secrets.json` del PC. Las keys se pegan una
> vez dentro de la app (menú > Cerebros) y quedan en el almacenamiento privado del teléfono.

---

## 1. Compilar el APK con GitHub (no necesitas instalar nada)

1. En GitHub crea un repositorio **privado** (por ejemplo `miia`). Puede ser el mismo que luego uses como nube de MIIA.
2. Sube a ese repositorio **todo el contenido** de esta carpeta (en el navegador: *Add file > Upload files* y arrastra
   los archivos y carpetas). Asegúrate de que se suba la carpeta oculta `.github`.
   - Si no aparece `.github/workflows/build-apk.yml` en el repositorio: *Add file > Create new file*, escribe como
     nombre `.github/workflows/build-apk.yml`, pega el contenido de `workflow/build-apk.yml` y guarda.
3. Abre la pestaña **Actions**. Si GitHub pide activar los workflows, acéptalo.
4. Elige **Compilar APK de MIIA** > **Run workflow**. La primera vez tarda entre 30 y 60 minutos (después, menos).
5. Al terminar, entra en esa ejecución y baja el archivo **MIIA-apk** (un .zip con el `.apk` dentro).

Si el workflow falla, abre la ejecución, copia las últimas ~60 líneas del paso que salió en rojo y pásamelas para
corregirlo. Esta versión no se pudo compilar en el entorno donde se escribió (no tiene el SDK de Android), así que es
posible que haga falta algún ajuste en la primera compilación.

## 2. Instalar en el Galaxy A02s

1. Pasa el `.apk` al teléfono y ábrelo. Android te pedirá permitir «instalar apps de esta fuente».
2. Si Play Protect avisa de una app no verificada, elige *Instalar de todos modos* (es tu propia app).
3. Las próximas versiones se instalan **encima** sin perder datos (el APK usa siempre la misma firma, la de
   `signing/debug.keystore`). No desinstales la app para actualizar: se perdería la memoria local.

## 3. Primer arranque

1. **Cerebros**: menú > Cerebros. Elige un proveedor, pega su API key y toca *Añadir cerebro*. Usa keys **nuevas**
   (las que subiste antes al chat conviene regenerarlas).
2. **Hablar**: toca el botón *Hablar*; acepta el permiso de micrófono (y el de notificaciones).
3. **«MIIA» en segundo plano**: menú > *Escuchar «MIIA»*. Aparece una notificación fija «MIIA escuchando» (es
   obligatoria en Android mientras el micrófono está en uso). Para apagarlo: el mismo botón, o *Detener* en la notificación.
4. **Samsung (importante para escuchar con la pantalla apagada)**:
   - Ajustes > Aplicaciones > MIIA > Batería > **Sin restricciones** (o Ajustes dentro de MIIA > *Ajustes de batería*).
   - Cuidado del dispositivo > Batería > Límites de uso en segundo plano: quita MIIA de «apps en suspensión».
   - No deslices MIIA para cerrarla desde recientes; usa el botón atrás o *Segundo plano* del menú.
5. **Nube (opcional)**: menú > Nube (GitHub). Repositorio privado `usuario/repositorio`, token *fine-grained* con
   *Contents* y *Workflows* en lectura y escritura, *Guardar*, *Probar conexión*, *Instalar servidor*. Luego crea los
   secretos de tus proveedores en el repositorio (la pantalla te lista los nombres).

## 4. Cómo funciona la voz

- **Palabra «MIIA»**: el micrófono se escucha por tandas con el reconocimiento de voz de Google del teléfono. Es una
  aproximación: reconoce «MIIA», «oye MIIA», «hey MIIA» al **principio** de la frase. No es un detector dedicado como el
  de Siri, así que gasta algo más de batería y puede fallar en ambientes ruidosos. Sin internet solo funciona si
  descargaste el idioma sin conexión (Ajustes de Android > Google > Reconocimiento de voz) y activas *Preferir
  reconocimiento sin internet*.
- **Respuesta anticipada**: cuando haces una pausa a mitad de frase, MIIA lanza una respuesta con lo que lleva. Si lo que
  finalmente dices coincide, usa esa respuesta; si no, la descarta. **Solo usa cerebros sin tope diario** (no gasta tu
  cuota limitada), no ejecuta herramientas y tiene un tope diario configurable (60 por defecto).
- **Modo conversación**: tras responder sigue escuchando unos segundos para que no repitas «MIIA».
- **Pitidos del micrófono**: MIIA silencia notificaciones/sistema mientras escucha. Si en tu teléfono el pitido sale por
  *multimedia*, activa en Ajustes *Silenciar también multimedia* (apaga la música de otras apps mientras esperas «MIIA»).
- **Voz Elvira**: usa el servicio gratuito de Edge. Microsoft cambia a veces sus claves internas; si Elvira deja de
  sonar, ve a Ajustes > *Actualizar claves de Edge*. Mientras tanto MIIA habla con la voz de Android.

## 5. Contenido

| Ruta | Qué es |
|---|---|
| `main.py`, `miia_android/` | La app (interfaz Kivy, voz, respuesta anticipada, motor) |
| `miia_core.py` | El núcleo de MIIA (el mismo del PC; sin descargas ni voces de pago) |
| `java_src/` | Puente con el reconocimiento de voz de Android y el servicio de escucha en segundo plano |
| `tools/patch_p4a.py` | Declara el servicio de escucha en el manifiesto durante la compilación |
| `buildozer.spec` | Configuración de la compilación (API 34, ARM de 32 y 64 bits) |
| `.github/workflows/build-apk.yml` | Receta de GitHub Actions que compila el APK |
| `signing/debug.keystore` | Firma estable de tu APK (repositorio privado; no la compartas) |
| `tests/` | Pruebas de la lógica que no depende de Android |

## 6. Seguridad

- Ninguna API key ni memoria personal está en este proyecto. `.gitignore` evita subirlas por accidente.
- El repositorio debe ser **privado**: contiene la firma de tu app y, si activas la nube, tu memoria y charlas.
- Regenera las API keys que compartiste por chat antes de usar la app.
