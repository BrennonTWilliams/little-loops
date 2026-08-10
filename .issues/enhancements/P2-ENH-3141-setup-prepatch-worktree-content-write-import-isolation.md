---
id: ENH-3141
title: "setup_prepatch_worktree() \u2014 pre-patch worktree fork with content-write\
  \ and import isolation"
type: ENH
priority: P2
status: done
discovered_date: 2026-08-10
completed_at: '2026-08-10T09:26:50Z'
epic: EPIC-2856
parent: ENH-2991
labels:
- rework
- verification
testable: true
learning_tests_required:
- pytest
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3141: setup_prepatch_worktree() — pre-patch worktree fork with content-write and import isolation

## Summary

Add `setup_prepatch_worktree()` to `scripts/little_loops/worktree_utils.py`: an
additive sibling of `setup_worktree()` that forks a worktree at a base ref, then
materializes caller-supplied *test-file content* directly into the fork
(content-write, not `git apply`). This is the isolated-tree primitive that
ENH-2991's `prepatch_check.py` core will build on.

## Parent Issue

Decomposed from ENH-2991: Pre-patch check core — candidate identification, tree
reconstruction, and verdict. Covers Proposed Change step 2 ("Reconstruct the
pre-patch tree") and the worktree-placement, content-write, and import-isolation
Design Notes.

## Motivation

Without this primitive, ENH-2991's pre-patch check core has no safe way to
materialize a pre-patch tree for test execution: reconstructing content in the
live working tree risks corrupting the user's checkout, and existing
`setup_worktree()` `copy_files` only copies on-disk files, not synthesized
content. This blocks ENH-2991 from proceeding.

## Current Behavior

`setup_worktree()` (`worktree_utils.py:157`) forks a worktree and can copy whole
on-disk files into it via `copy_files` (`shutil.copy2`), but has no way to write
synthesized in-memory content into the fork. There is no worktree variant that
forks at an arbitrary base ref and injects caller-supplied file content instead
of copying existing files.

## Expected Behavior

`setup_prepatch_worktree(base_ref, test_files, src_dir)` forks a worktree at
`base_ref` via `setup_worktree()`'s existing `base_branch` param, then writes
each `test_files[path]` string directly into the fork at `path` (content-write).
The resulting worktree:

- Sits outside the tamper guard's repo-root scan scope, so its own scratch state
  never registers as a tamper finding.
- Resolves imports from the worktree ahead of the main tree's editable-install
  site-packages when `src_dir` is provided (PYTHONPATH injection), so pre-patch
  code cannot accidentally import post-patch modules.
- Leaves the user's working tree unchanged on both success and failure paths.

`setup_worktree()` / `cleanup_worktree()` signatures are unchanged.

## Proposed Change

1. Add `setup_prepatch_worktree(base_ref: str, test_files: dict[str, str], src_dir: str | None) -> Path` to `worktree_utils.py`, wrapping `setup_worktree()`'s existing `base_branch` param (validated by `git rev-parse --verify`, `worktree_utils.py:213-220`).
2. After the fork, write each entry of `test_files` (repo-relative path → content) directly into the worktree — content-write, no patch parsing, no 3-way-merge conflict mode, no reject-hunk handling. `conftest.py` changes are included automatically since `test_files` is caller-supplied per ENH-2973's default patterns (assert this rather than re-deriving a glob list in this issue).
3. Support `src_dir`-based PYTHONPATH injection ahead of site-packages, modeled on `verify_epic_branch_before_merge()`'s `src_dir` parameter (`worktree_utils.py:483-489`) — the direct precedent for editable-install import isolation. Read `BUG-2629`, `BUG-2640`, `BUG-2649` before implementing.
4. Ensure the worktree path this function chooses sits outside `tamper_guard_changed_files()`'s repo-root scan scope (`scripts/little_loops/test_tamper_guard.py:175-190` unions `git diff --name-only HEAD` with `git ls-files --others --exclude-standard` at the repo root) — a test proves no tamper finding is attributable to the worktree's own scratch state.
5. Guarantee the working tree is restored to its original state on both success and failure paths (teardown via `cleanup_worktree()` in a `finally`, following `verify_epic_branch_before_merge()`'s create → run-in-isolation → teardown-in-`finally` shape, `worktree_utils.py:380-510`).

## Design Notes

- **Content-write over `git apply`.** `read_paths_at_ref()` (`scripts/little_loops/test_tamper_guard.py:112-120`) already reads file content at an arbitrary ref without a worktree, and points toward content-write (it returns text to write, not a diff to apply). A repo-wide grep for `git apply` returns zero hits — there is no existing content-materialization precedent to compare against. Content-write is the recommended default; pin it during implementation.
- **`copy_files` is not reusable for this.** `setup_worktree()`'s existing `copy_files` mechanism (`worktree_utils.py:245-262`) copies whole files from the main repo via `shutil.copy2` — it does not accept synthesized in-memory content. `test_files: dict[str, str]` is a genuinely new capability.
- **Import isolation is load-bearing.** A worktree checkout of the pre-patch tree can still import the *main-tree* package when the project is installed editable (the install pins an absolute path). Resolve imports from the worktree, and prove the isolation with a test — `test_src_dir_prepends_worktree_source_onto_pythonpath` (`test_worktree_utils.py:447`), `test_falsy_src_dir_leaves_pythonpath_uninjected` (`:479`), and `test_verify_gate_marker_set_in_child_env` (`:556`) are the direct template (probe-subprocess pattern via inline `python3 -c`).
- **Tamper-guard placement is a correctness requirement, not a nice-to-have.** `tamper_guard_changed_files()` is a pure function of its `repo_root` argument — safety depends entirely on what `repo_root` the caller passes into the tamper-guard check, not on any property internal to the function. A pre-patch worktree placed inside that tree is not protected by anything in `tamper_guard_changed_files()` itself. Under `tamper_guard: fail` (which `oracles/code-run-gate.yaml:50` sets), an unprotected placement jumps the run straight to the failure terminal.
- Use an isolated worktree rather than mutating the working tree in place; this primitive must never leave the user's tree in a different state than it found it.
- `setup_worktree()`'s current full signature (`worktree_utils.py:157-166`): `setup_worktree(repo_path, worktree_path, branch_name, copy_files, logger, git_lock, base_branch=None, checkout_existing=False)`. Body order: mutual-exclusivity check on `base_branch`/`checkout_existing` (`:195-196`) → `base_branch` resolved via `git rev-parse --verify` (`:213-220`) → `git worktree add` (`:222-235`) → git-config copy (`:238-244`) → `.claude/` copytree (`:246-253`) → `copy_files` loop (`:256-271`) → session marker write (`:276-278`). `cleanup_worktree(worktree_path, repo_path, logger, git_lock, delete_branch=True)` (`:281-286`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Stale anchor correction**: `copy_files` loop in `setup_worktree()` is cited above as `worktree_utils.py:245-262` — the loop actually starts at line 256 and ends at line 271 (`for file_path in copy_files:` → `logger.debug(f"Skipped {file_path} (not found in main repo)")`); lines 245-255 are the preceding `.claude/` copytree block, not the `copy_files` loop.
- **Stale anchor correction**: the three PYTHONPATH/import-isolation test citations above (`test_worktree_utils.py:447`, `:479`, `:556`) are stale — the file has grown since those were recorded. Current locations: `test_src_dir_prepends_worktree_source_onto_pythonpath` at `:694`, `test_falsy_src_dir_leaves_pythonpath_uninjected` at `:726`, `test_verify_gate_marker_set_in_child_env` at `:803`. There is also a fourth, previously uncited sibling test at this location: `test_falsy_src_dir_does_not_inject_under_ambient_pythonpath` (`:762`) — a BUG-2649 regression guard that an ambient (caller-set) `PYTHONPATH` is left untouched, not just unset, when `src_dir` is falsy.
- **`cleanup_worktree()` calls `preserve_before_teardown()` before force-removing** (`worktree_utils.py`, inside `cleanup_worktree`, BUG-2963 #8) — it snapshots any non-noise uncommitted work in the worktree to a durable ref before `git worktree remove --force`. This is relevant to the "user's working tree is unchanged... including on failure paths" acceptance criterion: teardown already has a built-in safety net for uncommitted scratch state in the worktree itself, independent of anything `setup_prepatch_worktree()` adds.

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/worktree_utils.py` — new additive sibling `setup_prepatch_worktree()` wrapping `setup_worktree()`. `setup_worktree()` / `cleanup_worktree()` signatures **unchanged** — `fsm/executor.py` (`:942`), `cli/loop/run.py` (`:484`), and `parallel/worker_pool.py`'s `_setup_worktree()` / `_cleanup_worktree()` (`:762-834`, `:834-865+`) call them directly.

### Similar Patterns to Follow

- `verify_epic_branch_before_merge()` (`worktree_utils.py:380-510`) — the create → run-in-isolation → teardown-in-`finally` shape, plus its `src_dir` PYTHONPATH-injection fix at `:483-489` for editable-install import isolation.
- `read_paths_at_ref()` (`scripts/little_loops/test_tamper_guard.py:112-120`) — reads file content at an arbitrary ref without a worktree; the closest existing precedent for the content-materialization direction this issue takes.

### Tests

- `scripts/tests/test_worktree_utils.py` — extend for `setup_prepatch_worktree()`, modeled on `TestVerifyEpicBranchBeforeMerge` (lines 350-690), specifically `test_src_dir_prepends_worktree_source_onto_pythonpath` (`:447`), `test_falsy_src_dir_leaves_pythonpath_uninjected` (`:479`), and `test_verify_gate_marker_set_in_child_env` (`:556`).
- `scripts/tests/test_orchestrator.py` patches `little_loops.worktree_utils.setup_worktree` at ~7 sites (lines 1761-1888) and `scripts/tests/test_cli_loop_worktree.py` covers `ll-loop run --worktree` — both must keep passing, which the additive-signature constraint guarantees.
- `scripts/tests/test_worker_pool.py::TestWorkerPoolWorktreeManagement` (`:634-1052`) exercises the real `_setup_worktree()`/`_cleanup_worktree()` bodies (not mocked) and asserts on captured git argv; confirm it keeps passing.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_test_tamper_guard.py` — the AC4 tamper-guard-scope test (no finding attributable to the pre-patch worktree) has no existing worktree-adjacent coverage in this file and should be added here (not only in `test_worktree_utils.py`), modeled on `TestTamperGuardCandidatePaths::test_finds_tracked_test_files` (`:273`) / `test_includes_untracked_test_files` (`:285`) and `TestTamperGuardChangedFiles::test_no_changes_returns_empty` (`:313`) — create a repo, write a file under `.worktrees/`, assert it's absent from both `tamper_guard_candidate_paths()` and `tamper_guard_changed_files()` [Agent 3 finding].
- `scripts/tests/test_worktree_concurrency.py` (`test_concurrent_setup_cleanup_leaves_no_orphans`, lines 45-100) — calls `setup_worktree()`/`cleanup_worktree()` directly, unmocked, against a real repo across threaded workers (regression guard for BUG-140/BUG-579); additive change keeps it passing, confirm [Agent 1 finding].
- `scripts/tests/test_git_operations.py::test_cleanup_worktree_preserves_before_removing` (`:397`) — calls `cleanup_worktree()` directly, unmocked, asserting the abandoned-branch backstop is wired in; additive change keeps it passing, confirm [Agent 1 finding].
- `scripts/tests/test_subprocess_mocks.py` (lines 559-753) — exercises `WorkerPool._setup_worktree()`/`_cleanup_worktree()` via mocked subprocess, overlapping `test_worker_pool.py::TestWorkerPoolWorktreeManagement` coverage; confirm it keeps passing [Agent 1 finding].
- Content-write pattern precedent: `_write_scaffold(target: Path, files: dict[Path, str])` (`scripts/little_loops/cli/create_extension.py:35`) is the closest existing "write a dict of {path: content} to disk" idiom (`mkdir(parents=True, exist_ok=True)` + `write_text`), though its keys are pre-resolved absolute paths rather than repo-relative strings — `setup_prepatch_worktree()` needs its own path-joining step before writing [Agent 3 finding].
- Teardown-in-`finally` on a mid-body exception (after worktree creation, before normal completion) has no existing test precedent among the three known `src_dir`/PYTHONPATH tests — a new test should force an exception after fork and assert `cleanup_worktree()` still ran [Agent 3 finding].

### Documentation

- `docs/reference/WORKTREES.md` — the "Related" list (`:40`) currently names only `setup_worktree()`/`verify_epic_branch_before_merge()`; add `setup_prepatch_worktree()` as a third named function.

### Related Issues

- `ENH-2991` (parent) — the `prepatch_check.py` core that consumes this primitive.
- `ENH-2854` (peer, landed 2026-07-31) — supplies the ref-reading primitive (`read_paths_at_ref`) this issue's content-write approach is modeled after.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Path correction**: `read_paths_at_ref()` and `tamper_guard_changed_files()` live in `scripts/little_loops/test_tamper_guard.py` (a `little_loops` module, not a `scripts/tests/` test file as earlier references in this issue implied) — the pytest coverage for this module is `scripts/tests/test_test_tamper_guard.py`. Bare `test_tamper_guard.py` mentions elsewhere in this issue have been corrected to the full path above.
- **Worktree placement convention**: the one existing precedent (`verify_epic_branch_before_merge()`) places worktrees *inside* `repo_path` under a caller-supplied `worktree_base` (typically `.worktrees`, the config default in `config-schema.json:255,321` and `.gitignore:71`) — not physically outside the repo directory tree. `tamper_guard_changed_files()`'s scan (`git diff --name-only HEAD` + `git ls-files --others --exclude-standard`) is blind to a gitignored path regardless of nesting, since `--exclude-standard` respects `.gitignore`. "Outside the tamper guard's repo-root scan scope" (Expected Behavior) is satisfiable by gitignore exclusion under `.worktrees/`, matching the existing convention, and does not require placement outside `repo_path` on disk.
- **No shared batch-write utility exists.** `scripts/little_loops/cli/create_extension.py:35-39`'s `_write_scaffold(target: Path, files: dict[Path, str])` is the one existing "write a dict of {path: content} to disk" loop in the codebase, but it is module-private and unrelated to worktrees/git. `scripts/little_loops/file_utils.py` has `atomic_write(path, content)` (single-file only) — no batch/dict variant to reuse.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Alternative existing precedent for path-prefix worktree exclusion**: `scripts/little_loops/work_verification.py:19-44` defines `EXCLUDED_DIRECTORIES = (".issues/", "issues/", ".speckit/", "thoughts/", ".worktrees/", ".auto-manage")` and `filter_excluded_files(files: list[str]) -> list[str]`, which drops any path whose string `.startswith()` one of those prefixes. This is a second, independent convention for excluding `.worktrees/` content from a repo-root file scan — distinct from `tamper_guard_changed_files()`'s gitignore-based (`--exclude-standard`) exclusion already discussed above. Both conventions currently co-exist in the codebase; `tamper_guard_changed_files()` relies on the gitignore route only, so this issue's tamper-guard-scope AC does not need to touch `work_verification.py`, but an implementer should know a second, stricter (explicit-prefix) exclusion pattern exists elsewhere in case future work needs to harden past gitignore-only filtering.

## Scope Boundaries

- **Not this issue**: candidate-test identification, running tests inside the worktree, verdict/retry-flaky logic, or the `PrePatchEvidence` bundle — all ENH-2991 (the sibling core-module issue).
- **Not this issue**: the `base_dirty` reader in `history_reader.py` — that lands in ENH-2991.
- **Not this issue**: changing `setup_worktree()` / `cleanup_worktree()` signatures.

## Acceptance Criteria

- [x] `setup_prepatch_worktree(base_ref, test_files, src_dir)` forks a worktree at `base_ref` and writes each `test_files[path]` entry directly into the fork (content-write, not `git apply`).
- [x] `conftest.py` changes are applied to the pre-patch tree when present in `test_files` — a test asserts it (no glob list re-implemented here).
- [x] The pre-patch worktree resolves imports from itself, not the main tree's editable install, when `src_dir` is provided; a test proves a post-patch-only module is unimportable from the worktree.
- [x] The pre-patch worktree is created outside the tamper guard's repo-root scan scope; a test asserts running inside a `tamper_guard`-guarded window produces no tamper finding attributable to this worktree.
- [x] The user's working tree is unchanged after `setup_prepatch_worktree()` / teardown, including on failure paths.
- [x] `setup_worktree()` / `cleanup_worktree()` signatures are unchanged; existing call sites in `fsm/executor.py`, `cli/loop/run.py`, and `parallel/worker_pool.py` keep passing (`test_orchestrator.py`, `test_cli_loop_worktree.py`, `test_worker_pool.py::TestWorkerPoolWorktreeManagement`).

## Resolution

Added `setup_prepatch_worktree()` to `scripts/little_loops/worktree_utils.py`,
right after `cleanup_worktree()`. It forks via the existing `setup_worktree(base_branch=base_ref,
copy_files=[])`, then content-writes each `test_files[path]` entry with
`Path.write_text()` after `mkdir(parents=True)`. `src_dir`, when given, is
validated to exist in the fork (`RuntimeError` + `cleanup_worktree()` teardown
if absent) — the actual `PYTHONPATH` prepend for running tests in the worktree
is caller-side (ENH-2991's job; this issue explicitly excludes running tests).
Any exception during materialization tears the worktree down before
re-raising; the main repo's working tree is never touched either way since
`git worktree add`/`remove` never mutate `repo_path` in place. Default
`worktree_base=".worktrees"` (gitignored) keeps the fork outside
`tamper_guard_changed_files()`'s `--exclude-standard` scan scope.

7 new tests added: `test_worktree_utils.py::TestSetupPrepatchWorktree` (6 —
content-write, conftest.py write, import isolation via a real post-patch-only
module, missing-`src_dir` teardown, working-tree-unchanged, exception-after-fork
teardown) and `test_test_tamper_guard.py::TestTamperGuardScopeExcludesPrepatchWorktree`
(1 — AC4). `docs/reference/WORKTREES.md`'s Related list updated. Also fixed an
unrelated pre-existing prose-dependency drift gate failure: ENH-3142 names
ENH-3141 as a hard blocking dependency in prose without a `depends_on:`
frontmatter edge — added `depends_on: [ENH-3141]`.

Full suite: 18868 passed, 43 skipped (`--deselect
tests/test_research_triage.py::TestCorpusBaseline::test_full_predicate_is_not_inert`,
9m27s). That one test hangs under `-n auto` xdist both with and without this
change (reproduced on unmodified `main` via `git stash`) — a pre-existing,
unrelated environmental issue, not caused by this work.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

### Types

- `test_files: dict[str, str]` — repo-relative path → content, the same shape returned by `read_paths_at_ref()` (`scripts/little_loops/test_tamper_guard.py:112-120`: `dict[str, str | None]`, `None` where a path is absent at the ref).
- `src_dir: str | None` — matches `verify_epic_branch_before_merge()`'s existing `src_dir` parameter (`worktree_utils.py:380-389`), truthy-gated.

### Signatures

- `setup_worktree(repo_path: Path, worktree_path: Path, branch_name: str, copy_files: list[str], logger: Logger, git_lock: GitLock, base_branch: str | None = None, checkout_existing: bool = False) -> None` — unchanged; `setup_prepatch_worktree()` calls this with `base_branch=base_ref`, `copy_files=[]`.
- `cleanup_worktree(worktree_path: Path, repo_path: Path, logger: Logger, git_lock: GitLock, delete_branch: bool = True) -> None` — unchanged; called in the new function's `finally`.
- Target: `setup_prepatch_worktree(base_ref: str, test_files: dict[str, str], src_dir: str | None) -> Path`.

### Call Path

`setup_prepatch_worktree()` -> `setup_worktree(base_branch=base_ref, copy_files=[])` (fork) -> per-entry `Path.write_text()` over `test_files` (content-write, new code path distinct from the existing `copy_files` loop at `worktree_utils.py:256-271`) -> (caller-side) subprocess env built with `PYTHONPATH` prepended from `src_dir`, mirroring `verify_epic_branch_before_merge()`'s injection at `worktree_utils.py:483-489` -> `cleanup_worktree()` in `finally`.

### Decision Rules

N/A — no new decision logic; this issue reuses `setup_worktree()`'s existing `base_branch` validation and adds a content-write step, not a new gate or threshold.

## Impact

- **Priority**: P2 — prerequisite primitive for ENH-2991's pre-patch check core.
- **Effort**: Medium — one additive function plus import-isolation and tamper-guard-scope tests; no new evidence-bundle logic.
- **Risk**: Medium — `setup_worktree()`/`cleanup_worktree()` are called directly by three other modules; any signature change must stay additive.
- **Breaking Change**: No — additive worktree variant only.

## Status

**Open** | Created: 2026-08-10 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-10T09:26:29 - `973df193-be4f-4902-bf46-c2a0fdbdba68.jsonl`
- `/ll:ready-issue` - 2026-08-10T07:55:14 - `1a6c43ab-0f6b-4b34-b300-a294ff5aabd2.jsonl`
- `/ll:confidence-check` - 2026-08-10T07:53:05 - `d007670e-b4dc-40fc-906a-1b689fab0a2e.jsonl`
- `/ll:verify-issues` - 2026-08-10T07:50:43 - `c2a403c5-d326-4d45-a929-0cc10b29647e.jsonl`
- `/ll:refine-issue` - 2026-08-10T07:48:41 - `8ab2b9f6-8272-4ec2-890f-4104d90d814f.jsonl`
- `/ll:verify-issues` - 2026-08-10T07:43:11 - `47fe4a3a-43de-48ca-a76b-3c784e00e016.jsonl`
- `/ll:wire-issue` - 2026-08-10T07:38:26 - `876ca9c3-8a25-42ad-aa0f-defd4976d57c.jsonl`
- `/ll:refine-issue` - 2026-08-10T07:28:53 - `90b829b5-d753-42b7-96ef-c482b858c8e5.jsonl`
- `/ll:issue-size-review` - 2026-08-10T07:23:33 - `7e0f8f7e-cdcf-448e-8ae7-22d89c36b63b.jsonl`
