---
id: BUG-3101
priority: P2
type: BUG
status: done
captured_at: '2026-08-08T04:44:28Z'
completed_at: '2026-08-08T06:06:03Z'
discovered_date: '2026-08-08'
discovered_by: capture-issue
discovered_commit: 2371728a
discovered_branch: main
testable: true
labels:
- learning-tests
- fsm
- gates
relates_to:
- BUG-3100
- BUG-3102
- ENH-3073
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 98
score_complexity: 25
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3101: Learning-state re-check omits staleness nulling, producing a false `proven` verdict

## Summary

`_execute_learning_state` treats a date-stale `proven` record as absent so the retry path
re-proves it (ENH-2208). That nulling is applied **once, before** the retry loop. The
re-check **inside** the loop is a bare `check_learning_test(target)` with no such treatment.

So a remedy that changes nothing returns the same still-stale `proven` record, the `while`
condition goes false, and the state emits `learning_target_proven` and routes `on_yes`. The
gate reports success for a target it never verified, and the retry budget never engages.

## Current Behavior

In `scripts/little_loops/fsm/executor.py`, `_execute_learning_state`:

```python
for target in targets:
    record = check_learning_test(target)
    # Treat a date-stale proven record as absent so the retry path
    # re-proves it (ENH-2208).
    if (
        _lt_staleness_enabled
        and record is not None
        and record.status == "proven"
        and is_record_stale(record, _lt_stale_days)
    ):
        record = None                      # <-- applied ONCE, here

    attempts = 0
    while record is None or record.status == "stale":
        if attempts >= max_retries:
            return _blocked_target("retries_exhausted", target)
        ...
        self._run_action(f"/ll:explore-api {target}", ...)
        attempts += 1
        record = check_learning_test(target)   # <-- nulling NOT re-applied

    if record.status == "refuted":
        ...
    self._emit("learning_target_proven", {...})
```

The pre-loop nulling and the in-loop re-check apply different definitions of "proven."

**Observed** — `ll-loop run ready-to-implement-gate --context "targets=ruamel.yaml"` against a
`proven` record dated `2026-06-19` (50 days old, `stale_after_days: 30`) on `2371728a`:

```
[1/50] prove (0s) -> ✦ /ll:explore-api ruamel.yaml
       [skill asked a question and returned without touching the record — BUG-3100]
       -> done
Loop completed: done (1 iterations, 25.5s)
```

One iteration, verdict `done`, record still `date: 2026-06-19`. `max_retries` is 2; neither
retry fired, because after attempt 1 the re-check returned a `proven` record and the loop
exited.

Contrast with the same record after `ll-learning-tests mark-stale` — where staleness lives in
the *status field* and so survives the re-check:

```
Loop completed: blocked (1 iterations, 51.8s)   # 2 invocations, then retries_exhausted
```

The retry machinery is correct. Only the date-staleness case is mis-evaluated, because that
form of staleness is dropped on re-read.

## Expected Behavior

The re-check inside the retry loop applies the same staleness definition as the pre-loop
check. A remedy that leaves a record date-stale consumes a retry; exhausting retries routes
`on_blocked` with `retries_exhausted`. `learning_target_proven` is emitted only for a record
that is both `proven` **and** not date-stale.

## Steps to Reproduce

1. On commit `2371728a`, ensure a `proven` learning-test record exists whose `date` is older
   than `stale_after_days` (e.g. `ruamel.yaml` dated `2026-06-19`, 50 days old against
   `stale_after_days: 30`).
2. Run `ll-loop run ready-to-implement-gate --context "targets=ruamel.yaml"`.
3. Observe the loop completes in 1 iteration with verdict `done`, and the record's `date` field
   is unchanged (still `2026-06-19`) — i.e. `learning_target_proven` was emitted and `on_yes` was
   routed without the target ever being re-proven, and without either of the 2 configured
   retries firing.

Contrast: run `ll-learning-tests mark-stale ruamel.yaml` first (moving the staleness signal from
the date field into the `status` field), then repeat step 2 — the loop instead completes
`blocked` after 2 invocations (`retries_exhausted`), which is the correct behavior this bug's fix
should produce for the date-stale case too.

## Motivation

This is a correctness hole in a gate whose only purpose is correctness. `ready-to-implement-gate`
is what `ll-auto` runs before implementing any issue declaring `learning_tests_required` — it
exists to guarantee the agent has verified the external API it is about to build against.

Today that gate returns `done` for any target with a date-stale `proven` record, having
verified nothing. The failure is silent and indistinguishable from a real pass, so it does not
merely fail to help — it actively certifies unverified ground. Of this repo's 31 records, 7 are
date-stale right now, and every one of them would pass the gate falsely.

It also masks [[BUG-3100]]: because the verdict is `done`, the skill's refusal to re-prove
looks like success at every layer above it.

## Root Cause

`scripts/little_loops/fsm/executor.py` → `_execute_learning_state`: the ENH-2208 date-staleness
nulling is inline, immediately after the initial `check_learning_test`, rather than factored
into a helper used by both read sites. The in-loop re-read calls `check_learning_test` directly
and inherits the raw registry semantics.

## Proposed Solution

Extract the nulling into a local closure and use it at both read sites:

```python
def _fresh_record(target: str):
    """Read a record, treating a date-stale ``proven`` record as absent (ENH-2208)."""
    rec = check_learning_test(target)
    if (
        _lt_staleness_enabled
        and rec is not None
        and rec.status == "proven"
        and is_record_stale(rec, _lt_stale_days)
    ):
        return None
    return rec

for target in targets:
    record = _fresh_record(target)
    attempts = 0
    while record is None or record.status == "stale":
        if attempts >= max_retries:
            return _blocked_target("retries_exhausted", target)
        ...
        self._run_action(f"/ll:explore-api {target}", ...)
        attempts += 1
        record = _fresh_record(target)      # same definition on both reads
    ...
```

Single definition, both call sites, no signature change and no ripple beyond this function.

Note this fix alone makes the gate **correctly blocked** rather than falsely `done` — it does
not make re-proving work. That requires [[BUG-3100]]. The two should land together; fixing this
one first turns a silent false pass into a loud, accurate block, which is the right ordering if
they must be split.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
N/A — no data shape is introduced or modified; the fix reuses the existing `LearnTestRecord` (`status`, `date` fields) and the existing `_lt_staleness_enabled: bool` / `_lt_stale_days: int` locals.

### Signatures
- `check_learning_test(target: str, *, base_dir: Path | None = None) -> LearnTestRecord | None` — `scripts/little_loops/learning_tests/__init__.py:149-151`, pure lookup, no staleness logic.
- `is_record_stale(record: LearnTestRecord, stale_after_days: int) -> bool` — `scripts/little_loops/learning_tests/gate.py:45-63`, already imported locally inside `_execute_learning_state` (`executor.py:1113`) and in lexical scope at both read sites.
- Proposed new local closure (per `## Proposed Solution`): `_fresh_record(target: str) -> LearnTestRecord | None`, defined inside `_execute_learning_state` immediately before the `for target in targets:` loop, mirroring the existing `_blocked_target(reason: str, target: str) -> str | None` closure already defined at `executor.py:1144-1150` and called from two sites in the same method (`:1168`, `:1205`).

### Call Path
`FSMExecutor._execute_state` (`executor.py:1467`) -> `FSMExecutor._execute_learning_state` (`executor.py:1088-1216`) -> `_fresh_record(target)` (new closure, replacing the two raw `check_learning_test(target)` calls at `:1153` pre-loop and `:1198` in-loop) -> `check_learning_test` (`learning_tests/__init__.py:149`) -> `is_record_stale` (`learning_tests/gate.py:45`, invoked only when `_lt_staleness_enabled` and `record.status == "proven"`).

### Decision Rules
N/A — no new decision logic; this fix consolidates an existing predicate (`is_record_stale`) to a second existing call site, it does not introduce a new gap kind, gate, threshold, or keyword list.

## Impact

- `ready-to-implement-gate` returns `done` for unverified targets — every date-stale record.
- `ll-auto` proceeds to implement issues whose `learning_tests_required` gate never ran.
- `ll-learning-tests prove` inherits the false success and exits 0 (its own reporting gap is
  covered by [[ENH-3073]]'s `cmd_prove` hardening).
- `migrate-sdk-version` would hit the same re-check once [[BUG-3102]] lets it queue anything.
- `proof-first-task.yaml` (`gate_direct` state, `:37`) and `oracles/enumerate-and-prove.yaml`
  (`prove` state, `:77`) both invoke `ready-to-implement-gate` as a sub-loop, so any caller of
  those wrapper loops observes the same false-`done` verdict today and the same
  correctly-`blocked` verdict once this fix lands, with no code change of their own required.

## Integration Map

- `scripts/little_loops/fsm/executor.py` — `_execute_learning_state`, both record read sites
- `scripts/little_loops/learning_tests/gate.py` — `is_record_stale`, the shared predicate
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — canonical `type: learning` consumer
  (confirmed the only loop with a `type: learning` state — `grep -rl "type: *learning"
  scripts/little_loops/loops/` returns only this file)
- `scripts/tests/test_learning_tests_gate.py`, `scripts/tests/test_learning_state.py` — existing
  coverage for the learning state; the regression test belongs in one of these

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/proof-first-task.yaml:37` — `gate_direct` state invokes
  `loop: ready-to-implement-gate`; no code change needed, but its behavior changes from
  false-`done` to correctly-`blocked` for date-stale targets once this fix lands.
- `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml:77` — `prove` state invokes
  `loop: ready-to-implement-gate`; same behavior-change note as above.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- `scripts/little_loops/fsm/executor.py:1088-1216` — full extent of `_execute_learning_state`; pre-loop nulling at `:1152-1163`, `while` loop condition at `:1166`, in-loop re-check (defect site) at `:1198`, post-loop status branch at `:1200-1210`.
- `scripts/little_loops/fsm/executor.py:1467` — `FSMExecutor._execute_state` is the sole caller, dispatching only when `state.type == "learning" and state.learning is not None`; `_execute_learning_state`'s return value is returned directly, so `on_yes`/`on_blocked` routing is fully resolved inside the function itself (`interpolate(state.on_yes, ctx)` at `:1216`, `_blocked_target()` at `:1144-1150`) — no re-derivation by the caller to rely on.
- `scripts/little_loops/learning_tests/__init__.py:149-151` — `check_learning_test(target, *, base_dir=None) -> LearnTestRecord | None`, a pure lookup with no staleness logic; both call sites (`:1153` pre-loop, `:1198` in-loop) call it identically.
- `scripts/little_loops/learning_tests/gate.py:45-63` — `is_record_stale(record, stale_after_days) -> bool`; unparseable/missing `record.date` returns `False` (not stale). This predicate is imported locally inside `_execute_learning_state` (`from little_loops.learning_tests.gate import is_record_stale` at `:1113`), so it is in scope at both read sites already — the bug is that the in-loop site never calls it, not a scoping problem.
- `_lt_staleness_enabled` / `_lt_stale_days` (`executor.py:1130-1142`) are plain local variables of `_execute_learning_state`, computed once from `BRConfig(Path.cwd()).learning_tests`, and lexically in scope for the rest of the method including the `while` loop — confirms the fix needs no new plumbing, only a second call site.
- Other `is_record_stale` production call sites, each with its own inline null-if-stale pattern (no shared "get fresh record" wrapper exists anywhere in `scripts/little_loops/learning_tests/`): `scripts/little_loops/learning_tests/release_gate.py:58`, `scripts/little_loops/hooks/learning_tests_gate.py:134`, `scripts/little_loops/hooks/install_learning_gate.py:122`, `scripts/little_loops/cli/learning_tests.py:41`.
- Existing closure convention this fix should follow: `_blocked_target` (`executor.py:1144-1150`) is a nested `def` defined once near the top of `_execute_learning_state` and called from two later points in the same method (`:1168`, `:1205`) — the same "one closure, multiple call sites within a state method" shape the issue's proposed `_fresh_record` follows. No docstring is enforced on such closures; the proposal's one-line `(ENH-2208)`-citing docstring matches the repo's convention of citing the originating issue ID near staleness logic (`executor.py:1154-1156`, `:1102`).
- Test coverage gap (both `codebase-analyzer` and `codebase-pattern-finder` independently confirmed via grep): no test in `scripts/tests/test_learning_state.py` (or elsewhere) constructs a `BRConfig`/`.ll/ll-config.json` with `learning_tests.enabled: true` and exercises `_execute_learning_state` — the `_lt_staleness_enabled`/`_lt_stale_days` branch and the date-staleness nulling it enables are entirely untested at the FSM-executor level, at both the pre-loop and in-loop positions. `LearningTestsConfig.enabled` defaults to `False` (`scripts/little_loops/config/features.py:484`).
- Reusable test scaffolding in `scripts/tests/test_learning_state.py`: `_MockRunner` (dataclass, `:30-81`) simulates `/ll:explore-api`, optionally writing a `LearnTestRecord` via `write_record()`; `_learning_fsm(targets, *, on_yes, on_no, on_blocked, max_retries)` (`:84-104`) builds a minimal one-state FSM. `TestLearningStateMaxRetriesExhausted.test_retries_exhausted_routes_to_blocked` (`:257`) is the direct template for this bug's regression test — it already asserts `len(explore_calls) == 2` and `blocked[0]["reason"] == "retries_exhausted"`, the same two assertions the acceptance criteria ask for.
- Convention for opting a test into `learning_tests.enabled`: `scripts/tests/test_learning_tests_discoverability.py:38-55`'s `_write_config(project_dir, *, enabled=True, ..., stale_after_days=None)` writes `.ll/ll-config.json`'s `learning_tests` block directly — no equivalent helper currently exists in `test_learning_state.py`, so the regression test will need either this pattern adapted or a `monkeypatch` of `BRConfig.learning_tests`.
- Note: `record.status == "stale"` (the registry's own explicit staleness marker set by `mark_stale()`) is a separate, orthogonal signal from the ENH-2208 *date*-based staleness this bug concerns — `is_record_stale` never inspects `status` itself, and the `while` loop's `record.status == "stale"` arm already handles that case correctly regardless of this bug's fix.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Nested-closure-vs-module-level-helper convention (codebase-pattern-finder): a predicate used across multiple independent modules is promoted to a module-level helper — `is_record_stale` itself lives in `scripts/little_loops/learning_tests/gate.py:45-63` and is imported by five independent consumers (`release_gate.py:58`, `hooks/learning_tests_gate.py:134`, `hooks/install_learning_gate.py:122`, `cli/learning_tests.py:53`, `cli/ctx_stats.py:680`, plus `fsm/executor.py:1161`). A null-or-not wrapper built *on top of* that predicate, used only within one method's own call sites, instead stays a nested closure — exactly what `_blocked_target` (`executor.py:1144-1150`) already does for its own two call sites in this same method. No counter-example of a null-if-stale wrapper implemented as a module-level helper exists in this codebase; the proposed `_fresh_record` closure matches this convention, not an exception to it.
- Consolidation-scope check (codebase-pattern-finder, cross-referencing BUG-3102's decision log at `.ll/decisions.d/72e163e7-46bf-4580-a8ce-ba1c2daf01f1.json`): that sibling issue treats reuse of `is_record_stale` as load-bearing but scopes its own consolidation discussion to a different call site (`migrate-sdk-version.yaml`'s loop heredoc), not to unifying the five inline null-if-stale wrappers with each other. No issue or comment anywhere proposes collapsing those five call sites' duplicated inline checks into one shared function — each remains independently duplicated as of this commit, so this bug's local `_fresh_record` closure is consistent with, not a partial step short of, an unrealized broader consolidation.

## Acceptance Criteria

- [ ] A test drives `_execute_learning_state` with a `proven` but date-stale record and a remedy
      that leaves the record untouched, and asserts the state routes `on_blocked` with
      `retries_exhausted` — **not** `on_yes`.
- [ ] A test asserts `learning_target_proven` is not emitted for a date-stale `proven` record.
- [ ] A test asserts the remedy is invoked `max_retries` times in that scenario (today: once).
- [ ] A remedy that genuinely re-dates the record still routes `on_yes` on the following
      re-check — the fix must not break the success path.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Issues

- BUG-3100 — `/ll:explore-api` refuses to re-prove an existing record; the reason the remedy is
  a no-op. This bug is what makes that no-op invisible; fix together
- BUG-3102 — `migrate-sdk-version` queues only `status: stale` records
- ENH-2208 — introduced the date-staleness nulling that this bug applies inconsistently
- ENH-3073 — blocked by this and BUG-3100

## Status

Open. Mechanism confirmed by reading `_execute_learning_state` and by direct reproduction on
`2371728a` (verdict `done` in 1 iteration against a 50-day-old record, retries never fired).
Fix is local to one function.


## Session Log
- `/ll:manage-issue` - 2026-08-08T06:05:42 - `0095583c-378d-4ce3-8c7e-4da48a20a9bd.jsonl`
- `/ll:ready-issue` - 2026-08-08T05:56:24 - `c764ecfb-6265-4e90-b4a9-781d48409375.jsonl`
- `/ll:confidence-check` - 2026-08-08T05:52:51 - `bf78ab50-8f10-4df7-83ce-f0f37e86d806.jsonl`
- `/ll:verify-issues` - 2026-08-08T05:51:29 - `a6419a1b-0f3f-48cd-8102-7db62f9341e9.jsonl`
- `/ll:wire-issue` - 2026-08-08T05:50:27 - `0490e223-ca08-4b08-ad0e-13241a8fdba0.jsonl`
- `/ll:refine-issue` - 2026-08-08T05:44:17 - `3df59510-de37-44c2-a213-b8613b824277.jsonl`
- `/ll:confidence-check` - 2026-08-08T05:23:41 - `32cab529-b0e3-489a-9bfd-6cf54ad65ad2.jsonl`
- `/ll:verify-issues` - 2026-08-08T05:22:11 - `69e9dd14-f77c-404b-ba32-3bedb138ff58.jsonl`
- `/ll:refine-issue` - 2026-08-08T05:16:14 - `928d3925-14dd-458e-a18c-80f3b4010a4a.jsonl`
- `/ll:capture-issue` - 2026-08-08T04:47:04 - `0c442e3b-c3d8-4743-b597-7b3551a75ba6.jsonl`
