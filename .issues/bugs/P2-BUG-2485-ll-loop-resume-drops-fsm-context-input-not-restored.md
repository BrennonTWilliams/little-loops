---
id: BUG-2485
title: '`ll-loop resume` drops `fsm.context` (including `input`), so resumed states
  fail immediately with "Path ''input'' not found in context"'
type: BUG
status: open
priority: P2
captured_at: '2026-07-05T21:49:56Z'
discovered_date: '2026-07-05'
discovered_by: capture-issue
labels:
- fsm
- loop-runner
- persistence
- resume
confidence_score: 98
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-2485: `ll-loop resume` drops `fsm.context` (including `input`), so resumed states fail immediately

## Summary

The `ll-loop stop` → `ll-loop resume` cycle does **not** persist or restore the
FSM's `context` dict. Any context key injected at loop-start — the positional
`input` task-description string, `program.md` fields, and any programmatic
`--context KEY=VALUE` values — is lost when a running loop is stopped and never
restored on resume. Every resumed state whose action template references
`${context.input}` (or any other lost key) fails immediately with
`Path 'input' not found in context`.

Resume *appears* to work — the CLI returns no error and the correct
state/iteration are restored — right up until every templated action fails and
the loop terminates (`failed`) within the same second, discarding all subsequent
progress.

**Observed in run:** `general-task-20260705T124158` (via `/ll:debug-loop-run
general-task` against the `cards` project). Stopped mid-`do_work` at iteration
105; resumed at iteration 106; failed at iteration 114 with zero productive work.

## Current Behavior

1. At `ll-loop run <loop> "<input>"`, the positional input lands in
   `fsm.context[fsm.input_key]` (`cli/loop/run.py:138-151`). `program.md` fields
   (`:157-158`) and `--context` overrides (`:159-163`) also populate `fsm.context`.
2. State is persisted to `<instance>.state.json` via `LoopState.to_dict()`, which
   serializes `captured`, `prev_result`, retry counters, `messages`, timing — **but
   not `fsm.context`**.
3. On resume, `cmd_resume()` calls `load_loop()` to build a **fresh** FSM with an
   empty/YAML-default context, then re-derives only `run_dir` and (conditionally)
   `input_hash`. `PersistentExecutor.resume()` restores executor bookkeeping but
   never touches `fsm.context`.
4. `${context.input}` therefore resolves against an empty context and raises
   `Path 'input' not found in context` on every templated action.

## Expected Behavior

On `ll-loop resume <loop>`, the full original FSM context — including `input` and
any other programmatically-injected keys — is reloaded from the persisted state so
resumed actions render identically to how they would have rendered had the loop
never been stopped. CLI `--context` overrides supplied at resume time should still
win over the restored values.

## Steps to Reproduce

1. Start a loop that references `${context.input}` in its states (e.g.
   `general-task`): `ll-loop run general-task "Do the distinctive task XYZ"`.
2. Let it advance a few iterations into `do_work`, then `ll-loop stop general-task`.
3. `ll-loop resume general-task`.
4. Observe `events.jsonl`: every resumed state emits
   `action_error error="Path 'input' not found in context"` → `retry_exhausted`
   → `diagnose` → `failed`, within the same second. Only `diagnose` (whose
   template has no `${context.input}` ref) executes cleanly, confirming the missing
   variable is the defect, not a broader context-restore failure.

## Root Cause

The FSM `context` dict is not part of the serialized runner state. Two-stage
failure:

1. **Serialize-time loss** — `PersistentExecutor._save_state()`
   (`fsm/persistence.py:737-766`) and the final-state builder in `run()`
   (`:793-806`) never pass `self.fsm.context` into the `LoopState` constructor.
   The `LoopState` dataclass (`:163-218`) has no `context` field, and
   `to_dict()`/`from_dict()` (`:220-304`) neither write nor read one.

2. **Resume-time no-op** — `PersistentExecutor.resume()` (`:812-870`) restores
   `current_state`, `iteration`, `captured`, `prev_result`, retry counters, and
   `messages` onto the executor, but never restores `fsm.context`. Meanwhile
   `cmd_resume()` (`cli/loop/lifecycle.py:466`) builds a fresh FSM and re-injects
   only `run_dir` (`:493-494`) and `input_hash` (`:497-498`). The `input_hash`
   guard is effectively dead code on resume because it is gated on
   `isinstance(fsm.context.get("input"), str)` — and `input` was never restored.

`run_dir` and `design_tokens_context` survive resume only because they are
independently re-derived; `input` has no such re-derivation path.

## Impact

- **Priority**: P2 — Significant reliability gap. Any `general-task`-style loop
  (or any loop referencing `${context.input}` in a resumed state) fails
  immediately after stop/resume, forcing a full restart from scratch or manual
  context patching.
- **Effort**: Small — Add one persisted field + populate it at save time +
  restore it at resume time; localized to `persistence.py` and `lifecycle.py`.
- **Risk**: Low — Additive persistence field with a JSON-serializability guard;
  old state files without the field load unchanged (default `{}`).
- **Breaking Change**: No — restores intended behavior; no schema break for
  existing state files.

**Downstream effects:**
- The bug is not `input`-specific: `program.md` fields and any programmatic
  `--context` key set at start are equally lost, so the general fix covers all of
  them.
- Users currently must avoid `ll-loop stop`/`resume` entirely for
  `${context.input}`-dependent loops, or re-run fresh and duplicate all work up to
  the stop point.

## Proposed Solution

Persist and restore `fsm.context` as first-class runner state, rather than a
one-off `input` patch:

1. Add a `context: dict[str, Any]` field to `LoopState`
   (`fsm/persistence.py:163`), serialized in `to_dict()` with a JSON-safe filter
   (drop non-serializable values, debug-log what is dropped) and read back in
   `from_dict()` with a default of `{}` for backward compatibility.

2. Populate it wherever state is snapshotted — `_save_state()` (`:745`) and the
   final-state builder in `run()` (`:793`) — from `dict(self.fsm.context)`. Because
   `_save_state()` fires on every `state_enter`, this captures the live context as
   of the last checkpoint (better fidelity than start-only).

3. Seed the restored context in `cmd_resume()` (`cli/loop/lifecycle.py`), where
   the `LoopState` is already in hand as `state_for_display` (`:433`). Insert the
   restore immediately after `load_loop()` (`:466`) and **before** the existing
   `--context` loop (`:485`), so precedence is: restored persisted context (base)
   → `--context` CLI overrides win → the `if not in`-guarded re-derivations
   (`run_dir`, `input_hash`, `design_tokens_context`) fill or no-op. With `input`
   restored, the `input_hash` derivation at `:497-498` now works correctly.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/persistence.py`
  - `LoopState` dataclass (`:163-218`) — add `context: dict[str, Any] = field(default_factory=dict)`
  - `LoopState.to_dict()` (`:220-254`) — emit `context` (JSON-safe filtered) when non-empty
  - `LoopState.from_dict()` (`:256-304`) — read `context` with `.get("context", {})`
  - `PersistentExecutor._save_state()` (`:745-766`) — pass `context=dict(self.fsm.context)` (filtered)
  - `PersistentExecutor.run()` final-state builder (`:793-806`) — same
- `scripts/little_loops/cli/loop/lifecycle.py`
  - `cmd_resume()` — seed `fsm.context` from `state_for_display.context` after `load_loop()` (`:466`), before the `--context` loop (`:485`)

### Dependent / Reference Files

- `scripts/little_loops/cli/loop/run.py:138-163` — the injection points whose
  values must survive round-trip (`input`, `program.md`, `--context`)
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.input_key` (default `"input"`);
  the persisted context key is `fsm.input_key`, not hardcoded `"input"`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — **serializes `LoopState.to_dict()`
  directly** into `ll-loop status --json` / `ll-loop list --json`
  (`print_json([s.to_dict() for s in states])`). Because the fix emits `context`
  from `to_dict()` (truthiness-gated), the restored context dict will now **leak
  into CLI JSON output**. This is a design decision the issue does not yet
  resolve — see "JSON-output contract decision" below. [Agent 1/2 finding]
- `scripts/little_loops/session_store.py` — `_backfill_loops()` `json.loads()`s
  every `.state.json` but reads only `loop_name`/`current_state`/`updated_at` via
  `.get()`; the new `context` key is silently ignored — **no change needed, FYI
  only**. [Agent 2 finding]
- `scripts/little_loops/fsm/__init__.py` — exports `LoopState` /
  `PersistentExecutor` / `StatePersistence`; no new symbol is added, so **no
  change needed**. [Agent 1 finding]

### JSON-output contract decision (added by `/ll:wire-issue`)

The Proposed Solution emits `context` from `LoopState.to_dict()` whenever
non-empty. `cli/loop/info.py` feeds `to_dict()` straight into the documented
`ll-loop status --json` / `ll-loop list --json` contract, so restored context
(including the full `input` string and any `--context` values) becomes
**user-visible CLI JSON**. Implementer must choose one:

1. **Document it** — add a `context` row to the field table in
   `docs/reference/json-output-contracts.md` and accept it in the public
   contract. (Simplest; exposes possibly-large/verbose context in status output.)
2. **Keep it internal** — persist `context` in the `.state.json` on-disk state
   but strip it from the CLI-facing dict path (e.g. an `info.py`-side filter or a
   `to_dict(include_context=False)` param), so resume works without changing the
   status JSON contract.

Recommendation: option 2 keeps the fix scoped to persistence/resume and avoids a
public JSON-contract change, but either is acceptable — the choice must be made
explicitly, not by accident.

### Tests

- `scripts/tests/test_fsm_persistence.py` — add a regression test: start a loop
  with a distinctive `input` string (and a second `--context` key), save state
  mid-`do_work`, resume, and assert the resumed state's rendered action template
  contains the original `input` value (and the second key) rather than raising
  `Path 'input' not found in context`.
- Follow the existing `test_signal_interrupted_loop_can_be_resumed` fixture
  pattern in the same file for the stop/resume harness.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_lifecycle.py` — **coverage gap to close.**
  `test_input_hash_injected_via_cmd_resume` (`:843-871`) fully **mocks
  `PersistentExecutor`** and manually sets `mock_fsm.context = {"input": ...}`
  before calling `cmd_resume` — so it assumes `input` is already present and
  **structurally cannot catch BUG-2485**. Every `TestCmdResume*` class here mocks
  the executor, so none exercises a real `.state.json` → `resume()` round-trip.
  The new regression test therefore belongs in `test_fsm_persistence.py` (real,
  non-mocked executor), not here. Optionally add a `cmd_resume`-level test that
  does NOT mock the restore path. [Agent 3 finding]
- `scripts/tests/test_json_output_contracts.py` — `TestLoopStatusJsonContract` /
  `_make_loop_state()` / `REQUIRED_FIELDS` consume `LoopState(**defaults)` and
  `to_dict()`. Safe against the new field (default `dict`; `REQUIRED_FIELDS` uses
  subset containment, not strict key-set match — verified no `to_dict() == {...}`
  full-dict assertion exists anywhere). If option 1 of the JSON-contract decision
  is chosen, add a `context` assertion here; if option 2, assert `context` is
  **absent** from the status-JSON dict. [Agent 2/3 finding]
- `scripts/tests/test_ll_loop_commands.py` — constructs `LoopState(...)` directly
  at 4 sites; won't break (new field defaults) but never sets/asserts `context`.
  No change required. [Agent 2 finding]
- **New-field test trio (confirmed pattern):** model on the `rate_limit_retries`
  dict-field tests — roundtrip (`test_fsm_persistence.py:2276`), omitted-when-empty
  (`:2358`), defaults-when-missing (`:2374`) — plus the save+resume pair
  `test_save_state_includes_rate_limit_retries` (`:2391`) /
  `test_resume_restores_rate_limit_retries` (`:2425`), which exercise the real
  `_save_state()` write path that currently omits `context`. The render-path
  regression should mirror `test_resume_preserves_captured_for_interpolation`
  (`:1626-1683`) with `action='echo "${context.input}"'`. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### LoopState` field-list code block; add a
  `context` row (block is already stale — also missing `accumulated_ms`,
  `retry_counts`, `continuation_prompt`). [Agent 2 finding]
- `docs/reference/json-output-contracts.md` — `## ll-loop status --json` example
  + field-reference table; update per the JSON-output contract decision above
  (add `context` row, or note it is intentionally omitted). [Agent 2 finding]
- `docs/generalized-fsm-loop.md` — `### State Persistence` illustrative
  `.state.json` example; optional — could show `input`/`context` restoration
  (currently shows none). [Agent 2 finding]
- `skills/debug-loop-run/SKILL.md` — Step 1 enumerates `LoopState` JSON fields for
  agent consumption; partial/curated subset, optional update. [Agent 2 finding]
- `CHANGELOG.md` — add an entry under a concrete `## [X.Y.Z] - DATE` section (not
  `[Unreleased]`, per project convention). [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (all pre-existing line
references above were independently verified accurate against current code):_

- **No JSON-safe filter helper exists to reuse.** The Proposed Solution assumes a
  "drop non-serializable values, debug-log what is dropped" filter, but no such
  helper exists anywhere in `scripts/little_loops/`. The codebase idiom for
  tolerating non-serializable values is `json.dumps(value, default=str)`
  (stringify-fallback), used at `session_store.py:1439-1445` (`_hash_args`) and
  `post_tool_use.py:153-154` — *not* key-dropping. Moreover,
  `StatePersistence.save_state()` (`fsm/persistence.py:339-358`) currently calls
  plain `json.dumps(state.to_dict(), indent=2)` with **no `default=` and no
  try/except** — a non-serializable context value would raise uncaught inside
  `save_state()`. Implementer decision: write a small new drop-and-debug-log
  filter (as the issue describes), or adopt the existing `default=str` idiom. If
  the filter drops keys, prefer it over `default=str` so restored context keys
  round-trip to their original types rather than to stringified reprs.

- **Closer test analog than the cited fixture.**
  `test_resume_preserves_captured_for_interpolation`
  (`test_fsm_persistence.py:1626-1683`) is a better model than
  `test_signal_interrupted_loop_can_be_resumed`: it constructs a
  `PersistentExecutor` against a pre-`save_state()`d `StatePersistence`, calls
  `.resume()`, and asserts on the **rendered action string**
  (`'use "captured-value"' in mock_runner.calls[0]`). The BUG-2485 regression test
  should mirror it with a `StateConfig(action='echo "${context.input}"')` state and
  assert `'echo "<original-input>"' in mock_runner.calls[0]`, which exercises the
  exact render path that currently raises `Path 'input' not found in context`.

- **Follow the established 3-test shape for the new field.** Dict-typed
  `LoopState` fields (`messages` at `test_fsm_persistence.py:91-120`,
  `rate_limit_retries` at `:2276-2386`) each ship a trio: *roundtrip* (survives
  `to_dict`→`from_dict`), *omitted-when-empty* (`"context" not in to_dict()`), and
  *defaults-when-missing* (old state file lacking the key → `{}`). The `context`
  field should follow `captured`'s convention exactly: `field(default_factory=dict)`,
  truthiness-gated emit in `to_dict()`, and `data.get("context", {})` in `from_dict()`.

- **Restore site confirmed to be `cmd_resume()`, not `resume()`.** `resume()`
  (`persistence.py:812-870`) copies executor-internal attributes off the saved
  `LoopState` onto `self._executor` (e.g. `:830 self._executor.captured =
  state.captured`) but never touches `self.fsm.context` — because `fsm.context`
  lives on the freshly-built `FSMLoop` that `cmd_resume()` constructs via
  `load_loop()` (`lifecycle.py:466`). The context restore therefore belongs in
  `cmd_resume()` (which holds the `state_for_display` `LoopState`), exactly as the
  Proposed Solution states. `_save_state()` fires on every `state_enter` (plus
  `loop_complete`/`baseline_complete`), so `context=dict(self.fsm.context)` there
  captures the live context at each checkpoint.

- **`input_key` location:** `FSMLoop.input_key: str = "input"` is defined at
  `fsm/schema.py:1005`. Persist/restore must key off `fsm.input_key`, not a
  hardcoded `"input"` — but since the fix persists the whole `context` dict, the
  positional key survives regardless of its name.

## Acceptance Criteria

- [ ] `LoopState` serializes and deserializes `fsm.context` (JSON-safe filtered),
      with a `{}` default so pre-existing state files load unchanged.
- [ ] After `ll-loop stop` + `ll-loop resume`, a state whose action references
      `${context.input}` renders the original input string and does **not** raise
      `Path 'input' not found in context`.
- [ ] Non-`input` context keys (a `program.md` field and a programmatic
      `--context KEY=VALUE`) also survive the stop/resume round-trip.
- [ ] `--context KEY=VALUE` supplied on the `resume` invocation overrides the
      restored value for that key.
- [ ] `run_dir` and `input_hash` remain correct on resume (input_hash now derives
      from the restored `input`).
- [ ] A new regression test in `test_fsm_persistence.py` covers the stop →
      resume → render path and fails against the current code.

## Status

**Open** | Created: 2026-07-05 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-07-05T22:20:00 - `d9cd216c-efbf-4bc3-b5e8-d7d5ff0e7e50.jsonl`
- `/ll:wire-issue` - 2026-07-05T22:10:44 - `7dfa9bdf-2d34-4c08-bb7e-aa21b321b95e.jsonl`
- `/ll:refine-issue` - 2026-07-05T21:57:41 - `3cc1b314-11de-43da-962b-eb4a83fb4e4c.jsonl`
- `/ll:capture-issue` - 2026-07-05T21:49:56Z - `17c6e3c5-bec4-4376-b614-0e3210a85cab.jsonl`
