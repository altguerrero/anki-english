# Sesiones de inglés

Los lotes reales se guardan en `YYYY-MM-DD/tema-hash.json` mediante Anki English Coach.
Cada archivo es un CardBatch válido, importable sin transformación. Un lote puede contener
02, 03 o ambos; no se impone una cuota. Los ejemplos de `examples/` no son historial personal.

El plugin revisa los lotes de esta carpeta para evitar duplicados exactos y revisa objetivos
similares antes de guardar. No ve notas creadas directamente en tu Anki. Este repositorio
es público: guarda únicamente contenido de aprendizaje adecuado para publicar, sin transcripciones
completas ni detalles personales sensibles.

Para importar un lote guardado, con el entorno activado y Anki abierto:

```bash
git pull --ff-only
anki-en check card-specs/sessions/AAAA-MM-DD/tema-hash.json
anki-en add card-specs/sessions/AAAA-MM-DD/tema-hash.json
```

Usa la ruta real que devuelva el plugin. `check` es offline; `add` genera audio y comprueba
UIDs en Anki. Reimportar el mismo lote omite notas existentes. Guardar en GitHub no equivale
a importar en Anki. No edites ni borres lotes anteriores para representar una sesión nueva.
