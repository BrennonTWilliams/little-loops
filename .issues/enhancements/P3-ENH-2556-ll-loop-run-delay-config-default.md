---
id: ENH-2556
title: Config-defaultable --delay for ll-loop run via loops.run_defaults
type: ENH
priority: P3
status: done
captured_at: '2026-07-09T03:17:41Z'
completed_at: '2026-07-10T00:17:12Z'
discovered_date: 2026-07-09
discovered_by: capture-issue
relates_to:
- ENH-735
- ENH-2454
labels:
- config
- loops
- cli
confidence_score: 100
outcome_confidence: 88
score_complexity: 21
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 22
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
   (`scripts/little_loops/config/features.py:613-620`) and read it in
   `from_dict` (`...:622-636`), validating it's a non-negative number when
   present. `config/features.py` has **no existing numeric-bound validation**
   precedent (only string-enum `raise ValueError` checks, e.g. `show_diagrams`
   at line 624); mirror the `show_diagrams` `raise ValueError(f"loops.run_defaults....: ...")`
   shape but test `isinstance(delay, (int, float)) and not isinstance(delay, bool)`
   then `delay < 0`, following the numeric-bound idiom used in
   `scripts/little_loops/fsm/validation.py` (`cost_ceiling` block lines
   960-995; `backoff` check line 1188: `if fsm.backoff is not None and
   fsm.backoff < 0: ...`).
2. **Schema** — add the `delay` property to `loops.run_defaults` in
   `scripts/little_loops/config-schema.json:950-977` (`additionalProperties:
   false` is set on this block — an unlisted `delay` key is schema-rejected
   until added).
3. **Backfill** — in the `run`-command run-defaults block
   (`scripts/little_loops/cli/loop/__init__.py:869-875`), add:
   `if args.delay is None and rd.delay is not None: args.delay = rd.delay`.
   This matches the existing `show_diagrams` None-sentinel idiom exactly
   (`--delay` is `type=float, default=None`, same shape as `--show-diagrams`).
   Note `--delay` is defined **twice** — once for `run` (line 140-149) and
   once for `resume` (line 483-490) — but only the `run`-command backfill
   block needs the addition per the issue's stated scope (resume already
   reads `args.delay` via `getattr(args, "delay", None)` at
   `lifecycle.py:529-530`, so if `resume` should also honor the config
   default, confirm whether `resume` shares the same backfill block or needs
   a duplicate — currently the block is gated on `args.command == "run"` only).
4. **Verify passthrough** — `--delay` is already consumed at `run.py:128-129`
   and `lifecycle.py:529-530` (sets `fsm.backoff`); no change needed there once
   `args.delay` is populated.
5. **Init/scaffolding** — `scripts/little_loops/init/core.py` `build_config()`
   (lines 77-200) constructs the initial `loops.run_defaults` block from
   schema defaults (lines 188-198); confirm the new `delay: null` default
   flows through automatically (it should, since `build_config` reads schema
   defaults) but verify via `test_init_core.py`. `init/tui.py` (lines 444,
   460) reads existing `run_defaults` for interactive-init fallback display —
   no code change expected there since `delay` defaults to `null`/unset.
6. **Docs** — update `docs/reference/CONFIGURATION.md` (`loops.run_defaults`
   field table, lines 868-877) and `docs/reference/API.md`
   (`LoopRunDefaults` dataclass docs, lines 537-542) to document the new
   `delay` field.
7. **Tests** — extend `scripts/tests/test_loop_cli_defaults.py`, which already
   covers this exact backfill mechanism for `clear`/`show_diagrams`/`include`
   across two classes:
   - `TestLoopRunDefaultsDataclass` (lines 130-206): add a `delay` case to
     `test_from_dict_defaults` (line 133, assert `result.delay is None`), plus
     new `test_from_dict_delay_valid` / `test_from_dict_delay_negative_raises`
     tests modeled on `test_from_dict_show_diagrams_valid`/`_invalid_raises`
     (lines 171, 190).
   - `TestLoopRunDefaults` (lines 13-127, CLI-level via `main_loop()`): add
     `test_delay_default_applied_from_config` modeled on
     `test_show_diagrams_default_applied_from_config` (line 58), and
     `test_explicit_delay_overrides_config` modeled on
     `test_explicit_show_diagrams_overrides_config` (line 76), plus a
     `test_invalid_delay_in_config_raises_value_error` modeled on
     `test_invalid_show_diagrams_in_config_raises_value_error` (line 116).
   - Cover: config default injected when flag absent; explicit `--delay`
     overrides config; `null`/absent ⇒ no injection (no test class currently
     asserts this for a numeric field the way
     `test_empty_config_include_leaves_context_unset`, line 293, does for
     `include` — model the assertion shape but note `include` injects into
     `fsm.context`, not `args`, so it's not a direct template for the
     `args.delay` assertion).
   - `scripts/tests/test_ll_loop_parsing.py:244-260` already covers `--delay`
     argparse parsing in isolation (`test_delay_flag_accepts_float`,
     `test_delay_flag_accepts_zero`, `test_delay_default_is_none`) — no
     changes needed there.
   - `scripts/tests/test_cli_loop_dispatch.py:716` (`test_delay_forwarded`)
     covers explicit `--delay` full-dispatch forwarding — no changes needed
     there; it's a useful reference for the dispatch-level mocking pattern
     (`_mock_handlers`, `_make_loop_project` fixtures at lines 26, 61) if a
     dispatch-level config-backfill test is added instead of/in addition to
     the `test_loop_cli_defaults.py` tests.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation. They are additive to Steps 1-7 above._

8. **Schema-conformance test** — add `test_loops_run_defaults_in_schema` to
   `scripts/tests/test_config_schema.py` guarding `delay` against
   `additionalProperties: false` (model on `test_health_url_in_schema`). This is
   the only test-enforced wiring surface; the rest below are consistency-only.
9. **Configure skill** — wire `delay` into `/ll:configure loops.run_defaults`:
   `skills/configure/areas.md` (values block, field description, JSON example,
   TUI question), `skills/configure/show-output.md` (`--show` mockup line), and
   `skills/configure/SKILL.md` (two parenthetical field lists).
10. **Guide + CLI docs** — add `delay` to `docs/guides/LOOPS_GUIDE.md`
    `run_defaults` section (JSON example + prose) and optionally cross-reference
    config-defaultability from the two `--delay` rows in `docs/reference/CLI.md`
    (lines 527, 747).
11. **Dataclass default-shape test** — extend
    `test_loop_cli_defaults.py::TestLoopRunDefaultsDataclass::test_from_dict_defaults`
    with `assert result.delay is None` and add a `delay` key to
    `test_loops_config_includes_run_defaults`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- All anchors cited in the original issue were verified accurate against the
  current codebase (confirmed by `codebase-analyzer`): `LoopRunDefaults`
  class/fields at `config/features.py:613-620`, `from_dict` at `:622-636`,
  backfill block at `cli/loop/__init__.py:869-875` (exact match), `--delay`
  flag at `:140-149`, `run.py:128-129`, `lifecycle.py:529-530`, and
  `config-schema.json:950-977`.
- `--delay` is defined **twice** in `cli/loop/__init__.py` — once for the
  `run` subparser (140-149) and once for `resume` (483-490) — but the
  run-defaults backfill block only exists for `args.command == "run"`. The
  issue's proposed backfill line only patches `run`; whether `resume` should
  also honor `loops.run_defaults.delay` is unresolved (see Implementation
  Step 3).
- A near-identical precedent exists: `ENH-2371` ("add loops.run_defaults
  include config field", completed) added the `include` field to
  `LoopRunDefaults` following the same dataclass → schema → backfill →
  tests sequence — useful as a second reference precedent alongside
  `show_diagrams`, though `include` backfills into `fsm.context` rather than
  `args`, so `show_diagrams` remains the closer structural template for
  `delay`.
- `scripts/little_loops/init/core.py:build_config()` (77-200) and
  `init/tui.py` (444, 460) also read/construct `loops.run_defaults` — not
  mentioned in the original issue's Integration Map. These likely need no
  code change (schema defaults propagate automatically) but should be
  covered by existing `test_init_core.py` / `test_init_e2e.py` runs as a
  regression check.
- Docs not covered by the original issue: `docs/reference/CONFIGURATION.md`
  (field table, lines 868-877) and `docs/reference/API.md`
  (`LoopRunDefaults` dataclass docs, lines 537-542) both document
  `run_defaults` fields today and should be updated for consistency, though
  neither is enforced by a test.

## Integration Map (Wiring Pass)

_Wiring pass added by `/ll:wire-issue` — surfaces not covered by the original
Integration Map / Implementation Steps. `show_diagrams` and `mode` set the
precedent for every one of these: any file that enumerates `run_defaults` fields
needs a `delay` entry to stay consistent (none are test-enforced except
`test_config_schema.py`)._

### Configuration Skill Surface (`/ll:configure loops.run_defaults`)

The `/ll:configure` skill is the interactive registration path for
`run_defaults` fields — the direct behavioral analog to the `show_diagrams`
"structural precedent" the issue leans on. Adding `delay` as a config key
without wiring the configure skill leaves it undiscoverable via `/ll:configure`
and its field lists reading as stale:

- `skills/configure/areas.md` — `## Area: loops.run_defaults` (line 1383). Add a
  `delay:` row to the current-values display block (lines 1390-1392), a
  `**`delay`**` field description under line 1400, a `delay` key in the JSON
  example (lines 1411-1420), and a `delay` TUI question modeled on the
  `show_diagrams` question at line 1436 [Agent 2 finding]
- `skills/configure/show-output.md` — `## loops.run_defaults --show` mockup
  (lines 263-265) enumerates `clear`/`show_diagrams`/`mode`; add a `delay:` line
  [Agent 2 finding]
- `skills/configure/SKILL.md` — parenthetical field lists at line 119 (table
  row) and line 152 (inline help) both read `(clear, show_diagrams, mode)`; add
  `delay` [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — the `loops.run_defaults` block section (lines
  613-636) shows a JSON example with `clear`/`show_diagrams` only and lists the
  readable fields; add `delay` to the example and prose [Agent 2 finding]
- `docs/reference/CLI.md` — `--delay` flag-description rows appear **twice**
  (lines 527 and 747, `run` and `resume` tables); optionally note the flag is
  now config-defaultable via `loops.run_defaults.delay` [Agent 1 + 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — **new test needed**. This file is the
  established per-block schema-conformance convention (one test per config block
  that has `additionalProperties: false`), but there is **no `run_defaults` test
  today at all** — the schema side of `delay` would ship with zero regression
  coverage. Add `test_loops_run_defaults_in_schema` asserting `delay` is declared
  with `type: ["number","null"]`, `default: null`, and that
  `additionalProperties` is `false`. Closest nullable-number analog to model:
  `test_health_url_in_schema` (~lines 257-277) [Agent 3 finding]
- `scripts/tests/test_loop_cli_defaults.py::TestLoopRunDefaultsDataclass::test_from_dict_defaults`
  (line 133) — enumerates every default field; add `assert result.delay is None`
  (does not break, but incomplete by this file's convention) [Agent 3 finding]
- `scripts/tests/test_loop_cli_defaults.py::TestLoopRunDefaultsDataclass::test_loops_config_includes_run_defaults`
  (~line 197) — extend the parsed `run_defaults` block with a `delay` key and
  assert it round-trips [Agent 3 finding]

### Scope Clarification — init generated config (corrects Impl Step 5)

Implementation Step 5 assumes `build_config()` "reads schema defaults" so
`delay: null` "flows through automatically." Agent 3 confirmed
`init/core.py:build_config()` (lines 188-198) writes **only** `clear` and
`show_diagrams` keys explicitly — it does not emit `mode`, `include`, or (after
this change) `delay` into the generated `run_defaults`. `test_init_core.py`
even asserts `"mode" not in rd`. This is fine — an absent key reads as
`null`/disabled — so **no `init/core.py` code change is required**, but the
issue's stated *reason* is inaccurate: the key is absent, not defaulted-through.
No new init wiring is in scope. [Agent 3 finding]

### Files confirmed NOT to break (no change needed)

- `scripts/tests/integration/test_init_e2e.py` (lines 65-71) — asserts only
  `clear`/`show_diagrams` by key, no exhaustive shape check [Agent 3]
- `scripts/tests/test_init_core.py::test_loops_run_defaults_keys` — asserts
  `"mode" not in rd`; unaffected since `delay` isn't wired into `build_config`
  [Agent 3]
- `scripts/tests/test_cli_loop_worktree.py` `_mock_br_config` (~line 826) —
  MagicMock auto-vivifies `run_defaults.delay`; no strict spec, won't raise
  [Agent 3]
- `scripts/tests/test_cli_loop_lifecycle.py` (fixtures at lines 1276, 1372
  already carry `args.delay`) — dispatch-level, unaffected [Agent 1]
- `LoopRunDefaults` has no `to_dict`/`asdict` serializer and no external
  construction sites, so adding a field breaks no round-trip contract [Agent 2]

### FYI (no change required)

- `.ll/ll-config.json` (lines 92-95) — this project's own dogfooded
  `run_defaults` block (`clear`/`show_diagrams`); a `delay` example could be
  added but is optional [Agent 1 + 2]
- `CHANGELOG.md` — prior `run_defaults` field additions (ENH-2371 `include`,
  ENH-2109 initial fields) each added a dated release-section bullet; follow the
  same pattern at release time (not `[Unreleased]`) [Agent 2]

## Root Cause / Anchors

- CLI flag def: `scripts/little_loops/cli/loop/__init__.py:140-149` (`run`
  subparser `--delay`); duplicated at `:483-490` for `resume`
- Run-defaults backfill (pattern to mirror): `...cli/loop/__init__.py:869-875`
  — gated on `args.command == "run"` only
- Dataclass: `scripts/little_loops/config/features.py:613-620`
  (`LoopRunDefaults`), `from_dict` at `:622-636`
- Schema: `scripts/little_loops/config-schema.json:950-977` (`run_defaults`,
  `additionalProperties: false`)
- Flag consumption: `cli/loop/run.py:128-129` and `cli/loop/lifecycle.py:529-530`
- Numeric non-negative validation idiom (no precedent in `config/features.py`
  itself): `scripts/little_loops/fsm/validation.py` `cost_ceiling` block
  (960-995), `backoff` check (1188-1194)
- Precedent issue (same dataclass→schema→backfill→tests sequence):
  `ENH-2371` (`include` field, completed)
- Primary test file to extend: `scripts/tests/test_loop_cli_defaults.py`
  (`TestLoopRunDefaults` 13-127, `TestLoopRunDefaultsDataclass` 130-206)
- Secondary tests (no change expected, confirm still pass):
  `scripts/tests/test_ll_loop_parsing.py:244-260`,
  `scripts/tests/test_cli_loop_dispatch.py:716`
- Init scaffolding (verify, likely no code change):
  `scripts/little_loops/init/core.py:build_config()` (77-200),
  `scripts/little_loops/init/tui.py` (444, 460)
- Docs to update: `docs/reference/CONFIGURATION.md` (868-877),
  `docs/reference/API.md` (537-542)

## Acceptance Criteria

- [x] `loops.run_defaults.delay` accepted in config and `config-schema.json`,
      default `null`, validated as non-negative number.
- [x] With `delay: N` set and no `--delay` flag, `ll-loop run` pauses N seconds
      between iterations.
- [x] Explicit `--delay M` overrides the configured `N`.
- [x] Absent/`null` config key produces identical behavior to today.
- [x] `python -m pytest scripts/tests/` passes (new tests included). *(3 pre-existing
      `rn-refine.yaml` failures are unrelated to this change and pre-date it — see
      Resolution.)*

## Resolution

Implemented `loops.run_defaults.delay` following the `show_diagrams` structural
precedent exactly:

- **Dataclass** (`config/features.py`) — added `delay: float | None = None` to
  `LoopRunDefaults` with non-negative-number validation in `from_dict` (rejects
  `bool`, non-numeric, and negative values with a `ValueError`).
- **Schema** (`config-schema.json`) — added `delay` (`["number","null"]`,
  `default null`, `minimum 0`) under `loops.run_defaults`.
- **Backfill** (`cli/loop/__init__.py`) — `if args.delay is None and rd.delay is
  not None: args.delay = rd.delay`, gated on `args.command == "run"`. `resume`
  intentionally left untouched per the issue's stated scope. Explicit `--delay`
  always wins (populated by argparse before backfill runs).
- **Tests** — extended `test_loop_cli_defaults.py` (CLI-level + dataclass-level:
  default injection, explicit override, no-injection-when-absent, negative/
  non-numeric ValueError) and added `test_loops_run_defaults_in_schema` to
  `test_config_schema.py`.
- **Docs/skill wiring** — `CONFIGURATION.md`, `API.md`, `CLI.md`, `LOOPS_GUIDE.md`,
  and the `/ll:configure` skill (`areas.md`, `show-output.md`, `SKILL.md`).

No `init/core.py` change (an absent key reads as `null`/disabled, matching `mode`
and `include`).

**Test status:** all new tests pass; the full suite has 14445 passing. Three
pre-existing failures (`test_rn_refine.py::…test_synthesis_chain_present`,
`test_builtin_loops.py::…test_no_bare_bash_variable_in_shell_actions`,
`test_builtin_loop_interpolation.py[rn-refine.yaml]`) concern `rn-refine.yaml`
(under active separate work, ENH-2565) and were confirmed to fail on a clean
checkout without this change — they are out of scope for ENH-2556.

## Session Log
- `/ll:manage-issue` - 2026-07-10T00:16:30Z - `cd9248df-cb6b-4a02-ab4e-6a0ce1569d84.jsonl`
- `/ll:ready-issue` - 2026-07-10T00:07:55 - `c0d62f64-6612-4398-a221-482107328da4.jsonl`
- `/ll:confidence-check` - 2026-07-09T23:45:00 - `3900346d-dd47-4b19-b25f-58b0143712e9.jsonl`
- `/ll:wire-issue` - 2026-07-09T23:34:17 - `c7eb1b8c-0172-49ad-b14a-4a7ee79cd87b.jsonl`
- `/ll:refine-issue` - 2026-07-09T23:24:37 - `c8cd61c2-73e4-42dd-b1c2-a08f953c8a46.jsonl`
- `/ll:capture-issue` - 2026-07-09T03:17:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6ebdc66-ddb5-46f2-ab91-46e0483cfd6d.jsonl`

---

## Status
- **Created**: 2026-07-09
- **Priority**: P3
- **Type**: ENH
