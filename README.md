# Anki English

Compilador local de tarjetas de inglés: **CardSpec JSON → validación → cloze → audio opcional → Anki**.

Incluye CLI, contrato Pydantic/JSON Schema, deduplicación por UID, AnkiConnect y Kokoro
como extra opcional. El usuario confirmó la importación y reproducción de una tarjeta con
audio en su Mac con Python 3.12.15 el 12 de octubre de 2026. Las pruebas automatizadas usan
un servidor HTTP simulado; la nueva presentación Aura requiere revisión final en Anki.

## Diseño Aura editorial

Frases en Georgia, fondo crema, acento azul para recuperación y verde suave para el ejemplo.
El anverso muestra la frase con hueco, una pista de significado en español desplegable y la
instrucción de completar y decir la frase en voz alta. La pista empieza cerrada: pulsa
«Show meaning hint» para abrirla o vuelve a pulsar para cerrarla; también funciona
con teclado. Reutiliza `MeaningES`: funciona en las
notas existentes sin migrar campos ni reimportar contenido.
El reverso separa frase, audio, expresión, significado, cómo usarlo y otro contexto.
Las etiquetas, instrucciones y la guía de calificación están en inglés sencillo; la pista,
el significado y las explicaciones de uso conservan su contenido en español. Los botones
nativos de Anki siguen el idioma de la aplicación. Una guía de calificación desplegable
queda disponible sin ocupar el repaso habitual.
Los bloques opcionales se ocultan si el campo está vacío. Audio solo en el reverso.
Incluye modo oscuro (`nightMode`/`night_mode`), tamaños móviles, controles de 44 px y foco
visible. No usa JavaScript, fuentes remotas ni imágenes externas.

### Cómo estudiar y redactar las tarjetas

1. Aprende primero qué significa la expresión y escucha su pronunciación. La tarjeta sirve
   para practicar algo que ya has entendido.
2. Lee la frase e intenta recuperar la expresión; abre la pista si necesitas precisar el
   significado. Di la frase completa antes de
   revelar. Si no puedes hablar en ese momento, responde mentalmente. No te quedes bloqueado:
   el manual de Anki sugiere revelar tras unos 10 segundos sin respuesta.
3. Revela, compara y escucha el audio si está disponible. Repite para practicar pronunciación;
   califica el recuerdo de la expresión, no tu acento ni si te resultó familiar al verla.
4. Usa **Otra vez** si fallaste; **Difícil** si acertaste con mucho esfuerzo; **Bien** si
   acertaste con esfuerzo normal; **Fácil** si acertaste sin esfuerzo. No uses Difícil para un olvido.

Para redactar un lote, usa `examples/cards.json` como contrato y sigue estos criterios:

- Una expresión útil por tarjeta; el resto de la frase debe ser comprensible para tu nivel.
- `meaning_es`: una glosa breve y contextual en español. Puede desplegarse **antes** de responder;
  no incluyas la expresión inglesa ni listas de traducciones ajenas a ese contexto.
- Oculta la expresión completa que quieres practicar y evita repetirla en la parte visible.
- `pattern`: una regla breve y aplicable; explica en español y conserva las formas inglesas.
  `example`: otra frase natural y sencilla que muestre un uso diferente. Usa `null` si no aportan.
- Si varias respuestas encajan, precisa la pista o reformula la frase. Una alternativa válida
  no demuestra un fallo de memoria. Edita la nota en Anki si hace falta: reimportarla la omite.
- Al terminar, elige unas pocas expresiones e intenta usarlas en otra situación; comprueba
  tus frases con un profesor o compañero competente. Es práctica adicional, no una tarea
  obligatoria en cada repaso ni parte de su calificación.

El respaldo empírico corresponde a recuperar y comprobar vocabulario, no a una superioridad
demostrada de esta plantilla. La pista y la organización visual son decisiones de diseño.
Las tarjetas complementan la escucha y la conversación; no garantizan por sí solas fluidez.
Referencias: [Karpicke y Roediger, 2008](https://doi.org/10.1126/science.1152408),
[Kang, Gollan y Pashler, 2013](https://pubmed.ncbi.nlm.nih.gov/23681928/),
[calificación en Anki](https://docs.ankiweb.net/studying.html).

### Aplicar el diseño a las tarjetas existentes

Con Anki abierto, desde tu clon y con el entorno activado:

```bash
git pull --ff-only
python -m pip install -e .
anki-en init --update-style
```

El flag autoriza reemplazar el anverso, reverso y CSS del tipo de nota configurado. Se aplica
a todas sus tarjetas, conservando campos, audio, IDs, nombre de plantilla y repasos.
Antes de cambiar nada, guarda una copia JSON del diseño previo en
`~/.local/share/anki-english/backups/` y muestra su ruta. Si hay un fallo entre las dos
operaciones de AnkiConnect, repite el comando para completar la actualización.
Ejecutar `init` sin el flag sigue sin sobrescribir un diseño diferente.
Para volver manualmente al diseño previo, copia `Front`, `Back` y `css` del JSON de respaldo
en los apartados correspondientes del editor de tarjetas de Anki.

## Instalación

Recomendado: **Python 3.12**, especialmente para audio. El núcleo acepta 3.11+, pero Kokoro
no admite Python 3.14 en la versión utilizada. Requiere Anki Desktop con
[AnkiConnect](https://ankiweb.net/shared/info/2055492159).
Anki debe permanecer abierto al ejecutar `init` o publicar. `check` y `--dry-run` funcionan sin Anki.

```bash
cd anki-english
brew install python@3.12
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
anki-en check examples/cards.json
anki-en init
anki-en add examples/cards.json --no-audio
```

Para usar el portapapeles en macOS, copia JSON puro (sin delimitadores Markdown):

```bash
anki-en paste --no-audio
```

`--no-audio` es explícito: no se publican tarjetas sin audio como consecuencia silenciosa
de un fallo de TTS. El modo por defecto intenta generar audio con Kokoro.

## Audio local opcional

```bash
brew install ffmpeg espeak-ng
python -m pip install -e '.[audio]'
anki-en add examples/cards.json
# Si ya importaste los ejemplos sin audio, usa un lote NUEVO:
anki-en paste
```

La primera síntesis puede descargar modelos de Kokoro y dependencias lingüísticas y tardar
considerablemente más. No se ha medido el rendimiento en tu Mac. Tras descargar todo lo
necesario, la síntesis se ejecuta localmente. El texto no se envía a una API de generación.
No se necesita una clave de OpenAI.

La caché incluye texto exacto, modelo, versión de Kokoro, voz, dialecto, velocidad y parámetros
MP3. Escribe primero en un temporal y mueve el archivo terminado a la caché. El campo `Audio`
se añade únicamente al reverso para no revelar la respuesta antes del intento.

Si importas primero con `--no-audio`, volver a importar no añadirá sonido a esas notas:
el mismo UID se omite. La actualización de notas existentes es trabajo futuro.

## Comandos

| Comando | Comportamiento |
| --- | --- |
| `anki-en init` | Crea/verifica mazo y modelo Cloze; no reemplaza un modelo incompatible. |
| `anki-en init --update-style` | Respalda y actualiza anverso/reverso/CSS de las tarjetas existentes. |
| `anki-en check cards.json` | Valida, avisa y previsualiza sin red ni TTS. |
| `anki-en add cards.json --dry-run` | Misma comprobación offline. |
| `anki-en add cards.json` | Comprueba Anki/UID, pide confirmación, genera audio y publica. |
| `anki-en paste` | Mismo flujo leyendo `pbpaste` en macOS. |

`add` y `paste` aceptan `--yes` para automatización y `--no-audio` para una importación
intencionadamente sin sonido. Una sesión no interactiva exige `--yes`. Salidas: `0` éxito,
`1` error, `2` error de argumentos y `130` interrupción.

Configuración opcional y explícita:

```bash
cp config.example.toml config.toml
anki-en --config config.toml init
```

Los valores por defecto crean `English::02 Sentences & Chunks` y `English – Sentence & Chunk`.
Si AnkiConnect usa API key, define `ANKI_CONNECT_API_KEY` en tu entorno; no la añadas al repo.
V1 solo permite un endpoint loopback (`127.0.0.1`, `localhost` o `::1`), sin proxy HTTP.

## Contrato y decisiones

- `examples/cards.json` es un lote válido completo. Todos los campos están presentes;
  `pattern`, `example`, `tts_text`, `source.label` y `source.url` permiten `null`.
- `answer` es el texto exacto oculto, `target` su forma canónica. `answer_occurrence` cuenta
  desde 1, distingue mayúsculas y busca coincidencias literales no solapadas en límites de palabra.
- El compilador crea una sola omisión `c1`. Rechaza sintaxis Anki aportada por el autor,
  propiedades desconocidas, texto vacío, controles, ocurrencias inexistentes y tags reservados.
- HTML se muestra como texto escapado. URLs de fuente solo HTTP(S), sin credenciales.
- UID = SHA-256 sobre versión de identidad, tipo, frase/respuesta normalizadas y ocurrencia.
  Normalización: Unicode NFC, espacios y case-folding. Cambiar glosa o tags no crea otra nota.
  Una nota existente se omite; no se actualiza ni se pierde su historial.
- `UID` es el primer campo para apoyar también la comprobación nativa de duplicados.
- Los tags de tipo, origen e isla los calcula el programa. Los tags del autor admiten
  minúsculas ASCII, números, guiones, guiones bajos y una jerarquía `::`.
- Los avisos pedagógicos son **heurísticas**, no una validación científica ni una garantía
  de que una frase sea correcta, adecuada para el nivel o tenga un único objetivo conceptual.
  Incluyen coincidencias de la respuesta/expresión en la pista y respuestas repetidas en la
  frase que pueden revelar la solución. Son avisos, no bloqueos: revisa los posibles falsos positivos.
- `schemas/card-spec-v1.schema.json` es el contrato exportado para autores/herramientas.
  Se genera desde Pydantic para evitar dos definiciones mantenidas a mano. Las pruebas detectan
  divergencias. Las relaciones entre campos, el markup y las reglas semánticas se validan
  adicionalmente en Python: el JSON Schema por sí solo no basta.

## Publicación y fallos

Se valida todo el lote antes de contactar con Anki. Se omiten UID repetidos dentro del lote
y en la colección. Después de confirmar se vuelve a comprobar cada UID antes de escribir.
La publicación es secuencial con `addNote`: permite informar el ID de cada éxito y detenerse
en el primer fallo, sin depender de diferencias de comportamiento de `addNotes` entre versiones.

El lote **no es transaccional**. Las notas ya creadas permanecen. Si falla o se interrumpe,
ejecuta el mismo lote de nuevo: los UID existentes se omiten. Tras un timeout de escritura,
el resultado de esa nota puede ser desconocido hasta volver a consultarlo. Si el audio se
guardó y luego falló `addNote`, puede quedar un medio sin usar; no se borra automáticamente.
No hay operaciones de borrado, modificación del repaso, sincronización ni actualización masiva.

## Desarrollo

```bash
python scripts/export_schema.py
python -m unittest discover -s tests -v
```

Las pruebas cubren contrato, cloze, XSS/markup, UID/ocurrencias, inicialización idempotente,
rechazo de modelos incompatibles, HTTP/API key, CLI offline, confirmación, duplicados,
publicación parcial y reintentos, y actualización de diseño con respaldo, recuperación tras
fallo y rechazo de modelos incompatibles. No sustituyen una prueba real de Anki Desktop/AnkiMobile.

Estructura:

- `src/anki_english/spec.py`: tipos y validación semántica.
- `compiler.py`: campos, cloze, identidad y avisos, sin I/O.
- `anki.py`: adaptador AnkiConnect y protocolo `AnkiGateway`.
- `audio.py`: protocolo `TTSProvider`, Kokoro y caché MP3.
- `service.py`: publicación con resultados por tarjeta.
- `cli.py`: entrada JSON/portapapeles, preview y confirmación.
- `templates/`: front/back/CSS empaquetados con la instalación.

Próximo hito: validar el nuevo diseño Aura y el audio en AnkiMobile/AnkiDroid.
Después: avisos de similitud y actualización explícita del contenido de notas.
MCP, API de IA, GUI y otros motores de voz quedan fuera de esta primera entrega.

Repositorio: [altguerrero/anki-english](https://github.com/altguerrero/anki-english).

Referencias técnicas: [AnkiConnect API](https://git.sr.ht/~foosoft/anki-connect),
[manual de cloze de Anki](https://docs.ankiweb.net/templates/cloze.html),
[Kokoro](https://github.com/hexgrad/kokoro).
