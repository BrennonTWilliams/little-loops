---
id: BUG-2323
title: "ll-parallel/ll-sprint hardcode 'main' as base branch; no default-branch detection"
type: BUG
status: open
priority: P2
captured_at: "2026-06-26T22:26:49Z"
discovered_date: "2026-06-26"
discovered_by: audit
labels:
- parallel
- sprint
- git
- worktree
relates_to:
- BUG-180
parent: EPIC-1867
---

# BUG-2323: ll-parallel/ll-sprint hardcode 'main' as base branch; no default-branch detection

## Summary

`ll-parallel` and `ll-sprint` determine the base/integration branch by reading the
*current* branch (`git rev-parse --abbrev-ref HEAD`) and falling back to the literal
string `"main"` on any failure. There is **no detection of the repository's actual
default branch** — `git symbolic-ref refs/remotes/origin/HEAD` / `origin/HEAD` appears
**nowhere** in `scripts/little_loops/`. On a detached HEAD, or in any repo whose default
branch is `master`/`develop`/`trunk`, worktrees can be forked from — and merges targeted
at — the wrong branch.

## Motivation

`little-loops` is a Claude Code **plugin that runs inside arbitrary user repositories**,
not only this one. Many repos default to `master` or `develop`. The hardcoded `"main"`
fallback and the missing default-branch detection mean that, for those installs, a worker
that ends up on a detached HEAD (or any non-`main` HEAD where the fallback fires) will
merge into a branch the user never intended — silent, hard-to-notice integration errors.
This repo itself is on `main`, which is why the gap has stayed latent.

## Current Behavior

Base branch is resolved from the current HEAD with a hardcoded fallback:

- `scripts/little_loops/cli/parallel.py` — `main_parallel()`, the inline `_base_branch`
  detection block (commented `# Detect current branch ... (BUG-439)`):
  ```python
  _branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], ...)
  _base_branch = _branch_result.stdout.strip() if _branch_result.returncode == 0 else "main"
  ```
- `scripts/little_loops/cli/sprint/run.py` — the `_detect_current_branch()` helper **and** a
  second, independent inline copy of the same logic inside `_cmd_sprint_run()`. Both use the
  `... else "main"` fallback (the `_cmd_sprint_run()` copy does not even call the helper).
- `scripts/little_loops/parallel/types.py` — `ParallelConfig.base_branch` field defaults to
  `"main"` (consumed by `MergeCoordinator` for `git pull`/`git merge` targets).

On detached HEAD, `git rev-parse --abbrev-ref HEAD` returns `HEAD` (not an error), so the
fallback may not even fire — the literal string `"HEAD"` could be used as a branch name.

## Expected Behavior

The base branch is resolved to the repository's real default/integration branch:
1. Prefer `git symbolic-ref --short refs/remotes/origin/HEAD` (strip the `origin/` prefix).
2. Fall back to the current branch via `git rev-parse --abbrev-ref HEAD` **only when it is
   a real branch name** (not `HEAD`).
3. Fall back to `main` only as a last resort.

All three call sites and the `ParallelConfig` default route through one helper.

## Root Cause

There is no shared default-branch detection utility. The logic is duplicated three ways —
the inline block in `main_parallel()`, the `_detect_current_branch()` helper, and a second
inline copy in `_cmd_sprint_run()` that bypasses that helper — and `ParallelConfig.base_branch`
repeats the literal once more. Each variant does "current branch, else `main`". None consult
`origin/HEAD`, and none guard the detached-HEAD case where `rev-parse --abbrev-ref HEAD`
yields `HEAD`.

## Proposed Solution

Add a `detect_default_branch(repo_path, git_lock=None) -> str` helper (natural home:
`scripts/little_loops/worktree_utils.py`, alongside the other git helpers, or a small
`git_utils` module):

```python
def detect_default_branch(repo_path: Path) -> str:
    # 1. origin/HEAD symbolic ref
    r = subprocess.run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                       cwd=repo_path, capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().removeprefix("origin/")
    # 2. current branch, if it's a real branch (not detached HEAD)
    r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                       cwd=repo_path, capture_output=True, text=True)
    cur = r.stdout.strip() if r.returncode == 0 else ""
    if cur and cur != "HEAD":
        return cur
    # 3. last resort
    return "main"
```

Route the `main_parallel()` inline block (`cli/parallel.py`), the `_detect_current_branch()`
helper, and the inline copy in `_cmd_sprint_run()` (`cli/sprint/run.py`) through it. For
`ParallelConfig.base_branch`, keep the literal default but have the CLI override it with the
detected value at construction time (the config already receives `base_branch=` explicitly).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The `origin/HEAD` pattern already exists in this repo** (just not in Python). Mirror the
  canonical shell form already used in `commands/describe-pr.md:27` and `commands/open-pr.md:88`:
  ```bash
  git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main"
  ```
  The issue's "appears nowhere" claim is accurate **only** for `scripts/little_loops/` (the Python
  package); the desired behavior is already established repo-wide in the slash commands.
- **Match `worktree_utils.py` house style.** Existing helpers (`setup_worktree()`,
  `cleanup_worktree()`) take `repo_path: Path` first and accept a `git_lock: GitLock` for
  thread-safe calls via `git_lock.run([...], cwd=repo_path, timeout=N)` (args **without** the
  `"git"` prefix; returns `CompletedProcess`). So the new helper should:
  - With `git_lock` (mid-run, concurrent):
    `git_lock.run(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo_path, timeout=10)`.
  - With `git_lock is None` (CLI startup — the orchestrator's lock does not exist yet):
    bare `subprocess.run(["git", ...], cwd=repo_path, capture_output=True, text=True)`.
- **⚠ Do NOT route `_detect_current_branch()` through the new helper.** Research shows
  `_detect_current_branch()` (`cli/sprint/run.py:90`) only populates `SprintWorkerContext.branch`
  — a diagnostic/prompt **label** — at call sites `:524` and `:657`. It does **not** set
  `ParallelConfig.base_branch`. The real base-branch source in the sprint parallel path is the
  **inline block at `cli/sprint/run.py:585–592`**. Only two sites feed `base_branch` and should
  route through `detect_default_branch()`: `cli/parallel.py:211–218` and `cli/sprint/run.py:585–592`.
  Collapsing `_detect_current_branch()` onto default-branch detection would silently change the
  worker-context label from *current* branch to *default* branch.

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` — add `detect_default_branch()` (new helper).
- `scripts/little_loops/cli/parallel.py` — replace the inline `_base_branch` block in
  `main_parallel()` with the helper.
- `scripts/little_loops/cli/sprint/run.py` — route both `_detect_current_branch()` and the
  inline copy in `_cmd_sprint_run()` through the helper (collapse the duplication).
- `scripts/little_loops/parallel/types.py` — leave the `ParallelConfig.base_branch` default as
  `"main"` but document that the CLI is expected to override; no behavioral change required if
  all callers pass a detected `base_branch`.

### Dependent Files
- `scripts/little_loops/parallel/merge_coordinator.py` — consumes `config.base_branch` for
  `git checkout` / `git pull --rebase` / `git merge` targets; benefits automatically once the
  detected value flows through.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py` — **missing from the original Dependent Files;
  also consumes `parallel_config.base_branch`** at two sites that the change must be checked
  against [Agent 1 + Agent 2 finding]:
  - `_get_pending_worktree_info()` `:400` — `git rev-list --count <base_branch>..<branch_name>`
    (commits-ahead for pending-worktree detection).
  - `_open_pr_for_feature_branch()` `:1122` — `gh pr create --base <base_branch>`. This is the
    **user-facing** consequence: a wrong base here opens the PR against the wrong integration
    branch — the same silent-wrong-target failure the bug describes, surfaced via the GitHub PR.
    Benefits automatically once the detected value flows through `config.base_branch`, but should
    be listed because it is a distinct, externally-visible consumer beyond merge_coordinator.
- `scripts/little_loops/cli/loop/run.py` — imports `setup_worktree` / `cleanup_worktree` from
  `worktree_utils`; not a `base_branch` consumer (FYI: confirms the new symbol is additive — no
  `__all__` exists in `worktree_utils.py`, so `detect_default_branch()` is importable with no
  registration step) [Agent 2 finding].

### Similar Patterns
- The three branch-detection variants (above) are themselves the duplicated pattern — keep
  them consistent by collapsing them onto the single helper rather than patching each.

### Tests
- `scripts/tests/test_worker_pool.py` / `test_orchestrator.py` — add unit tests for
  `detect_default_branch()` covering: `origin/HEAD` present (returns stripped name),
  detached HEAD (`rev-parse` → `HEAD`, helper must not return `"HEAD"`), and the bare-repo
  last-resort path.
- Add a regression test asserting a `master`-default repo yields `master`, not `main`.

  > ⚠ **Refinement (`/ll:refine-issue`):** `test_worker_pool.py` / `test_orchestrator.py` use the
  > `temp_repo_with_config` fixture, which does **not** run `git init` (all git is mocked) —
  > unsuitable for exercising real detached-HEAD / `origin/HEAD` behavior. Model the new tests on
  > the real-`git init` pattern in `test_hooks_integration.py:2802` (`_make_worktree()`): init a
  > repo in `tmp_path`, set `origin/HEAD`, and use `git checkout --detach` for the detached case.
  > A dedicated `scripts/tests/test_worktree_utils.py` is the natural home.

_Wiring pass added by `/ll:wire-issue`:_

**New tests (the two real `base_branch` entry points are currently uncovered):**
- `scripts/tests/test_cli.py` — `TestMainParallelIntegration` (`:516–1735`) call-throughs already
  patch `ParallelOrchestrator` but assert only on non-branch kwargs; **no test exercises the
  `cli/parallel.py:211–218` detection block**. Add a case that patches
  `worktree_utils.detect_default_branch` and asserts the returned value reaches
  `parallel_config.base_branch` [Agent 3 finding].
- `scripts/tests/test_cli_sprint.py` — the **multi-issue `_cmd_sprint_run` parallel path**
  (`cli/sprint/run.py:586–592`, the inline block being replaced) has **no coverage** today;
  `TestFeatureBranchWarning` only exercises the single-issue in-place path via
  `_detect_current_branch()`. Add a test that the multi-issue path routes through
  `detect_default_branch()` [Agent 3 finding].

**Test fixture pattern (alternative to `_make_worktree()`):**
- `scripts/tests/test_merge_coordinator.py` — `temp_git_repo()` fixture (`:21`) is a second
  real-`git init` model (yields a repo with one real commit; sets identity via `git config`).
  Either it or `_make_worktree()` can seed the new `test_worktree_utils.py`. Note: `_make_worktree()`
  does **not** pass `--initial-branch`, so tests needing a known HEAD name must pass
  `git init --initial-branch main|master` explicitly [Agent 3 finding].

**Tests to guard (do NOT break — confirm the issue's scope decisions hold):**
- `scripts/tests/test_cli_sprint.py` — `TestFeatureBranchWarning._run` (`:818`) patches
  `little_loops.cli.sprint.run._detect_current_branch` and asserts `"main" in matching[0]` (`:835`).
  This is the guard rail behind the "⚠ Do NOT route `_detect_current_branch()`" decision: if that
  helper is retired/rerouted, this patch path stops intercepting and the test hits real git. Leaving
  `_detect_current_branch()` untouched (as planned) keeps it green [Agent 3 finding].
- `scripts/tests/test_parallel_types.py` — `test_to_dict` (`~:848`) and
  `test_from_dict_defaults_for_missing_fields` (`:996`) assert `base_branch == "main"`. These pin the
  `ParallelConfig` field default to the literal `"main"`. The plan **keeps** that literal (detection
  runs in the CLI, before `from_dict`/`create_parallel_config`), so they stay green — but they are a
  hard constraint: do **not** make the field default dynamic [Agent 3 finding].

### Documentation
- N/A — no user-facing doc describes the base-branch selection behavior; the change is
  internal and behavior-preserving for `main`-default repos.

  > ⚠ **Correction (`/ll:wire-issue`):** the "N/A" above is inaccurate — **three docs do describe
  > the `main` default** and will read as stale once auto-detection lands. Update each to mention
  > that the base branch is auto-detected (`origin/HEAD` → current branch → `main`) when
  > `parallel.base_branch` is unset [Agent 2 finding]:
  > - `docs/reference/CONFIGURATION.md:338` — the `### parallel` table row: `| base_branch | "main" |
  >   Base branch targeted by PR creation … Also used as the rebase target for worktree updates. |`.
  >   The `"main"` Default column + description are now incomplete for non-`main` repos.
  > - `docs/guides/SPRINT_GUIDE.md:302` — "fully merged into `parallel.base_branch` (the branch that
  >   was checked out when `ll-parallel` last ran, **defaulting to `main`**)". The parenthetical
  >   description of resolution is now wrong.
  > - `config-schema.json:399` — the `parallel.base_branch` `"description"` ends "Defaults to 'main'."
  >   Reword to reflect auto-detection-when-absent (this is the **schema description text**, distinct
  >   from the schema-key-exists / precedence point already noted under ### Configuration below).

### Configuration
- N/A — no config key controls the base branch today. (A future `orchestration.base_branch`
  override could layer on top of the helper, but it is out of scope for this fix.)

  > ⚠ **Correction (`/ll:refine-issue`):** a config key **does** already exist —
  > `parallel.base_branch` in `config-schema.json:397–406` ("Base branch targeted by PR creation …
  > also used as the rebase target for worktree updates. Defaults to 'main'"), deserialized by
  > `ParallelAutomationConfig` (`config/automation.py`). Today the CLI-detected value **overrides**
  > it unconditionally (passed explicitly to `create_parallel_config(base_branch=…)`), so a
  > user-set `parallel.base_branch` is silently ignored. Decide the precedence: an explicit config
  > value should likely win over auto-detection. The "future override" is therefore not
  > hypothetical — it already exists and is being shadowed.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional `"main"` literals beyond those listed above (the fix should cover all five):**
- `scripts/little_loops/parallel/types.py:509` — `ParallelConfig.from_dict()` repeats
  `data.get("base_branch", "main")` (a second literal beyond the field default at `:382`).
- `scripts/little_loops/config/automation.py:61,96` — `ParallelAutomationConfig.base_branch:
  str = "main"` (field default **and** `from_dict()` fallback); the config-layer backstop used
  when the CLI passes `base_branch=None`.

**Override seam (where a detected value enters config):**
- `scripts/little_loops/config/core.py:503` — `BRConfig.create_parallel_config()` does
  `base_branch=base_branch if base_branch is not None else self._parallel.base_branch`. The CLI
  already passes the detected value explicitly (`cli/parallel.py:239`, `cli/sprint/run.py:602`),
  so swapping the detection block for `detect_default_branch()` needs **no** config-layer change.

**Exact call-site anchors:**
- `cli/parallel.py:211–218` (inline `_base_branch` block) → forwarded at `:239`.
- `cli/sprint/run.py:585–592` (inline duplicate) → forwarded at `:602`.

**Downstream consumers of `config.base_branch` (benefit automatically once detection flows in):**
- `parallel/merge_coordinator.py` — `_process_merge()` `:624` (`git checkout <base>`,
  `git pull --rebase <remote> <base>`) via `git_lock.run`; `_handle_conflict()` `:875–893`
  (`git fetch <remote> <base>`, `git rebase <remote>/<base>`) via **bare** `subprocess.run`
  (operates on the worktree's separate index).
- `parallel/worker_pool.py` — merge/diff/prune operations incl. `git branch --merged <base>`.

**GitLock:** the shared lock is a `threading.RLock` created in `parallel/orchestrator.py:94`
(`ParallelOrchestrator.__init__`) and threaded into `WorkerPool` + `MergeCoordinator`. CLI-level
detection runs **before** the orchestrator exists, so `detect_default_branch(repo_path,
git_lock=None)` is correct at startup; the `git_lock` param matters only if the helper is later
called mid-run (then pass the orchestrator's lock to serialize with concurrent checkout/pull).

## Impact

- **Priority**: P2 — silent wrong-base merges for non-`main` downstream installs; latent here.
- **Effort**: Small — one helper + three call-site swaps.
- **Risk**: Low–Medium — touches the integration-target selection; cover with the tests above.
- **Breaking Change**: No (behavior is unchanged for `main`-default repos).

## Labels

`parallel`, `sprint`, `git`, `worktree`

## Session Log
- `/ll:wire-issue` - 2026-06-26T23:05:03 - `bca75a9e-fd12-4557-a58b-c6d7f5a6d56b.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:51:16 - `5abe280f-1381-4870-967b-c1984b8aafbb.jsonl`
- `/ll:format-issue` - 2026-06-26T22:42:21 - `225111da-83b8-43d3-8d76-e3acb2287cd4.jsonl`
- audit (branch & worktree management) - 2026-06-26 - `thoughts/audits/2026-06-26-branch-worktree-management-audit.md`

---

## Status

- **Status**: open
- **Priority**: P2
