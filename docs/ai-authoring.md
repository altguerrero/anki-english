# Instrucciones para la IA que prepara mis tarjetas

Usa estas instrucciones junto con `schemas/card-spec-v1.schema.json` y
`examples/mixed.json`. El programa importa JSON; la elección pedagógica ocurre en
esta conversación. No existe un clasificador de IA ejecutándose dentro del CLI.

## Elegir el tipo

- Si encuentro una expresión útil que quiero aprender, elige `sentence_chunk`:
  se publicará en **English::02 Sentences & Chunks**.
- Si en el material aparece un intento real mío, una corrección fundamentada y un
  error recurrente o relevante para algo que uso, elige `my_error`: se publicará en
  **English::03 My Errors**. Una frase enseñada por un profesor o un ejemplo hipotético
  no demuestran que yo haya cometido ese error.
- Decide por el origen de la tarjeta, no por su tema: una estructura gramatical
  también puede ir al 02 si simplemente la estoy aprendiendo.
- Respeta mi elección explícita de mazo cuando sea compatible con los datos. Si pido
  el 03 sin aportar mi intento y una corrección, pide lo que falta; no lo inventes ni
  cambies silenciosamente el destino. Si no hay elección explícita ni evidencia de
  error personal, usa el 02 solo cuando el contenido merezca una tarjeta.
- No generes ambos tipos para el mismo objetivo a menos que lo solicite expresamente.
- No hay cuota obligatoria por mazo. Un lote puede tener solo 02, solo 03 o ambos.
- Si no hay ninguna tarjeta útil, dilo: no fabriques contenido para llenar un lote.

## Comprobar la corrección

Antes de crear `my_error`, determina qué intentaba comunicar. La corrección debe
preservar ese significado y el contexto. No presentes una preferencia de estilo,
una variante regional válida o una afirmación incierta como un error.

La corrección puede proceder del feedback aportado o de una explicación lingüística
que puedas justificar. En `correction_source`, identifica honestamente quién dio ese
feedback (por ejemplo, la profesora o ChatGPT en esta conversación). No inventes
profesores, citas, fuentes, fechas ni verificaciones externas. Si no puedes resolver
una ambigüedad relevante, pregunta antes de emitir esa tarjeta.

## Redactar el contenido

- Una tarjeta evalúa un solo objetivo. Usa frases cortas, naturales y comprensibles
  para mi nivel, preferiblemente tomadas de mis actividades reales.
- `sentence` siempre es la frase **correcta**. `answer` es el fragmento exacto que
  se ocultará; debe evaluar la corrección, no otra palabra incidental de la frase.
  `answer_occurrence` cuenta desde 1 y distingue mayúsculas.
- `target` es la forma canónica de la expresión. `meaning_es` es una pista breve en
  español, sin revelar las palabras inglesas; solo se verá al desplegarla.
- `pattern` es una regla breve opcional. `example` muestra otra situación con el
  mismo objetivo. Usa `null` si no aportan; evita repetir la explicación en varios campos.
- `source` identifica de dónde salió el material original. `source.url` y
  `source.label` permiten `null`; no inventes enlaces.
- Usa `tts_text: null`: el audio se generará a partir de `sentence`.
- `islands` y `tags` pueden ser listas vacías. No escribas tags reservados `type::`,
  `source::`, `island::` ni, en errores, `error::`. El compilador los añade.
- No incluyas HTML, Markdown de formato, sintaxis cloze ni `[sound:...]` en los campos.

Para `my_error`, añade:

| Campo | Contenido |
| --- | --- |
| `original` | Mi intento real, sin corregirlo ni reconstruirlo. |
| `explanation_es` | Por qué funciona la corrección, en español y en una frase breve. |
| `error_type` | `grammar`, `word_choice` o `collocation`. |
| `correction_source` | Quién dio la corrección y, si hace falta, su contexto. |
| `observed_on` | Fecha real `AAAA-MM-DD`, o `null` cuando no se conozca. |

Esta versión no genera tarjetas para errores exclusivamente de pronunciación.
Si un intento contiene varios errores, no ocultes uno dejando los demás sin corregir:
la frase de práctica debe ser correcta. Selecciona un objetivo claro y conserva el
intento original como referencia; separa otros objetivos solo si realmente aportan.

## Entrega

Devuelve un objeto JSON puro, sin cercas Markdown ni comentarios, con
`"schema_version": "1.0"` y `"cards": [...]` (entre 1 y 50 tarjetas). Cada tarjeta
lleva su `kind`; no añadas `deck`, `deckName`, `model`, puntuaciones de confianza ni
campos ajenos al esquema. La configuración local resuelve los destinos.

El CLI mostrará el destino de cada tarjeta, el intento/corrección del 03 y los avisos
antes de pedir confirmación. El usuario puede revisar el JSON antes de publicarlo.
Las comprobaciones del programa validan estructura y consistencia; no pueden demostrar
que un error sea real, que una corrección sea lingüísticamente correcta o que una
fuente sea auténtica. Esa revisión sigue siendo responsabilidad del autor y del usuario.

Los archivos `examples/errors.json` y `examples/mixed.json` contienen demostraciones
sintéticas identificadas como tales. Nunca los atribuyas al usuario ni los uses como
evidencia de sus errores.
