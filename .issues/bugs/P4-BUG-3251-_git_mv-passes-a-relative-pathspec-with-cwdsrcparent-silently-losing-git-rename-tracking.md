---
id: BUG-3251
type: BUG
title: _git_mv passes a relative pathspec with cwd=src.parent, silently losing git
  rename tracking
priority: P4
status: open
testable: true
relates_to:
- BUG-3243
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T20:04:02Z'
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/finalize_decomposition.py:38-46,56-60` --
  `cmd_finalize_decomposition()`, the sole caller of
  `finalize_decomposed_parent()`. Destructures `result["moved"]` into a stdout
  print and `result["warnings"]` into stderr; if the fix adds a distinct
  "moved via git vs. shutil fallback" signal to the summary dict, this is
  the one place deciding whether to surface it.
- (Conditional -- only if the optional git-mv-helper consolidation named in
  Codebase Research Findings is taken) `scripts/little_loops/cli/issues/normalize.py:463`
  and `scripts/little_loops/cli/issues/prioritize.py:143` -- both call
  `issue_lifecycle.py`'s `git_mv_with_fallback()`, the second existing git-mv
  implementation. Consolidating onto one shared helper would make these two
  callers part of the change surface; leaving `_git_mv` fixed in isolation
  (the default reading of the issue) does not touch them.

### Tests
- Model the fixture on `_git_repo(tmp_path)` in
  `scripts/tests/test_verify_private_refs.py:250-259`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_recursive_finalize.py` -- `test_parent_moved_when_explicitly_requested`
  (lines 62-73) and `test_cli_move_flag_uses_legacy_completed_dir` (lines
  152-173) both drive `_git_mv` through a `tmp_path` that is **not** a git
  repo, and today only assert `moved is True` / file-exists-at-destination --
  never `git status --porcelain` rename tracking. Post-fix, both tests will
  hit `_git_mv`'s `git mv` failure + `shutil.move` fallback (and the new
  warning log line) on every run as-is; update them (e.g. via a
  `_git_repo`-style fixture) to exercise the git-success path, or add
  assertions distinguishing fallback from success. No test in this file
  calls `_git_mv` directly today.
- New test needed: `_git_mv` asserted directly (not just through
  `finalize_decomposed_parent`) in a real temp git repo, covering both
  relative/absolute path forms and src/dst in different directories --
  pattern to follow is `TestGitCompletionDatePathFormIndependence` in
  `scripts/tests/test_issue_history_parsing.py:264-302`
  (`monkeypatch.chdir(tmp_path)` + `f.resolve()` vs `Path(f.name)`).
- New test needed: `caplog`-based assertion that the `shutil.move` fallback
  logs git's stderr, modeled on
  `test_git_log_fallback_none_but_debug_logged_when_tracked`
  (`scripts/tests/test_issue_history_parsing.py:224-239`), keyed on logger
  name `little_loops.recursive_finalize` once added.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1555-1573` -- `ll-issues finalize-decomposition`
  reference. Confirms `_git_mv` is reachable only behind the already-deprecated
  `--move` flag (`move_to_completed` guard at `recursive_finalize.py:171`);
  no textual change required for the fix itself, but this is the doc a user
  would consult if git-rename-tracking behavior becomes newly documented.

### Related Issues
- BUG-3243 -- same defect shape in `_parse_completion_date`, explicitly scoped
  to exclude this instance.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

- **Reachability confirmed via the production call chain.** `finalize_decomposed_parent`'s only caller, `cmd_finalize_decomposition` (`scripts/little_loops/cli/issues/finalize_decomposition.py:38-46`), resolves `issues_dir` to absolute via `Path.cwd()` whenever `--config`/`-C` is not passed: `project_root = args.config or Path.cwd()`. All four current invocation sites (`rn-decompose.yaml:232`, `autodev.yaml:1130`, `autodev.yaml:1485`, `recursive-refine.yaml:431`, `recursive-refine.yaml:722`) call `ll-issues finalize-decomposition "$ID" --children-file ...` with no `--config` flag, so `issues_dir`/`src`/`dst` are absolute in every currently-wired call and the defect is not exercised today. It is reachable only via an explicit relative `--config` value, or a direct/future caller of `finalize_decomposed_parent()`/`_git_mv()` with relative paths. The fix is still correct to make — `_git_mv` should not depend on its caller's path form — but this bounds the bug's current blast radius to latent rather than active.
- **`dst` always differs from `src`'s directory when `_git_mv` is invoked** (confirmed, not just claimed): the guard `"completed" not in parent_path.parts` (`recursive_finalize.py:171`) ensures `src` is never already under `completed/`, and `dst.parent` is always `issues_dir / "completed"` (`:172`) — so `src.name`/`dst.name` alone (the BUG-3243 remedy) cannot work here.
- **No logging capability exists in this module today.** `recursive_finalize.py`'s module docstring (line 9) states it is deliberately filesystem-only ("no git, no Logger, no BRConfig") so it can be unit tested against a temp `.issues` tree — any fix that logs the fallback needs to either accept a logger dependency here or return/print through another channel, a design tradeoff not yet made.
- **Directly analogous existing precedent for the logging half**: `scripts/little_loops/issue_discovery/search.py:415-418` already does `logger.warning(f"git mv failed, using manual copy: {result.stderr}")` at a `git mv` fallback branch — same shape, different module (one that does have a logger in scope).
- **A second existing `git mv` implementation with no `cwd` mismatch**: `scripts/little_loops/issue_lifecycle.py:1339-1346` (`git_mv_with_fallback`) passes full path strings with no `cwd=` argument at all — worth checking during implementation whether consolidating onto one shared git-mv helper (rather than fixing `_git_mv` in isolation) is in scope, per the capability-search guidance for avoiding duplicate near-identical logic.
- **Codebase-wide pattern survey**: no other `subprocess.run(["git", ...])` call site in the repo pairs a caller's full/relative path with `cwd=<that path's own parent>` — the three shapes that do work are (a) pathspec reduced to agree with `cwd` (`issue_history/parsing.py:224-240`, the BUG-3243 fix; test fixtures using bare filenames), (b) `cwd` omitted and full/absolute paths used directly (`issue_lifecycle.py:1339`, `cli/migrate.py:52-84`, `issue_discovery/search.py:410-418`), (c) `cwd` fixed at the repo root with bare relative args (`parallel/git_lock.py:81-142`, `hooks/post_tool_use.py:115-134`, which explicitly resolves the path to absolute before calling git). `_git_mv` is the only site combining a caller-relative path with `cwd=` set to that path's own parent.
- **No existing test file covers `_git_mv`/`finalize_decomposed_parent`'s git-tracking behavior.** `scripts/tests/test_recursive_finalize.py` has general coverage of `finalize_decomposed_parent()` (e.g. `test_parent_moved_when_explicitly_requested`, lines 62-73) but does not assert on `git status --porcelain` rename detection. `scripts/tests/test_issue_migration.py:55-80` exercises a different function (`cli/migrate.py`'s `_move_file`) via mocked `subprocess.run`, not a real repo.
- Second regression-test precedent to model beyond `_git_repo(tmp_path)`: `TestGitCompletionDatePathFormIndependence` in `scripts/tests/test_issue_history_parsing.py:264-289` — the standing "same operation, relative and absolute path form, assert identical outcome" shape (using `monkeypatch.chdir(tmp_path)` for the relative case).

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

**Signatures**
- `_git_mv(src: Path, dst: Path) -> None` — `scripts/little_loops/recursive_finalize.py:74-89` (existing, full body already confirmed):
  ```python
  def _git_mv(src: Path, dst: Path) -> None:
      dst.parent.mkdir(parents=True, exist_ok=True)
      try:
          result = subprocess.run(["git", "mv", str(src), str(dst)],
                                   capture_output=True, text=True, cwd=src.parent)
          if result.returncode == 0:
              return
      except (OSError, subprocess.SubprocessError):
          pass
      shutil.move(str(src), str(dst))
  ```
- Sole caller: `finalize_decomposed_parent()` (`recursive_finalize.py:~148-176`) — `dst = issues_dir / "completed" / parent_path.name`; `_git_mv(parent_path, dst)` called only when `move_to_completed` is set and `dst` doesn't already exist.

**Call Path**
`ll-issues finalize-decomposition "$ID"` -> `cmd_finalize_decomposition()` (`cli/issues/finalize_decomposition.py:38-46`, resolves `issues_dir` absolute via `Path.cwd()` unless `--config` is relative) -> `finalize_decomposed_parent(issues_dir, ...)` (`recursive_finalize.py:~137-176`) -> `_git_mv(parent_path, dst)` (`:175`) -> `subprocess.run(["git", "mv", str(src), str(dst)], cwd=src.parent)` -> non-zero exit on relative-path mismatch -> silent `shutil.move(str(src), str(dst))` fallback (no log line, no distinction recorded in the caller's summary dict).

**Decision Rules**
N/A — no new gap kind, gate, or threshold. This is a path-resolution correctness fix plus adding a previously-absent log line on the fallback path; it does not introduce new classification logic.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

1. `_git_mv(src, dst)` produces a git-tracked rename (`git status --porcelain` shows `R`) for a tracked file, regardless of whether the caller passes relative or absolute `src`/`dst`, and regardless of whether `src` and `dst` are in different directories (`recursive_finalize.py:170-176` guarantees they always are, when `_git_mv` is invoked from `finalize_decomposed_parent`).
2. When the `git mv` invocation fails (non-zero exit, or `OSError`/`SubprocessError`) and the `shutil.move` fallback runs, a log line names git's captured `stderr` — matching the existing precedent at `scripts/little_loops/issue_discovery/search.py:415-418` (`logger.warning(f"git mv failed, using manual copy: {result.stderr}")`). `recursive_finalize.py` currently has no logger in scope (module docstring, line 9); decide deliberately whether to add one or route the notice through the caller instead of leaving the fallback silent.
3. `python -m pytest scripts/tests/` passes, including new regression coverage in a real temp git repo (model on `_git_repo(tmp_path)`, `scripts/tests/test_verify_private_refs.py:250-259`, or the path-form-independence shape in `TestGitCompletionDatePathFormIndependence`, `scripts/tests/test_issue_history_parsing.py:264-289`) asserting the rename stages correctly for both relative and absolute path forms, and that `src`/`dst` in different directories is handled (the case `.name`-only remedies from BUG-3243 do not cover).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `logger = logging.getLogger(__name__)` to `recursive_finalize.py` following
  the repo convention at `scripts/little_loops/subprocess_utils.py:10,28`
  (module-scope, immediately after imports) -- this is the first `logging`
  import in this module, which contradicts the module docstring's "no
  Logger" claim (line 9); update that docstring line to match.
- Update `scripts/tests/test_recursive_finalize.py` --
  `test_parent_moved_when_explicitly_requested` and
  `test_cli_move_flag_uses_legacy_completed_dir` currently run against a
  non-git `tmp_path` and will silently exercise the fallback path post-fix;
  give them a `_git_repo`-style fixture or add assertions that distinguish
  git-success from fallback.
- Add a direct `_git_mv` unit test (relative/absolute path forms,
  cross-directory src/dst) and a `caplog` test for the fallback warning line,
  per the Tests subsection of the Integration Map above.
- No `docs/reference/CLI.md` or `docs/reference/API.md` text change is
  required for the fix itself (confirmed by wiring pass) -- `_git_mv` is
  reachable only behind the already-deprecated `--move` flag.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-18 — based on codebase analysis:_

Confirmed exact mechanism, and confirmed the shutil.move fallback is unconditionally silent today: `_git_mv`'s `except (OSError, subprocess.SubprocessError): pass` and its implicit fallthrough on non-zero `returncode` both drop straight to `shutil.move(str(src), str(dst))` with no print/log/exception of `result.stdout`/`result.stderr` — because `recursive_finalize.py` has no `Logger`/logging import anywhere in the module (its docstring at line 9 states this is deliberate, so the module can be unit-tested filesystem-only). The caller (`finalize_decomposed_parent`) only records whether a move happened (`moved: True/False`) in its summary dict, not whether it went through `git mv` or the fallback — so a lost rename is invisible end to end, not just at the subprocess boundary.

Also confirmed: in every currently-wired production call path (`rn-decompose.yaml`, `autodev.yaml`, `recursive-refine.yaml` — none pass `--config`), `issues_dir` resolves to absolute via `Path.cwd()` before reaching `_git_mv`, so the defect is latent rather than actively triggered today; it would trigger the moment a caller supplies a relative `--config` or calls `finalize_decomposed_parent`/`_git_mv` directly with relative paths. See Integration Map for the exact resolution chain.

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
- `/ll:wire-issue` - 2026-08-19T00:25:55 - `f3fa68b7-2bba-49c2-bc92-65b2f7b84de6.jsonl`
- `/ll:refine-issue` - 2026-08-18T14:51:52 - `1b75a5d5-cd19-4f54-9db4-f0438e3206cc.jsonl`
- `/ll:capture-issue` - 2026-08-17T20:04:13 - `86ab77f1-d20d-487b-9f55-2f4d8abf9a06.jsonl`
