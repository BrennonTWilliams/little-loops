---
id: FEAT-2562
title: "per-EPIC integration branch \u2014 _inspect_worktree() epic-branch comparison"
type: FEAT
priority: P3
status: done
captured_at: '2026-07-09T00:00:00Z'
completed_at: '2026-07-11T03:03:50Z'
discovered_date: 2026-07-09
discovered_by: confidence-check-decomposition
labels:
- parallel
- epics
- git
- worktree
parent: EPIC-2451
relates_to:
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2449
- FEAT-2561
unblocks:
- FEAT-2450
decision_needed: false
notes: "blocked_by FEAT-2561 cleared 2026-07-09 \u2014 helper landed (issue_progress.py)."
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-2562: per-EPIC integration branch — _inspect_worktree() epic-branch comparison

## Summary

Unit B extracted from FEAT-2449 (decomposed via `/ll:confidence-check` on
2026-07-09). Makes the orchestrator's `_inspect_worktree()` commit-count
comparison **epic-aware**: when the inspected worktree is an EPIC child, the
`rev-list --count` must compare against the EPIC integration branch, not
`base_branch` — otherwise an EPIC child's commits are miscounted (they diverge
from `epic/<id>`, not from `main`).

This is a single-method logic change plus a test audit; it is independent of
FEAT-2449's completion/merge lifecycle and of FEAT-2563's sprint warning. It
depends only on the shared EPIC-ancestor helper (FEAT-2561) to map the inspected
worktree's issue-ID to its EPIC.

## Motivation

Without an epic-aware base, `_inspect_worktree()` under-reports the worktree's
own delta in any multi-issue EPIC run with `epic_branches.enabled=True`. The
`rev-list --count` diverges from the actual diff against the EPIC integration
branch by however many sibling-commits already merged into `epic/<id>-<slug>`,
breaking the orchestrator's "is this worktree behind its base?" signal and
causing spurious re-runs or false completion verdicts. The bug currently only
manifests on EPIC-anchored parallel runs (non-EPIC paths are preserved
byte-for-byte by the `epic_branches.enabled` guard). Getting this right is the
last functional blocker for the EPIC integration branch feature surface area
(FEAT-2449 / EPIC-2451).

## Current Behavior

`_inspect_worktree()` (`scripts/little_loops/parallel/orchestrator.py:398`)
parses the issue ID from the worktree directory name
(`re.match(r"worker-([a-z]+-\d+)-\d{8}-\d{6}", ...)` at `:413`, upper-cased at
`:414`) and then runs `git rev-list --count {base}..{branch_name}` (`:417-421`,
base at `:418`) **unconditionally** — the comparison base is
`self.parallel_config.base_branch` with no EPIC-aware branch swap. For an EPIC
child worktree whose commits diverged from `epic/<epic-id-lower>-<slug>`, the
count includes commits already merged into the EPIC branch from other child
runs, misreporting ahead/behind status.

## Expected Behavior

For an EPIC child worktree, the `rev-list --count` base becomes the EPIC
integration branch (`epic/<epic-id-lower>-<slug>`) — implemented by resolving
the issue's nearest EPIC ancestor via the FEAT-2561 helpers
(`find_nearest_epic_ancestor()`, `build_parent_map()` in `issue_progress.py`)
and constructing the branch name with the same slug shape as
`WorkerPool._resolve_branch_targets()` (`worker_pool.py:1615-1641`) +
`_load_epic_slug()` (`:1682-1705`). For non-EPIC worktrees, the behavior is
byte-for-byte identical to today (compared against `base_branch`).

## Use Case

**Who**: A user running `ll-parallel` against an EPIC-anchored issue set (e.g.,
EPIC-2451 with N children, `epic_branches.enabled=True`).

**Context**: Three sibling EPIC children have finished and merged into
`epic/epic-2451-<slug>`; a fourth child worktree
(`worker-feat-2562-20260709-...`) is still in flight, branched from
`epic/epic-2451-<slug>`.

**Goal**: The orchestrator inspects the fourth worktree to decide whether it
can integrate or is behind its base — and the "base" must be the EPIC
integration branch, not `main`; otherwise sibling-child merges into
`epic/...` show up as "this child is ahead of `main` by N commits" — a
contradiction.

**Outcome**: `_inspect_worktree()` reports an accurate diff (only the commits
THIS child added on top of `epic/...`), downstream re-run gating fires
correctly, and `_maybe_complete_epic` (`orchestrator.py:1177-1264`) sees
consistent counts before deciding to merge the EPIC integration branch.

## Parent Issue

Decomposed from FEAT-2449 on 2026-07-09 (was Scope item #3). EPIC-2451 is the
parent EPIC and remains the coordination container.

## Scope

1. **`_inspect_worktree()` epic-branch comparison base**
   (`scripts/little_loops/parallel/orchestrator.py`, method starts at `:398`) —
   the issue-ID is parsed from the worktree directory name at `orchestrator.py:413`
   (`re.match(r"worker-([a-z]+-\d+)-\d{8}-\d{6}", worktree_path.name)`,
   upper-cased at `:414`). The `rev-list --count` call at `orchestrator.py:417-421`
   currently reads `{self.parallel_config.base_branch}..{branch_name}` (the base is
   at `:418`, read unconditionally — no existing branch swaps it). Change the
   comparison base to `{epic_branch or base_branch}..{branch_name}` when the
   worktree's issue is an EPIC child:
   - Resolve the issue's EPIC via the shared helpers (landed in FEAT-2561):
     `find_nearest_epic_ancestor(issue, build_parent_map(all_issues))`, both
     imported from `little_loops.issue_progress`
     (`issue_progress.py:67-77` and `:80-101`), using the orchestrator's
     `self._issue_info_by_id` (init at `orchestrator.py:128`, populated at `:776`)
     as the issue source. **Mirror the sibling method `_maybe_complete_epic`
     (`orchestrator.py:1177-1264`), which already imports and calls these two
     helpers at `:1206-1211`** — copy that import + call shape.
   - Construct the epic branch the same way `WorkerPool._resolve_branch_targets()`
     does (`worker_pool.py:1615-1641`): `epic/<epic-id-lower>-<slug>`, slug from
     the EPIC title via `_load_epic_slug()` (`worker_pool.py:1682-1705`). Do NOT
     assume a bare `epic/<id>`.
   - Only substitute the base when `epic_branches.enabled` and an EPIC ancestor
     exists; otherwise byte-for-byte identical to today (no-op for non-EPIC runs).
     `epic_branches.enabled` is read on the orchestrator today at `:1078`/`:1196`.

2. **Tests** —
   - `scripts/tests/test_orchestrator.py::TestInspectWorktree`
     (`:1006-1180`, 6 tests that mock `git rev-list --count` and assert on its
     args) — audit each for compatibility with the
     `{epic_branch or base_branch}..{branch_name}` shape. Specifically
     `test_returns_actual_branch_for_feature_branch_mode` (`:1095`) plus the 5
     others: `test_extracts_issue_id` (`:1009`),
     `test_detects_uncommitted_changes` (`:1038`),
     `test_handles_inspection_failure` (`:1071`),
     `test_returns_none_when_rev_parse_fails` (`:1123`),
     `test_inspect_worktree_uses_rev_parse_not_string_replace` (`:1151`). Non-EPIC
     fixtures must keep asserting `main..<branch>`; add at least one EPIC-child
     fixture asserting the **full slugged branch** `epic/<epic-id-lower>-<slug>..<branch>`
     (e.g. `epic/epic-2451-<slug>..<branch>`), not bare `epic/EPIC-2451`.
   - `scripts/tests/test_orchestrator.py::TestOrphanedWorktreeCleanup`
     (`:416-911`), specifically `test_deletes_branch_via_rev_parse` (`:582`) —
     add an `epic/*` audit verifying an `epic/<EPIC-ID>-<slug>` branch is **NOT**
     deleted by `_cleanup_orphaned_worktrees` (FEAT-2339 Decision Rationale #3 /
     ARCHITECTURE-094 — epic branches are explicitly-deleted only, never via the
     `parallel/*` cleanup gate).

   > **Anchor correction (carried from FEAT-2449 wiring pass)**: the stale
   > reference to `test_inspect_worktree_with_feature_branch` at
   > `test_worker_pool.py:1001` is wrong — the real target is
   > `test_returns_actual_branch_for_feature_branch_mode` at
   > `test_orchestrator.py:1095`; `test_worker_pool.py:1001` is unrelated
   > worktree-setup code.

## Out of Scope

- EPIC-completion detection, completion-merge/PR, partial-failure gate,
  config-branch wiring — **FEAT-2449**.
- `cli/sprint/run.py` in-place warning — **FEAT-2563**.
- Any change to `_is_ll_branch()` / `cleanup_worktree()` in `worktree_utils.py`
  (must NOT match `epic/*` — FEAT-2339 Decision Rationale #3) or to
  `MergeCoordinator._cleanup_worktree()` (`parallel/` prefix hardcode is correct
  by accident) — boundary-preserved.

## Acceptance Criteria

- [x] `_inspect_worktree()` compares against the epic branch for EPIC children
      (`epic/<epic-id-lower>-<slug>..<branch>`) and against `base_branch` otherwise.
- [x] With `epic_branches.enabled=False` (default), behavior is byte-for-byte
      identical — non-EPIC `TestInspectWorktree` fixtures still assert
      `main..<branch>`.
- [x] At least one new EPIC-child fixture in `TestInspectWorktree` asserts the
      full slugged `epic/<epic-id-lower>-<slug>..<branch>` comparison base.
- [x] `TestOrphanedWorktreeCleanup` gains an `epic/*` NOT-deleted audit.
- [x] Full `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — Internal orchestrator correctness; only manifests under
  `epic_branches.enabled=True` for EPIC child worktrees (a relatively new
  feature path), not on the default non-EPIC parallel flow.
- **Effort**: Small — One method (`_inspect_worktree`), one comparison-base
  swap gated by an EPIC ancestor lookup that already runs in the sibling
  `_maybe_complete_epic` method (`orchestrator.py:1177-1264`); ~2 files (1
  impl + 1 test).
- **Risk**: Low — Non-EPIC path preserved byte-for-byte by the
  `epic_branches.enabled` + EPIC-ancestor guard; existing
  `TestInspectWorktree` non-EPIC fixtures still assert `main..<branch>`;
  FEAT-2339 boundary preserved (no edit to `worktree_utils.py` `_is_ll_branch()`
  / `cleanup_worktree()` or `MergeCoordinator._cleanup_worktree()`).
- **Breaking Change**: No.

## Files Touched

**Implementation (1 file):**
- `scripts/little_loops/parallel/orchestrator.py` (`_inspect_worktree` comparison
  base at `:418`, EPIC resolution via the `issue_progress` helpers landed in
  FEAT-2561)

**Tests (1 file):**
- `scripts/tests/test_orchestrator.py` (`TestInspectWorktree` audit + EPIC
  fixture; `TestOrphanedWorktreeCleanup` epic/* audit)

**Estimated file count:** 1 implementation + 1 test = **2 files**.

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `parallel/orchestrator.py::_check_pending_worktrees()` (`:471`) — the sole
  in-repo caller of `_inspect_worktree()`; consumes `info.commits_ahead` /
  `info.has_pending_work` without depending on which branch produced the
  count, so no contract break. No other caller of `_inspect_worktree()`
  exists anywhere in the repo (verified by wiring pass). [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:363` — the `epic_branches.enabled` row
  currently states *"Worker-pool / merge-coordinator / orchestrator wiring
  lands in FEAT-2448 / FEAT-2449 / FEAT-2450 — until those ship this flag is
  parsed and stamped into generated configs but the orchestrator path is not
  active."* This becomes inaccurate once `_inspect_worktree()` gains a real
  `.enabled`-gated orchestrator consumer (this issue) — update to reflect
  that the orchestrator path is now partially active, independent of
  FEAT-2449/2450's completion-flow wiring. [Agent 2 finding]

### Files to Modify (adjacent — verify in scope during implementation)

_Wiring pass added by `/ll:wire-issue`:_
- `parallel/orchestrator.py:482` (inside `_check_pending_worktrees()`, **not**
  `_inspect_worktree()` — a different method in the same file) — hardcodes
  `f"{info.commits_ahead} commit(s) ahead of main"`. Once an EPIC-child
  worktree's `commits_ahead` is computed against `epic/<id>-<slug>` instead
  of `base_branch`, this log line becomes misleading (it always says "ahead
  of main" even when the true comparison base was the EPIC branch). This
  method is outside the issue's declared Scope §1 (`_inspect_worktree()`
  only) — confirm intentionally whether to fix the wording in this issue or
  defer; if deferred, note it explicitly as a known follow-up so it isn't
  silently forgotten. [Agent 2 finding]

- **Files to Modify**: `parallel/orchestrator.py`
- **Depends On**: FEAT-2561 (DONE) — `find_nearest_epic_ancestor` /
  `build_parent_map` in `little_loops/issue_progress.py` (`:80-101` / `:67-77`)
- **Similar Patterns**: `_inspect_worktree` uses `base_branch` **unconditionally**
  today (no local base-swap idiom exists). Model the guard on
  `WorkerPool._resolve_branch_targets()` (`worker_pool.py:1615-1641`), which
  returns `(base, base)` or `(epic_branch, epic_branch)` under `epic_branches.enabled`;
  and copy the helper import/call from `_maybe_complete_epic`
  (`orchestrator.py:1206-1211`).
- **Tests**: `TestInspectWorktree` (`:1006-1180`), `TestOrphanedWorktreeCleanup`
  (`:416-911`)
- **Boundary (do NOT modify)**: `worktree_utils.py` `_is_ll_branch()` /
  `cleanup_worktree()`; `merge_coordinator.py` `_cleanup_worktree()`.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-09). The issue's
own line citations have drifted ~forward as the files grew; the named symbols/tests
all still exist. Verify against current line numbers below._

### Blocker status: FEAT-2561 is DONE — helper path confirmed

- The shared helpers **exist and are in active use**: `build_parent_map()`
  (`scripts/little_loops/issue_progress.py:67-77`) and
  `find_nearest_epic_ancestor()` (`issue_progress.py:80-101`) — module-level pure
  functions, not on `WorkerPool`. `blocked_by: FEAT-2561` is now satisfied; this
  issue is effectively unblocked.
- **Canonical usage to mirror**: `_inspect_worktree`'s sibling method
  `_maybe_complete_epic` (`orchestrator.py:1177-1264`) **already imports and uses
  these two helpers directly** (`orchestrator.py:1206-1211`). Copy that import +
  call shape — do NOT reach into `self.worker_pool._find_nearest_epic_ancestor(issue)`
  (the fallback note in Scope §1 is now moot since FEAT-2561 landed).

### Corrected anchors (implementation)

- `_inspect_worktree()` starts at `orchestrator.py:398` (called from
  `_check_pending_worktrees()` at `:471`).
- Issue-ID regex: `orchestrator.py:413` (issue cites `:410`) —
  `re.match(r"worker-([a-z]+-\d+)-\d{8}-\d{6}", ...)`, upper-cased at `:414`.
- `rev-list --count` call: `orchestrator.py:417-421`; the comparison base
  `f"{self.parallel_config.base_branch}..{branch_name}"` is at **`:418`**
  (issue cites `:415`). Read **unconditionally once** — no existing branch swaps it.
- `self._issue_info_by_id`: init at `orchestrator.py:128` (`dict[str, IssueInfo]`,
  confirmed); **populated at `:776`** inside `_execute()` (issue cites `:773`),
  only from `_scan_issues()` — i.e. current-run issues, not a full repo scan.

### Correction: "Similar Patterns" idiom is NOT in `_inspect_worktree`

- The issue's Integration Map claims "the `rev-list --count` comparison-base idiom
  already used for feature-branch mode elsewhere in `_inspect_worktree`". **This is
  wrong** — `_inspect_worktree` uses `base_branch` unconditionally with no
  mode-aware branching.
- The real idiom to model after is **`WorkerPool._resolve_branch_targets()`**
  (`worker_pool.py:1615-1641`): it returns `(base_branch, base_branch)` when
  `epic_branches.enabled` is False or the issue has no EPIC ancestor, and
  `(epic_branch, epic_branch)` otherwise. Mirror its enabled-guard shape, not a
  (non-existent) local idiom.

### Epic branch naming — includes a slug (AC precision)

- The AC says `epic/<id>..<branch>`, but the real branch name is
  **`epic/<epic-id-lower>-<slug>`** — built at `worker_pool.py:1639` as
  `f"{prefix}{epic_id.lower()}-{slug}"`, `prefix` default `"epic/"`
  (`EpicBranchesConfig`, `types.py:312-334`), `slug` from the EPIC title via
  `_load_epic_slug()` (`worker_pool.py:1682-1705`, `slugify()`; falls back to
  `epic_id.lower()`). New EPIC-child test fixtures must assert the **full slugged
  branch** (e.g. `epic/epic-2451-<slug>..<branch>`), not bare `epic/EPIC-2451`.
  `epic_branches.enabled` is read on the orchestrator at `:1078` / `:1196` today —
  reuse that accessor.

### Corrected anchors (tests, `scripts/tests/test_orchestrator.py`)

- `TestInspectWorktree`: **`:1006-1180`** (issue cites `:909-1082`), 6 methods —
  `test_extracts_issue_id` (`:1009`), `test_detects_uncommitted_changes` (`:1038`),
  `test_handles_inspection_failure` (`:1071`),
  `test_returns_actual_branch_for_feature_branch_mode` (**`:1095`**, issue cites
  `~:998`), `test_returns_none_when_rev_parse_fails` (`:1123`),
  `test_inspect_worktree_uses_rev_parse_not_string_replace` (`:1151`).
- `TestOrphanedWorktreeCleanup`: **`:416-911`** (issue cites `:319-516`), 13
  methods; `test_deletes_branch_via_rev_parse` at **`:582`** (issue cites `:485`).
- The stale-anchor correction in Scope §2 stands: the real target is
  `test_returns_actual_branch_for_feature_branch_mode` (now `:1095`), not
  `test_worker_pool.py:1001`.

### Codebase Research Findings (2026-07-10 re-verification pass)

_Added by `/ll:refine-issue --auto` — re-verified against current codebase state;
the prior research pass above (2026-07-09) remains accurate. These are
additional corrections/patterns found on a second pass._

- **`_inspect_worktree()` full span confirmed**: `orchestrator.py:398-446`
  (49 lines incl. docstring; next method `_check_pending_worktrees` starts at
  `:448`). The `rev-list --count` call now spans **`:417-422`** (one line later
  than the `:417-421` cited above) — base string still constructed at `:418`.
  Re-check this line on implementation since it shifts easily.
- **Correction to `epic_branches.enabled` read-site claim**: the issue states
  above that `.enabled` "is read on the orchestrator today at `:1078`/`:1196`".
  Only **`:1078`** is actually an `.enabled` check (inside `_on_worker_complete`,
  gating the call to `_maybe_complete_epic`). Line `:1196` inside
  `_maybe_complete_epic` itself is `cfg = self.parallel_config.epic_branches`
  (an assignment, not an `.enabled` check) — that method's own gate at `:1199`
  only checks `cfg.merge_to_base_on_complete` / `cfg.open_pr`, relying on the
  caller's `:1078` gate for `.enabled`. The second true `.enabled` read site is
  **`worker_pool.py:1632`** (inside `_resolve_branch_targets`), not another
  orchestrator line. `_inspect_worktree()`'s own new `.enabled` check will need
  to be added fresh — there's no existing orchestrator-side `.enabled` check to
  reuse other than the `:1078` one (different call site/purpose).
- **Test-assertion idiom gap**: none of the current 6 `TestInspectWorktree`
  tests assert on the actual `rev-list` comparison-base string — they only
  branch on `args[0] == "rev-list"` inside a hand-written `mock_git_run` stub
  (no `assert_called_with` usage anywhere in `test_orchestrator.py` for
  `_git_lock.run`). For the new EPIC-child fixture (AC #3, needs to assert the
  full slugged `epic/<epic-id-lower>-<slug>..<branch>` string), model the
  **capture-into-list-then-assert** idiom instead, e.g. as used in
  `TestOrphanedWorktreeCleanup.test_deletes_branch_via_rev_parse`
  (`test_orchestrator.py:594-613`, keys on `args[:2]` and appends to a list) or
  `TestEpicCompletionMerge._capture_git` (`:1272-1286`) — key on
  `args[:3] == ["rev-list", "--count", ...]` and append `args[3]` (the
  `{base}..{branch}` string) for an exact-match assertion.
- **Fixture to model the new EPIC-child test on**:
  `TestResolveBranchTargets._make_issue_file` (`test_worker_pool.py:3415-3446`)
  writes real on-disk issue files with a real EPIC title, so the slug is
  produced by the actual `_load_epic_slug()`/`slugify()` path end-to-end (see
  `test_epic_parent_returns_epic_branch_tuple`, `:3481-3519`, which asserts the
  literal `("epic/epic-2451-my-epic-title", "epic/epic-2451-my-epic-title")`
  tuple). This is a better model than `make_epic_orchestrator`
  (`test_orchestrator.py:149-238`, already used by `TestEpicCompletionMerge`)
  because the latter never asserts on a slug string — only status-driven
  merge/hold behavior — though `make_epic_orchestrator` is still the right
  model for **prepopulating `self._issue_info_by_id`**, which `_inspect_worktree`
  will need. Consider combining both idioms: write a real EPIC+child issue file
  pair (for a real slug) AND prepopulate `self._issue_info_by_id` directly
  (since `_inspect_worktree` is not going through `_execute()`'s populate step
  in these unit tests).
  `TestEpicCompletionMerge._EPIC_BRANCH = "epic/epic-2451-integration"`
  (`:1270`) is a reusable literal-constant pattern if a fixture wants to bypass
  slug computation entirely.
- **`_is_ll_branch()` exact location for the `TestOrphanedWorktreeCleanup`
  epic/* audit** (AC #4): `worktree_utils.py:213-223`. Accepts only
  `parallel/*` prefix or `^\d{8}-\d{6}-` timestamp-prefixed names; rejects
  everything else including `epic/*` by construction (no `epic/*` string
  appears in the function). Used as the deletion gate at `orchestrator.py:304`
  and `:328` inside `_cleanup_orphaned_worktrees`. No existing test currently
  asserts the `epic/*` exclusion explicitly — confirmed gap, matches AC #4.
- **No other call site duplicates this pattern**: a third, independent
  EPIC-ancestor walk exists at `cli/issues/list_cmd.py:203-211`
  (`_find_epic_ancestor`, used for `ll-issues list --group-by epic` badge
  grouping) but it's a separate non-consuming implementation (FEAT-2561's own
  research flagged it as "not migrated" to the shared helper) — not a
  comparison-base swap and not relevant to this issue's scope.

## Blocks

- FEAT-2450 (CLI/TUI/docs polish waits on all functional epic-branch work)

## Resolution

Made `_inspect_worktree()` (`orchestrator.py:398-479`) epic-aware: when
`epic_branches.enabled` is `True` and the worktree's issue resolves to an EPIC
ancestor (via `find_nearest_epic_ancestor(issue_info, build_parent_map(all_issues))`,
mirroring `_maybe_complete_epic`), the `rev-list --count` comparison base becomes
`epic/<epic-id-lower>-<slug>` (slug via `self.worker_pool._load_epic_slug()`)
instead of `base_branch`. Non-EPIC and `epic_branches.enabled=False` paths are
unchanged (guard short-circuits before any lookup).

Added `test_uses_epic_branch_as_base_for_epic_child` to `TestInspectWorktree`
(asserts the full slugged comparison base string) and
`test_does_not_delete_epic_branch` to `TestOrphanedWorktreeCleanup` (confirms
`epic/*` branches are never targeted by `_cleanup_orphaned_worktrees`, since
`_is_ll_branch()` never matches `epic/*` by construction). All 6 pre-existing
`TestInspectWorktree` fixtures pass unchanged (non-EPIC orchestrator fixture
defaults `epic_branches.enabled=False`). Updated
`docs/reference/CONFIGURATION.md:363` to reflect that the orchestrator path is
now active (FEAT-2449 + this issue), leaving only CLI/TUI/docs polish to
FEAT-2450.

Deferred (noted, not fixed): `orchestrator.py:482`'s log line hardcodes
"ahead of main" even when the comparison base is now an EPIC branch — out of
this issue's declared Scope §1 (`_inspect_worktree()` only); a cosmetic
follow-up for whoever next touches `_check_pending_worktrees()`.

Full `python -m pytest scripts/tests/`: 14571 passed, 36 skipped, 0 failed.
`ruff check` and `mypy` clean on both changed files.

## Status

**Open** | Created: 2026-07-09 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-07-11T03:03:10Z - `caca19e4-cee3-4e61-8b1c-c2eb5da3d1e7.jsonl`
- `/ll:ready-issue` - 2026-07-11T02:57:21 - `c4f00d88-17aa-45d5-8432-f17cfa765efc.jsonl`
- `/ll:confidence-check` - 2026-07-11T02:55:03Z - `341dc073-dfba-4bfc-905e-bb2714d1839d.jsonl`
- `/ll:wire-issue` - 2026-07-11T02:52:47 - `38000e2c-5d0e-48d2-8280-d5989d3b2d59.jsonl`
- `/ll:refine-issue` - 2026-07-11T02:45:36 - `d99e5cce-dd77-41be-a4d5-5846f9a4485c.jsonl`
- `/ll:format-issue` - 2026-07-10T01:30:31 - `6c2887ba-aeeb-4bbd-a8a3-28ecb1683d90.jsonl`
- `/ll:refine-issue` - 2026-07-10T00:28:05 - `619a64ab-3e40-4458-8035-169732c36dc8.jsonl`
- `/ll:confidence-check` - 2026-07-09T00:00:00 - `b4b437e8-ceeb-4657-a600-ad4fd9cabd3d.jsonl` (decomposition of FEAT-2449)
