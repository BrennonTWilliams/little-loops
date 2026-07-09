---
id: ENH-2557
title: Default --clear and --show-diagrams clean for ll-loop run in target projects
type: enh
status: done
priority: P3
completed_at: 2026-07-09 03:29:17+00:00
labels:
- cli
- loops
- init
- config
confidence_score: 100
outcome_confidence: 100
score_complexity: 15
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 20
---

# ENH-2557: Default --clear and --show-diagrams clean for ll-loop run in target projects

## Summary

Make `ll-loop run` default to both `--clear` (clear terminal / alt-screen between
iterations) and `--show-diagrams clean` in newly-initialized target projects, across **all**
install paths — including headless `ll-init --yes`. Achieved by flipping the two
`loops.run_defaults` schema defaults, the single source of truth that `build_config()` and
the interactive TUI fallbacks both read.

## Current Behavior

The runtime backfill was already wired: `cli/loop/__init__.py:869-875` applies
`run_defaults.clear` onto `args.clear` and `run_defaults.show_diagrams` onto
`args.show_diagrams` when the CLI flags are absent. The gap was an install-path divergence:

- **Interactive `ll-init`** already recommended `clear: true` / `show_diagrams: "clean"`
  (TUI fallbacks in `init/tui.py:444`, `:452-469`).
- **Headless `ll-init --yes` / schema-sourced** installs pulled `clear: false` /
  `show_diagrams: null` from `config-schema.json`, so those projects got neither.
  `build_config()` (`init/core.py:188-198`) sources both values from `schema_default(...)`.

## Expected Behavior

Every newly-initialized target project — interactive or headless — writes
`loops.run_defaults: {"clear": true, "show_diagrams": "clean"}`, so `ll-loop run` shows the
pinned-diagram display by default without retyping flags.

Safety: `--clear`'s terminal effects are gated on `sys.stdout.isatty()`
(`cli/loop/_helpers.py:898`, `:1622`), so defaulting it on is inert under non-interactive
automation (`ll-auto` / `ll-parallel` / headless `ll-loop`).

## Solution Implemented

Flipped the two schema defaults; no code changes were needed since `build_config()` and the
TUI fallbacks already read from the schema.

### Files Modified

- `scripts/little_loops/config-schema.json` — `loops.run_defaults.clear` default
  `false → true`; `show_diagrams` default `null → "clean"`.
- `scripts/tests/test_init_core.py` — `test_loops_run_defaults_keys` assertions flipped to
  `clear is True` / `show_diagrams == "clean"`.
- `scripts/tests/integration/test_init_e2e.py` — fresh-install assertions + comment flipped
  to the new schema-sourced defaults.
- `docs/reference/CONFIGURATION.md` — `run_defaults` defaults table updated to
  `true` / `"clean"`.

## Verification

- Targeted tests (init core + e2e + loop-defaults + TUI wiring): **299 passed**.
- Full suite (repo CI gate — `python -m pytest scripts/tests/`): **14402 passed, 36 skipped**.
- End-to-end sanity: `ll-init --yes --dry-run --plan` in a fresh project emits
  `"run_defaults": {"clear": true, "show_diagrams": "clean"}`.
- Runtime backfill remains covered by `test_loop_cli_defaults.py` (flags absent →
  `args.clear is True`, `args.show_diagrams == "clean"`).

## Impact

- **Priority**: P3
- **Effort**: Small — 2 schema default values + test/doc alignment
- **Risk**: Low — additive default; `--clear` inert under non-tty automation
- **Breaking Change**: No


## Session Log
- `hook:posttooluse-status-done` - 2026-07-09T03:29:45 - `98fc9591-6e15-49e7-89b9-9a2f58fcd3fc.jsonl`
