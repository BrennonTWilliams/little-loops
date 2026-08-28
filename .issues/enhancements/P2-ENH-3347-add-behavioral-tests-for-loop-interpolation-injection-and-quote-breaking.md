---
id: ENH-3347
type: ENH
title: Add behavioral tests for loop interpolation injection and quote-breaking
priority: P2
status: done
discovered_by: manual-review
discovered_date: '2026-08-27'
captured_at: '2026-08-27T00:00:00Z'
completed_at: '2026-08-28T22:41:41Z'
parent: EPIC-3336
blocked_by:
- BUG-3339
- BUG-3340
- BUG-3341
blocks:
- ENH-3342
confidence_score: 100
outcome_confidence: 95
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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
3. **Python injection.** Pinned to `loop-router`'s `parse_project_score` (the
   state whose pre-fix shape interpolated the goal into `python3 -c` source): a
   goal containing `'; import os; os.system("touch <tmp_path>/pwned") #` does
   **not** create the file. Use pytest's `tmp_path`, **not a fixed `/tmp`
   path** — fixed paths collide across parallel/xdist runs and leak between
   tests.
4. **Shell injection at a site whose pre-conversion shape was `-c "..."`.**
   Pinned to `loop-router`'s `discover_loops` (converted by BUG-3339 from
   `python3 -c "..."` to a quoted heredoc). `discover_loops` never references
   `${context.goal}` — its user-controlled interpolations are
   `${context.include:shell}` and `${context.exclude:shell}` — so the payload
   goes in `context.include`: `"; touch <tmp_path>/pwned; #` does not create
   the file. This is the shell-injection half that **only** the pre-fix `-c "`
   shape exhibits, and it is why this needs its own case rather than folding
   into case 3.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- All three blockers are `status: done` (verified via `ll-issues show
  --json`): BUG-3339, BUG-3340, BUG-3341. Two of the four cases' named
  example sites are stale as written:
- **`list_loops` is not a state name anywhere in the codebase** — searched
  repo-wide across `.yaml`/source/issue files, zero hits outside this
  issue's own text. The state BUG-3339 actually converted off the `-c "..."`
  shape is `discover_loops` (`scripts/little_loops/loops/loop-router.yaml:27`),
  now a quoted heredoc (`python3 << 'PYEOF'`), not `-c "..."`. Case 4 should
  target `discover_loops`, not `list_loops`.
- `parse_project_score` (`scripts/little_loops/loops/loop-router.yaml:205-229`)
  is already fixed for **both** BUG-3340 (goal bound via
  `LL_ARG_GOAL=${context.goal:shell}` env var, line 211) **and** BUG-3341
  (`${captured.project_score.output}` rendered inside a
  `cat > ... << 'LL_RAW_9F3C1A7E_EOF'` heredoc, lines 207-210) — it is
  simultaneously case 1's and case 2's natural target state, not case 1's
  alone.
- The one remaining `python3 -c "..."` in `loop-router.yaml` is
  `finalize_failed` (`:584-588`) — a fixed literal JSON string with no
  interpolation, not an injection surface; do not target it for case 3 or 4.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- No shared/importable helper exists in either test file for "extract a
  named state's action from a loaded loop" — every existing class defines
  its own private `_run*`/`_dedup_action`/`_verify_action` method scoped to
  that class; simple cases inline `data["states"][name]["action"]` directly
  in the test body. A new helper is not required by convention — each of
  the four cases can follow the same self-contained shape.
- `TestBug2468ErrorRouting` (`scripts/tests/test_brainstorm.py:617-702`), the
  precedent this issue already cites, breaks down concretely as: a `data`
  fixture (`yaml.safe_load(LOOP_FILE.read_text())`), a `_seeded_run_dir(tmp_path)`
  helper, a `_dedup_action(...)` method chaining `.replace()` calls per
  `${...}` token, and a `_bash(action, tmp_path)` wrapper around
  `subprocess.run(["bash", "-c", action], cwd=tmp_path, capture_output=True,
  text=True)`; its own `test_triple_quote_payload_no_longer_crashes`
  (`:689-702`) asserts `returncode == 0` plus a stdout/file-content check.
- No existing `assert not (...).exists()` site in `test_builtin_loops.py`
  (8 representative sites: `:811`, `:5371`, `:6072`, `:6120`, `:6242`,
  `:6680`, `:12780`, `:18046`, `:18181`) frames the check as an
  injection-sentinel (a file the payload itself would create, e.g.
  `pwned`) — all existing sites check normal state-output artifacts for
  absence under a routing branch. Cases 3/4's sentinel-absence assertions
  are a new usage of an otherwise-conventional shape, not an established
  pattern to copy verbatim.

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
- **Bind every `${...}` reference the pinned state's action makes** in
  `InterpolationContext` — `interpolate()` raises on a missing key with no
  `:default=`. Concretely: `discover_loops` interpolates `context.include`
  **and** `context.exclude` (case 4 puts the payload in one but must bind
  both) plus `context.run_dir`; `parse_project_score` interpolates
  `context.goal`, `context.run_dir`, and `captured.project_score.output`.
- **Bind `context.run_dir` to the test's `tmp_path`** — every targeted action
  writes artifacts to `${context.run_dir}`, so the exit-0 assertions fail on a
  missing directory otherwise, and it colocates the injection sentinel. Do not
  copy the fixed `/tmp` path from the existing convention sites
  (`test_builtin_loops.py:560-575`).
- **Case 4's action shells out to `ll-loop list --json` at test runtime**
  (both current and pre-fix shapes). It degrades gracefully (`2>/dev/null`
  plus the `or '[]'` fallback in the Python), so the case works where the CLI
  is absent — but it is a real multi-second subprocess per run. Either accept
  the fallback behavior or PATH-stub a fake `ll-loop` printing `[]` for
  speed; the injection assertion does not depend on catalog output, and in
  the red demo the injected `touch` fires at shell-parse time regardless.
- These shell out; keep each fast and bounded. A test invoking a >120s command
  loops forever under xdist (thread-timeout kills the worker, orphans the
  grandchild, xdist respawns and re-runs).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- `interpolate(template: str, ctx: InterpolationContext) -> str` is actually at
  `scripts/little_loops/fsm/interpolation.py:274`, not `:209` as cited above —
  `:209` is `parse_interpolation_suffixes()`, a suffix-parsing helper
  `interpolate()` calls internally, not `interpolate()` itself. Verified by
  direct read.
- Concrete construction convention for driving a payload through the real
  `interpolate()` (from its only two call sites in the test suite,
  `scripts/tests/test_builtin_loops.py:560-575` and `:2303-2330`): extract the
  action as `data["states"][name]["action"]` (raw `yaml.safe_load` dict) or
  `fsm.states[name].action` (via `load_and_validate`), then
  `InterpolationContext(context={...}, captured={"name": {"output": ...,
  "stderr": ..., "exit_code": ...}}, prev={...})` — plain dict literals
  matching the shapes `captured`/`prev` take at runtime — and call
  `interpolate(action, ctx)`.
- No existing test in `test_builtin_loops.py` or `test_brainstorm.py` chains
  real `interpolate()` output into `subprocess.run(["bash", "-c", ...])` —
  this issue's cases would be the first. All 24 existing extract-action /
  subprocess sites (including `TestBug2468ErrorRouting`, this issue's own
  cited precedent) instead build the rendered action via string `.replace()`
  substitution on the literal `${...}` tokens, not the real `interpolate()`
  function.
- `scripts/little_loops/fsm/runners.py:297` boundary confirmed as
  `cmd = ["bash", "-c", action]`, then
  `subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, text=True,
  cwd=working_dir, start_new_session=True, env=project_child_env())`. A test
  reproducing via `subprocess.run(["bash", "-c", action], capture_output=True,
  text=True)` need not replicate `env=project_child_env()` or
  `start_new_session=True` to exercise the injection surface itself.

## Implementation Steps

1. Demonstrate each case **red** against pre-conversion action text — a test
   that was never red proves nothing. All three conversions have already
   landed, so recover the pre-conversion action from git history via
   `git show <sha>^:scripts/little_loops/loops/loop-router.yaml`, run the
   payload through it once to observe the failure, and record the result in
   the test docstring per AC 2. Per-case conversion commits (verified
   2026-08-28 by inspecting each commit's parent):
   - Cases 1 & 3 (`parse_project_score` goal →
     `LL_ARG_GOAL=${context.goal:shell}`): `9a4f997b2` (BUG-3340 batch 3).
   - Case 2 (`captured.project_score.output` → `LL_RAW` heredoc):
     `dc9fe247e` (BUG-3341 batch 2).
   - Case 4 (`discover_loops` `python3 -c "..."` → quoted heredoc):
     `9709fd22f` (BUG-3339) — its parent has the pre-fix `-c "` shape with
     `include_raw = '${context.include}'`.
2. Land the cases against the current (converted) actions, green.
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
5. Case 4 targets a site whose **pre-conversion** shape was `python3 -c "..."`
   (converted by BUG-3339 to a quoted heredoc) — `loop-router`'s
   `discover_loops` — not a site that was already a heredoc before the epic,
   and the payload is delivered via `context.include`/`context.exclude` (the
   variables that state actually interpolates), not `context.goal`.
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
- `/ll:manage-issue` - 2026-08-28T22:41:22 - `ad539cb2-7e53-4a4d-8db5-9e08a67425ec.jsonl`
- `/ll:confidence-check` - 2026-08-28T22:21:03 - `7874a9d3-a25b-4635-aed9-23b27560bb75.jsonl`
- `/ll:refine-issue` - 2026-08-28T22:06:59 - `013c35fe-cc74-469a-aa25-ae000475e3a9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T02:22:58 - `bd65b096-20a2-4a7e-b430-c4b13ac5b81d.jsonl`
