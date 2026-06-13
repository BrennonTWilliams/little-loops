---
id: ENH-2109
title: 'll-loop run: persistent default flags via config (--clear, --show-diagrams,
  --mode)'
type: ENH
status: done
priority: P3
captured_at: '2026-06-13T14:38:41Z'
completed_at: '2026-06-13T15:10:52Z'
discovered_date: '2026-06-13'
discovered_by: capture-issue
labels:
- loops
- cli
- config
confidence_score: 90
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 16
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2109: ll-loop run: persistent default flags via config (--clear, --show-diagrams, --mode)

## Summary

Add a `run_defaults` block to the `loops` section of `.ll/ll-config.json` (backed by `config-schema.json`) that lets users declare persistent CLI defaults for `ll-loop run`. When set, `--clear`, `--show-diagrams <MODE>`, and `--mode <VALUE>` are automatically prepended to every `ll-loop run` invocation without requiring the user to type them each time.

## Current Behavior

Every `ll-loop run` invocation requires the user to explicitly pass `--clear`, `--show-diagrams clean` (or another mode), and any other persistent preferences on the command line. There is no way to declare "I always want `--clear --show-diagrams clean`" once in config.

## Expected Behavior

After adding `run_defaults` to `.ll/ll-config.json`:

```json
{
  "loops": {
    "run_defaults": {
      "clear": true,
      "show_diagrams": "clean",
      "mode": null
    }
  }
}
```

Running `ll-loop run my-loop` behaves identically to `ll-loop run my-loop --clear --show-diagrams clean`. Explicit CLI flags still override the config defaults (CLI wins over config).

## Motivation

Users who run loops interactively nearly always want the same display settings. Requiring repetitive flag entry adds friction and leads to inconsistent loop output between runs where the user forgets to add the flags.

## Scope Boundaries

- **In scope**: `--clear`, `--show-diagrams`, and `--mode` flags for `ll-loop run` only
- **Out of scope**: Persistent defaults for other `ll-loop` subcommands (`validate`, `diagnose`, `list`, etc.)
- **Out of scope**: Per-loop overrides — `run_defaults` is project-wide config, not per-loop YAML
- **Out of scope**: New `ll-loop run` flags beyond the three named here; only existing flags are wired
- **Out of scope**: Changes to FSM execution logic; this is purely a CLI/config-layer change

## Proposed Solution

1. **Schema** (`config-schema.json`): Add a `run_defaults` object under `loops` with:
   - `clear` (`boolean`, default `false`) — if `true`, inject `--clear`
   - `show_diagrams` (`string | null`, default `null`) — if non-null, inject `--show-diagrams <value>`; valid values mirror the `--show-diagrams` argument: topologies (`layered`, `neighborhood`, `inline`) and presets (`detailed`, `summary`, `clean`, `local`, `slim`, `oneline`); bare `true` (for the no-value form) can be represented as `"default"`
   - `mode` (`string | null`, default `null`) — if non-null, inject `--mode <value>` (future-proofing for any `--mode` flag added to `ll-loop run`)

2. **Runner** (`scripts/little_loops/cli/loop/__init__.py`): After `parse_args()`, load the `loops.run_defaults` config block and backfill any unset args with config values before dispatching to the run handler. Explicit CLI flags (where `argparse` sets a non-default value) take precedence.

3. **Schema validation**: Add enum constraints for `show_diagrams` derived from `TOPOLOGY_VALUES | PRESET_VALUES` in `scripts/little_loops/cli/loop/diagram_modes.py` so invalid values are caught at config-load time.

## Integration Map

### Files to Modify
- `config-schema.json` — add `loops.run_defaults` object with `clear`, `show_diagrams`, `mode` properties and enum constraint for `show_diagrams`
- `scripts/little_loops/cli/loop/__init__.py` — inject defaults after `parse_args()` in the `run` subcommand handler, before dispatching to the run handler
- `scripts/little_loops/cli/loop/diagram_modes.py` — use the already-public `TOPOLOGY_VALUES` and `PRESET_VALUES` constants for schema enum generation (no re-export needed)
- `scripts/little_loops/config/features.py` — add `LoopRunDefaults` dataclass to `LoopsConfig`; expose `loops.run_defaults` as a typed config field

### Dependent Files (Callers/Importers)
- Grep `loops` config block references: `grep -r "loops" scripts/little_loops/config/features.py` to confirm loader location
- Grep `ll-loop run` invocations in automation scripts to verify no callers break with new backfill logic

### Similar Patterns
- Check how other CLI tools in `scripts/little_loops/cli/` apply config defaults to argparse args for consistency
- Check if `config-schema.json` already has a `defaults` object under another section to follow that naming pattern

### Tests
- `scripts/tests/test_loop_cli_defaults.py` (new) — three cases: (a) config default applied when flag omitted, (b) explicit CLI flag overrides config default, (c) invalid `show_diagrams` value raises config validation error

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — document new `run_defaults` block with JSON example and CLI behavior note

### Configuration
- `.ll/ll-config.json` — new `loops.run_defaults` block (user-facing; not committed to repo)

## API/Interface

**New config block** (`config-schema.json` / `.ll/ll-config.json`):
```json
{
  "loops": {
    "run_defaults": {
      "clear": true,
      "show_diagrams": "clean",
      "mode": null
    }
  }
}
```
- `show_diagrams` valid values: topologies (`layered`, `neighborhood`, `inline`) and presets (`detailed`, `summary`, `clean`, `local`, `slim`, `oneline`, `"default"` for bare `--show-diagrams`)
- All fields optional; absent field = argparse default wins

**New dataclass** (`scripts/little_loops/config/features.py`):
```python
@dataclass
class LoopRunDefaults:
    clear: bool = False
    show_diagrams: str | None = None
    mode: str | None = None
```

**CLI behavior**: `run_defaults` values are backfilled only when the corresponding `args` attribute equals its argparse-declared default — explicit CLI flags always take precedence.

## Implementation Steps

1. Add a `LoopRunDefaults` dataclass to `scripts/little_loops/config/features.py` (where `LoopsConfig` is defined) with `clear: bool = False`, `show_diagrams: str | None = None`, `mode: str | None = None`.
2. Update `config-schema.json`: add `run_defaults` under `loops.properties` with the three fields; add `enum` for `show_diagrams` using the preset/topology names from `diagram_modes.py`.
3. In `scripts/little_loops/cli/loop/__init__.py` run handler: after `args = parser.parse_args()`, read `config.loops.run_defaults` and for each default field, only apply it when the corresponding `args` attribute is still at its argparse-declared default (`None` for `--show-diagrams`, `False` for `--clear`).
4. Add tests: `scripts/tests/test_loop_cli_defaults.py` — verify (a) config default is applied when flag omitted, (b) explicit CLI flag overrides config default, (c) invalid `show_diagrams` value raises config validation error.
5. Update `docs/guides/LOOPS_GUIDE.md` to document the new `run_defaults` block.

## Impact

- **Priority**: P3 — Quality-of-life improvement; unblocked by other work; primarily affects interactive loop users
- **Effort**: Small — new `LoopRunDefaults` dataclass, schema extension, ~20-line backfill in `__init__.py`, and one new test file; no FSM or execution logic changes
- **Risk**: Low — defaults only apply when CLI arg is at its argparse-declared default; all existing invocations with explicit flags are unaffected
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/LOOPS_GUIDE.md` | Primary loop usage guide; update with run_defaults example |
| `config-schema.json` | Schema to extend |
| `scripts/little_loops/cli/loop/diagram_modes.py` | Valid `--show-diagrams` values to enumerate |

## Labels

loops, cli, config

## Session Log
- `/ll:ready-issue` - 2026-06-13T14:51:23 - `8e139cd2-b224-4e36-8c3b-a233df5da17d.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `579b1a98-2ed2-4b4e-aa3b-ebba4a134d2b.jsonl`
- `/ll:format-issue` - 2026-06-13T14:43:30 - `fed867ff-c49e-4716-8027-9c1986e1033e.jsonl`
- `/ll:capture-issue` - 2026-06-13T14:38:41Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10f332cc-0aed-4ae6-b16b-d88cb5f34bdd.jsonl`

---

## Resolution

Implemented via:
- `LoopRunDefaults` dataclass added to `scripts/little_loops/config/features.py` with `clear`, `show_diagrams`, and `mode` fields; validates `show_diagrams` against known topology/preset values at config-load time
- `LoopsConfig.run_defaults` field added; parsed by `LoopsConfig.from_dict()`
- `config-schema.json` extended with `loops.run_defaults` object and `enum` constraint on `show_diagrams`
- Backfill logic in `scripts/little_loops/cli/loop/__init__.py` after `parse_args()` for the `run` subcommand; CLI flags always take precedence
- 11 tests in `scripts/tests/test_loop_cli_defaults.py`
- `docs/guides/LOOPS_GUIDE.md` updated with Project-Wide Run Defaults section
- `LoopRunDefaults` exported from `little_loops.config`

## Status

**done**
