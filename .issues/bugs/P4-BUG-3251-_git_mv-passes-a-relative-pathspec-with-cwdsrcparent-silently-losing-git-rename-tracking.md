---
id: BUG-3251
type: BUG
title: _git_mv passes a relative pathspec with cwd=src.parent, silently losing git
  rename tracking
priority: P4
status: open
testable: true
relates_to: [BUG-3243]
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T20:04:02Z'
---

# BUG-3251: _git_mv passes a relative pathspec with cwd=src.parent, silently losing git rename tracking

## Summary

`_git_mv` in `scripts/little_loops/recursive_finalize.py:74-89` passes `src`
and `dst` as-is while setting `cwd=src.parent`. When the caller supplies
relative paths, git re-interprets them relative to that `cwd` and the move
fails, silently falling through to `shutil.move` -- which moves the file
correctly but outside git's index, losing rename tracking.

Same defect shape as BUG-3243 (`_parse_completion_date`'s `git log` fallback),
found while reviewing it. This instance degrades safely, so it costs history
fidelity rather than correctness -- hence P4.

## Current Behavior

```python
result = subprocess.run(
    ["git", "mv", str(src), str(dst)],
    capture_output=True, text=True,
    cwd=src.parent,
)
if result.returncode == 0:
    return
...
shutil.move(str(src), str(dst))
```

With a relative `src` of the form `<issues-dir>/epics/<name>.md` and `cwd` set
to that same `epics/` directory, git resolves the pathspec with the directory
prefix repeated twice, which does not exist. `git mv` exits non-zero, the guard falls through, and
`shutil.move` performs the move. The file lands in the right place and the
operation reports success, so the failure is invisible.

Unlike BUG-3243 this does not produce wrong data. The observable cost is that
git records a delete plus an add instead of a rename, so `git log --follow`
and blame across the move are degraded for the affected file.

## Expected Behavior

`_git_mv` uses `git mv` whenever the file is tracked and the repo is available,
regardless of the path form the caller passed. Falling back to `shutil.move` is
logged, so a lost rename is discoverable.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

1. Make pathspec and `cwd` agree. Note `dst` may be in a different directory
   than `src`, so `src.name`/`dst.name` is not generally correct here (it is in
   BUG-3243, where there is one path); prefer resolving both against a common
   base, or run from the repo root with the paths left as-is.
2. Log at `debug` (or `warning`) when the `git mv` fails and the `shutil.move`
   fallback is taken, quoting git's stderr. Today the fallback is
   indistinguishable from the happy path.

## Integration Map

### Files to Modify
- `scripts/little_loops/recursive_finalize.py:74-89` -- `_git_mv`

### Dependent Files
- `scripts/little_loops/recursive_finalize.py:170-176` -- the sole caller:
  `dst = issues_dir / "completed" / parent_path.name`, then
  `_git_mv(parent_path, dst)`. Path form depends on how `issues_dir` /
  `parent_path` reach this function; confirm as part of the fix. Note `dst` is
  in a **different** directory (`completed/`) from `src` (`epics/`), which is
  why the `file_path.name` remedy used in BUG-3243 does not transfer here.

### Tests
- Model the fixture on `_git_repo(tmp_path)` in
  `scripts/tests/test_verify_private_refs.py:250-259`.

### Related Issues
- BUG-3243 -- same defect shape in `_parse_completion_date`, explicitly scoped
  to exclude this instance.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Steps to Reproduce

In a scratch repo, reproducing the exact `cwd`/pathspec relationship the code
creates (verified 2026-08-17):

```bash
mkdir -p gmvtest/sub && cd gmvtest && git init -q .
echo hi > sub/a.md && git add -A && git commit -qm init

(cd sub && git mv "sub/a.md" "sub/b.md"; echo "relative exit=$?")
# -> fatal: bad source, source=sub/sub/a.md, destination=sub/sub/b.md
#    relative exit=128

(cd sub && git mv "$(pwd)/a.md" "$(pwd)/b.md"; echo "absolute exit=$?")
# -> absolute exit=0
git status --porcelain
# -> R  sub/a.md -> sub/b.md
```

The absolute form stages a rename (`R`); the relative form exits 128 and, in
`_git_mv`, falls through to `shutil.move`, which produces a delete+add instead.

## Root Cause

Pathspec and `cwd` are inconsistent. `cwd=src.parent` is set so the call runs
inside the repo, but the pathspecs are still the caller's, valid only relative
to the caller's cwd. Identical to Fault 1 in BUG-3243.

Unlike BUG-3243 there is no second fault making it silent at the git layer --
`git mv` does exit non-zero. It is silent at the *application* layer, because
the fallback is unconditional and unlogged.

## Acceptance Criteria

- [ ] `_git_mv` produces a git-tracked rename for a tracked file whether the
      caller passes relative or absolute paths.
- [ ] The `shutil.move` fallback still runs when git is genuinely unavailable
      or the file is untracked, and emits a log line naming git's stderr.
- [ ] A regression test in a real temp git repo asserts the rename is staged
      (`git status --porcelain` shows `R`) for both path forms.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found while reviewing BUG-3243; recorded there under "noted but deliberately
out of scope". Worth a grep for further instances of the
`subprocess.run([... str(relative_path)], cwd=<that path's parent>)` pattern
beyond these two.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `git`, `correctness`

## Status

**Open** | Created: 2026-08-17 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-08-17T20:04:13 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
