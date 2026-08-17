---
id: BUG-3243
type: BUG
title: _parse_completion_date's git fallback silently returns None for relative paths,
  so ll-history analyze --since counts depend on the caller's path form
priority: P2
status: open
testable: true
discovered_by: little-loops-hermes
discovered_date: '2026-08-17'
captured_at: '2026-08-17T18:48:10Z'
discovered_commit: 3713d7f9268bfb4478a62f0adac15531e5b486e1
discovered_branch: main
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3243: `_parse_completion_date`'s git fallback silently returns None for relative paths, so `ll-history analyze --since` counts depend on the caller's path form

## Summary

`_parse_completion_date` falls back to `git log` for issues whose completion
date is in neither frontmatter nor a Resolution section. That call passes the
file path as a pathspec *and* sets `cwd` to the file's own parent:

```python
subprocess.run(
    ["git", "log", "--format=%as", "-1", "--", str(file_path)],
    capture_output=True, text=True, cwd=file_path.parent,
)
```

When `file_path` is absolute the two agree and git returns a date. When it is
relative, the pathspec is re-interpreted relative to `cwd` — a path of the form
`<issues-dir>/<type>/<name>.md` is looked up as that same prefix repeated twice,
which matches nothing. Git exits **0**
with empty stdout, so the `returncode == 0` guard passes, the body is skipped,
and the function returns `None`.

The failure is silent in both channels: no exception, no non-zero exit, no log
line. A file that has a knowable completion date is recorded as having none.

## Current Behavior

Scanning the same 2905 `status: done` files, the count of issues completed since
2026-08-10 changes by 18 depending only on whether the caller passed a relative
or absolute directory:

```
relative: (2905, 90)
absolute: (2905, 108)
```

`ll-history analyze --format json --since 2026-08-10` reports
`total_completed: 108`, because `cli/history.py:281` builds `issues_dir` from
`config.project_root`, which is absolute. Any caller passing a relative
`--directory` — or calling `scan_completed_issues(Path(".issues"))` directly —
silently gets 90 for the same repo at the same instant.

The affected set is exactly the issues with no `completed_at` frontmatter and no
Resolution date — the only ones that reach the git fallback. Repo-wide that is
**131 of 2905**, and the fallback fails for **all** of them under a relative
path, not merely some:

```
none under absolute: 0
none under relative: 131
```

So the fallback has a 100% failure rate whenever it is reached with a relative
path, and a 0% failure rate with an absolute one. 18 of those 131 fall inside
the 2026-08-10 window, which is the 108-vs-90 difference above.

## Steps to Reproduce

1. Show the mechanism against any tracked issue file:

   ```bash
   cd <little-loops>
   f=$(ls .issues/bugs/*.md | head -1)

   git log --format=%as -1 -- "$(pwd)/$f"
   # → 2026-05-30

   (cd "$(dirname $f)" && git log --format=%as -1 -- "$f"; echo "exit=$?")
   # → (no output)
   #   exit=0
   ```

   The relative form is the one the code produces, and it exits 0.

2. Show the effect on the scanner:

   ```bash
   python3 -c "
   import sys; sys.path.insert(0,'scripts')
   from pathlib import Path
   from datetime import date
   from little_loops.issue_history.parsing import scan_completed_issues
   def cnt(d):
       i = scan_completed_issues(d)
       return len(i), len([x for x in i if x.completed_date and x.completed_date >= date(2026,8,10)])
   print('relative:', cnt(Path('.issues')))
   print('absolute:', cnt(Path.cwd() / '.issues'))
   "
   # → relative: (2905, 90)
   #   absolute: (2905, 108)
   ```

   Both forms are deterministic across repeated runs; the difference is purely
   the path form.

## Expected Behavior

`_parse_completion_date` returns the same date for a given file regardless of
whether the caller passed a relative or absolute path, and a git lookup that
finds nothing is distinguishable from one that was never able to match.

## Root Cause

Two independent faults compound:

1. **The pathspec and `cwd` are inconsistent.** `cwd=file_path.parent` is set so
   the call runs inside the repo, but the pathspec is still the *caller's* path,
   which is only valid relative to the caller's cwd. Either the pathspec should
   be `file_path.name` (correct given that `cwd`), or `cwd` should be the repo
   root with the path left as-is. Passing `file_path.resolve()` fixes it for
   both.

2. **"No commits matched this pathspec" is not an error to git.** `git log` exits
   0 with empty output, which is the same shape as a legitimately untracked
   file. The `returncode == 0 and result.stdout.strip()` guard therefore cannot
   tell "this path is nonsense" from "this file has no history", and both fall
   through to `return None`.

Fault 1 alone would be a visible break. Fault 2 is what makes it silent, and is
why this survived: the resulting count is plausible, just wrong.

## Impact

- **A completion metric changes with an implementation detail of the caller.**
  Two callers of the same function on the same repo at the same moment report
  108 and 90. Nothing in either result indicates which is complete.
- **It biases toward undercounting**, and specifically undercounts the issues
  with the least frontmatter — the older or hand-edited ones. Any trend computed
  over that set is skewed, not merely noisy.
- **`subprocess.run` here has no `check`, no timeout, and no logging**, so the
  fallback cannot report that it failed even in principle.

## Program Design

### Types

- `_GitDateResult: tuple[date | None, bool]` — the fallback's outcome as
  (parsed date, `tracked_without_history`). The second element is what lets the
  caller distinguish "this file has no git history" from "the lookup silently
  matched nothing", which the current single `date | None` return cannot express.

### Signatures

- `_git_completion_date(file_path: Path) -> _GitDateResult` (new, extracted from
  the inline fallback block in `issue_history/parsing.py`)
- `_parse_completion_date(content: str, file_path: Path, *, batch_dates: dict[str, date] | None = None, fm: dict[str, Any] | None = None) -> date | None` (unchanged signature, `issue_history/parsing.py:137`)
- `scan_completed_issues(issues_dir: Path, category_dirs: list[str] | None = None) -> list[CompletedIssue]` (unchanged signature, gains the aggregated warning, `issue_history/parsing.py:289`)

### Call Path

`scan_completed_issues(issues_dir)` -> `parse_completed_issue(file_path)` ->
`_parse_completion_date(content, file_path)` -> (frontmatter miss, Resolution
miss, `batch_dates is None`) -> `_git_completion_date(file_path)` ->
`subprocess.run(["git", "log", "--format=%as", "-1", "--", file_path.name], cwd=file_path.parent, timeout=...)`.
On empty stdout, a second `subprocess.run(["git", "ls-files", "--error-unmatch", "--", file_path.name], cwd=file_path.parent, timeout=...)`
sets the `tracked_without_history` flag. `_parse_completion_date` returns the
date and logs the flag at `debug`; `scan_completed_issues` counts flagged files
and emits one aggregated `logger.warning` after the scan.

The three direct callers outside the scanner —
`cli/issues/list_cmd.py:112`, `cli/issues/list_cmd.py:124` (`batch_dates={}`,
never reaches git), and `cli/issues/search.py:397` — enter at
`_parse_completion_date`, which is why the fix belongs at that layer rather
than at the `scan_completed_issues` boundary.

## Proposed Solution

1. **Use `file_path.name` as the pathspec** with the existing
   `cwd=file_path.parent`, so pathspec and `cwd` agree.

   Chosen over `file_path.resolve()`: `.resolve()` collapses symlinks, and the
   tests for this run under macOS `tmp_path` where `/tmp` is a symlink to
   `/private/tmp`. A resolved (physical) pathspec against a worktree that git
   discovered by a logical path is an avoidable class of flake.
   `file_path.name` is also correct for every input form including a bare
   `Path("X.md")`, where `.parent` is `Path(".")`.

2. **Distinguish "no match" from "no history"** via a second
   `git ls-files --error-unmatch -- <name>` call, run only when the `git log`
   stdout is empty (rare once fault 1 is fixed, so no meaningful added cost on
   the hot path).

3. **Log the tracked-but-no-history case at `debug` per file, and emit one
   aggregated `warning` per scan.** A per-file warning would be routinely noisy
   rather than exceptional: an issue file that `/ll:capture-issue` has `git
   add`ed but not yet committed is tracked with an empty `git log`, which is a
   normal working state in this repo. Per-file warnings would spray stderr
   during `ll-history analyze --format json` over ~2900 files.

4. **Add a `timeout=` to both `subprocess.run` calls** — and widen the `except`
   clause in the same edit (see Implementation Notes; the current clause does
   not catch the exception a timeout raises).

## Acceptance Criteria

- [ ] `scan_completed_issues(Path(".issues"))` and
      `scan_completed_issues(Path.cwd() / ".issues")` return identical
      `completed_date` values for every file.
- [ ] A regression test asserts that equality on a fixture repo containing at
      least one issue with no `completed_at` and no Resolution date — the only
      files that reach the fallback. A fixture whose issues all carry
      `completed_at` will pass while the bug is fully present.
- [ ] A file that genuinely has no git history (untracked, or outside any repo)
      still yields `None`, and does so with no log output at any level.
- [ ] A tracked file whose git lookup returns nothing is logged at `debug` per
      file, and `scan_completed_issues` emits exactly one aggregated
      `logger.warning` naming the count — not one warning per file. A scan in
      which no file hits that case emits no warning.
- [ ] `ll-issues list --sort completed` and `ll-issues search --sort completed`
      produce the same ordering whether their issue paths are relative or
      absolute. These are the only surfaces whose *output* changes when this
      lands: `ll-history analyze` already passes an absolute `issues_dir`
      (`cli/history.py:281`), so its counts are correct today and must not move.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/parsing.py` — `_parse_completion_date`,
  the `git log` fallback block

### Implementation Notes

- **Adding `timeout=` requires widening the `except` clause in the same edit.**
  `parsing.py:193` catches `(OSError, ValueError)`. `subprocess.TimeoutExpired`
  subclasses `subprocess.SubprocessError`, **not** `OSError`, so adding a
  timeout without touching the handler converts a hang into an uncaught
  exception propagated through every caller of `scan_completed_issues` and
  `ll-issues list`. Widen to `(OSError, ValueError, subprocess.SubprocessError)`.
- **Two existing tests will silently mis-exercise the new second subprocess
  call.** `test_git_log_fallback_returns_none_when_empty`
  (`test_issue_history_parsing.py:210-217`) and
  `test_git_log_fallback_returns_none_on_oserror` (`:232-240`) patch
  `subprocess.run` with a single `return_value` / `side_effect`. Once an empty
  `git log` triggers a follow-up `git ls-files --error-unmatch`, that second
  call receives the *same* `returncode=0` mock and reads as "tracked" for an
  untracked `tmp_path` file — putting the test on the warning path and directly
  contradicting AC 3. Convert these to ordered `side_effect=[...]` sequences
  supplying a distinct `CompletedProcess` per call.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/history.py` — `analyze` (`--since` / `--until`
  filter) and `summary`'s file-parsing fallback
- `scripts/little_loops/decisions.py`, `scripts/little_loops/cli/issues/decisions.py`
- Any caller of `scan_completed_issues` / `parse_completed_issue`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/list_cmd.py:110-124` — two direct calls to
  `_parse_completion_date(content, issue.path, ...)`, for `--sort completed`
  and for `--json` output's completion date. `issue.path` here is not
  guaranteed absolute, so `ll-issues list` is a second observable surface
  (beyond `ll-history analyze`) affected by the same relative-path defect.
- `scripts/little_loops/cli/issues/search.py:395-397` — same direct call to
  `_parse_completion_date(content, issue.path)` for `ll-issues search --sort
  completed`.

### Tests
- `scripts/tests/test_issue_history_parsing.py`
- `scripts/tests/test_cli_history.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_history_parsing.py` — `TestParseCompletionDate`
  (lines 159-240) mocks `subprocess.run` in every case and every fixture
  path comes from `tmp_path`, which is always absolute; none of the existing
  cases exercise a relative path or assert on the actual `git log` argv
  passed to the subprocess call. Extend with a real-git-repo regression test
  (model the fixture on `_git_repo(tmp_path)` in
  `scripts/tests/test_verify_private_refs.py:250-259`) that calls
  `_parse_completion_date` with both an absolute and a relative form of the
  same tracked file and asserts identical results. For the new "tracked file,
  fallback yields nothing" warning (AC 4), reuse the
  `caplog.at_level("WARNING", logger="little_loops.issue_history.parsing")`
  pattern from `test_scan_logs_warning_on_unreadable_file` (same file, lines
  419-435).
- `scripts/tests/test_issue_history_cli.py` — `TestMainHistoryAnalyze`
  (`test_main_history_analyze_since` / `_until`, lines 555-614) always
  invokes `ll-history analyze` with an absolute `-d`/`--directory` value;
  add a case that passes a relative `--directory` (or omits it under a
  relative cwd) to cover the end-to-end path this bug affects.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### parse_completed_issue` (~line 2257-2275)
  documents the git-log fallback's "one subprocess per file" performance
  note; should note the fix makes the result path-form independent.
- `docs/reference/CLI.md` — `#### ll-history analyze` (~line 2816-2826,
  `--since`/`--until`), `#### ll-history export <topic>` (~line 2839,
  `--since`), and `ll-issues decisions extract-from-completed --since`
  (~line 2604) all document the "completed on or after DATE" contract this
  bug undermines.
- `skills/update-docs/SKILL.md:108` — embedded script calls
  `scan_completed_issues(Path('.issues'))` with a **relative** path literal,
  a live reproduction of this exact defect class; behavior should be
  re-verified once the fix lands.

## Related Observation — not part of this bug

While isolating the above, the two available "issues completed since 2026-08-10"
figures were compared directly:

- **90** issue *files* on disk with `status: done` and a completion date in the
  window (relative-path scan; 108 by the absolute-path scan above)
- **67** rows in `issue_events` with `transition = 'done'` and `ts` in the window

Set membership is cleanly contained: **every** event corresponds to a file on
disk, and 23 files have no event. There are zero events without a file. So the
event store undercounts completions rather than disagreeing about them.

Whether those 23 *should* have emitted an event is not established here — issues
closed by direct file edit rather than through the pipeline would produce exactly
this shape, and that may be entirely expected. It is recorded because ENH-3237
cites the same discrepancy from a partly incorrect premise: it states that
`analyze` "scans completed issue *files*" while `issue_events` records events,
and infers the gap is events-never-emitted. The first half is right
(`analyze` calls `scan_completed_issues`, the file scanner) but the numbers it
quotes (107 vs 66) straddle this bug, so the size of that gap was never the
quantity it appeared to be.

## Notes

Found while verifying the numbers behind an `ll-history` consumer in
`little-loops-hermes` (see ENH-3237), not by auditing this module. The
`ll-history analyze --since` output was cross-checked against a direct scan and
the two disagreed by 18; the path form turned out to be the only difference.

## Labels

`bug`, `history`, `cli`, `correctness`


## Status

- [ ] open


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 100/100 → PROCEED (overridden — see below)
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- `## Program Design` section is missing entirely (not present-but-nonspecific —
  `format-check` reports it under `missing`, and `program_design_nonspecific` is
  empty). `ll-issues check-design BUG-3243` fails, which forces
  `STOP — ADDRESS GAPS` regardless of the 100/100 readiness sum above. Add a
  `## Program Design` section with concrete types/signatures and a call path
  (run `/ll:refine-issue` or `/ll:reconcile-issue`), or set
  `program_design_not_applicable: true` in frontmatter if this is judged
  genuinely trivial.
- `## Status` section is also reported missing by `format-check` — the issue
  file has no `## Status` footer.

### Outcome Risk Factors
- Point 2 of the Proposed Solution leaves an unresolved either/or ("check
  whether the path is tracked at all via `git ls-files --error-unmatch`, or run
  the lookup from the repo root") — pick one approach before implementing to
  avoid a mid-implementation design decision.

### Resolution of the Above — 2026-08-17

All three gaps are closed; `ll-issues check-design BUG-3243` now exits 0.

- `## Program Design` added with types, signatures, and a call path.
- `## Status` footer added.
- The Proposed Solution either/or is resolved: `git ls-files --error-unmatch`
  on empty stdout, with the pathspec fixed by `file_path.name` (not
  `.resolve()`, for the symlink reason recorded there).

Three further changes made in the same pass:

- The tracked-but-no-history signal is specified as per-file `debug` plus one
  aggregated per-scan `warning`, because the per-file warning AC 4 originally
  mandated would fire routinely for staged-but-uncommitted issue files.
- An AC was added for `ll-issues list`/`search --sort completed`, the only
  surfaces whose output actually changes; `ll-history analyze` counts must not
  move, since it already passes an absolute path.
- Two implementation traps are recorded under Integration Map → Implementation
  Notes: `subprocess.TimeoutExpired` escaping the existing `except` clause, and
  two existing tests whose single-value `subprocess.run` mock would
  mis-exercise the new second git call.

Noted but deliberately out of scope: `recursive_finalize.py:74-89` `_git_mv`
has the identical pathspec/`cwd` mismatch. It degrades safely (non-zero exit
falls through to `shutil.move`), so the effect is lost git rename tracking
rather than wrong data — worth a separate capture.

## Session Log
- `/ll:confidence-check` - 2026-08-17T19:45:58 - `62bab2ff-2e1c-48e4-ad61-470060df1e73.jsonl`
- `/ll:verify-issues` - 2026-08-17T19:43:38 - `93bf5317-f847-4d5e-adb2-63d9cc3864ac.jsonl`
- `/ll:wire-issue` - 2026-08-17T19:42:10 - `07640cd8-6bac-4fa7-bbea-0a0ea91ebf47.jsonl`
