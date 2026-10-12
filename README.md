# Anki English

Compilador local de tarjetas de inglés: **CardSpec JSON → validación → cloze → audio opcional → Anki**.

Primera versión implementada. Incluye CLI, contrato Pydantic/JSON Schema, plantillas,
deduplicación por UID y adaptador AnkiConnect. Kokoro está implementado como extra opcional;
su síntesis real y el renderizado/importación en Anki Desktop todavía requieren validación
en el equipo del usuario. Las pruebas usan un servidor HTTP de AnkiConnect simulado.

## Instalación

Requiere Python 3.11+ y Anki Desktop con [AnkiConnect](https://ankiweb.net/shared/info/2055492159).
Anki debe permanecer abierto al ejecutar `init` o publicar. `check` y `--dry-run` funcionan sin Anki.

```bash
cd anki-english
python3 -m venv .venv
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
# O, después de copiar un lote nuevo:
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
publicación parcial y reintentos. No sustituyen una prueba real de Anki Desktop/AnkiMobile.

Estructura:

- `src/anki_english/spec.py`: tipos y validación semántica.
- `compiler.py`: campos, cloze, identidad y avisos, sin I/O.
- `anki.py`: adaptador AnkiConnect y protocolo `AnkiGateway`.
- `audio.py`: protocolo `TTSProvider`, Kokoro y caché MP3.
- `service.py`: publicación con resultados por tarjeta.
- `cli.py`: entrada JSON/portapapeles, preview y confirmación.
- `templates/`: front/back/CSS empaquetados con la instalación.

Próximo hito: importar una tarjeta nueva con audio en el Mac, revisar ambas caras y reproducir
el sonido en Desktop y móvil. Después: avisos de similitud y actualización explícita de notas.
MCP, API de IA, GUI y otros motores de voz quedan fuera de esta primera entrega.

## Subir a GitHub

Este directorio ya es un repositorio Git en `main`. Cuando exista el remoto vacío:

```bash
git remote add origin <URL-DEL-REPOSITORIO>
git push -u origin main
```

Si tienes GitHub CLI autenticado, puedes crear el repo privado y subirlo en un paso:

```bash
gh repo create anki-english --private --source=. --remote=origin --push
```

Referencias técnicas: [AnkiConnect API](https://git.sr.ht/~foosoft/anki-connect),
[manual de cloze de Anki](https://docs.ankiweb.net/templates/cloze.html),
[Kokoro](https://github.com/hexgrad/kokoro).
