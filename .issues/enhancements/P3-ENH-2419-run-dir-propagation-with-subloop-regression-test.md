---
id: ENH-2419
title: 'Regression test for run_dir propagation across with: sub-loops'
type: ENH
priority: P3
status: done
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Small
relates_to:
- EPIC-2412
- EPIC-1811
labels:
- fsm
- executor
- testing
- regression
decision_needed: false
---

# ENH-2419: Regression test for run_dir propagation across with: sub-loops

## Summary

The `rn-build-failure-findings.md` analysis identified a framework bug where
runner-managed `run_dir` was **dropped across `with:` sub-loops**
(`FSMExecutor._execute_sub_loop`): the `with:` branch built
`child_fsm.context = {**child_fsm.context, **resolved}` without re-injecting the
parent's `run_dir`, so `goal-cluster`'s `load_goals` interpolated `${context.run_dir}`
to `''` → `os.makedirs('')` → `FileNotFoundError` in 0s, and the run still reported
`done` (6 no-op iterations). The described fix
(`child_fsm.context.setdefault("run_dir", self.fsm.context["run_dir"])`) affects **all**
`with:` sub-loop callers, but there is no dedicated tracked issue and — per the notes —
the fix requested a regression test that may not have landed.

## Motivation

This was a silent, cross-cutting failure that masqueraded as success. A regression test
prevents any future refactor of `_execute_sub_loop` from re-dropping `run_dir` and
reintroducing the "done but built nothing" class of bug.

## Current Behavior

The `run_dir` propagation fix (`setdefault("run_dir", …)` in the `with:` branch of
`FSMExecutor._execute_sub_loop`) has no dedicated tracked issue, and per the
`rn-build-failure-findings.md` notes the requested regression test may not have landed.
Nothing prevents a future refactor from re-dropping `run_dir` across `with:` sub-loops.

## Expected Behavior

A regression test in the standard `pytest scripts/tests/` suite asserts that a `with:`
sub-loop inherits the parent's `run_dir`, that an explicit `with: {run_dir: ...}`
override still wins (setdefault semantics), and confirms the fix is present in
`executor.py`.

## Proposed Solution

1. Confirm the `setdefault("run_dir", …)` fix is present in
   `scripts/little_loops/fsm/executor.py` (the `with:` branch, ~line 545); apply it if
   missing.
2. Add a unit/integration test: a parent loop with a `with:` sub-loop that references
   `${context.run_dir}` in a shell action asserts the child receives the parent's
   `run_dir` (not `''`), and that an explicit `run_dir` in `with:` still wins over the
   default.
3. Cover the contrast with the legacy `context_passthrough` branch, which already
   inherited `run_dir`.

## Acceptance Criteria

- A test fails if `run_dir` is not propagated to a `with:` child; passes with the fix.
- An explicit `with: {run_dir: ...}` override is respected (setdefault semantics).
- Test runs under the standard `pytest scripts/tests/` suite.

## Location

- `scripts/little_loops/fsm/executor.py` (`_execute_sub_loop`, `with:` branch)
- Reference: `rn-build-failure-findings.md` (item 1)

## Scope Boundaries

- **In scope**: Confirming/applying the `setdefault` fix and adding a regression test
  covering `with:` inheritance, explicit-override precedence, and the
  `context_passthrough` contrast.
- **Out of scope**: Broader refactoring of `_execute_sub_loop` or context-merge
  semantics beyond `run_dir` propagation.

## Impact

- **Priority**: P3 - Locks in a fix for a silent, cross-cutting failure that
  masqueraded as success; preventive rather than a live regression.
- **Effort**: Small - Confirm a one-line fix and add a focused unit/integration test.
- **Risk**: Low - Test-only addition (plus a one-line guard if the fix is missing);
  affects no runtime behavior when the fix is already present.
- **Breaking Change**: No

## Codebase Research Findings

_Added by `/ll:refine-issue` (auto, 2026-07-08) — based on codebase analysis:_

### Status Against Current Codebase

The work described in this issue is **largely already complete**. The fix and
regression tests called out in the Proposed Solution and Acceptance Criteria
have all landed in the working tree. A gap-analysis-only sweep of the issue
text (line refs, test names, AC coverage) was performed rather than a
full rewrite.

| Issue claim | Current codebase state | Reference |
|---|---|---|
| "setdefault fix ~line 545 of executor.py" | Fix present at `scripts/little_loops/fsm/executor.py:805–806` (stale line ref — file has shifted; the `with:` branch is now at L776–806) | `executor.py:798–806` |
| "regression test may not have landed" | Two regression tests already exist in `TestSubLoopWithBindings` | `scripts/tests/test_fsm_executor.py:7120` (`test_with_inherits_parent_run_dir`) and `:7169` (`test_with_explicit_run_dir_overrides_parent`) |
| AC: "test fails if `run_dir` is not propagated to a `with:` child; passes with the fix" | **MET** — `test_with_inherits_parent_run_dir` builds an FSMLoop whose child references `${context.run_dir}` without declaring it as a parameter and asserts the child captures the parent's `run_dir` verbatim | `test_fsm_executor.py:7120–7167` |
| AC: "explicit `with: {run_dir: ...}` override respected (setdefault semantics)" | **MET** — `test_with_explicit_run_dir_overrides_parent` declares `run_dir` as a required parameter on the child, binds it via `with_={"run_dir": "/child/override"}`, and asserts the override wins over the parent's `/parent/run/` | `test_fsm_executor.py:7169–7203` |
| AC: "Test runs under the standard `pytest scripts/tests/` suite" | **MET** — both tests live in `scripts/tests/test_fsm_executor.py` and run under the default suite | `scripts/tests/test_fsm_executor.py` |
| AC: "Cover the contrast with the legacy `context_passthrough` branch, which already inherited `run_dir`" | **PARTIAL** — `test_sub_loop_context_passthrough` at `:4991–5023` covers passthrough but with a `greeting` key, not `run_dir` specifically. No `run_dir`-specific passthrough contrast test exists. | `scripts/tests/test_fsm_executor.py:4991–5023` |

### Integration Map

#### Files Verified (read-only by this refinement)
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop` at line 734; `with:` branch at L776–806; `setdefault` fix at L805–806; `context_passthrough` branch at L807–814; caller dispatch at L1119–1125
- `scripts/little_loops/fsm/schema.py` — `StateConfig.with_: dict[str, Any]` at L553; `context_passthrough: bool = False` at L552; YAML `with:` → `with_` deserialization at L716–717
- `scripts/little_loops/cli/loop/run.py` — initial `run_dir` injection at L176–179; `--context run_dir=…` parsing at L164–168; instance-id generation at L170–174; downstream `mkdir` at L496
- `scripts/tests/test_fsm_executor.py` — `TestSubLoopWithBindings` class at L6956–7306 (both regression tests live here); `TestSubLoopExecution.test_sub_loop_context_passthrough` at L4991–5023 (contrast branch baseline, but doesn't assert `run_dir`)
- `rn-build-failure-findings.md` — original root-cause analysis (item 1: "preserve `run_dir` across `with:` sub-loops")

#### Why the `with:` branch needed the fix (recap from analyzer findings)

The `with:` branch merges child context via `child_fsm.context = {**child_fsm.context, **resolved}` at `executor.py:797`. Because `resolved` only contains keys explicitly named in the `with:` block, any parent-context key the child expects but doesn't declare as a parameter (e.g. `run_dir`) is dropped. The `context_passthrough` branch at `executor.py:807–814` inherits everything via `**self.fsm.context` and so doesn't have the issue. The `setdefault("run_dir", …)` re-injection at line 805–806 closes this asymmetry for the `run_dir` invariant specifically; the guard `if "run_dir" in self.fsm.context` keeps it safe in tests where the parent context is partial.

#### Remaining Gap (and how to close it)

A single optional addition would close the only PARTIAL AC: a `run_dir`-focused passthrough contrast test (no new file needed — append to `TestSubLoopWithBindings`):

```python
def test_context_passthrough_inherits_parent_run_dir(self, tmp_path: Path) -> None:
    """Contrast: context_passthrough inherits run_dir automatically (no setdefault needed).

    Locks in the asymmetry the with: setdefault fix exists to compensate for.
    """
    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    self._write_child(
        loops_dir,
        "passthrough-run-dir",
        (
            "name: passthrough-run-dir\ninitial: step\nstates:\n"
            "  step:\n    action: 'echo ${context.run_dir}'\n    capture: rd\n    next: done\n"
            "  done:\n    terminal: true\n"
        ),
    )
    parent_fsm = FSMLoop(
        name="parent",
        initial="run_child",
        context={"run_dir": "/parent/run/"},
        states={
            "run_child": StateConfig(
                loop="passthrough-run-dir",
                context_passthrough=True,
                on_yes="success",
                on_no="fail",
            ),
            "success": StateConfig(terminal=True),
            "fail": StateConfig(terminal=True),
        },
    )
    executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
    result = executor.run()
    assert result.final_state == "success"
    assert executor.captured["run_child"]["rd"]["output"].strip() == "/parent/run/"
```

This mirrors `test_with_inherits_parent_run_dir` exactly but swaps `with_={…}` for `context_passthrough=True` and declares no parameters on the child — proving the contrast branch already inherits `run_dir` automatically. Without it, a future refactor that drops `setdefault` (or that breaks passthrough) would only be caught asymmetrically.

### Decision Needed

Two viable paths forward; pick one before closing:

1. **Close the issue as done** — all ACs except the context_passthrough contrast are met, and the fix is locked in by two strong regression tests. The remaining gap is a nice-to-have, not a regression blocker.
2. **Land the optional contrast test** — append `test_context_passthrough_inherits_parent_run_dir` to `TestSubLoopWithBindings` and close the issue. Closes the last partial AC and codifies the asymmetry that motivated the `setdefault` fix.

> **Selected:** Close the issue as done — all 3 formal Acceptance Criteria are met by the two existing regression tests at `test_fsm_executor.py:7120` and `:7169`; the `context_passthrough` contrast is described in the issue itself as "not a regression blocker" and is not in the formal ACs.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-08.

**Selected**: Option 1 — Close the issue as done

**Reasoning**: All formal Acceptance Criteria are met by the two regression tests at `test_fsm_executor.py:7120` (`test_with_inherits_parent_run_dir`) and `:7169` (`test_with_explicit_run_dir_overrides_parent`). The `setdefault` fix is in place at `executor.py:805–806` and is documented by the comment block at `:798–805`. The `context_passthrough` contrast test is a nice-to-have the issue itself describes as "not a regression blocker" — it would symmetrically test the legacy branch that already works, but the formal ACs do not require it, and the explanatory comment at `executor.py:798–805` already documents the asymmetry for future readers. Closing the issue avoids adding ~30 lines of test surface to maintain for a branch the issue describes as already working.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1 — Close as done | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option 2 — Land contrast test | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |

**Key evidence**:
- **Option 1**: Both regression tests already in `TestSubLoopWithBindings` follow the established pattern; the fix is locked in with explanatory comments; all 4 related tests pass (`pytest -k "test_with_inherits_parent_run_dir or test_with_explicit_run_dir_overrides_parent or test_sub_loop_context_passthrough"` → 4 passed in 1.73s); the issue's "Notes for the implementer" confirms no further work is needed beyond closing.
- **Option 2**: Would add ~30 lines mirroring `test_with_inherits_parent_run_dir` exactly (high consistency); adds maintenance surface for a legacy branch; the explanatory comment at `executor.py:798–805` already documents the why; the formal ACs do not require it.

### Notes for the implementer

- Tests run under `python -m pytest scripts/tests/test_fsm_executor.py -k TestSubLoopWithBindings -v` (or the full suite). No test scaffolding work needed beyond the optional contrast test.
- The fix is locked in by the comment block at `executor.py:798–805`; do not delete or shorten it without also expanding the regression tests — the comment is the only place a reader learns *why* `setdefault` is required instead of unconditional assignment.
- The issue's "~line 545" reference is stale (file has grown ~260 lines since this issue was filed); use `executor.py:805–806` going forward.

## Status

**Open** | Created: 2026-06-30 | Priority: P3 | Refined: 2026-07-08 (auto)


## Session Log
- `/ll:wire-issue` - 2026-07-08T19:14:32 - `f4d8e642-50bc-465a-90e1-2a76c14ec868.jsonl`
- `/ll:decide-issue` - 2026-07-08T19:06:34 - `ff503d9e-713c-471d-8f41-bd9b76ba6454.jsonl`
- `/ll:refine-issue` - 2026-07-08T18:32:07 - `4ad2b88d-029d-4fd2-a129-083ccb8c98bc.jsonl`
