# CardSpec 1.0 — project compatibility

Read the live repository contract before publication. `contract-snapshot.json` records the bundled source hashes. Files under `scripts/runtime/anki_english` are exact copies of the project's Pydantic contract and compiler, not a second implementation. `card-spec-v1.schema.json` is the corresponding JSON Schema.

A batch contains only `schema_version: "1.0"` and `cards` (1–50 items). Do not emit an empty batch. All fields below are required except `sentence_es` and `observed_on`; nullable fields must still be included when required. Unknown properties are rejected. JSON strings must be nonblank, one line, without control characters, cloze markup, or sound tags. Use plain text, never HTML.

| Field | Value / limit |
| --- | --- |
| `kind` | `sentence_chunk` or `my_error` |
| `sentence` | Correct English, 1–300 chars |
| `answer` | Exact word/phrase in sentence, 1–100 chars; no surrounding whitespace |
| `answer_occurrence` | Integer ≥1, case-sensitive occurrence at word boundaries |
| `target` | Canonical learning target, 1–100 chars |
| `meaning_es` | Brief Spanish gloss, 1–120 chars |
| `sentence_es` | Full Spanish translation, 1–500 chars, or null; include when confident |
| `pattern` | Brief rule/construction, 1–140 chars, or null |
| `example` | Another correct English context, 1–250 chars, or null |
| `source` | Object with `type`, `label` (1–200 or null), `url` (HTTP/S or null) |
| `islands` | ≤20 unique lowercase kebab-case themes, max60 chars each |
| `tags` | ≤30 unique simple lowercase tags, max80 chars, optional one `::` namespace |
| `tts_text` | Use null; audio reads the correct `sentence` |

`source.type`: `manual`, `lingq`, `platzi`, `chatgpt`, `conversation`, `book`, `video`, `other`. Use `conversation` for a user's actual conversational attempt and `chatgpt` for assistant-created teaching content; preserve an explicitly supplied real origin. A label like “ChatGPT practice — daily routine” identifies context without inventing a transcript URL. Use `url: null` unless an actual relevant link is known. Never invent dates or sources to fill fields.

Do not author tags beginning with `type::`, `source::`, `island::`, or `error::`; the compiler adds them. Prefer a few useful themes such as `work`, `daily-life`, `social`; do not create a taxonomy for every lesson.

Additional 03 fields:

| Field | Value / limit |
| --- | --- |
| `original` | Actual learner attempt, 1–300 chars; must differ from correction |
| `explanation_es` | Actionable Spanish explanation, 1–300 chars |
| `error_type` | `grammar`, `word_choice`, or `collocation` |
| `correction_source` | Honest feedback attribution, 1–200 chars |
| `observed_on` | Actual ISO calendar date `YYYY-MM-DD`, or null/omitted |

For 03, any non-null `tts_text` must equal the corrected sentence; use null. The default deck names are resolved from kind by the local CLI config. Do not add `deck`, `UID`, `audio`, `session_id`, confidence, explanation metadata, or timestamps to CardSpec.

UID identity is computed by the compiler, never written into author JSON. Translation, tags, feedback and dates are not identity. Different original attempts can create distinct 03 UIDs for the same target: review pedagogical duplicates before saving. Updating JSON never silently edits existing Anki notes; `add` skips duplicates, and `update-translations` only fills empty translations.
