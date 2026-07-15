---
id: ENH-2641
type: ENH
priority: P3
status: done
captured_at: '2026-07-14T23:40:13Z'
completed_at: '2026-07-15T00:11:07Z'
discovered_date: 2026-07-14
discovered_by: capture-issue
relates_to:
- BUG-2640
- BUG-2614
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 21
---

# ENH-2641: verify-detail.txt truncation hides the real failure

## Summary

The epic-merge verify gate writes `verify-detail.txt` into the run dir as a blind
character-prefix of `test_cmd` output (capped at ~500 chars). For a pytest run that
begins with pytest-benchmark/xdist warnings, this cap captures **only the warnings**
and cuts off before the `FAILED …` short-summary lines — so the artifact records that
verify failed but not *why*. The run becomes undiagnosable from its own artifacts.

## Motivation

On run `sprint-refine-and-implement-20260714T180411` (EPIC-2370, see BUG-2640),
`verify-detail.txt` contained nothing but two `PytestBenchmarkWarning` blocks; the 9
actual `FAILED test_issues_cli.py::…` lines were truncated away. Diagnosing the false
negative required a full manual re-run of the suite (~71s) to see the real failures.
A better artifact would have surfaced the root cause immediately.

## Current Behavior

`verify-detail.txt` = first ~500 chars of combined stdout/stderr. When leading output
is warnings/banners, the substantive failure summary is dropped.

## Expected Behavior

The artifact should preserve the diagnostic tail of a pytest run — at minimum the
`=== short test summary info ===` / `FAILED …` block and the final
`N failed, M passed …` line. Options:
- Capture the **last** N lines (tail) rather than the first N chars, or
- Grep for and always include `FAILED`/`ERROR`/`short test summary` lines regardless
  of position, or
- Raise the cap and prefer the tail.

## Impact

Low severity but high friction: every failed verify is currently opaque, forcing a
manual re-run to learn what broke. Fixing this makes false negatives (like BUG-2640)
and true failures alike diagnosable directly from the run dir.

## Implementation Steps

1. Find where `verify-detail.txt` is written (the epic-merge verify path;
   `scripts/little_loops/parallel/orchestrator.py` verify helpers or the FSM
   finalize/merge states).
2. Change the capture to tail-based (or grep-for-failures) so the pytest summary is
   retained; keep a reasonable size bound.
3. Verify with a deliberately-failing suite that `FAILED` lines appear in the artifact.

## Acceptance Criteria

- [x] `verify-detail.txt` includes the pytest `FAILED`/summary lines when the suite fails.
- [x] Leading warnings no longer crowd out the failure summary.
- [x] Size stays bounded (no unbounded full-log dump into the run dir).

## API/Interface

No public API change; internal artifact-capture behavior only.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Two truncation sites, not one — the epic path truncates *before* the YAML

The issue's Implementation Steps point only at the FSM loop, but there are **two**
`[:500]` truncations, and the one that actually fired on the EPIC-2370 run is the
first, in Python:

- `scripts/little_loops/worktree_utils.py:346` — in
  `verify_epic_branch_before_merge()`:
  ```python
  detail = (result.stderr or result.stdout or "").strip()[:500]
  message = f"{label}_cmd failed (exit {result.returncode}): {detail}"
  return False, message, result.returncode
  ```
  This is the epic-branch verify path (worktree-attached suite run). It builds
  `message` from a **first-500-char prefix**, so the `FAILED …` summary is already
  gone by the time it returns.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:378` — in the `verify`
  state's `emit()`: `(run_dir / 'verify-detail.txt').write_text(detail[:500])`.
  For epic runs `detail` is the already-truncated `message` from above, so this is a
  redundant second cap. For **non-epic in-place** runs (yaml:402–403) it is the
  sole cap, applied to `(result.stderr or result.stdout or '').strip()`.

**Root cause (why warnings crowd out failures):** both sites use
`result.stderr or result.stdout` — stderr is preferred whenever non-empty.
pytest-benchmark / xdist emit `PytestBenchmarkWarning` blocks to **stderr**, while
pytest's `=== short test summary info ===` / `FAILED …` lines go to **stdout**. So
when warnings are present, stderr wins the `or`, stdout is discarded entirely, and
the surviving stderr is first-500-char clipped — exactly reproducing BUG-2640's
"only warnings, no FAILED lines" artifact. A tail alone does not fix this; the
`stderr or stdout` selection must also be addressed (combine both, or grep the
summary out of stdout).

### Precedent for tail-based capture

- `scripts/little_loops/cli/loop/_helpers.py:1827` —
  `for _line in reason_text.splitlines()[-40:]:` caps scrollback by keeping the
  **last** N lines. Model the fix after this (line-tail), not a char-prefix.

### Tests to extend

- `scripts/tests/test_worktree_utils.py` — covers
  `verify_epic_branch_before_merge`; add a case asserting a `FAILED`/summary line
  survives in the returned `message` when stderr carries leading warnings.
- `scripts/tests/test_builtin_loops.py:2103–2160` — `verify` state coverage
  (`test_verify_state_*`, `test_verify_attaches_epic_worktree`); add an assertion on
  `verify-detail.txt` content for a failing suite.
- `scripts/tests/test_orchestrator.py` — also references the verify path.

### Decision point (2+ viable resolutions)

**Option A**: Capture the **last** N lines (line-tail) of combined stdout+stderr
instead of the first N chars, and combine streams (`stdout + stderr`) rather than
`stderr or stdout`, so the pytest summary at the tail survives.

> **Selected:** Option A (line-tail of combined streams) — reuses proven `splitlines()[-N:]` and `stderr + stdout` idioms; tool-agnostic and directly testable via the existing verify-state shell harness.

**Option B**: Grep for and always include `FAILED` / `ERROR` /
`=== short test summary info ===` lines regardless of position, appended to a
bounded head/tail snippet.

**Recommended**: Option A — line-tail of combined streams — as the minimal fix that
directly restores the diagnostic summary and matches the existing
`splitlines()[-40:]` precedent; grep-augmentation (Option B) can layer on later if
tail alone proves insufficient for non-pytest test commands. Apply the fix at
**both** `worktree_utils.py:346` and `auto-refine-and-implement.yaml:378` (or make
the YAML cap a no-op once the Python side preserves the tail), keeping a bounded
size (e.g. last ~40 lines / ~2 KB).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-14.

**Selected**: Option A — line-tail of combined stdout+stderr

**Reasoning**: The codebase has direct precedent for line-tail capture
(`cli/loop/_helpers.py:1827` `splitlines()[-40:]`, built for the same
"otherwise-invisible failure reason" problem) and for stream concatenation
(`merge_coordinator.py:635/674/763` `stderr + stdout`), so Option A copies proven
idioms with no new abstraction. Option B has zero precedent for marker-grep
extraction of subprocess output and would bake in pytest-specific patterns
(`FAILED`, `=== short test summary info ===`) that are fragile because `test_cmd`
is user-configurable (npm, mypy, ruff), which the issue itself flags as a
"layer-on-later" concern.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A (line-tail + combined streams) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| B (grep failure markers) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: Reuses `splitlines()[-N:]` (`_helpers.py:1827`) and `stderr + stdout`
  (`merge_coordinator.py`, `executor.py:1383`) idioms; the existing
  `TestVerifyStateConfigReadShell._run` harness (`test_builtin_loops.py:2906+`)
  runs the real verify shell and already asserts on `verify-detail.txt`. Risk
  docked one point because `worker_pool.py:422,601` share the `stderr or stdout`
  failure-hiding idiom but sit outside the two named sites.
- Option B: No marker-grep extraction utility exists anywhere in the tree;
  `output_parsing.py` targets LLM-authored markdown headers, not raw pytest text —
  builds from scratch (reuse score 0) and is pytest-coupled in a tool-agnostic
  test-cmd surface.

## Resolution

Implemented Option A (line-tail of combined stderr+stdout). Added
`format_verify_detail()` to `worktree_utils.py`: it concatenates streams in
`stderr + stdout` order (so pytest's stdout FAILED/short-summary lands at the
tail) and keeps the last 40 lines bounded to 2000 chars. Both truncation sites
now route through it — the epic-branch path (`verify_epic_branch_before_merge`,
formerly `(stderr or stdout)[:500]`) and the non-epic in-place path in
`auto-refine-and-implement.yaml` — and the YAML `emit()` no longer re-clips the
already-bounded detail to 500 chars. Root cause of BUG-2640 (stderr warnings
winning the `or` and crowding out the stdout failure summary) is fixed by
combining both streams rather than selecting one.

Tests: `TestFormatVerifyDetail` (unit) + a real-shell case in
`TestVerifyStateConfigReadShell` reproducing the leading-warnings shape.

## Session Log
- `/ll:manage-issue` - 2026-07-15T00:10:31Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c6be7e2-e0de-4e54-a1b4-190576241cd4.jsonl`
- `/ll:confidence-check` - 2026-07-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7b2d56e-3fff-48e8-ad00-24ee5a0d39a2.jsonl`
- `/ll:decide-issue` - 2026-07-15T00:01:22 - `ec47f6fe-5d97-40c7-be98-71f5616aee1d.jsonl`
- `/ll:refine-issue` - 2026-07-14T23:58:00 - `408fe6fb-d6a1-44e9-b5f9-1ce0fd41ea12.jsonl`
- `/ll:capture-issue` - 2026-07-14T23:40:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb11f3d4-9b5d-4067-814a-1a27441ae683.jsonl`

---

## Status

- **Status**: open
- **Priority**: P3
