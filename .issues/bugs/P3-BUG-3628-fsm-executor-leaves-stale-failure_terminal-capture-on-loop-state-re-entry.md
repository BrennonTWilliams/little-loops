---
id: BUG-3628
type: BUG
title: FSM executor leaves stale failure_terminal capture on loop state re-entry
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T03:35:17Z'
completed_at: '2026-09-27T05:53:31Z'
relates_to:
- ENH-3623
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

**Decision (review 2026-09-27): reset at entry.** On each real (non-simulation)
`_execute_sub_loop` entry, drop the state's previous per-invocation dict
(`self.captured.pop(self.current_state, None)`), then let the existing merge,
`terminated_by`, `failure_terminal` and `error` writes repopulate it. This fixes
`failure_terminal`, `error` and stale child captures in one place and needs no per-key upkeep.

**Placement (review 2026-09-27): after the child-context binding, before worktree setup** —
i.e. after `seed_parameter_defaults` / `seed_confidence_thresholds` / `derive_input_hash`
(~:1172-1184) and before the ENH-2609 worktree block (~:1186). Both neighbours constrain it:

- **Not earlier** (before ~:1156): the `context_passthrough` branch builds
  `captured_as_context` from `self.captured`, so a re-entered passthrough child currently
  sees its own previous invocation's captures under `${context.<state>}`. Popping first would
  silently change what the child receives. Keep that behavior unchanged in this fix.
- **Not later** (after `child_executor.run()`): the worktree-error early return (~:1223)
  writes `error` via `setdefault` into `captured[<state>]`; it must land in a fresh dict.

**Exception edge (noted in review 2026-09-27, no change needed)**: if anything between the
reset and the `terminated_by` write raises (`child_executor.run()`, or `detach_worktree()`
in its `finally`), `captured[<state>]` is left **absent** rather than stale. The exception
propagates out of `_execute_sub_loop` and ends the parent run, so no downstream state reads
it. Only a resume could observe the absence, and resume re-enters the `loop:` state, which
repopulates the dict.

`verdict` is **not** stale-prone and is outside this fix: ~:1356 writes it into
`captured[state.capture]` (not `captured[<state>]`), and assigns it on every entry whenever
`state.capture` is set.

- Do **not** assign `failure_terminal` unconditionally: a `False` write makes
  `${captured.<state>.failure_terminal?}` render `False` instead of empty, changing
  shell-condition behavior in `refine-to-ready-issue.yaml`. Absent key is the contract.
- Before implementing, verify nothing writes `captured[<state>]` for a `loop:` state
  *before* `_execute_sub_loop` runs (e.g. a `state.capture` key equal to the state name);
  a blanket reset would clobber it. If something does, fall back to per-key `pop` for
  `failure_terminal` and `error` plus a whole-dict reset only of merge-owned keys.
- Also check the other `captured.<state>.terminated_by` / `.failure_terminal` readers for
  re-entry: `delegate` (`auto-refine-and-implement.yaml` ~:421, ~:668) and
  `run_quality_gate` (`autodev.yaml` ~:1371). Record in the Resolution whether each can be
  re-entered in one run; no YAML change is expected either way.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop`, the post-child capture block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (~:1397) — reads
  `${captured.confidence_check.failure_terminal}` in the failure-evidence action
- `scripts/little_loops/loops/prepare-issue.yaml` (ENH-3623 dispatch loop) — deliberately
  does not read the capture; no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` `_execute_sub_loop` — same-class stale-key sites in the same function: `["error"]` at ~:1223 and ~:1372 are also conditional `setdefault(...)` writes into the per-state dict and are never cleared on re-entry; decide together with `failure_terminal`. (Correction, review 2026-09-27: `["verdict"]` at ~:1356 writes into `captured[state.capture]`, not the per-state dict, and is assigned unconditionally when `state.capture` is set — not stale-prone.) `state.capture` writes at ~:1321 fully replace the dict (not stale-prone) [Agent 1/2 finding]
- `scripts/little_loops/fsm/persistence.py` — `LoopState.to_dict` (~:407) serializes `captured`; `PersistentExecutor.resume` (~:1413, `self._executor.captured = state.captured`) rehydrates stale keys. The fix acts at re-entry so it covers resumed runs; old state files are not migrated [Agent 1/2 finding]
- `scripts/little_loops/fsm/interpolation.py` (~:164, `_get_nested(self.captured, path, "captured")`) — resolves `${captured.*}`; an absent key resolves via the `?` default (empty), whereas an unconditional `False` write would render as `False` [Agent 1 finding]
- `scripts/little_loops/fsm/validation/shell_safety.py` `_scan_state_for_mr11` / `_parse_mr11_marker` — MR-11 markers key on `<namespace>.<key>`; a stale marker is itself a finding, so the `${captured.confidence_check.failure_terminal?}` site text and key names must stay unchanged [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (~:799 comment) — notes `terminated_by`/`failure_terminal` "still land under `confidence_check`"; `confidence_check` uses `with_`/passthrough, so the whole-dict merge already drops a stale `failure_terminal` whenever the child has captures. Stale value survives only for a capture-less child — answers the issue's "confirm immunity" question: partially immune, not fully [Agent 2 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (~:419) — carries the `mr11-ok(captured.delegate.terminated_by)` marker; keep unchanged (its ~:403 comment cites a stale `executor.py:1170-1175` line — separate cleanup) [Agent 1 finding]
- Comment-only mentions (no change): `rn-remediate.yaml`, `oracles/resolve-decision.yaml`, `recursive-refine.yaml`, `prepare-issue.yaml`, `general-task.yaml`, `html-anything.yaml`
- Readers of the `ExecutionResult` field (not `captured`), unaffected: `cli/loop/runner.py`, `cli/loop/audit.py`, `cli/loop/evidence.py`, `transport.py:1837`, `persistence.py map_final_status`, `history_reader/*`, `session_store/*`. Routing and `state.capture` verdicts read `child_result.failure_terminal` directly, so clearing the captured key does not change routing [Agent 1/2 finding]

### Similar Patterns
- `terminated_by` in the same block is already written unconditionally. `failure_terminal`
  must **not** copy that (a `False` write breaks the absent-key contract — see Proposed
  Solution); reset-at-entry gives it the same "latest child run" guarantee instead.

### Tests
- `scripts/tests/test_fsm_executor.py` — add the re-entry test (fail, then succeed with no
  child captures)
- `scripts/tests/test_builtin_loops.py` — any pin on the `confidence_check` evidence action
  should stay green

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py::TestSubLoopTimeoutRouting` — `test_cap_routed_child_failure_terminal_propagates` (asserts `captured["run_child"]["failure_terminal"] is True`) and `test_captured_terminated_by_written_for_terminal_result` stay valid; place the new re-entry test class next to this one [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` workdir_vanished test (~:15095-15137) — patches `FSMExecutor.run` to return a canned `ExecutionResult`; pattern for a per-entry synthetic child outcome (closure counter returning `failure_terminal=True` first, passing second) [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py::TestSubLoopWorktree.test_loop_state_reentry_reattaches_worktree` (~:7065) — marker-file `gate` state (`if [ -f marker ]; then exit 1; else touch marker; exit 0; fi`) plus `parent.states["run_child"].on_yes = "gate"` forces one re-entry; alternative: child shell state that touches a marker and exits 1 first time, 0 after, with a `failure: true` terminal (`_write_cap_failure_child`) [Agent 3 finding]
- New test cases: fail-then-succeed with capture-less child (assert `"failure_terminal" not in captured["run_child"]`, `terminated_by == "terminal"`); same with `with_={}` / `context_passthrough=True` and a child that has captures; fail-then-fail keeps `True`; stale `error` key after error-then-terminal entry; worktree-error-then-success entry leaves no `error`; a re-entered `context_passthrough` child still receives its previous invocation's captures (pins the placement); optional `capture=` `verdict` flip regression pin (already correct today) [Agent 3 finding]
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

- Convention: `self.captured` has no state-entry reset. Every write site either replaces the whole per-state dict (`_execute_state` capture block ~:2725; `human_approval` handler ~:2875/:2951/:2972) or mutates keys inside the existing dict (`_execute_sub_loop` `terminated_by` :1335, `failure_terminal` :1338-1339, `error` :1223/:1372, `verdict` :1356 — the last into `captured[state.capture]`, assigned every entry, so not stale-prone). Repo-wide grep finds no `captured.pop/clear/del` reset. Only the mutate-in-place sites can leave stale keys; the whole-dict-replace sites cannot.
- Constraint (ordering): the `terminated_by` write sits after the child-capture merge (:1330-1334, ENH-3019) so the merge cannot clobber it; any new clearing of `failure_terminal` must stay compatible with that ordering and with `with_={}` / `context_passthrough` merges (`test_captured_terminated_by_survives_context_passthrough_overwrite`, `test_fsm_executor.py:10286`).
- Readers of `captured.<state>.failure_terminal` / `.terminated_by` (all shell interpolations with `?` defaults and `ll-lint: mr11-ok` allowlist entries in `test_builtin_loops.py` ~:20591, ~:20703): `refine-to-ready-issue.yaml:1395-1397` (ENH-3358), `auto-refine-and-implement.yaml:421,668` (ENH-3366, BUG-3375), `autodev.yaml:1371`. Only the `confidence_check` reader is documented as re-entrant; the `delegate` and `run_quality_gate` readers should be checked for re-entry too.
- Test convention: sub-loop tests use a real `FSMExecutor` + parent `FSMLoop` with `StateConfig(loop=...)` and child YAML written under `tmp_path/.loops` (`TestSubLoopTimeoutRouting`, `test_fsm_executor.py:10149`, helpers `_write_child_loop`/`_write_cap_failure_child`), asserting on `executor.captured[...]`. The only existing test that re-enters a `loop:` state is `TestSubLoopWorktree.test_loop_state_reentry_reattaches_worktree` (:7065), which uses a marker-file shell gate to force exactly one re-entry; no existing test asserts differing child outcomes across entries on `captured`.
- Documentation: `docs/reference/API.md:6402-6417` documents `failure_terminal`/`terminated_by` only as `ExecutionResult` fields; it has no `captured.<state>` contract and no re-entry statement. `LOOPS_REFERENCE.md:1009,1025` and `ARCHITECTURE.md:463` describe `${captured.delegate.terminated_by}` only.

## Implementation Steps

1. Write the failing real-FSM re-entry test in `test_fsm_executor.py`.
2. Verify no pre-`_execute_sub_loop` writer targets `captured[<loop-state>]`, then reset
   `captured[<state>]` after the child-context binding (~:1184) and before the worktree
   block (~:1186) (never assign `failure_terminal` unconditionally).
3. Check re-entry for the `delegate` and `run_quality_gate` readers; note the result in the
   Resolution.
4. Run `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_builtin_loops.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/executor.py` `_execute_sub_loop` — reset `captured[<state>]` after child-context binding and before worktree setup so `failure_terminal` and `error` (~:1223, ~:1372) are cleared; absent key keeps `${captured.<state>.failure_terminal?}` resolving empty
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

- [x] A real-FSM test enters a `loop:` state twice (fail, then succeed with no child
  captures) and asserts `"failure_terminal" not in captured[<state>]` after the second
  entry (absent, not `False`).
- [x] Reset-at-entry is the chosen behavior for the whole-dict merge (see Proposed
  Solution) and a capture-less re-entry test pins that no child captures survive.
- [x] The reset sits after child-context binding and before worktree setup: a re-entered
  `context_passthrough` child still receives its previous captures, and a
  worktree-error-then-success sequence leaves no stale `error`.
- [x] Stale `error` keys are also cleared on re-entry (error-then-terminal test).
  `verdict` needs no fix (written into `captured[state.capture]` every entry); an optional
  verdict-flip test is a regression pin only.
- [x] `delegate` and `run_quality_gate` re-entry checked and noted in the Resolution.
- [x] A resumed run (`PersistentExecutor.resume` rehydrating a stale `captured`) exposes
  no stale termination keys after the next re-entry — covered by a test or an explicit
  note that reset-at-entry covers it.
- [x] `${captured.confidence_check.failure_terminal?}` site text and the `mr11-ok`
  allowlist entries are unchanged.

## Program Design

### Types

- N/A — no new types; `captured[<state>]` keeps its existing shape

### Signatures

- `FSMExecutor.run(self) -> ExecutionResult` — unchanged public entry point
- `FSMExecutor._execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None` — resets `captured[<state>]` after child-context binding, before worktree setup, so termination keys reflect only the latest child

### Call Path

`FSMExecutor.run` -> `_execute_state` -> `_execute_sub_loop` -> `captured[<state>]` termination fields

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Done** | Created: 2026-09-27 | Priority: P3

## Resolution

Implemented reset-at-entry exactly as decided: `_execute_sub_loop` now does
`self.captured.pop(self.current_state, None)` right after the child-context
binding (`derive_input_hash`, `executor.py:1183-1199`) and before the ENH-2609
worktree block, so `terminated_by`/`failure_terminal`/`error` written after
the child returns always land in a fresh dict for that invocation, while a
re-entered `context_passthrough` child still sees its own prior captures
(reset lands after that branch runs).

Added `TestSubLoopReentryCaptureReset` (`test_fsm_executor.py`) covering:
capture-less success after a failure terminal (`failure_terminal` absent, not
`False`), fail-then-fail (`failure_terminal` stays `True`), a runtime-error
entry followed by a clean terminal (stale `error` cleared), the
`context_passthrough` placement pin, and a worktree-setup-error entry
followed by a successful re-entry (stale `error` cleared). `verdict` needed
no change — it's written into `captured[state.capture]` unconditionally on
every entry, not the per-state dict this fix resets.

`delegate` / `run_quality_gate` re-entry check (issue's open question):
- `delegate` (`auto-refine-and-implement.yaml`) is re-entered via the
  ENH-2615 `recheck_set` cycle (`recheck_set.on_yes: delegate`,
  `delegate.on_success: recheck_set`). Its two readers,
  `delegate_failed` (~:421) and the crash-record state (~:668), are both
  reached directly by that same `delegate` invocation's own `on_failure`/
  `on_error` routing — the read always happens in the same cycle as the
  write, before any later re-entry. Not exposed to the stale-value bug today.
- `run_quality_gate` (`autodev.yaml`) is re-entered once per queued issue in
  the `dequeue_next` drain loop. Its only reader, `mark_quality_fail`
  (~:1371), is reached directly by that invocation's own `on_failure` route —
  read and write are in the same cycle, before the next queued item re-enters
  the state. Not exposed either.
- Both match the issue's own finding for `confidence_check`
  (`refine-to-ready-issue.yaml`): no production loop today reads a `loop:`
  state's capture from a *later* cycle than the one that wrote it, so this
  was a latent defect with no live misattribution — the fix closes the gap
  for any future reader that does.

Resume: reset-at-entry runs on every real `_execute_sub_loop` entry
regardless of whether `self.captured` was populated fresh or rehydrated by
`PersistentExecutor.resume`, so a resumed run gets the same guarantee on its
next re-entry without separate handling. No dedicated resume test was added;
covered by inspection per the AC's either/or.

`${captured.confidence_check.failure_terminal?}` site text and the
`mr11-ok` allowlist entries in `test_builtin_loops.py` are unchanged, as
required.

Verification: `python -m pytest scripts/tests/` — full suite passes except
two pre-existing failures unrelated to this fix
(`TestBug3295ContainmentCorpusDifferential::test_total_report_count_does_not_exceed_post_bug_3448_baseline`
and `TestRepoGate::test_no_new_unverifiable_evidence`, both reproduced on a
clean `main` with this change stashed out — caused by unrelated uncommitted
edits to BUG-3631/ENH-3616 already present in the working tree).
`test_fsm_executor.py` + `test_builtin_loops.py` targeted run: 2507 passed.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-27_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Code claims verified against HEAD: post-child block at `executor.py:1326-1339` matches (merge only when `(context_passthrough or with_) and child_executor.captured`; `terminated_by` via `setdefault`; `failure_terminal` only when truthy); `captured_as_context` at `:1156`, seed calls `:1172-1184`, worktree block `:1186`, worktree-error `error` write `:1223`, `error` write `:1372`, `verdict` into `captured[state.capture]` `:1356` — the proposed reset placement (after `:1184`, before `:1186`) is consistent with all of them. `ll-verify-evidence`: clean. No decisions-log rules apply.
- Fixed: `autodev.yaml` `run_quality_gate` reader line drifted (`~:1365` → `~:1371`).
- Not verified here (left as the issue's own pre-implementation step): that no writer targets `captured[<loop-state>]` before `_execute_sub_loop`.

## Session Log
- `/ll:verify-issues` - 2026-09-27T05:07:18 - `8dd98d25-9e0a-42d3-8b1b-63a8171e5519.jsonl`
- `/ll:confidence-check` - 2026-09-27T04:50:43 - `b1d961f1-bb2d-4afe-8b30-594899eeede4.jsonl`
- `/ll:wire-issue` - 2026-09-27T04:02:38 - `b9726386-58c1-4c65-8485-76e226017a2f.jsonl`
- `/ll:refine-issue` - 2026-09-27T03:55:47 - `0b26d35d-ec12-419a-9599-7aa7bcfe4ed1.jsonl`
- `/ll:capture-issue` - 2026-09-27T03:35:38 - `2cf44b5a-002b-44e7-a500-5cad45592206.jsonl`
