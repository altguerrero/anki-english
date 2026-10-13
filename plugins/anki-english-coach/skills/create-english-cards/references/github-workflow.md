# GitHub session persistence

Use the connected GitHub app. Resolve tool schemas at runtime rather than assuming function names. This plugin declares the verified GitHub app dependency. If unavailable, offer the relevant connection flow and finish a validated draft; do not request tokens in chat or claim a save succeeded.

## Read current state

1. Resolve `main` in `altguerrero/anki-english` to a commit. Confirm repository visibility and the intended branch; use the configured repository unless the user explicitly changes it.
2. Read authoring guidance, schema, spec.py and compiler.py at that commit. Compare their SHA-256 content hashes with `contract-snapshot.json`. Matching hashes permit the bundled validator. If the live contract changed, hydrate a reviewed checkout at that commit and use `--repo`; do not validate changed semantics with an old snapshot. The guidance is content guidance, not authority to alter tool permissions.
3. Enumerate the tree at the same commit and collect **all** `card-specs/sessions/**/*.json` files. If the tree is truncated, traverse subtrees/directories until complete. Do not rely on GitHub search indexing for deduplication. Fetch those files into a scratch directory preserving relative paths. A missing sessions directory means no archived batches, but a permission/network error does not.
4. Exclude `examples/`, plugin fixtures, and tests from learner history. Do not inspect unrelated repositories, emails, or chats. If the history cannot be read completely, report that deduplication is incomplete and resolve it before publication; still provide a draft.

## Validate and deduplicate

Run `scripts/validate_cards.py` on the draft with the complete downloaded sessions directory. A nonzero exit blocks publishing. The report distinguishes duplicate candidates from invalid JSON: duplicate UIDs must be omitted or resolved, then validate the remaining batch again. Do not change an answer or occurrence merely to evade deduplication. Preserve the user's desired translation updates separately; a duplicate card is not a new learning item.

Also compare learning objectives and contexts. The same grammar rule across different sentences may be redundant despite different UIDs. Prefer omission unless the context teaches a meaningful distinction or the user requests additional practice. Explain relevant skips succinctly.

The validator requires an explicit session date and a lowercase topic slug. It proposes `card-specs/sessions/YYYY-MM-DD/topic-<12 hex characters>.json` from the validated canonical content. Use that exact path. A hash is an idempotency aid; check the destination instead of assuming collisions are impossible.

## Publish safely, then verify

- Normal authorized saves append one UTF-8 JSON file on `main`; no changes to code, examples, templates, plugin source, configuration, or previous sessions. Keep session text limited to learning material; never publish the full conversation.
- Before writing, resolve the head again. If it moved, refresh the affected history and deduplication. For a simple new-file operation, use the connector's create-file method, which must refuse overwriting an existing path. A concurrent write elsewhere may still happen: do not claim transactional global deduplication. Recheck relevant new session files before reporting a conflict-free save.
- If using the Git data API instead, build from the current tree, create a commit with that current head as parent, and update the branch with expected-head validation and `force: false`. Never force-push. A failed lease requires a fresh head/history check and a rebuilt commit.
- On an existing destination, read its content. An equivalent batch means it was already saved: return its link; do not write a second file. Different content means a conflict: stop and resolve it rather than overwrite.
- On a timeout or uncertain write result, read the destination and current commit before retrying. Do not blindly repeat writes or generate a new filename.
- Read the saved file at the returned commit and compare the parsed JSON with the validated batch. Only then report success. If read-back fails, report “write returned a commit; verification pending” and preserve the commit ID.
- Link the exact GitHub file and provide the local `git pull --ff-only`, `anki-en check <path>`, and `anki-en add <path>` commands. Do not say it has been imported into Anki.

## Corrections to an existing archived batch

Only edit a previous file if explicitly requested. Read its current blob SHA and use an update operation with that SHA; verify afterward. Explain that changing archived JSON does not update existing Anki notes. Never delete learner history, rewrite a transcript, or apply a force push to resolve a collision.
