---
id: ENH-2109
title: "ll-loop run: persistent default flags via config (--clear, --show-diagrams, --mode)"
type: ENH
status: open
priority: P3
captured_at: "2026-06-13T14:38:41Z"
discovered_date: "2026-06-13"
discovered_by: capture-issue
labels: [loops, cli, config]
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

## Proposed Solution

1. **Schema** (`config-schema.json`): Add a `run_defaults` object under `loops` with:
   - `clear` (`boolean`, default `false`) — if `true`, inject `--clear`
   - `show_diagrams` (`string | null`, default `null`) — if non-null, inject `--show-diagrams <value>`; valid values mirror the `--show-diagrams` argument: topologies (`layered`, `neighborhood`, `inline`) and presets (`detailed`, `summary`, `clean`, `local`, `slim`, `oneline`); bare `true` (for the no-value form) can be represented as `"default"`
   - `mode` (`string | null`, default `null`) — if non-null, inject `--mode <value>` (future-proofing for any `--mode` flag added to `ll-loop run`)

2. **Runner** (`scripts/little_loops/cli/loop/__init__.py`): After `parse_args()`, load the `loops.run_defaults` config block and backfill any unset args with config values before dispatching to the run handler. Explicit CLI flags (where `argparse` sets a non-default value) take precedence.

3. **Schema validation**: Add enum constraints for `show_diagrams` that mirror `_PARSE_SHOW_DIAGRAMS_VALID` in `scripts/little_loops/cli/loop/diagram_modes.py` so invalid values are caught at config-load time.

## Integration Map

- `config-schema.json` — add `loops.run_defaults` object with `clear`, `show_diagrams`, `mode` properties
- `scripts/little_loops/cli/loop/__init__.py` — inject defaults after `parse_args()` in the `run` subcommand handler, before dispatching
- `scripts/little_loops/cli/loop/diagram_modes.py` — re-export the valid values list for schema enum generation
- `scripts/little_loops/config.py` (or equivalent config loader) — expose `loops.run_defaults` as a typed config field

## Implementation Steps

1. Locate where `loops` config is loaded (likely `scripts/little_loops/config.py`) and add a `LoopRunDefaults` dataclass with `clear: bool = False`, `show_diagrams: str | None = None`, `mode: str | None = None`.
2. Update `config-schema.json`: add `run_defaults` under `loops.properties` with the three fields; add `enum` for `show_diagrams` using the preset/topology names from `diagram_modes.py`.
3. In `scripts/little_loops/cli/loop/__init__.py` run handler: after `args = parser.parse_args()`, read `config.loops.run_defaults` and for each default field, only apply it when the corresponding `args` attribute is still at its argparse-declared default (`None` for `--show-diagrams`, `False` for `--clear`).
4. Add tests: `scripts/tests/test_loop_cli_defaults.py` — verify (a) config default is applied when flag omitted, (b) explicit CLI flag overrides config default, (c) invalid `show_diagrams` value raises config validation error.
5. Update `docs/guides/LOOPS_GUIDE.md` to document the new `run_defaults` block.

## Impact

- **Users**: No friction for repeat flag patterns; display settings persist across sessions.
- **Scope**: Config-layer change only; no FSM execution logic touched.
- **Risk**: Low — defaults only apply when CLI arg is at its null/false default; existing invocations with explicit flags are unaffected.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/LOOPS_GUIDE.md` | Primary loop usage guide; update with run_defaults example |
| `config-schema.json` | Schema to extend |
| `scripts/little_loops/cli/loop/diagram_modes.py` | Valid `--show-diagrams` values to enumerate |

## Labels

loops, cli, config

## Session Log
- `/ll:capture-issue` - 2026-06-13T14:38:41Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10f332cc-0aed-4ae6-b16b-d88cb5f34bdd.jsonl`

---

## Status

**open** — ready for refinement
