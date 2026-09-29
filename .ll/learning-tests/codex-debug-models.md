---
target: codex debug models
date: '2026-09-28'
status: proven
assertions:
- claim: codex debug models exits 0 and prints a JSON object on stdout (codex-cli 0.152.1)
  result: pass
- claim: the JSON has a top-level "models" list and no other top-level keys
  result: pass
- claim: every entry has a string "slug" and a "visibility" of "list" or "hide"
  result: pass
- claim: 'each entry''s "upgrade" is either null or an object with "model" and "retirement_at" keys'
  result: pass
- claim: a non-null upgrade.retirement_at is an ISO-8601 string with a Z suffix
  result: pass
- claim: the --bundled flag is accepted, exits 0 and prints the same JSON shape
  result: pass
- claim: the bundled catalog lists different slugs than the refreshed catalog
  result: pass
- claim: an unknown flag makes codex debug models exit non-zero
  result: pass
- claim: codex debug models writes nothing to stderr on success
  result: pass
raw_output_path: .ll/learning-tests/raw/codex-debug-models.txt
---
