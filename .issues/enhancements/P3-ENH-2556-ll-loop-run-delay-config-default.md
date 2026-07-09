---
id: ENH-2556
title: Config-defaultable --delay for ll-loop run via loops.run_defaults
type: ENH
priority: P3
status: open
captured_at: "2026-07-09T03:17:41Z"
discovered_date: 2026-07-09
discovered_by: capture-issue
relates_to: [ENH-735, ENH-2454]
labels: [config, loops, cli]
---

# ENH-2556: Config-defaultable `--delay` for `ll-loop run` via `loops.run_defaults`

## Summary

Make the existing `ll-loop run --delay SECONDS` flag persistable as a project
default, mirroring how `loops.run_defaults.show_diagrams` already backfills
`--show-diagrams`. Add a `delay` key to `loops.run_defaults` (config +
`config-schema.json`) that, when set, is injected whenever the `--delay` flag is
absent. Default is **off / not included** (`null`) so behavior is unchanged for
projects that don't opt in. An explicit `--delay` on the CLI always wins.

## Motivation

`--delay` already exists (ENH-735) and serves both recording and host-memory-
pressure relief (ENH-2454), but it must be re-typed on every invocation. Users
who always want an inter-iteration pause (e.g. to relieve memory pressure on a
constrained host, or for consistent screen-recording cadence) have no way to set
it once. `show_diagrams` solved the identical ergonomics problem via
`loops.run_defaults`; `delay` should follow the same well-worn path. This is
purely additive — no default behavior changes.

## Current Behavior

- `--delay` is a `float`/`SECONDS` flag on `run` (and `resume`) that overrides
  `fsm.backoff`. It defaults to `None` and must be passed each run.
- `loops.run_defaults` already backfills `clear`, `show_diagrams`, and `include`
  from config, but has no `delay` key.

## Proposed Behavior

- New optional `loops.run_defaults.delay` (number, default `null`).
- When `args.delay is None` and `rd.delay is not None`, set `args.delay = rd.delay`
  in the run-defaults backfill block — the same spot `show_diagrams` is backfilled.
- Explicit `--delay` always overrides the config default.
- Absent/`null` config key ⇒ no injection ⇒ current behavior preserved.

## API/Interface

`config-schema.json` addition under `loops.run_defaults.properties`:

```json
"delay": {
  "type": ["number", "null"],
  "description": "Inject --delay <seconds> into every ll-loop run invocation (inter-iteration pause). Explicit --delay overrides. Null disables.",
  "default": null,
  "minimum": 0
}
```

## Implementation Steps

1. **Dataclass** — add `delay: float | None = None` to `LoopRunDefaults`
   (`scripts/little_loops/config/features.py:614`) and read it in `from_dict`
   (`...:631`), validating it's a non-negative number when present.
2. **Schema** — add the `delay` property to `loops.run_defaults` in
   `scripts/little_loops/config-schema.json:950` (block ends ~:977).
3. **Backfill** — in the `run`-command run-defaults block
   (`scripts/little_loops/cli/loop/__init__.py:869-875`), add:
   `if args.delay is None and rd.delay is not None: args.delay = rd.delay`.
4. **Verify passthrough** — `--delay` is already consumed at `run.py:128-129`
   and `lifecycle.py:529-530` (sets `fsm.backoff`); no change needed there once
   `args.delay` is populated.
5. **Tests** — cover: config default injected when flag absent; explicit
   `--delay` overrides config; `null`/absent ⇒ no injection.

## Root Cause / Anchors

- CLI flag def: `scripts/little_loops/cli/loop/__init__.py:140` (`--delay`)
- Run-defaults backfill (pattern to mirror): `...cli/loop/__init__.py:869-875`
- Dataclass: `scripts/little_loops/config/features.py:614` (`LoopRunDefaults`)
- Schema: `scripts/little_loops/config-schema.json:950` (`run_defaults`)
- Flag consumption: `cli/loop/run.py:128` and `cli/loop/lifecycle.py:529`

## Acceptance Criteria

- [ ] `loops.run_defaults.delay` accepted in config and `config-schema.json`,
      default `null`, validated as non-negative number.
- [ ] With `delay: N` set and no `--delay` flag, `ll-loop run` pauses N seconds
      between iterations.
- [ ] Explicit `--delay M` overrides the configured `N`.
- [ ] Absent/`null` config key produces identical behavior to today.
- [ ] `python -m pytest scripts/tests/` passes (new tests included).

## Session Log
- `/ll:capture-issue` - 2026-07-09T03:17:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6ebdc66-ddb5-46f2-ab91-46e0483cfd6d.jsonl`

---

## Status
- **Created**: 2026-07-09
- **Priority**: P3
- **Type**: ENH
