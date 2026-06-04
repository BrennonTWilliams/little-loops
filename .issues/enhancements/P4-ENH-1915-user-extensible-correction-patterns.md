---
id: ENH-1915
title: User-extensible correction detection phrases via analytics.capture.correction_patterns
type: ENH
priority: P4
status: open
decision_needed: false
discovered_date: 2026-06-03
captured_at: "2026-06-03T21:38:03Z"
discovered_by: capture-issue
parent: EPIC-1707
relates_to: [EPIC-1707, ENH-1831, ENH-1887]
labels:
  - history-db
  - configurability
---

# ENH-1915: User-extensible correction detection phrases

## Summary

Correction detection (ENH-1831/1887, done) uses a fixed built-in regex/phrase
set. Expose a user-extensible list, `analytics.capture.correction_patterns`
(list[str]), that is **appended to** the built-ins so projects can teach the
detector their own correction phrasings without forking code.

## Current Behavior

The correction detector uses a fixed built-in regex/phrase set. Projects with
domain-specific correction language ("not quite", "actually use X instead",
etc.) have those corrections silently missed — no mechanism exists to extend
the phrase set without forking code.

The three hardcoded module-level compiled regexes in `session_store.py`
(`_CORRECTION_RE` at line 99, `_PHRASE_RE` at line 104, `_REMEMBER_RE` at
line 120) are compiled once at import and never rebuilt. `is_correction()` at
line 123 accepts only `text: str` — there is no parameter for additional
patterns and no config injection point.

## Expected Behavior

Users add `analytics.capture.correction_patterns: ["not quite", "actually use X
instead"]` to `.ll/ll-config.json`. Configured patterns are appended to the
built-ins; built-ins always remain active. Absent config → zero behavior change.
Malformed config (non-list or non-string items) → degrades gracefully to
built-ins only, never raises.

## Motivation

The `user_corrections` corpus is the EPIC's core signal, but the detector only
recognizes built-in phrasings. Teams with domain-specific correction language
("not quite", "actually use X instead", etc.) silently lose those corrections.
Making the phrase set extensible improves capture recall — a write-side quality
lever, so it belongs in the `analytics.*` (capture/write) namespace per the
ratified split.

## API/Interface

- `analytics.capture.correction_patterns` — list[str], default `[]`, appended to
  the built-in patterns (built-ins always remain active).

## Implementation Steps

1. **`config-schema.json` (~line 1400)**: Add `correction_patterns` property to
   the `analytics.capture` object (currently at lines 1374–1402) before the
   closing `"additionalProperties": false`. Follow the `skills`/`cli_commands`
   pattern (both use `"type": "array"`, `"items": {"type": "string"}`):
   ```json
   "correction_patterns": {
     "type": "array",
     "items": { "type": "string" },
     "default": [],
     "description": "Additional regex patterns appended to the built-in correction detector. Built-ins always remain active."
   }
   ```

2. **`scripts/little_loops/config/features.py:426` — `AnalyticsCaptureConfig`**:
   Add `correction_patterns: list[str] = field(default_factory=list)` field.
   Update `from_dict` (line 440) to read leniently — coerce malformed values to
   `[]` rather than raising:
   ```python
   raw = data.get("correction_patterns", [])
   correction_patterns = [p for p in raw if isinstance(p, str)] if isinstance(raw, list) else []
   ```
   Follow the `skills`/`cli_commands` lenient-get pattern already in that method.

3. **`scripts/little_loops/config/core.py:619-623` — `BRConfig.to_dict()`**:
   Add `"correction_patterns": list(self._analytics_capture.correction_patterns)`
   to the `analytics.capture` dict alongside the four existing keys.

4. **`scripts/little_loops/session_store.py:123` — `is_correction()`**:
   Add an optional `extra_patterns: Sequence[str] = ()` parameter. When
   non-empty, compile them into a combined alternation regex (`re.IGNORECASE`,
   wrap each in `re.escape()` for literal matching or leave raw for regex); catch
   `re.error` per pattern and skip invalid ones (log a warning). Evaluation:
   ```python
   return bool(
       _REMEMBER_RE.match(t)
       or _CORRECTION_RE.match(t)
       or _PHRASE_RE.search(t)
       or (_extra_re and _extra_re.search(t))
   )
   ```
   Keep the three module-level constants unchanged — they are not rebuilt.

5. **`scripts/little_loops/hooks/user_prompt_submit.py:71` — live call site**:
   Currently calls `is_correction(user_prompt)` at line 71, then constructs
   `capture` inside the block at line 75. Reorder: construct `capture` first
   (same nested `.get("analytics", {}).get("capture", {})` pattern), then call
   `is_correction(user_prompt, extra_patterns=capture.correction_patterns)`.

6. **`scripts/little_loops/session_store.py:930` — `mine_corrections_from_messages()`**:
   This function already accepts a `config` dict. Extract `correction_patterns`
   from `config.get("analytics", {}).get("capture", {}).get("correction_patterns", [])`
   and pass to `is_correction(content, extra_patterns=...)` in the row loop.

7. **Tests**: Add to `test_config.py:TestAnalyticsCaptureConfig` (around line 1183):
   - `test_correction_patterns_default` — `from_dict({})` yields `correction_patterns == []`
   - `test_correction_patterns_set` — custom patterns round-trip
   - `test_correction_patterns_malformed_non_list` — non-list coerces to `[]`
   - `test_correction_patterns_malformed_mixed` — list with non-str items → only str items kept

   Add to `test_session_store.py:TestIsCorrectionHeuristic` (around line 1200):
   - `test_extra_patterns_fire` — custom phrase in `extra_patterns` triggers `True`
   - `test_extra_patterns_do_not_replace_builtins` — built-in still fires when extra_patterns provided
   - `test_extra_patterns_empty` — `extra_patterns=[]` is identical to no-arg call

## Acceptance Criteria

- Absent config → built-in behavior unchanged.
- Configured patterns are additive (never replace built-ins); malformed config
  degrades to built-ins, never raises.

## Scope Boundaries

- **In scope**: `correction_patterns` key under `analytics.capture` in
  `config-schema.json`; `AnalyticsCaptureConfig.from_dict` reading the key
  leniently (default `[]`); `is_correction()` accepting optional extra patterns;
  both call sites (`user_prompt_submit.py:71`, `mine_corrections_from_messages`)
  passing configured patterns; `BRConfig.to_dict()` serializing the new field.
- **Out of scope**: Replacing or disabling built-in patterns; changes to the
  `history` namespace (ENH-1913); file-event tool→path map (ENH-1832,
  intentionally not filed); any UI/GUI for managing patterns.

## Integration Map

### Files to Modify
- `config-schema.json:1374-1402` — `analytics.capture` object; add `correction_patterns` property before `"additionalProperties": false`
- `scripts/little_loops/config/features.py:426` — `AnalyticsCaptureConfig` dataclass; add field + lenient `from_dict` reading (method at line 440)
- `scripts/little_loops/config/core.py:619-623` — `BRConfig.to_dict()` `analytics.capture` block; add `correction_patterns` serialization
- `scripts/little_loops/session_store.py:123` — `is_correction()` signature; add `extra_patterns: Sequence[str] = ()` parameter
- `scripts/little_loops/hooks/user_prompt_submit.py:71` — reorder: construct `AnalyticsCaptureConfig` before calling `is_correction()`, then pass `correction_patterns`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/user_prompt_submit.py:71` — calls `is_correction(user_prompt)` directly (live hook path); also imports `is_correction` at line 29
- `scripts/little_loops/session_store.py:930` — `mine_corrections_from_messages()` calls `is_correction(content)` per row in backfill loop; already receives `config` dict so patterns can be extracted without signature change to the outer function

### Similar Patterns
- `scripts/little_loops/config/features.py:440` — `AnalyticsCaptureConfig.from_dict()`: existing `skills`/`cli_commands` fields use `data.get(key, ["*"])` — same lenient-get pattern; add `correction_patterns` with `data.get("correction_patterns", [])` + coercion
- `scripts/little_loops/config/features.py:208` — `IssuesConfig.from_dict()` built-in + user merge: uses a module-level `REQUIRED_CATEGORIES` constant and fills missing entries — conceptually similar to "built-ins always remain active"
- `config-schema.json:1382` — `skills` field: `"type": "array", "items": {"type": "string"}, "default": ["*"]` — exact schema shape to replicate for `correction_patterns` (with `"default": []`)

### Tests
- `scripts/tests/test_config.py:1183` — `TestAnalyticsCaptureConfig` class; add 4 new test methods here
- `scripts/tests/test_session_store.py:1200` — `TestIsCorrectionHeuristic` class; add 3 new parametrized tests here
- `scripts/tests/test_config_schema.py` — `test_analytics_capture_in_schema`; verify `correction_patterns` appears in schema

### Documentation
- N/A — internal config key; no user-facing docs need updating

### Configuration
- `config-schema.json` (`analytics.capture.correction_patterns`)

## Notes

- Write-side namespace (`analytics.*`), so does **not** depend on ENH-1913 — but
  it is **not** schema-free (it edits `analytics.capture`).
- ENH-1832's file-event tool→path map is a lower-value optional, intentionally
  not filed.
- `is_correction()` currently does NOT accept config — the call site in
  `user_prompt_submit.py` constructs `AnalyticsCaptureConfig` *after* the
  correction check. Step 5 must reorder this to avoid constructing `capture`
  twice. The hook already has the raw `config` dict in scope.
- User-supplied patterns should be treated as raw regex strings (not literals) to
  match the `_PHRASE_RE` style — document this in the schema description.
  Alternatively, `re.escape()` them for literal-phrase matching. Choose one
  approach and document it; the issue's examples ("not quite") suggest literal
  phrase matching is the primary use case.

## Dependencies

- Follow-up to ENH-1831 / ENH-1887 (both done).

## Impact

- **Priority**: P4 — Incremental quality-of-life improvement; correction recall gap exists but no blocking impact on existing workflows
- **Effort**: Small — 3 targeted edits: schema addition, config class update, matcher compilation
- **Risk**: Low — Additive config with graceful fallback; built-ins remain active regardless of user config
- **Breaking Change**: No

## Session Log
- `/ll:refine-issue` - 2026-06-04T02:29:55 - `8ca0ff26-0dbe-4d77-b23c-320c3c557a9b.jsonl`
- `/ll:refine-issue` - 2026-06-03T22:30:00 - `39a37568-d7a7-42c9-8508-05b4e238e1ce.jsonl`
- `/ll:format-issue` - 2026-06-03T21:44:21 - `39a37568-d7a7-42c9-8508-05b4e238e1ce.jsonl`
- `/ll:capture-issue` - 2026-06-03T21:38:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`

---

## Status

open
