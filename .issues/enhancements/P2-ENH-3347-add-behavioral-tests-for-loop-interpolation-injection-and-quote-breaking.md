---
id: ENH-3347
type: ENH
title: Add behavioral tests for loop interpolation injection and quote-breaking
priority: P2
status: open
discovered_by: manual-review
discovered_date: '2026-08-27'
captured_at: '2026-08-27T00:00:00Z'
parent: EPIC-3336
blocked_by: [BUG-3339, BUG-3340, BUG-3341]
blocks: [ENH-3342]
---

# ENH-3347: Add behavioral tests for loop interpolation injection and quote-breaking

## Summary

Add the four **behavioral** test cases EPIC-3336 needs and no child currently
owns: they extract a real loop action, run it through `bash -c`, and assert the
defect is actually gone — an apostrophe goal, a `"""` capture, a Python injection
payload, and a shell injection at a converted `-c "` site.

Created during epic review (2026-08-27): BUG-3331 listed these as Step 8 / AC 6,
and the decomposition into EPIC-3336's six children dropped them. BUG-3339
mentions where they would live but does not claim them.

## Current Behavior

EPIC-3336's coverage after its other children is entirely **static**:

- ENH-3338's baseline proves *no site matches the unsafe pattern*
- `ll-loop validate` / MR-11 prove *the lint does not fire*

Neither executes a converted action. A conversion can be structurally clean —
baseline-empty, lint-clean — and still be wrong: a heredoc terminator that does
not match at runtime, an `os.environ` read with no binding, a `.strip()` that
changes a consumer's behavior. Every failure mode BUG-3341 warns about is
invisible to a static check.

The precedent for the missing style of test already exists:
`scripts/tests/test_brainstorm.py::TestBug2468ErrorRouting` covers exactly this
failure mode for the one state BUG-2468 fixed.

## Expected Behavior

Four cases in the established extract-action /
`subprocess.run(["bash", "-c", action])` shape in
`scripts/tests/test_builtin_loops.py`, each red before its corresponding
conversion and green after:

1. **Apostrophe goal.** A goal containing `don't` runs `loop-router`'s
   `parse_project_score` action to exit 0. Today: `SyntaxError`. Covers BUG-3340.
2. **`"""` capture.** A captured output containing `"""` **and a newline** runs a
   class-B action to exit 0. Covers BUG-3341, and the newline is as important as
   the quotes — it is what breaks a single-quoted literal.
3. **Python injection.** A goal containing
   `'; import os; os.system("touch <tmp_path>/pwned") #` does **not** create the
   file. Use pytest's `tmp_path`, **not a fixed `/tmp` path** — fixed paths
   collide across parallel/xdist runs and leak between tests.
4. **Shell injection at a converted `-c "` site.** A goal containing
   `"; touch <tmp_path>/pwned; #` run against a site converted by BUG-3339 (e.g.
   `loop-router`'s `list_loops`) does not create the file. This is the
   shell-injection half that **only** the `-c "` shape exhibits, and it is why
   this needs its own case rather than folding into case 3.

## Motivation

145 hand-edited sites, verified only by a pattern-matcher, in a system where a
bad conversion surfaces as a production loop failure weeks later. The static
guards answer "did we edit every site?"; these answer "did the edits work?".
They are different questions and the epic currently answers only the first.

## Integration Map

### Files to Modify

- `scripts/tests/test_builtin_loops.py` — the four cases.

### Dependent Files (Callers/Importers)

- N/A — tests only.

### Similar Patterns

- `scripts/tests/test_brainstorm.py::TestBug2468ErrorRouting` — the shipped
  precedent for the `"""`-capture case; same failure mode, one state.
- The existing extract-action / `subprocess.run(["bash", "-c", action])` cases in
  `test_builtin_loops.py` — the established shape to follow.

### Tests

- This issue *is* the tests.

### Documentation

- N/A

### Configuration

- N/A

## Scope Boundaries

**In scope:** four behavioral test cases in `scripts/tests/test_builtin_loops.py`
that execute a real converted action and assert the defect is gone.

**Out of scope:** the static sweep and baseline (ENH-3338); MR-11 unit tests
(ENH-3342); the conversions themselves (BUG-3339/3340/3341); broadening coverage
to every converted site — these four are representative, not exhaustive.

## Program Design

### Signatures

No production code changes; these are tests against existing engine entry points.

- `interpolate(template: str, ctx: InterpolationContext) -> str`
  (`scripts/little_loops/fsm/interpolation.py:209`) — each case drives the payload
  through this, not by hand-substituting into the action string.
- `InterpolationContext.resolve(self, namespace: str, path: str) -> Any`
  (`scripts/little_loops/fsm/interpolation.py:78`) — the substitution under test.
- `scripts/little_loops/fsm/runners.py:297` (`cmd = ["bash", "-c", action]`) — the
  boundary each case reproduces with `subprocess.run(["bash", "-c", action])`.
- `scripts/tests/test_brainstorm.py::TestBug2468ErrorRouting` — the existing
  class of test these four extend.

### Call Path

Per case: the test loads the loop, reaches the pinned state's `action`, renders it
with `interpolate(template, ctx)`
(`scripts/little_loops/fsm/interpolation.py:209`) against a context carrying the
payload, then executes the rendered string with
`subprocess.run(["bash", "-c", action])` — the same invocation
`scripts/little_loops/fsm/runners.py:297` makes. The assertion is on that
subprocess's exit code or on the absence of a `tmp_path` sentinel file.

No production call path changes; the tests reproduce the existing one.

### Decision Rules

Per case, the assertion is about the **action's runtime behavior**, not its text:

- cases 1 and 2 assert `returncode == 0` — the state survives input it used to
  die on
- cases 3 and 4 assert a sentinel file does **not** exist after the run — the
  payload did not execute

Do not assert on stdout content; a conversion may legitimately change formatting.

### Test hygiene

- **`tmp_path`, never a fixed `/tmp` path.** Fixed paths collide across
  pytest-xdist workers and leak between tests. This repo runs the suite in
  parallel.
- **Interpolate the payload through the real FSM path** (`interpolate()` +
  `bash -c`), not by hand-substituting into the action string — hand-substituting
  tests the test, not the engine.
- **Keep each case pinned to a named state** in a named loop. A case that scans
  for "some class-B action" silently stops testing anything when that action is
  refactored.
- These shell out; keep each fast and bounded. A test invoking a >120s command
  loops forever under xdist (thread-timeout kills the worker, orphans the
  grandchild, xdist respawns and re-runs).

## Implementation Steps

1. Write each case against its pinned state, **before** the corresponding
   conversion lands where practical, and confirm it is **red** — a test that was
   never red proves nothing.
2. Land the cases after BUG-3339/3340/3341, green.
3. Confirm ENH-3338's sweep is clean at the same commit; the static and
   behavioral guards should agree.

## Acceptance Criteria

1. Four cases exist in `scripts/tests/test_builtin_loops.py`, one per scenario
   above, each pinned to a named loop and state.
2. Each case is demonstrated **red** against pre-conversion action text and green
   after — recorded in the issue or the test docstring.
3. Cases 3 and 4 use pytest `tmp_path` for the sentinel; no fixed `/tmp` path
   appears.
4. Case 2's payload contains both `"""` and a newline.
5. Case 4 targets a site converted by BUG-3339, not a heredoc site.
6. `python -m pytest scripts/tests/` exits 0, including under xdist.

## Impact

- **Priority**: P2 — inherited from EPIC-3336; it is the epic's only end-to-end
  proof that the conversions work.
- **Effort**: Small — four tests in an established shape with a shipped precedent.
- **Risk**: Low. The one real hazard is writing tests that pass trivially because
  they were never red; AC 2 exists for that.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-27 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue shares
`scripts/tests/test_builtin_loops.py` with [ENH-3342]. This issue adds the
four behavioral injection/quote-breaking test cases; ENH-3342 adds the
marker-count ratchet assertion (AC 8c) and keeps ENH-3338's baseline test
green. The existing `blocked_by`/`blocks` edge (this issue blocks ENH-3342)
already sequences the edits — land in that order.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-28T02:22:58 - `bd65b096-20a2-4a7e-b430-c4b13ac5b81d.jsonl`
