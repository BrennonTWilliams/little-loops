---
id: ENH-2964
title: Tamper-guard strength metric is a per-file aggregate count, with false positives on
  legitimate refactors and a same-count evasion hole
type: ENH
priority: P3
captured_at: '2026-08-01T00:00:00Z'
discovered_date: 2026-08-01
discovered_by: review
relates_to:
- BUG-2954
- ENH-2935
- ENH-2933
decision_needed: true
---

# ENH-2964: Tamper-guard strength metric is a per-file aggregate count, with false positives on legitimate refactors and a same-count evasion hole

## Summary

BUG-2954 replaced the non-FSM tamper guard's pure sha256 discriminator with a
content-aware weakening classifier (`measure_test_strength` / `is_weakening` in
`scripts/little_loops/test_tamper_guard.py`). That fixed the motivating case —
a TDD-mode Phase 2 edit that *adds* cases to an existing test file no longer
trips the guard.

The metric it uses is a **per-file aggregate count** (assertions, test
functions, skip markers). That shape has two residual blind spots: it reads
some legitimate refactors as weakening (false positive, same user-visible
symptom as BUG-2954 but a narrower trigger), and it misses a same-count
substitution (false negative).

## Current Behavior

Verified empirically against `is_weakening` at current `HEAD`:

| Phase 2 edit | `is_weakening` | Correct? |
|---|---|---|
| Extract repeated assertions into a shared `_check()` helper | `True` | **No** — false positive |
| Move a test function out into a new test file | `True` | **No** — false positive |
| Add test cases to an existing file | `False` | Yes |
| Remove assertions / delete a test / add `skip`/`skipif`/`xfail` | `True` | Yes |
| Gut real assertions, backfill the same count of `assert True` | `False` | **No** — false negative |

Reproduction of row 1:

```python
from little_loops.test_tamper_guard import is_weakening

before = "def test_a():\n    assert 1\n    assert 2\ndef test_b():\n    assert 3\n    assert 4\n"
after = (
    "def _check(x):\n    assert x\n"
    "def test_a():\n    _check(1); _check(2)\n"
    "def test_b():\n    _check(3); _check(4)\n"
)
is_weakening(before, after, "test_x.py")  # -> True
```

## Expected Behavior

- A refactor that preserves test coverage while reducing a single file's raw
  counts — assertions extracted into a shared helper, a test function moved to
  another file — is not a weakening.
- A substitution that keeps counts constant while destroying assertion strength
  (`assert real_thing() == 5` → `assert True`) is a weakening.

## Motivation

The false-positive rows are the *same failure mode BUG-2954 was filed about*,
just with a narrower trigger: under the default `tamper_guard.policy: fail`,
an `ll-auto`/`ll-parallel`/`ll-sprint` run whose correct implementation
involves splitting an oversized test file or de-duplicating assertions is
still hard-blocked at Phase 3, burning the full implement cycle. Test-file
splits are routine on this repo (`test_builtin_loops.py`, `test_fsm_executor.py`
are both well past 10k lines).

The false-negative row is the cheapest available evasion of the guard for an
agent motivated to make a failing suite pass.

## Proposed Solution

Two candidate directions, not yet decided — this issue needs a design pass
before implementation:

1. **Repo-wide rather than per-file strength delta.** Sum strength across the
   whole candidate path set and compare totals, so a test moved from file A to
   file B nets to zero. Fixes both false-positive rows; does nothing for the
   false negative. Costs a `read_paths_at_ref` over every candidate path rather
   than only the modified ones.
2. **Per-test-function matching instead of aggregate counts.** Key strength by
   test-function name, so a function that survives with fewer assertions is
   flagged even when file totals hold, and a function that disappears from A
   while appearing in B is recognized as a move. Fixes all three rows;
   materially more implementation than option 1.

Neither addresses `assert True` backfill *within* a retained function without
some notion of assertion triviality (e.g. discounting assertions whose operand
is a literal constant) — worth scoping as a third, separable increment.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A**: Repo-wide rather than per-file strength delta. Sum strength
across the whole candidate path set and compare totals, so a test moved from
file A to file B nets to zero. Fixes both false-positive rows; does nothing for
the false negative. Costs a `read_paths_at_ref` over every candidate path
rather than only the modified ones.

**Option B**: Per-test-function matching instead of aggregate counts. Key
strength by test-function name, so a function that survives with fewer
assertions is flagged even when file totals hold, and a function that
disappears from A while appearing in B is recognized as a move. Fixes all
three rows; materially more implementation than Option A.

Evidence on relative implementation cost (see Integration Map → Codebase
Research Findings for anchors): Option A's before/after-across-multiple-files
primitive (`read_paths_at_ref`, `filter_weakening_findings`'s dict-shaped
batching) already exists unchanged — only the summation target moves from
per-path to whole-set. Option B's per-symbol identity primitive
(`node.name.startswith("test")` inside `measure_test_strength`'s existing AST
walk) also already exists — only the aggregation target changes from a counter
to a name-keyed set/dict, mirroring the per-symbol pattern already in use at
`codequery/fallback.py:111-130`. Both options build on functions that already
exist in `test_tamper_guard.py`; neither requires a new module.

## Integration Map

### Files to Modify
- `scripts/little_loops/test_tamper_guard.py` — `measure_test_strength`,
  `is_weakening`, `filter_weakening_findings`. Note this is the tamper-guard
  *core module*, not a test file, despite the `test_` prefix.
- `docs/reference/API.md` — the `### verify_work_was_done` section documents
  the current aggregate-count limitation and links here; update when fixed.

### Tests
- `scripts/tests/test_test_tamper_guard.py` — `TestMeasureTestStrength` /
  `TestIsWeakening` are the existing unit-coverage classes to extend. Add the
  refactor-to-helper and moved-test cases as false-positive regressions.
- `scripts/tests/test_issue_manager.py:2854`
  (`test_tamper_guard_trips_end_to_end_no_fsm_involved`) must keep passing
  unmodified — the guard against over-correcting into an inert guard.
- `scripts/tests/test_fsm_executor.py` —
  `test_tdd_mode_does_not_trip_guard_on_separate_verify_state` must keep
  passing; the FSM path never receives a `finding_filter` and stays byte-strict.

### Documentation
- `docs/reference/API.md` (`### verify_work_was_done`) — remove/replace the
  limitation sentence added alongside BUG-2954's closure.

### Configuration
- N/A — no new config key.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The actual non-FSM caller is `scripts/little_loops/work_verification.py`, not
  `test_tamper_guard.py` itself: `_run_non_fsm_tamper_guard()`
  (`work_verification.py:63-143`) computes `candidate_paths =
  tamper_guard_candidate_paths(repo_root, config=config)` (whole-repo test+config
  files via git `ls-files`) and `changed = tamper_guard_changed_files(repo_root)`
  (full changed-file set for the implement phase, from `git diff --name-only
  HEAD` plus untracked files), then calls `run_tamper_guard(before, changed,
  config, policy, repo_root, finding_filter=partial(filter_weakening_findings,
  repo_root=repo_root, ref=ref))` (`work_verification.py:110-115`). Both
  candidate options in `## Proposed Solution` build on this call site: the
  caller already has the whole-diff, multi-file path set available when
  `filter_weakening_findings` runs — option 1 (repo-wide sum) doesn't need a
  new path-discovery step, only a change to what `filter_weakening_findings`
  does with the set it's already handed.
- The FSM adapter (`scripts/little_loops/fsm/executor.py`, `_check_tamper_guard`)
  calls `run_tamper_guard(...)` with **no `finding_filter` argument** —
  deliberately, per `run_tamper_guard`'s own docstring
  (`test_tamper_guard.py:496-508`): "Defaults to None so callers that never pass
  it (the FSM adapter) keep full byte-level strictness, unaffected." Any change
  to `filter_weakening_findings`/`is_weakening` under this issue only affects
  the non-FSM path; the FSM path's byte-strict behavior is untouched by
  construction, not by an oversight that needs separate handling.
- Additional existing test files not yet listed above that already exercise this
  chokepoint and should keep passing unmodified: `scripts/tests/
  test_work_verification.py` (integration coverage for the two-window guard
  logic in `_run_non_fsm_tamper_guard`) and `scripts/tests/test_worker_pool.py`
  (ll-parallel end-to-end tamper guard coverage).
- `read_paths_at_ref(repo_root, ref, paths) -> dict[str, str | None]`
  (`test_tamper_guard.py:112-120`) already batches git-ref-relative content
  reads across an arbitrary path set, keyed by repo-relative path (`None` =
  absent at that ref, not an exception). `filter_weakening_findings`
  (`test_tamper_guard.py:302-331`) already builds `before_texts` via this
  function and `after_texts` via on-disk reads as two same-shaped dicts — the
  before/after-across-multiple-files primitive named in Proposed Solution
  Option A already exists; no new read/diff utility is needed for that
  direction.
- This codebase has an existing per-symbol (not aggregate-count) AST-walk
  pattern: `FallbackProvider.defines()`
  (`scripts/little_loops/codequery/fallback.py:111-130`) walks `ast.parse` /
  `ast.walk`, filters `FunctionDef`/`AsyncFunctionDef`, and keys results by
  `node.name` rather than a total. `measure_test_strength()`
  (`test_tamper_guard.py:235-281`) already imports `ast`, already walks the
  tree, and already special-cases `node.name.startswith("test")` inside that
  walk (`test_tamper_guard.py:266-268`) — it just increments a counter there
  instead of recording the name. Option B (per-test-function matching) would
  convert that one counter increment into a name-keyed set/dict; it does not
  require a new AST-walking module.
- `measure_test_strength()`'s own docstring already cites this issue as its
  follow-up (`test_tamper_guard.py:246-250`), and BUG-2954 established the
  precedent of layering a finer-grained filter on top of the existing
  byte-hash comparison via `run_tamper_guard`'s `finding_filter` hook
  (`test_tamper_guard.py:485-521`) rather than replacing it — the same
  incremental-layering shape either option here would extend.

## Impact

- **Priority**: P3 — narrower trigger than BUG-2954 (only refactor-shaped test
  edits, not every additive edit), and the false negative requires a
  deliberately adversarial agent. Real but not run-blocking for the common case.
- **Effort**: Medium — option 1 is small; option 2 is a rewrite of the metric.
- **Risk**: Medium — touches the shared Phase 3 verification chokepoint; must
  not over-correct into an inert guard.
- **Breaking Change**: No

## Root Cause

- **File**: `scripts/little_loops/test_tamper_guard.py`
- **Anchor**: in function `measure_test_strength()` / `is_weakening()`
- **Cause**: `TestStrength` is three per-file integers, and `is_weakening`
  compares them with `<`/`>`. Aggregate counts carry no identity information
  about *which* test or *which* assertion changed, so a coverage-preserving
  count reduction and a coverage-destroying one are indistinguishable, as are
  a strength-preserving and strength-destroying same-count edit.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:refine-issue` - 2026-08-01T19:51:12 - `d9b5af8b-d1a1-4e82-af36-c6b06a5fc367.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
