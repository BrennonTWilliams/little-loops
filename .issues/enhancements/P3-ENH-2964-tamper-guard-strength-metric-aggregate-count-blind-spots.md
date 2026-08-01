---
id: ENH-2964
title: Tamper-guard strength metric is a per-file aggregate count, with false positives
  on legitimate refactors and a same-count evasion hole
type: ENH
priority: P3
captured_at: '2026-08-01T00:00:00Z'
completed_at: '2026-08-01T22:46:37Z'
discovered_date: 2026-08-01
discovered_by: review
relates_to:
- BUG-2954
- ENH-2935
- ENH-2933
decision_needed: false
testable: true
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
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

Scope note: this section states the *end state*. The selected option delivers
only the moved-test half of the first bullet; helper extraction and the second
bullet are deferred to the separable increments named in `## Proposed
Solution`. See `## Acceptance Criteria` for what this issue is done against.

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

1. **Cross-file strength netting rather than a strict per-file delta.** Offset a
   file's strength deficit against strength appearing in the *other* findings of
   the same run, so a test moved from file A to file B nets to zero. Fixes the
   moved-test false positive only. Costs reading `added`-finding content in
   addition to today's `modified`-only reads.
2. **Per-test-function matching instead of aggregate counts.** Key strength by
   test-function name, so a function that survives with fewer assertions is
   flagged even when file totals hold, and a function that disappears from A
   while appearing in B is recognized as a move. Fixes the moved-test false
   positive and the same-count false negative; materially more implementation
   than option 1.

**Neither option fixes the helper-extraction false positive (row 1).** That
refactor is intra-file, and both metrics are assertion-count-derived: summing
is monotonic, so unchanged files contribute identically to both sides and the
deficit survives (verified: before `assertions=4` → after `assertions=1`;
repo-wide totals 5 → 2, still weakening). Per-function matching flags it too —
`test_a` goes from 2 assertions to 0 once the bodies become `_check(...)`
calls. Extracting duplicated assertions into a helper *inherently* reduces the
raw `ast.Assert` count. Fixing row 1 requires a distinct third mechanism:
attributing assertions through calls to project-local helper functions that
themselves contain assertions.

Separately, neither addresses `assert True` backfill *within* a retained
function without some notion of assertion triviality (e.g. discounting
assertions whose operand is a literal constant) — a fourth, separable
increment.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A**: Cross-file strength netting rather than a strict per-file delta.
Offset a file's strength deficit against strength appearing in the other
findings of the same run, so a test moved from file A to file B nets to zero.
Fixes the moved-test false positive only. Costs reading `added`-finding content
in addition to today's `modified`-only reads.

> **Selected:** Option A — reuses the existing `finding_filter` extension
> point and `read_paths_at_ref`/`filter_weakening_findings` primitives with a
> contained, low-risk change; Option B requires rewriting the `TestStrength`
> contract and existing test assertions for a false-negative fix that,
> per this issue's own Proposed Solution, still leaves row 1 unfixed.

**Option B**: Per-test-function matching instead of aggregate counts. Key
strength by test-function name, so a function that survives with fewer
assertions is flagged even when file totals hold, and a function that
disappears from A while appearing in B is recognized as a move. Fixes the
moved-test false positive and the same-count false negative (not row 1);
materially more implementation than Option A.

Evidence on relative implementation cost (see Integration Map → Codebase
Research Findings for anchors): Option A's before/after-across-multiple-files
primitive (`read_paths_at_ref`, `filter_weakening_findings`'s dict-shaped
batching) already exists unchanged — only the comparison baseline changes,
from a raw per-file before-total to one adjusted for relocated functions.
Option B's per-symbol identity primitive
(`node.name.startswith("test")` inside `measure_test_strength`'s existing AST
walk) also already exists — only the aggregation target changes from a counter
to a name-keyed set/dict, mirroring the per-symbol pattern already in use at
`codequery/fallback.py:111-130`. Both options build on functions that already
exist in `test_tamper_guard.py`; neither requires a new module.

### Decision Rationale

**Selected: Option A — cross-file strength netting rather than a strict
per-file delta.**

Scope correction (post-decision review): Option A fixes **one** of the three
bad rows — the moved-test false positive. It does not fix helper extraction
(row 1), and neither does Option B; see `## Proposed Solution` for the
verification. This narrows Option A's payoff but does not change the
selection, since Option B's extra cost buys only the same-count false negative
while sharing the row-1 gap.

Both options build on existing primitives in `test_tamper_guard.py`, but
Option A's wiring is materially more contained: it extends the same
`finding_filter` hook BUG-2954 already introduced, reuses
`read_paths_at_ref`/`filter_weakening_findings` largely unchanged, and the
full candidate path set it needs is already computed and in scope at the one
call site involved (`work_verification.py:109-114`). Option B requires
rewriting `TestStrength` from a flat 3-int dataclass into a name-keyed
structure, rewriting `is_weakening`'s scalar comparisons and
`filter_weakening_findings`'s per-file dispatch loop into a cross-file
name-matching algorithm, and rewriting the existing aggregate-count test
assertions in `test_test_tamper_guard.py` — a rewrite of the metric's core
contract, not an additive extension.

Critically, neither option actually closes every gap this issue opens with:
row 1 (helper extraction) survives both, and `assert True` backfill within a
retained function survives both. Since Option B's larger implementation cost
does not buy a complete fix either, its main advantage over Option A narrows
to the same-count false negative plus function renames within a file — real
but secondary wins relative to its cost and the new same-file-rename blind
spot its name-keyed matching introduces.

**Read scope (binding constraint on the implementation).** Do *not* implement
Option A as a literal sum over the whole candidate path set. Measured on this
repo, that is 496 candidate paths against an unbatched `git show` per path in
`read_paths_at_ref` — ~2.6s added to every Phase 3 verification (timed: 0.32s
for 60 paths). Scope the additional reads to `added`-finding content only,
which is the actual gap versus today's `modified`-only reads. Summing over
unchanged files also buys nothing: they contribute identically to both sides.

**Netting must be attributable, not a raw total.** A raw set-wide sum is a
cheap new evasion — delete a real test from file A, add twenty `assert True`
lines to file B, totals net positive, and the *entire* finding set passes.
Today's per-file check blocks that, so an unqualified sum trades a known false
negative for a cheaper new one, against this issue's own `## Impact` warning
about over-correcting into an inert guard. Offset a per-file deficit only
against strength attributable to a **matching test-function name** appearing
in an `added` finding of the same run; never against an unattributed total.

**Out of scope: whole-file renames.** `filter_weakening_findings` keeps every
`deleted` finding unconditionally (`test_tamper_guard.py:316-317`), so
`git mv test_foo.py test_bar.py` is delete+add and never reaches
`is_weakening` under either option. The split-an-oversized-test-file case named
in `## Motivation` is modify+add and *is* covered; a pure rename is not. Left
deliberately unfixed here — relaxing `deleted` handling is a separate change to
the guard's most conservative branch.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2/3 | 2/3 |
| Simplicity | 2/3 | 1/3 |
| Testability | 2/3 | 2/3 |
| Risk | 2/3 | 1/3 |
| **Total** | **8/12** | **6/12** |

Key evidence: `finding_filter`/`read_paths_at_ref` extension pattern
(`test_tamper_guard.py:112-120,485-521`, `work_verification.py:109-115`) vs.
`TestStrength`/`is_weakening`/`filter_weakening_findings` rewrite scope
(`test_tamper_guard.py:50-54,284-331`) and existing aggregate-count test
assertions (`scripts/tests/test_test_tamper_guard.py:591-683`).

## Integration Map

### Files to Modify
- `scripts/little_loops/test_tamper_guard.py` — primarily
  `filter_weakening_findings` (where the cross-file attribution lives) and
  `measure_test_strength`'s docstring, which currently cites this issue as its
  follow-up and must be narrowed to the limitations that remain. Under Option A
  `is_weakening`'s scalar contract is unchanged. Note this is the tamper-guard
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
  `filter_weakening_findings` runs — option 1 doesn't need a new
  path-discovery step, only a change to what `filter_weakening_findings` does
  with the finding set it is already handed.
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

## Program Design

### Signatures

```python
# scripts/little_loops/test_tamper_guard.py — new, module-private
def _test_functions(source: str) -> dict[str, ast.AST] | None:
    """Top-level ``test*`` function nodes by name; None when unparseable."""

def _subtract(total: TestStrength, parts: list[TestStrength]) -> TestStrength:
    """Field-wise ``total - sum(parts)``, floored at 0."""
```

`filter_weakening_findings(findings, repo_root, ref)` keeps its signature.
`measure_test_strength`, `is_weakening`, `TestStrength`, `read_paths_at_ref`
and `run_tamper_guard` are all unchanged. Per-function strength is obtained by
re-measuring a node's `ast.unparse(node)` through the existing
`measure_test_strength` — verified sufficient, so no refactor of it into a
node-walking core is required.

### Call Path

`work_verification._run_non_fsm_tamper_guard` -> `run_tamper_guard(...,
finding_filter=partial(filter_weakening_findings, ...))` ->
`filter_weakening_findings`:

1. (existing) read `before_texts` for `modified` paths via `read_paths_at_ref`,
   `after_texts` from disk.
2. (new) read on-disk content for `added`, non-config finding paths — no
   `read_paths_at_ref` call, since an added path has no content at *ref*.
3. (new) build `relocated`, the set of test-function names **newly present** in
   any other finding this run: for `added` paths every name qualifies; for
   `modified` paths only `names(after) - names(before)` does, using the texts
   already read in step 1. Presence alone must not qualify a name — 387 test
   names in `scripts/tests/` are defined in more than one file (`test_to_dict`
   in 40), so an unrelated pre-existing twin would otherwise launder a
   deletion.
4. (existing) per `modified` finding, compute `is_weakening`. (new) When True,
   recompute against an **adjusted baseline**: subtract the strength of each
   before-side test function whose name is in `relocated` from that file's
   before-`TestStrength` (via `_subtract`), then re-apply `is_weakening`'s
   scalar comparison. Keep the finding unless the adjusted comparison passes.

Step 4 must adjust the baseline rather than short-circuit on the name set. A
name-set-only check ("drop if every lost name reappears elsewhere") is a new
evasion: move one test out of a file and every remaining assertion in it
becomes free to delete in the same edit. Verified — before `assertions=4,
test_functions=2` -> after `assertions=1, test_functions=1` with `test_b`
relocated intact reads as fully accounted-for under a name-set check, while
the adjusted baseline (`assertions=2, test_functions=1`) correctly still
flags it. This is what AC rows 6 and 8 pin.

## Scope Boundaries

- Out of scope: helper extraction (AC row 1) — needs assertion attribution
  through calls to project-local helpers, a separate mechanism per
  `## Proposed Solution`.
- Out of scope: `assert True` backfill within a retained function (AC row 5) —
  needs assertion-triviality scoring.
- Out of scope: whole-file renames (AC row 7) — requires relaxing the
  unconditional `deleted`-finding branch (`test_tamper_guard.py:316-317`).
- Out of scope: the FSM path (`fsm/executor.py::_check_tamper_guard`), which
  passes no `finding_filter` by design and stays byte-strict.
- Out of scope: any new config key, and any change to
  `tamper_guard_candidate_paths`' whole-repo path discovery.

## Acceptance Criteria

Verdict table after the fix. Rows marked *unchanged* are the over-correction
guard — a change that flips them has made the guard inert and fails this issue.

| # | Phase 2 edit | Today | Required after fix |
|---|---|---|---|
| 1 | Extract repeated assertions into a shared `_check()` helper | `True` | `True` — *unchanged*, out of scope (needs helper-call attribution) |
| 2 | Move a test function from modified file A to added file B | `True` | **`False`** — the fix |
| 3 | Add test cases to an existing file | `False` | `False` — *unchanged* |
| 4 | Remove assertions / delete a test / add `skip`/`skipif`/`xfail` | `True` | `True` — *unchanged* |
| 5 | Gut real assertions, backfill the same count of `assert True` | `False` | `False` — *unchanged*, out of scope |
| 6 | Delete a real test in A, add unrelated trivial assertions in B | `True` | `True` — *unchanged*; the netting-evasion guard, must not net |
| 7 | `git mv test_foo.py test_bar.py` (delete+add) | `True` | `True` — *unchanged*, out of scope per Decision Rationale |
| 8 | Move `test_b` out of A **and** delete an assertion from A's retained `test_a` | `True` | `True` — *unchanged*; the adjusted-baseline guard, must not be laundered by the move |
| 9 | Delete `test_to_dict` from A while an unrelated, unmodified B already defines its own `test_to_dict` | `True` | `True` — *unchanged*; name-collision guard (`relocated` is newly-present names only) |

Additional criteria:

- Rows 1–9 are asserted as unit tests in `scripts/tests/test_test_tamper_guard.py`
  (rows 2, 6, 8 and 9 at the `filter_weakening_findings` level, since all four
  are cross-file and unreachable through `is_weakening` alone).
- Row 2 passes for **both** destination shapes: an `added` file B and an
  existing `modified` file B. The latter is the common split-an-oversized-file
  case and is not covered by reading `added` findings alone.
- No new `git show` call is issued for a path that has no finding: verified by
  asserting `read_paths_at_ref` is invoked only over `modified` finding paths,
  not the candidate set (`added` paths are read from disk only).
- The three named must-keep-passing tests in `## Integration Map → Tests` pass
  unmodified.
- `docs/reference/API.md` (`### verify_work_was_done`) states the *remaining*
  limitations (rows 1, 5, 7) rather than the current aggregate-count sentence.

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
- `/ll:manage-issue` - 2026-08-01T22:46:14 - `dbf963d5-eae9-42d1-9073-80b412860523.jsonl`
- `/ll:confidence-check` - 2026-08-01T22:36:40 - `b680ac0d-bfa8-4297-b0d5-f93678c11559.jsonl`
- `/ll:confidence-check` - 2026-08-01T22:33:14 - `446a45c6-99b0-4308-8fb4-ae64bdd94ebf.jsonl`
- `/ll:decide-issue` - 2026-08-01T22:24:53 - `2af9d556-d7ad-4171-bfdd-d4ae5457547b.jsonl`
- `/ll:refine-issue` - 2026-08-01T19:51:12 - `d9b5af8b-d1a1-4e82-af36-c6b06a5fc367.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
