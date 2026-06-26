---
id: BUG-2311
title: "ll-init writes null leaves (build_cmd/run_cmd/mode) to generated config"
type: BUG
status: open
priority: P2
captured_at: "2026-06-26T21:55:52Z"
discovered_date: "2026-06-26"
discovered_by: capture-issue
labels:
- init
- config
relates_to:
- BUG-2310
---

# BUG-2311: ll-init writes null leaves (build_cmd/run_cmd/mode) to generated config

## Summary

A freshly generated `.ll/ll-config.json` contains `null`-valued leaf keys copied
verbatim from the project-type template and from `build_config`'s own defaults.
These nulls are noise at best and a footgun once config-merge semantics are
involved (a `None` is a key-removal sentinel for `deep_merge`).

## Current Behavior

`build_config()` copies the template project block via
`dict(data.get("project", {}))` (`scripts/little_loops/init/core.py:56`). The
project-type templates carry `build_cmd: null` / `run_cmd: null`, so every fresh
config gets:

```json
"project": { "build_cmd": null, "run_cmd": null }
```

And `build_config` itself writes (`core.py:121-127`):

```json
"loops": { "run_defaults": { "mode": null } }
```

This is the recurring "null template value" concern. `test_init_core.py:525`
currently asserts `mode is None` is intentional.

## Expected Behavior

Generated configs omit unset optional keys rather than persisting `null` leaves
(or, if a key must be present for schema reasons, it carries a real default, not
`null`).

## Steps to Reproduce

1. Enter any project directory (new or existing)
2. Run `ll-init --yes` (any project type)
3. Inspect the generated `.ll/ll-config.json`
4. Observe: `"build_cmd": null`, `"run_cmd": null` under `project`, and `"mode": null` under `loops.run_defaults`

## Root Cause

1. `build_config` shallow-copies template `project` including `null` leaves.
2. `build_config` explicitly sets `loops.run_defaults.mode = None`.

## Proposed Solution

In `build_config()` (`scripts/little_loops/init/core.py`), add a recursive
`strip_none_leaves()` helper and call it on the assembled config dict before
returning. This covers both the shallow-copied template `project` block and the
explicit `loops.run_defaults.mode = None` assignment. Update the assertions in
`test_build_config` (within `scripts/tests/test_init_core.py`) to check for key
*absence* rather than `None`. Coordinate with BUG-2310: stripping nulls ensures
`deep_merge`-based re-init never uses a `None` leaf as a key-removal sentinel
against a user's existing value.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/core.py` — add `strip_none_leaves()` helper before `build_config()` return; no callers need updating (fix is transparent to all three call sites)
- `scripts/tests/test_init_core.py` — update `is None` assertions to key-absence assertions (lines 525, 537–538); audit any test asserting `config["project"]["build_cmd"] is None` or `config["project"]["run_cmd"] is None`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py:303` (`_run_yes()`) — calls `build_config()`; fix is automatic; result flows to `write_config()` → `atomic_write_json()` in `scripts/little_loops/file_utils.py`
- `scripts/little_loops/init/cli.py:398` (`_run_plan()`) — calls `build_config()`; fix also covers plan JSON output automatically
- `scripts/little_loops/init/cli.py` (`_run_apply()`) — does NOT call `build_config()`; consumes pre-built plan `proposed_config` directly — no change needed here

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/tui.py` — calls `build_config()` via `_build_final_config()` (line 648); fix is transparent (no code change needed here); note that `_build_final_config` re-inserts `None` values post-return for empty command strings (e.g. `type_cmd=""`→`None`), so `test_init_tui.py:TestBuildFinalConfig.test_command_overrides_applied` (lines 503–504) remains safe and unaffected
- `scripts/little_loops/init/__init__.py` — exports `build_config` as public API (line 3); no change needed

### Similar Patterns
- `scripts/little_loops/init/core.py:build_config()` — conditional `if` guards already used for `context_monitor`, `product`, `decisions`, `scratch_pad`, `session_capture`, `prompt_optimization` establish the codebase convention of key-omission over null assignment; confirms `strip_none_leaves()` aligns with existing idiom
- `scripts/little_loops/config/core.py:deep_merge()` — lines 44–71; `if value is None: result.pop(key, None)` — null leaves in a generated config are a confirmed footgun: they will silently delete the user's key when BUG-2310's re-init merge lands

### Tests
- `scripts/tests/test_init_core.py:TestBuildConfig.test_loops_run_defaults_keys` (line 518) — asserts `rd["mode"] is None` at line 525; must become `assert "mode" not in rd`
- `scripts/tests/test_init_core.py:TestBuildConfig.test_loops_run_defaults_override_via_choices` (line 527) — asserts `rd["mode"] is None` at line 538 and `rd["show_diagrams"] is None` at line 537; both must become key-absence assertions after `strip_none_leaves()` removes them
- `scripts/tests/test_init_core.py` — fake-template fixtures at lines 86–87, 129–130, 170–171, 211–212 carry `"build_cmd": None, "run_cmd": None`; any test asserting those values exist must be updated to assert key absence

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_tui.py:TestBuildFinalConfig.test_command_overrides_applied` (lines 503–504) — asserts `config["project"]["type_cmd"] is None` and `config["project"]["format_cmd"] is None`; these are SAFE: `_build_final_config` re-inserts the `None` values *after* `build_config()` returns (via `val or None` on empty-string inputs), so `strip_none_leaves()` never sees them
- `scripts/tests/test_init_core.py:TestStripNoneLeaves` (new class to add) — write direct unit tests for the `strip_none_leaves()` helper covering: empty dict, single null leaf removed, falsy-but-not-None values preserved (`False`, `0`, `""`), nested null removed, deeply nested null removed, mixed dict; add `strip_none_leaves` to the import at line 14 alongside `build_config`

### Templates (read-only — null values stay in source files, stripped at `build_config()` time)
- `scripts/little_loops/templates/python-generic.json` — `build_cmd: null, run_cmd: null`
- `scripts/little_loops/templates/generic.json` — six null command fields: `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`, `build_cmd`, `run_cmd`
- `scripts/little_loops/templates/javascript.json` — `build_cmd: null, type_cmd: null`

### Documentation
- `docs/reference/CONFIGURATION.md` — lines 21–22 show example config with `"build_cmd": null, "run_cmd": null`; update to show omitted keys after fix

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — lines 516–526 show a `run_defaults` authoring example with `"mode": null`; advisory: `ll-init` no longer generates this key, but users can still write it manually (schema allows it); consider removing `mode` from the example to avoid implying it is generated output

### Configuration
- `config-schema.json` — defines `build_cmd`/`run_cmd` as `["string", "null"]` with `default: null`; key absence ≠ explicit null, so no schema change required

## Implementation Steps

1. **Add `strip_none_leaves()` in `scripts/little_loops/init/core.py`** — recursive helper that removes any key whose value is `None` at any depth; call as `return strip_none_leaves(config)` at the end of `build_config()`
2. **Update assertions in `scripts/tests/test_init_core.py`**:
   - Line 525: `assert rd["mode"] is None` → `assert "mode" not in rd`
   - Line 537: `assert rd["show_diagrams"] is None` → `assert "show_diagrams" not in rd`
   - Line 538: `assert rd["mode"] is None` → `assert "mode" not in rd`
   - Audit tests referencing `build_cmd`/`run_cmd` in the project block; change any `is None` checks to `not in config["project"]`
3. **Verify plan path is also clean** — `_run_plan()` in `cli.py:398` shares `build_config()`; run `ll-init --plan /tmp/scratch` and confirm `proposed_config` in the plan JSON also contains no null leaves
4. **Run targeted tests**: `python -m pytest scripts/tests/test_init_core.py -v -k "build_config or loops_run_defaults or build_cmd or run_cmd"` — all should pass
5. **Smoke test**: `ll-init --yes` in a temp directory; inspect `.ll/ll-config.json` and confirm zero `null` values appear

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Add `TestStripNoneLeaves` unit tests in `scripts/tests/test_init_core.py`** — add `strip_none_leaves` to the import at line 14; write a dedicated test class covering: empty dict, single null leaf removed, falsy-but-not-None values preserved (`False`, `0`, `""`), nested null removed, deeply nested null removed, mixed dict with non-null values preserved
7. **Update `docs/reference/CONFIGURATION.md` lines 21–22** — remove `"build_cmd": null` and `"run_cmd": null` from the "Full Configuration Example" block to match the new generated output
8. **Advisory: review `docs/guides/LOOPS_GUIDE.md` lines 516–526** — the `run_defaults` example shows `"mode": null`; consider removing it to avoid implying `ll-init` generates it (the key remains valid to write manually)

## Impact

- **Priority**: P2 — Cosmetic for fresh installs; correctness-critical once BUG-2310's `deep_merge` lands (a `null` leaf silently removes the user's key on merge)
- **Effort**: Small — Add a `strip_none_leaves()` helper in `build_config()` and update a handful of test assertions; no new patterns needed
- **Risk**: Low — Only affects freshly-generated configs; existing configs that already contain `null` leaves continue to be read and merged correctly
- **Breaking Change**: No

## Labels

- init, config

## Session Log
- `/ll:wire-issue` - 2026-06-26T22:21:24 - `bb00a6b3-bb99-4165-8a0d-44506e20bca0.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:11:19 - `4405b36b-0acc-485d-bd10-aa2b8d7d1402.jsonl`
- `/ll:format-issue` - 2026-06-26T22:03:06 - `df942982-a9f6-4636-9b13-fcfbb439ce52.jsonl`
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
