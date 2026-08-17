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
relative, the pathspec is re-interpreted relative to `cwd` — `.issues/bugs/X.md`
becomes `.issues/bugs/.issues/bugs/X.md`, which matches nothing. Git exits **0**
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

## Proposed Solution

1. Pass `file_path.resolve()` as the pathspec (or use `file_path.name` with the
   existing `cwd`), so the pathspec and `cwd` agree.
2. Distinguish "no match" from "no history": when stdout is empty, check whether
   the path is tracked at all (`git ls-files --error-unmatch`) or run the lookup
   from the repo root, and log at warning level when the fallback yields nothing
   for a tracked file.
3. Add a `timeout=` to the `subprocess.run` call, matching the defensive posture
   elsewhere in this module.

## Acceptance Criteria

- [ ] `scan_completed_issues(Path(".issues"))` and
      `scan_completed_issues(Path.cwd() / ".issues")` return identical
      `completed_date` values for every file.
- [ ] A regression test asserts that equality on a fixture repo containing at
      least one issue with no `completed_at` and no Resolution date — the only
      files that reach the fallback. A fixture whose issues all carry
      `completed_at` will pass while the bug is fully present.
- [ ] A file that genuinely has no git history still yields `None`, and does so
      without a warning.
- [ ] A tracked file whose git lookup returns nothing logs a warning rather than
      returning `None` silently.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/parsing.py` — `_parse_completion_date`,
  the `git log` fallback block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/history.py` — `analyze` (`--since` / `--until`
  filter) and `summary`'s file-parsing fallback
- `scripts/little_loops/decisions.py`, `scripts/little_loops/cli/issues/decisions.py`
- Any caller of `scan_completed_issues` / `parse_completed_issue`

### Tests
- `scripts/tests/test_issue_history_parsing.py`
- `scripts/tests/test_cli_history.py`

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
