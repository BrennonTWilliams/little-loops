---
id: ENH-2371
title: Add loops.run_defaults.include config field for default loop allowlist
type: ENH
status: done
priority: P3
captured_at: '2026-06-28T17:57:12Z'
discovered_date: '2026-06-28'
discovered_by: capture-issue
labels:
- enhancement
- loops
- config
- captured
confidence_score: 98
outcome_confidence: 89
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 24
completed_at: '2026-06-28T18:38:28Z'
---

# ENH-2371: Add `loops.run_defaults.include` config field for default loop allowlist

## Summary

Three built-in FSM loops (`loop-router.yaml`, `loop-composer.yaml`, `loop-composer-adaptive.yaml`) support an `include` context variable that filters which loops are visible/selectable via a comma-separated allowlist (`loop-name`, `builtin:*`, `project:*`, `category:<label>`). Currently there is no way to set a persistent default for this value in `ll-config.json`; users must pass `--context include=...` on every invocation. This issue adds an `include` field to `LoopRunDefaults` so the runner auto-injects it into the initial FSM context when set.

## Current Behavior

`LoopsRunDefaults` (`config/features.py`) has three fields: `clear`, `show_diagrams`, and `mode`. The `ll-loop run` dispatcher in `cli/loop/__init__.py` backfills only those three from `config.loops.run_defaults` (lines ~807–811). There is no `include` field, so `fsm.context["include"]` is always populated from the YAML default (`""`), meaning all loops are shown regardless of any `ll-config.json` setting.

## Expected Behavior

When `loops.run_defaults.include` is set in `.ll/ll-config.json`, e.g.:

```json
{
  "loops": {
    "run_defaults": {
      "include": "project:*"
    }
  }
}
```

`ll-loop run loop-router` (and the composer variants) should behave as if `--context include=project:*` was passed, filtering the loop list to project-only loops. An explicit `--context include=...` CLI flag still takes precedence (overrides the config default).

## Motivation

Users who primarily work with project loops (not builtins) or who want to restrict the composer to a curated set of loop names have to remember to pass `--context include=...` on every `loop-router` / `loop-composer` invocation. The `run_defaults` mechanism already exists for `clear`, `show_diagrams`, and `mode`; this is a natural extension of that pattern.

## Proposed Solution

Three-part change:

1. **`LoopRunDefaults` dataclass** (`scripts/little_loops/config/features.py`):
   ```python
   @dataclass
   class LoopRunDefaults:
       clear: bool = False
       show_diagrams: str | None = None
       mode: str | None = None
       include: str = ""   # new field

       @classmethod
       def from_dict(cls, data: dict[str, Any]) -> LoopRunDefaults:
           ...
           return cls(
               clear=data.get("clear", False),
               show_diagrams=show_diagrams,
               mode=data.get("mode", None),
               include=data.get("include", ""),  # new
           )
   ```

2. **`cli/loop/__init__.py`** — backfill `include` into `args` before dispatch (same pattern as the three existing fields), and then inject into `fsm.context` in `run.py` only when not already set by `--context include=...`:
   ```python
   # in main_loop() after rd = config.loops.run_defaults
   if not getattr(args, "context_include", None) and rd.include:
       # inject as a synthetic --context kv before cmd_run sees it
       args.extra_context = [*getattr(args, "extra_context", []), f"include={rd.include}"]
   ```
   Alternatively, inject directly into `fsm.context["include"]` in `cli/loop/run.py` using the same guard pattern as `run_dir` / `max_steps` (lines ~162–178).

3. **`config-schema.json`** — add `include` to the `loops.run_defaults` object definition with a description matching the YAML comment syntax.

The simplest injection site is `run.py` alongside the other injected-if-absent context keys, after the existing `--context` overrides are applied.

## Integration Map

### Files to Modify
- `scripts/little_loops/config/features.py` — `LoopRunDefaults.from_dict()` + dataclass field
- `scripts/little_loops/cli/loop/__init__.py` — backfill step (optional if injection is in run.py)
- `scripts/little_loops/cli/loop/run.py` — inject `include` into `fsm.context` when absent
- `config-schema.json` — `loops.run_defaults.include` field definition

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — reads `config.loops.run_defaults`
- `scripts/little_loops/config/core.py` — `LoopsConfig.from_dict()` constructs `LoopRunDefaults`

### Similar Patterns
- `run_dir`, `max_steps`, `max_iterations` injection in `run.py` lines ~162–180 (inject-if-absent pattern)
- `clear` / `show_diagrams` backfill in `__init__.py` lines ~807–811

### Tests
- `scripts/tests/test_builtin_loops.py` — add tests verifying `include` context injection from config
- `scripts/tests/test_init_core.py` or a new `test_loops_config.py` — `LoopRunDefaults.from_dict({"include": "project:*"})` round-trip

### Documentation
- `docs/reference/API.md` — `LoopRunDefaults` class reference
- `config-schema.json` — (already listed above)

### Configuration
- `.ll/ll-config.json` example: `"loops": {"run_defaults": {"include": "project:*"}}`

## Implementation Steps

1. Add `include: str = ""` field to `LoopRunDefaults` dataclass and `from_dict()`.
2. Update `config-schema.json` with the new `include` property under `loops.run_defaults`.
3. In `cli/loop/run.py`, inject `fsm.context["include"]` from `_config.loops.run_defaults.include` when `"include" not in fsm.context` (follows the `run_dir`/`max_steps` pattern).
4. Write tests: config round-trip + end-to-end context injection.
5. Verify `--context include=...` still overrides the config default.

## Success Metrics

- `include` from config is applied: `ll-loop run loop-router` with `"include": "project:*"` in `.ll/ll-config.json` shows only project loops (no `--context` flag required)
- CLI override respected: `--context include=builtin:*` takes precedence over the config default
- No regression: omitting `include` from config (or setting it to `""`) leaves all loops visible — identical to current behavior

## Scope Boundaries

- Only injects into `fsm.context["include"]`; does not change how the three loops consume the value.
- Does not add per-loop overrides (all loops sharing this initial context get the same default).
- Does not expose a new CLI flag (`--include`); the existing `--context include=VALUE` path remains the override mechanism.

## API/Interface

```python
@dataclass
class LoopRunDefaults:
    clear: bool = False
    show_diagrams: str | None = None
    mode: str | None = None
    include: str = ""  # allowlist injected into fsm.context; empty = all loops
```

JSON config schema addition:
```json
"include": {
  "type": "string",
  "default": "",
  "description": "Default loop allowlist injected into FSM context for loop-router/loop-composer. Comma-separated selectors: loop-name, builtin:*, project:*, category:<label>. Empty = all loops."
}
```

## Impact

- **Priority**: P3 — quality-of-life improvement; no user is blocked, but the gap is a natural extension of the existing `run_defaults` mechanism
- **Effort**: Small — additive dataclass field + one inject-if-absent guard in `run.py` + schema update
- **Risk**: Low — purely additive; defaults to `""` (existing behavior unchanged for anyone who doesn't set the field)
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `config`, `captured`

## Session Log
- `ll-auto` - 2026-06-28T18:38:28 - `f931a287-14c8-4bd2-a36f-f39309d4ff04.jsonl`
- `/ll:ready-issue` - 2026-06-28T18:23:32 - `43c52cd2-7c77-4853-babe-350d18ba8e02.jsonl`
- `/ll:format-issue` - 2026-06-28T18:18:20 - `15bfadfe-1196-486b-b8a7-508cc3762090.jsonl`

- `/ll:capture-issue` - 2026-06-28T17:57:12Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/813b66f8-3628-4f7d-aeb6-e9dfbc7b6595.jsonl`
- `/ll:confidence-check` - 2026-06-28T19:00:00Z - `a963f017-885b-4831-950a-df656f539d7d.jsonl`

---

## Status

**Open** | Created: 2026-06-28 | Priority: P3


---

## Resolution

- **Action**: improve
- **Completed**: 2026-06-28
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
