---
id: BUG-3628
type: BUG
title: FSM executor leaves stale failure_terminal capture on loop state re-entry
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T03:35:17Z'
relates_to:
- ENH-3623
---

# BUG-3628: FSM executor leaves stale failure_terminal capture on loop state re-entry

## Summary

When a `loop:` state runs more than once in one run, the parent's
`${captured.<state>.failure_terminal}` can keep the previous invocation's value. The
executor overwrites `terminated_by` on every child return, but writes `failure_terminal`
only when the new child's value is truthy.

## Current Behavior

In `little_loops.fsm.executor` (`_execute_sub_loop` region, `executor.py` ~:1326-1339),
after a child loop returns:

- the child-capture merge replaces `captured[<state>]` only when
  `(state.context_passthrough or state.with_) and child_executor.captured`;
- `terminated_by` is then set unconditionally through `setdefault`;
- `failure_terminal` is set only inside `if child_result.failure_terminal:`.

Sequence that goes wrong: invocation 1 of the `loop:` state ends on a failure terminal, so
`failure_terminal` is recorded. Invocation 2 succeeds and the child captures nothing, so
the merge does not replace the dict and the falsy value is never written. After
invocation 2, `terminated_by` is current but `failure_terminal` is still invocation 1's
value, and any downstream state that reads it misclassifies invocation 2.

## Expected Behavior

Every per-invocation termination field under `captured[<state>]` reflects the latest child
run. A successful re-entry leaves no `failure_terminal` from an earlier run.

## Motivation

`${captured.<state>.failure_terminal}` is documented loop-author surface, and it has at
least one live reader: `refine-to-ready-issue.yaml`'s failure-evidence action (~:1397)
attributes a failure to `confidence_check` when `failure_terminal` is `True`, and
`confidence_check` (`loop: oracles/verify-confidence-scores`) can be re-entered across
refine rounds. If the oracle captures nothing on a later success, a stale `True` can
misattribute a later failure to `confidence_check` (diagnostic evidence only; routing is
unaffected). Confirm whether the oracle's own captures make that path immune.

## Proposed Solution

**Decision (review 2026-09-27): reset at entry.** At the start of each `_execute_sub_loop`
entry, drop the state's previous per-invocation dict (`self.captured.pop(self.current_state, None)`),
then let the existing merge, `terminated_by`, `failure_terminal`, `error` and `verdict`
writes repopulate it. This fixes `failure_terminal`, `error`, `verdict` and stale child
captures in one place and needs no per-key upkeep.

- Do **not** assign `failure_terminal` unconditionally: a `False` write makes
  `${captured.<state>.failure_terminal?}` render `False` instead of empty, changing
  shell-condition behavior in `refine-to-ready-issue.yaml`. Absent key is the contract.
- Before implementing, verify nothing writes `captured[<state>]` for a `loop:` state
  *before* `_execute_sub_loop` runs (e.g. a `state.capture` key equal to the state name);
  a blanket reset would clobber it. If something does, fall back to per-key `pop` for
  `failure_terminal`, `error`, `verdict` plus a whole-dict reset only of merge-owned keys.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop`, the post-child capture block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (~:1397) — reads
  `${captured.confidence_check.failure_terminal}` in the failure-evidence action
- `scripts/little_loops/loops/prepare-issue.yaml` (ENH-3623 dispatch loop) — deliberately
  does not read the capture; no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` `_execute_sub_loop` — same-class stale-key sites in the same function: `["error"]` at ~:1223 and ~:1372 and `["verdict"]` at ~:1356 are also conditional `setdefault(...)` writes into the per-state dict and are never cleared on re-entry; decide together with `failure_terminal`. `state.capture` writes at ~:1321 fully replace the dict (not stale-prone) [Agent 1/2 finding]
- `scripts/little_loops/fsm/persistence.py` — `LoopState.to_dict` (~:407) serializes `captured`; `PersistentExecutor.resume` (~:1413, `self._executor.captured = state.captured`) rehydrates stale keys. The fix acts at re-entry so it covers resumed runs; old state files are not migrated [Agent 1/2 finding]
- `scripts/little_loops/fsm/interpolation.py` (~:164, `_get_nested(self.captured, path, "captured")`) — resolves `${captured.*}`; an absent key resolves via the `?` default (empty), whereas an unconditional `False` write would render as `False` [Agent 1 finding]
- `scripts/little_loops/fsm/validation/shell_safety.py` `_scan_state_for_mr11` / `_parse_mr11_marker` — MR-11 markers key on `<namespace>.<key>`; a stale marker is itself a finding, so the `${captured.confidence_check.failure_terminal?}` site text and key names must stay unchanged [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (~:799 comment) — notes `terminated_by`/`failure_terminal` "still land under `confidence_check`"; `confidence_check` uses `with_`/passthrough, so the whole-dict merge already drops a stale `failure_terminal` whenever the child has captures. Stale value survives only for a capture-less child — answers the issue's "confirm immunity" question: partially immune, not fully [Agent 2 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (~:419) — carries the `mr11-ok(captured.delegate.terminated_by)` marker; keep unchanged (its ~:403 comment cites a stale `executor.py:1170-1175` line — separate cleanup) [Agent 1 finding]
- Comment-only mentions (no change): `rn-remediate.yaml`, `oracles/resolve-decision.yaml`, `recursive-refine.yaml`, `prepare-issue.yaml`, `general-task.yaml`, `html-anything.yaml`
- Readers of the `ExecutionResult` field (not `captured`), unaffected: `cli/loop/runner.py`, `cli/loop/audit.py`, `cli/loop/evidence.py`, `transport.py:1837`, `persistence.py map_final_status`, `history_reader/*`, `session_store/*`. Routing and `state.capture` verdicts read `child_result.failure_terminal` directly, so clearing the captured key does not change routing [Agent 1/2 finding]

### Similar Patterns
- `terminated_by` in the same block is already written unconditionally; `failure_terminal`
  should follow it

### Tests
- `scripts/tests/test_fsm_executor.py` — add the re-entry test (fail, then succeed with no
  child captures)
- `scripts/tests/test_builtin_loops.py` — any pin on the `confidence_check` evidence action
  should stay green

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py::TestSubLoopTimeoutRouting` — `test_cap_routed_child_failure_terminal_propagates` (asserts `captured["run_child"]["failure_terminal"] is True`) and `test_captured_terminated_by_written_for_terminal_result` stay valid; place the new re-entry test class next to this one [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` workdir_vanished test (~:15095-15137) — patches `FSMExecutor.run` to return a canned `ExecutionResult`; pattern for a per-entry synthetic child outcome (closure counter returning `failure_terminal=True` first, passing second) [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py::TestSubLoopWorktree.test_loop_state_reentry_reattaches_worktree` (~:7065) — marker-file `gate` state (`if [ -f marker ]; then exit 1; else touch marker; exit 0; fi`) plus `parent.states["run_child"].on_yes = "gate"` forces one re-entry; alternative: child shell state that touches a marker and exits 1 first time, 0 after, with a `failure: true` terminal (`_write_cap_failure_child`) [Agent 3 finding]
- New test cases: fail-then-succeed with capture-less child (assert `"failure_terminal" not in captured["run_child"]`, `terminated_by == "terminal"`); same with `with_={}` / `context_passthrough=True` and a child that has captures; fail-then-fail keeps `True`; stale `error` key after error-then-terminal entry; optional `capture=` `verdict` flip pin [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` (~:2139-2140, ~:2164-2165) — `test_write_failure_evidence_attributes_sub_loop_failure` / `..._no_route_sub_loop_failure` substitute `${captured.confidence_check.failure_terminal?}` with literals (`True`, empty); insensitive to the executor change, but an unconditional `False` write would make runtime differ from the empty-string case they simulate [Agent 1/3 finding]
- `scripts/tests/test_builtin_loops.py` (~:4405, ~:4463-4468, ~:20591-20592, ~:20703-20706) — text pins and `mr11-ok` allowlists for `captured.delegate.terminated_by` / `captured.confidence_check.*`; unaffected [Agent 1/3 finding]
- `scripts/tests/test_fsm_persistence.py` — only relevant if the fix also normalizes `captured` on resume; no existing assertion on stale `captured` keys [Agent 1/3 finding]
- No integration test covers sub-loop re-entry (`scripts/tests/integration/` has no `loop:` fixtures); `test_enh2814_failure_terminal_e2e.py` is top-level only and unaffected [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — check whether the `captured.<state>.failure_terminal` contract
  says anything about re-entry; state "latest child run" if it does not

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (~:6392-6417) — documents `failure_terminal`/`terminated_by` only as `ExecutionResult` fields (BUG-3499 semantics); there is no `captured.<state>` contract, so add the "latest child run" statement as a new sentence rather than editing an existing one [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` (~:1009, ~:1025) and `docs/ARCHITECTURE.md` (~:463) — describe `${captured.delegate.terminated_by}` only; optional one-line re-entry note [Agent 1/2 finding]
- No `captured.<state>.failure_terminal` contract exists in `skills/` or `commands/` (`skills/audit-loop-run/SKILL.md` ~:289-299 covers the `loop_complete` event field only) [Agent 2 finding]

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- No config or schema changes: `fsm-loop-schema.json` / `schema.py` mention `terminated_by` only as an `ExecutionResult` concept; MR-11 markers need no edits provided the `${captured.*?}` site text is unchanged [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Convention: `self.captured` has no state-entry reset. Every write site either replaces the whole per-state dict (`_execute_state` capture block ~:2725; `human_approval` handler ~:2875/:2951/:2972) or mutates keys inside the existing dict (`_execute_sub_loop` `terminated_by` :1335, `failure_terminal` :1338-1339, `error` :1223/:1372, `verdict` :1356). Repo-wide grep finds no `captured.pop/clear/del` reset. Only the mutate-in-place sites can leave stale keys; the whole-dict-replace sites cannot.
- Constraint (ordering): the `terminated_by` write sits after the child-capture merge (:1330-1334, ENH-3019) so the merge cannot clobber it; any new clearing of `failure_terminal` must stay compatible with that ordering and with `with_={}` / `context_passthrough` merges (`test_captured_terminated_by_survives_context_passthrough_overwrite`, `test_fsm_executor.py:10286`).
- Readers of `captured.<state>.failure_terminal` / `.terminated_by` (all shell interpolations with `?` defaults and `ll-lint: mr11-ok` allowlist entries in `test_builtin_loops.py` ~:20591, ~:20703): `refine-to-ready-issue.yaml:1395-1397` (ENH-3358), `auto-refine-and-implement.yaml:421,668` (ENH-3366, BUG-3375), `autodev.yaml:1365`. Only the `confidence_check` reader is documented as re-entrant; the `delegate` and `run_quality_gate` readers should be checked for re-entry too.
- Test convention: sub-loop tests use a real `FSMExecutor` + parent `FSMLoop` with `StateConfig(loop=...)` and child YAML written under `tmp_path/.loops` (`TestSubLoopTimeoutRouting`, `test_fsm_executor.py:10149`, helpers `_write_child_loop`/`_write_cap_failure_child`), asserting on `executor.captured[...]`. The only existing test that re-enters a `loop:` state is `TestSubLoopWorktree.test_loop_state_reentry_reattaches_worktree` (:7065), which uses a marker-file shell gate to force exactly one re-entry; no existing test asserts differing child outcomes across entries on `captured`.
- Documentation: `docs/reference/API.md:6402-6417` documents `failure_terminal`/`terminated_by` only as `ExecutionResult` fields; it has no `captured.<state>` contract and no re-entry statement. `LOOPS_REFERENCE.md:1009,1025` and `ARCHITECTURE.md:463` describe `${captured.delegate.terminated_by}` only.

## Implementation Steps

1. Write the failing real-FSM re-entry test in `test_fsm_executor.py`.
2. Verify no pre-`_execute_sub_loop` writer targets `captured[<loop-state>]`, then reset
   `captured[<state>]` at `_execute_sub_loop` entry (never assign `failure_terminal`
   unconditionally).
3. Run `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_builtin_loops.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/executor.py` `_execute_sub_loop` — reset `captured[<state>]` at entry so `failure_terminal`, `error` (~:1223, ~:1372) and `verdict` (~:1356) are all cleared; absent key keeps `${captured.<state>.failure_terminal?}` resolving empty
- Update `scripts/tests/test_fsm_executor.py` — add the re-entry test class near `TestSubLoopTimeoutRouting` (fail-then-succeed capture-less, `with_`/passthrough variant, fail-then-fail, stale `error`); pin the whole-dict merge decision
- Keep `${captured.confidence_check.failure_terminal?}` site text and `test_builtin_loops.py` `mr11-ok` allowlist entries unchanged
- Update `docs/reference/API.md` (~:6392-6417) — add a "latest child run" sentence for `captured.<state>` termination fields
- (Optional, separate cleanup — not part of this fix) stale `executor.py:1170-1175` reference in the `auto-refine-and-implement.yaml` (~:403) comment

## Impact

- **Priority**: P3. Latent; no known production loop reads `failure_terminal` after a
  re-entry today.
- **Effort**: Small. A one-line fix plus a real-FSM test.
- **Risk**: Low. It changes only what a re-entered `loop:` state exposes.
- **Found by**: the ENH-3623 review (the dispatch loop's `record_step`). ENH-3623 does not
  depend on this fix: its `prep record` reads the child's run record instead of the capture.

## Root Cause

`scripts/little_loops/fsm/executor.py` — the post-child capture block around
`self.captured.setdefault(self.current_state, {})["terminated_by"] = ...`: the
`failure_terminal` write is conditional, and nothing clears the key first. The whole-dict
merge above it has the same shape (it only fires when the child captured something), so
stale child captures from an earlier invocation also survive.

## Steps to Reproduce

1. Build a parent loop whose `loop:` state is entered twice in one run (for example a retry
   edge back to it).
2. Make the child end on a failure terminal on the first entry and succeed without
   capturing anything on the second.
3. Read `${captured.<state>.failure_terminal}` after the second entry: it still holds the
   first entry's value.

## Acceptance Criteria

- [ ] A real-FSM test enters a `loop:` state twice (fail, then succeed with no child
  captures) and asserts `failure_terminal` is absent or falsy after the second entry.
- [ ] Reset-at-entry is the chosen behavior for the whole-dict merge (see Proposed
  Solution) and a capture-less re-entry test pins that no child captures survive.
- [ ] Stale `error` and `verdict` keys are also cleared on re-entry (error-then-terminal
  and verdict-flip tests).
- [ ] A resumed run (`PersistentExecutor.resume` rehydrating a stale `captured`) exposes
  no stale termination keys after the next re-entry — covered by a test or an explicit
  note that reset-at-entry covers it.
- [ ] `${captured.confidence_check.failure_terminal?}` site text and the `mr11-ok`
  allowlist entries are unchanged.

## Program Design

### Types

- N/A — no new types; `captured[<state>]` keeps its existing shape

### Signatures

- `FSMExecutor.run(self) -> ExecutionResult` — unchanged public entry point
- `FSMExecutor._execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None` — resets `captured[<state>]` at entry so termination keys reflect only the latest child

### Call Path

`FSMExecutor.run` -> `_execute_state` -> `_execute_sub_loop` -> `captured[<state>]` termination fields

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-27T04:02:38 - `b9726386-58c1-4c65-8485-76e226017a2f.jsonl`
- `/ll:refine-issue` - 2026-09-27T03:55:47 - `0b26d35d-ec12-419a-9599-7aa7bcfe4ed1.jsonl`
- `/ll:capture-issue` - 2026-09-27T03:35:38 - `2cf44b5a-002b-44e7-a500-5cad45592206.jsonl`
