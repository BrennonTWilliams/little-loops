---
id: BUG-2403
title: auto-refine-and-implement closure metric counts the vestigial .issues/completed/
  directory, so every clean leaf-implementation sprint reports verdict=phantom
type: BUG
status: done
priority: P2
captured_at: '2026-06-30T00:00:00Z'
completed_at: '2026-06-30T21:56:27Z'
discovered_date: '2026-06-30'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- verdict
- closure
- regression
relates_to:
- ENH-2385
- ENH-2389
- ENH-2402
- ENH-2404
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-2403: closure metric counts the vestigial `.issues/completed/` directory

## Summary

`auto-refine-and-implement.finalize` computes its success token `CLOSED` strictly
as the diff of `ls .issues/completed/` between `init` and `finalize` (ENH-2385,
commit `2a292926`). But **leaf issues never enter `.issues/completed/`**: ENH-1418
decoupled status from directory location, so `ll-auto` completes an issue *in
place* by writing `status: done` + `completed_at:` to the file where it already
sits (`issue_lifecycle.py:620`, `:690`; the write target is `original_path`, no
move). `issue_history/parsing.py:121` records the decision verbatim — *"files no
longer move on completion."*

Only the **decomposition** path still `git mv`s into `completed/`
(`autodev.yaml` `enqueue_children` / `enqueue_or_skip`, via
`recursive_finalize`). So `CLOSED` can only ever count decomposed parents — never
implemented leaves.

**Net effect:** a sprint that cleanly implements N leaf issues gets `closed=0` →
`phantom`, **deterministically on every run**, not flakily. `NOT_CLOSED =
passed − completed` then counts every implemented leaf as "not closed." The
loop's verdict is structurally untrustworthy for its primary use case.

### Root cause — a regression, not a missing `git mv`

This is a collision between two prior decisions:

- **ENH-1418** — completion is in place (`status: done` + `completed_at:`); the
  `.issues/completed/` directory is vestigial for leaf work.
- **ENH-2385** — pinned the loop's "ground truth" to a diff of that vestigial
  directory.

ENH-2385's own Summary encodes the false premise (line 28-29): *"`ll-auto --only`
implements and moves issues to `.issues/completed/` (`complete_issue_lifecycle`)."*
That belief was seeded by a **stale docstring**: `complete_issue_lifecycle`
(`issue_lifecycle.py:661`) still reads *"This moves the issue to completed and adds
a resolution section,"* while the body (line 692) writes status in place and never
moves anything. The stale docstring is the propagation vector and must be fixed in
the same change, or the next author repeats the mistake.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Anchor correction**: the `issue_lifecycle.py:620`, `:690` citation earlier in
this Summary is stale relative to the current file (line numbers have shifted).
`complete_issue_lifecycle` is defined at `issue_lifecycle.py:653-720`. The stale
docstring text is exactly line 661: *"This moves the issue to completed and adds
a resolution section."* The in-place write is lines 688-692:
`update_frontmatter(content, {"status": "done", "completed_at":
_completed_at_now()})` then `original_path.write_text(content,
encoding="utf-8")` — no `git mv`, `shutil.move`, or `Path.rename` anywhere in the
function. The sibling `complete_issue_close` (lines ~609-650, used for
invalid-issue closure rather than completion) follows the identical in-place
pattern (lines 618-622), confirming the in-place convention is uniform across
both completion paths.

**Exact current `init`/`finalize` logic**
(`scripts/little_loops/loops/auto-refine-and-implement.yaml`):
- `init` (lines 35-48): the only snapshot taken is
  `ls .issues/completed/ | grep -oE '(BUG|FEAT|ENH|EPIC)-[0-9]+' | sort -u >
  "$RUN_DIR/auto-refine-and-implement-completed-baseline.txt"` (lines 45-46). No
  `status:done` baseline exists today — `init` never reads issue frontmatter.
- `finalize` (lines 129-191): re-lists `.issues/completed/` into
  `$P-completed-now.txt` (lines 143-144); `CLOSED=$(comm -13 baseline now | awk
  'NF{c++} END{print c+0}')` (lines 145-146); `NOT_CLOSED` is
  `autodev-passed.txt` minus `$P-completed-now.txt` via `comm -23` (lines
  152-158); the verdict table (lines 168-180) keys purely off
  `$CLOSED`/`$ERR`/`$SKIP`/`$NOT_CLOSED` and needs no change — only the *inputs*
  to `$CLOSED`/`$NOT_CLOSED` need correcting.

**Dependent files (decomposition move paths — must keep counting via the
union)**:
- `scripts/little_loops/loops/autodev.yaml:434-437` (`enqueue_children`) —
  `git mv "$PARENT_FILE" .issues/completed/ 2>/dev/null || mv "$PARENT_FILE"
  .issues/completed/`.
- `scripts/little_loops/loops/autodev.yaml:583-587` (`enqueue_or_skip`) — same
  `git mv ... || mv ...` idiom, run after `/ll:issue-size-review --auto`
  decomposes a parent.
- `scripts/little_loops/recursive_finalize.py:74-88` (`_git_mv`) and `:110-210`
  (`finalize_decomposed_parent`) — sets `status: done` + `completed_at` in place
  (lines 164-165) THEN conditionally `git mv`s (line 172) when
  `move_to_completed=True`. Wired through
  `scripts/little_loops/cli/issues/finalize_decomposition.py:19-61`
  (`cmd_finalize_decomposition`), invoked by `rn-decompose.yaml`'s
  `finalize_parent` state (lines 218-232).

**Reusable pattern for the `done-baseline.txt` snapshot** —
`scripts/little_loops/loops/rn-implement.yaml:261-269` (`select_next`, repeated
at `:423-434` and `:645-658`) already queries the live done-set this way:
```python
done_ids = set()
try:
    r = subprocess.run(
        ["ll-issues", "list", "--json", "--status", "done"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        done_ids = {i["id"] for i in json.loads(r.stdout) if "id" in i}
except Exception:
    pass
```
`_load_issues_with_status()` (`scripts/little_loops/cli/issues/search.py:121-165`)
confirms `ll-issues list --status done --json` scans type-category directories by
frontmatter — directory-agnostic, so it sees in-place-completed leaves. No
existing "union of two snapshot files" idiom was found under
`scripts/little_loops/loops/` (every existing `comm` use is `-13`/`-23`, never
combined with `cat A B | sort -u`) — a union step would be new but consistent
with the `sort -u` + `comm` style already used twice in this same loop.

## Current Behavior

`auto-refine-and-implement.finalize` computes `CLOSED` strictly as the diff of
`ls .issues/completed/` between `init` and `finalize`. Leaf issues never enter
that directory — `ll-auto` completes them in place (`status: done` +
`completed_at:`) — so `CLOSED` only ever counts decomposed parents, never
implemented leaves. A sprint that cleanly implements N leaf issues gets
`closed=0` → `verdict=phantom`, deterministically on every run.

## Steps to Reproduce

1. Scope a sprint of leaf-sized issues (no decomposition).
2. `ll-loop run auto-refine-and-implement --input scope=<sprint>`.
3. All issues reach `status: done` in place; `.issues/completed/` stays empty.
4. `summary.json` → `{"verdict":"phantom","closed":0,"not_closed":N,...}` even
   though every issue implemented and closed.

Observed in the `cards` project run (2026-06-30): 8 issues in, 3 passed (2 with
real implementation commits `b808ec0`, `ed54798`), `completed/` empty before and
after → `{"verdict":"phantom","closed":0,"not_closed":3,"skipped":5}`. See
`audit-loop-sprint-refine-and-implement-2026-06-30.md` (cards repo).

## Expected Behavior

- `CLOSED` counts issues that reached terminal completion **in place during the
  run window** — frontmatter flipped to `status: done` with `completed_at:` inside
  the run window — **UNIONed** with the existing `.issues/completed/` diff (so
  decomposed parents, which still move, keep counting).
- `NOT_CLOSED` is recomputed against that union (`passed − closed`), so a leaf
  that genuinely implemented is never reported as not-closed.
- A pure-leaf sprint that implements and closes every issue yields
  `verdict ∈ {success, partial}`, never `phantom`.

### Do NOT reintroduce directory moves (reject audit P3)

The source audit's proposal P3 — "add a finalize state that `git mv`s every
`status: done` issue into `.issues/completed/`" — is **rejected**. It would revive
the convention ENH-1418 deliberately removed and fight every in-place completer in
the system. The metric is wrong; mutating completion data to satisfy a wrong
metric is backwards. Fix the metric.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`
  - `init` — in addition to the `completed-baseline.txt` snapshot, snapshot the
    set of issues already `status: done` before the run (`done-baseline.txt`),
    mirroring the existing baseline pattern.
  - `finalize` — `CLOSED = (issues now status:done minus done-baseline) ∪
    (completed/ diff)`; recompute `NOT_CLOSED` against the union. Prefer the
    `completed_at:` run-window timestamp as the closure key if it proves cleaner
    than the baseline-set diff.
- `scripts/little_loops/issue_lifecycle.py`
  - Fix the stale docstring on `complete_issue_lifecycle` (line ~661) — it claims
    "moves the issue to completed"; the code completes in place. This is the
    propagation vector for the bug.

#### Codebase Research Findings — proposed shell-level change

_Added by `/ll:refine-issue` — based on codebase analysis:_

Mirror the existing `completed-baseline.txt`/`completed-now.txt` pair exactly
(`auto-refine-and-implement.yaml:41-46` and `:141-146`), using the
`ll-issues list --json --status done` idiom from `rn-implement.yaml:261-269`
(see Root Cause § Codebase Research Findings above) instead of a directory
listing:

- `init`: after the existing `completed-baseline.txt` snapshot (line 46), add a
  parallel snapshot —
  `ll-issues list --json --status done | python3 -c "..." | sort -u >
  "$RUN_DIR/auto-refine-and-implement-done-baseline.txt"`.
- `finalize`: re-run the same query into `$P-done-now.txt`; diff with
  `comm -13 $P-done-baseline.txt $P-done-now.txt` to get newly-done IDs; union
  that with the existing `comm -13 completed-baseline completed-now` result via
  `cat both | sort -u` (no existing union idiom in this codebase — keep it
  minimal, matching the `sort -u` + `comm` style already used twice in this
  loop). Count the union for `$CLOSED`.
- `NOT_CLOSED` (lines 152-158) must diff `autodev-passed.txt` against the new
  union file instead of `$P-completed-now.txt` alone, or a leaf closed only via
  the done-baseline path would still be miscounted as not-closed.
- Verdict thresholds (lines 168-180) are unchanged — they key purely off
  `$CLOSED`/`$NOT_CLOSED`/`$SKIP`/`$ERR`, so correcting the inputs is
  sufficient without touching the verdict table itself.

### Tests
- `scripts/tests/test_builtin_loops.py` — finalize verdict table: a run where
  issues reach `status: done` in place (no `completed/` move) MUST count as
  `closed` and yield `success`/`partial`, not `phantom`. Keep an existing case
  proving decomposed parents (which still move) still count via the union.

#### Codebase Research Findings — test integration points

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `TestAutoRefineAndImplementLoop` (`scripts/tests/test_builtin_loops.py:1666`)
  is the existing test class. `_run_finalize()` (lines 1799-1831) is the
  fixture/execution helper — it writes `auto-refine-and-implement-completed-baseline.txt`,
  creates `.issues/completed/` entries for the `closed`/`baseline` params, writes
  `autodev-passed.txt`/`-skipped.txt`/`-errored.txt`, then runs the literal
  `finalize` action string via `bash -c` and returns the parsed `summary.json`.
  It currently has **no parameter** for "an issue already `status: done` in
  place, outside `completed/`" — extending it with a
  `done_in_place: tuple[str, ...] = ()` param (writing a `.md` fixture per id,
  per the pattern below) is the natural integration point for the new case.
- `test_implement_current_reconciliation_skips_done_inflight`
  (`scripts/tests/test_builtin_loops.py:2933-2965`, class `TestAutodevLoop`) is
  the exact fixture shape to reuse: a `.md` file with `status: done` frontmatter
  written under a type directory (not `.issues/completed/`):
  ```python
  issues_dir = tmp_path / ".issues" / "enhancements"
  issues_dir.mkdir(parents=True)
  (issues_dir / "P3-ENH-0099-test-issue.md").write_text(
      "---\nid: ENH-0099\nstatus: done\n---\n"
  )
  ```
- `test_finalize_verdict_table` (lines 1833-1856) is a
  `(closed, passed, skipped, errored, expected_verdict)` tuple-list test; once
  `_run_finalize` supports `done_in_place`, add a case there for "leaf closed
  via done-baseline only, never touches `completed/`" expecting `success` (not
  `phantom`). `test_finalize_counts_decomposition_closure_as_closed`
  (1858-1869) is the existing model for a standalone single-case test if a
  tuple-table case proves awkward.
- `test_init_snapshots_completed_baseline` (1898-1912) is the direct model for
  a parallel `test_init_snapshots_done_baseline` test — same `bash -c` +
  `${context.run_dir}` path-substitution technique, run against the `init`
  state's raw `action` string, asserting the new `done-baseline.txt` contains
  IDs of pre-existing `status: done` issues.

## Acceptance Criteria

- [x] A sprint of N leaf issues that all reach `status: done` in place during the
      run → `CLOSED == N`, `NOT_CLOSED == 0`, `verdict ∈ {success, partial}` (never
      `phantom`).
- [x] Decomposed parents that `git mv` to `.issues/completed/` continue to count
      as closed (union preserves the existing path).
- [x] No new directory-move behavior is introduced for leaf completion.
- [x] `complete_issue_lifecycle` docstring corrected to describe in-place
      completion.
- [x] `ll-loop validate auto-refine-and-implement` passes; `test_builtin_loops.py`
      green.

## Impact

- **Priority**: P2 — a flagship built-in loop reports `phantom` on every clean
  leaf sprint, making its self-report untrustworthy and risking spurious
  downstream remediation. Implementation work still lands; only the verdict lies.
- **Effort**: Small-Medium — `init` + `finalize` shell in one YAML, a docstring
  fix, and the verdict-table test.
- **Risk**: Low — verdict semantics widen to count real closures; the only
  structured consumer (`audit-loop-run`) reads keys, not the directory.

## Session Log
- `/ll:confidence-check` - 2026-06-30T20:52:09Z - `a78ec122-2731-48c9-9a5f-d364422da749.jsonl`
- `/ll:refine-issue` - 2026-06-30T20:48:21 - `517f4fde-43d5-44f7-afc7-41dd7c15be45.jsonl`
- `/ll:format-issue` - 2026-06-30T20:38:17 - `4bf4d1ed-eaa9-464a-9d2e-9abf985fe2f8.jsonl`
- `audit-loop-run` - 2026-06-30 - reviewed
  `audit-loop-sprint-refine-and-implement-2026-06-30.md` (cards repo); traced
  root cause to ENH-2385 vs ENH-1418 in little-loops.
- `/ll:manage-issue` - 2026-06-30T21:56:27Z - `df65d7ca-2f4e-4eb3-8e1b-7c78f7a751a8.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-06-30
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`: `init` now snapshots
  the live `status: done` set (`ll-issues list --json --status done`) into
  `done-baseline.txt`, mirroring the existing `completed-baseline.txt` snapshot.
  `finalize` derives `CLOSED` from the UNION of two diffs — the `completed/`
  diff (decomposed parents) and the new `status:done` diff (leaf issues
  completed in place per ENH-1418) — so leaf closures are no longer dropped.
  `NOT_CLOSED` exclusion uses the full current snapshot of both sets (not just
  this run's new closures), preserving the original `completed-now` exclusion
  semantics for issues closed before the run started.
- `scripts/little_loops/issue_lifecycle.py`: fixed the stale docstring on
  `complete_issue_lifecycle` — it claimed "moves the issue to completed";
  corrected to describe in-place completion (ENH-1418).
- `scripts/tests/test_builtin_loops.py`: extended `_run_finalize` with
  `done_in_place`/`done_baseline` fixture support; added
  `test_finalize_counts_done_in_place_leaf_as_closed`,
  `test_finalize_excludes_pre_existing_done_baseline_from_closed`,
  `test_finalize_combines_completed_and_done_in_place_closures`,
  `test_finalize_not_closed_excludes_done_in_place_leaf`,
  `test_finalize_not_closed_excludes_pre_baseline_closure_in_passed`, and
  `test_init_snapshots_done_baseline`.

### Verification Results
- Tests: PASS (13182 passed, 23 skipped; full suite)
- Lint: PASS
- Types: PASS (pre-existing unrelated `wcwidth` stub gap in `cli/loop/layout.py`)
- Run: PASS (`ll-loop validate auto-refine-and-implement`)
- Integration: PASS

---

## Status

**Done** | Created: 2026-06-30 | Priority: P2
