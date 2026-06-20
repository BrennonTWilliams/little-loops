---
id: ENH-2243
title: Make --clear and --show-diagrams recommended defaults in ll-init wizard
type: ENH
status: open
priority: P3
captured_at: '2026-06-20T06:11:34Z'
discovered_date: '2026-06-20'
discovered_by: capture-issue
relates_to:
- ENH-2113
- ENH-2109
learning_tests_required:
- questionary
confidence_score: 100
outcome_confidence: 91
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 22
---

# ENH-2243: Make --clear and --show-diagrams recommended defaults in ll-init wizard

## Summary

ENH-2113 wired `loops.run_defaults` into `ll-init`, but hard-coded `clear=False` and `show_diagrams=None` — so every new project gets the "no diagrams, no clear" baseline instead of the recommended UX. This issue flips the recommended values to `clear=True / show_diagrams="clean"` and adds TUI prompts so users can accept or override them during `ll-init`.

## Motivation

The current ll-init always writes `loops.run_defaults` with conservative no-op defaults. Users who run `ll-init --yes` or accept defaults in the TUI get a config that silently disables the two most-visible loop UX improvements. The recommended experience should be the default, with an explicit opt-out — not something users have to discover and hand-edit after the fact.

## Current Behavior

`scripts/little_loops/init/core.py` `build_config()` hard-codes:
```python
config["loops"] = {"run_defaults": {"clear": False, "show_diagrams": None, "mode": None}}
```
The TUI (`tui.py`) has no prompts for these fields, so running `ll-init` interactively also lands on the no-op defaults.

## Expected Behavior

- `ll-init --yes` (headless) writes `clear: true` and `show_diagrams: clean`.
- The TUI presents two new prompts on Screen 3 (after prompt_optimization):
  - A `confirm` prompt: "Enable --clear by default for ll-loop run?" (default Yes)
  - A `select` prompt: "Default diagram mode for ll-loop run:" (choices: clean ✓, summary, layered, inline, Disabled)
- The summary panel shows a "Loop defaults" row reflecting the chosen values.
- Existing `ll-config.json` values pre-populate the prompts when re-running init on an already-configured project.

## Scope Boundaries

- Does **not** modify existing `ll-config.json` files — only new `ll-init` runs produce updated defaults
- Does **not** add new flags to `ll-loop run` — `--clear` and `--show-diagrams` already exist
- Does **not** change loop YAML behavior or FSM executor logic
- Does **not** add a new TUI screen — prompts are appended to Screen 3
- `mode` key in `run_defaults` remains `null` and is out of scope

## Implementation Steps

### 1. `scripts/little_loops/init/core.py` — flip headless defaults

In `build_config()` (lines 117–124), switch to config-driven recommended defaults:

```python
loop_clear = bool(choices.get("loop_clear_default", True))
loop_show_diagrams = choices.get("loop_show_diagrams_default", "clean")
config["loops"] = {
    "run_defaults": {
        "clear": loop_clear,
        "show_diagrams": loop_show_diagrams,
        "mode": None,
    }
}
```

### 2. `scripts/little_loops/init/tui.py` — three touch points

**A. Add two prompts** after the `prompt_optimization_enabled` block (after line ~350):

```python
# Loop run defaults — --clear
_ex_loop_clear = existing_config.get("loops", {}).get("run_defaults", {}).get("clear", True)
loop_clear_default = questionary.confirm(
    "Enable --clear by default for ll-loop run? (recommended)", default=_ex_loop_clear
).ask()
if loop_clear_default is None:
    return 130

# Loop run defaults — --show-diagrams
_SHOW_DIAGRAMS_CHOICES = [
    questionary.Choice("clean  (recommended)", value="clean"),
    questionary.Choice("summary", value="summary"),
    questionary.Choice("layered", value="layered"),
    questionary.Choice("inline", value="inline"),
    questionary.Choice("Disabled", value="__disabled__"),
]
_ex_sd = existing_config.get("loops", {}).get("run_defaults", {}).get("show_diagrams") or "clean"
_raw_sd = questionary.select(
    "Default diagram mode for ll-loop run:",
    choices=_SHOW_DIAGRAMS_CHOICES,
    default=_ex_sd if _ex_sd in ("clean", "summary", "layered", "inline") else "clean",
).ask()
if _raw_sd is None:
    return 130
loop_show_diagrams_default = None if _raw_sd == "__disabled__" else _raw_sd
```

**B. Thread through `_build_final_config()`**: add `loop_clear_default: bool = True` and `loop_show_diagrams_default: str | None = "clean"` parameters; pass them in the `build_config(...)` choices dict; forward them from `run_tui()`.

**C. Show in summary `_render_summary()`** — add "Loop defaults" row after "Prompt optim." (line ~664):

```python
rd = config.get("loops", {}).get("run_defaults", {})
rd_parts = []
if rd.get("clear"):
    rd_parts.append("--clear")
if rd.get("show_diagrams"):
    rd_parts.append(f"--show-diagrams {rd['show_diagrams']}")
table.add_row("Loop defaults", " ".join(rd_parts) if rd_parts else "none")
```

### 3. `scripts/tests/test_init_core.py` — update + extend

- **Update** `test_loops_run_defaults_keys` (line ~450): assert `clear=True` and `show_diagrams="clean"`.
- **Add** `test_loops_run_defaults_override_via_choices`: call `build_config(match, {"loop_clear_default": False, "loop_show_diagrams_default": None})` and assert `rd["clear"] is False` and `rd["show_diagrams"] is None`.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/core.py` — flip defaults in `build_config()`; add `loop_clear_default` and `loop_show_diagrams_default` to choices dict
- `scripts/little_loops/init/tui.py` — add two prompts on Screen 3; update `_build_final_config()` and `_render_summary()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/__init__.py` — re-exports `build_config` and `run_tui`; verify no signature breakage

### Similar Patterns
- `prompt_optimization_enabled` confirm prompt in `tui.py` — follow same confirm/select pattern for the two new prompts

### Tests
- `scripts/tests/test_init_core.py` — update `test_loops_run_defaults_keys`; add `test_loops_run_defaults_override_via_choices`
- `scripts/tests/test_loop_cli_defaults.py` — **exists**; tests runtime `run_defaults` backfill (ENH-2109), not `ll-init`; existing tests should continue passing unchanged
- `scripts/tests/test_init_tui.py` — TUI-specific tests; verify no regression on new prompts after adding two questionary blocks

### Documentation
- `docs/reference/API.md` — update `loops.run_defaults` default values in the ll-init section
- `docs/reference/CONFIGURATION.md` — may document `loops.run_defaults` defaults; verify and update if referenced
- `docs/guides/LOOPS_GUIDE.md` — may reference `run_defaults`; verify and update if referenced

### Configuration
- `config-schema.json` — confirm `loops.run_defaults.clear` and `loops.run_defaults.show_diagrams` are already in schema (no schema changes expected)

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Confirmed Anchor Points

- **`core.py:build_config()`** (lines 21–24, 117–124): Signature is `build_config(template: TemplateMatch, choices: dict[str, Any] | None = None) -> dict[str, Any]`. The `loops.run_defaults` block at lines 117–124 is unconditional and reads no `choices` keys today. Adding `loop_clear_default` and `loop_show_diagrams_default` to the choices dict mirrors exactly how `prompt_optimization_enabled` is handled.

- **`tui.py:run_tui()` → `prompt_optimization_enabled` block** (lines 344–350): The two new prompts go immediately after line 350 (end of this block).

- **`tui.py:_build_final_config()`** (lines 494–512): Add `loop_clear_default: bool = True` and `loop_show_diagrams_default: str | None = "clean"` as trailing keyword parameters after `prompt_optimization_enabled: bool = True`.

- **`tui.py:_build_final_config()` → `build_config()` call** (lines 516–531): The choices dict currently ends with `"prompt_optimization_enabled": prompt_optimization_enabled`. Append two keys:
  ```python
  "loop_clear_default": loop_clear_default,
  "loop_show_diagrams_default": loop_show_diagrams_default,
  ```

- **`tui.py:run_tui()` → `_build_final_config()` call**: After adding parameters to `_build_final_config()`, the call site in `run_tui()` must also pass `loop_clear_default=loop_clear_default` and `loop_show_diagrams_default=loop_show_diagrams_default`. The `run_tui()` outer signature does **not** need new parameters — values are collected via questionary internally.

- **`tui.py:_render_summary()`**: "Prompt optim." row renders `"off"` only when disabled (conditional pattern). The "Loop defaults" row follows the same convention — only render non-empty content.

### Schema Verification

`config-schema.json` (lines 913–935) confirms no changes needed:
- `clear`: boolean; `show_diagrams`: `["string", "null"]` with enum including `"clean"`, `"summary"`, `"layered"`, `"inline"`. The TUI sentinel `"__disabled__"` (mapping to `None`) is never written to the config file.

### `existing_config` Pre-population Pattern

Consistent with the established two-level `.get()` chain used throughout `run_tui()` (lines 316, 335, 345):
```python
_ex_loop_clear = existing_config.get("loops", {}).get("run_defaults", {}).get("clear", True)
_ex_sd = existing_config.get("loops", {}).get("run_defaults", {}).get("show_diagrams") or "clean"
```

## Verification

```bash
python -m pytest scripts/tests/test_init_core.py -k "loop" -v
python -m pytest scripts/tests/test_loop_cli_defaults.py -v
python -m mypy scripts/little_loops/init/tui.py scripts/little_loops/init/core.py
```

Manual: run `ll-init` in a temp directory — Screen 3 should show the two loop-default prompts defaulting to `Yes` / `clean`, and the summary panel should show a "Loop defaults" row with `--clear --show-diagrams clean`.

## Impact

- **Priority**: P3 — UX improvement for new project setup; existing configs and runtime behavior unaffected
- **Effort**: Small — 3 targeted file edits (core.py, tui.py, test_init_core.py); no new modules required
- **Risk**: Low — backwards compatible; only affects output of new `ll-init` runs, not loop execution or existing configs
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/reference/API.md](../../docs/reference/API.md) | ll-init core API reference |

## Labels

`enhancement`, `ll-init`, `tui`, `ux`

## Session Log
- `/ll:confidence-check` - 2026-06-20T00:00:00Z - `d17616de-870c-483a-8d41-e20429beb8b2.jsonl`
- `/ll:refine-issue` - 2026-06-20T06:21:08 - `e8fdda7f-8b2b-4ece-a637-8dec3548b5c5.jsonl`
- `/ll:format-issue` - 2026-06-20T06:15:17 - `82ae2197-fe4a-47b4-a984-2693281650dd.jsonl`
- `/ll:capture-issue` - 2026-06-20T06:11:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Status

**Status**: open
