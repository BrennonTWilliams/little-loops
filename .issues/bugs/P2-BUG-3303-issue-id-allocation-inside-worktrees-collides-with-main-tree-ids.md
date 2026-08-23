---
id: BUG-3303
type: BUG
title: Issue ID allocation inside worktrees collides with main tree IDs
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T19:19:29Z'
confidence_score: 94
outcome_confidence: 70
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 14
score_change_surface: 18
decision_needed: false
---

# BUG-3303: Issue ID allocation inside worktrees collides with main tree IDs

## Summary

Issue ID allocation (the next-ID scan behind `ll-issues create` / decomposition flows) reads only the `.issues/` tree visible from the current working directory. When automation runs inside a git worktree attached to a stale branch, the worktree's `.issues/` is missing issues that exist on main, so newly created issues are assigned IDs that already belong to different issues on main.

Observed 2026-08-23 in the `sprint-refine-and-implement` run on EPIC-3041: FEAT-3040's decomposition ran in a worktree on `epic/epic-3041-host-agnostic-advisor` (branched 2026-08-08, ~448 commits behind main). The worktree's `.issues/` predated main's re-anchoring, so the two telemetry children were allocated **FEAT-3117** and **FEAT-3118** — IDs already used on main by the wire-trigger issues (`P3-FEAT-3117-wire-confidence-gate-consult-trigger.md`, `P3-FEAT-3118-wire-pre-done-consult-trigger.md`). The children never landed (abandoned ref `b972a9c7c`) and were manually recovered as FEAT-3300/FEAT-3301 (commit `3e492b26a`). Had the branch merged cleanly, main would have received two colliding ID pairs, corrupting `depends_on`/`parent` resolution for the whole advisor cluster.

## Current Behavior

`get_next_issue_number()` (`scripts/little_loops/issue_parser.py:3196-3245`) scans only
directories derived from `BRConfig.project_root`, which is set verbatim from whatever
`Path` the caller passes to `BRConfig.__init__()` (`scripts/little_loops/config/core.py:251-257`,
`self.project_root = project_root.resolve()`) — no git-boundary walk, no worktree
detection, and no comparison against a main/common checkout. Every CLI entry point that
allocates an ID (`ll-issues create`, `ll-issues scaffold-epic`, `ll-issues next-id`, the
`IssueManager` failure path, GitHub sync) defaults `project_root` to `Path.cwd()`, so the
scan is scoped to whatever `.issues/` tree is reachable from the current working
directory. `create_issue()`'s advisory lock (`scripts/little_loops/cli/issues/create.py:446`,
`.id-alloc.lock`) also lives inside that same worktree-scoped `.issues/` directory, so it
provides no cross-tree serialization between a worktree and the main checkout.

## Expected Behavior

ID allocation resolves the canonical/main checkout even when the current process's
working directory is a linked worktree, so an ID allocated from inside a stale worktree
can never collide with one already allocated on the main tree — see Acceptance Criteria.

## Motivation

A colliding ID pair silently corrupts `depends_on`/`parent`/`blocked_by` resolution for
every issue that references either ID — the collision is invisible until two files with
the same `TYPE-NNN` both land, as in the FEAT-3117/FEAT-3118 incident this issue
documents. EPIC branches and other automation regularly run for hundreds of commits
behind main (the triggering `epic/epic-3041-host-agnostic-advisor` branch was ~448
commits behind), so any decomposition or `ll-issues create` call inside such a branch's
worktree is exposed today.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

No existing helper in this repo resolves a main/common checkout root from a linked worktree. The closest precedent is `hooks/scripts/session-cleanup.sh:30-37`, the only existing use of `git rev-parse --git-common-dir` in the codebase, which compares it against `--git-dir` to detect linked-worktree state (used there to skip destructive cleanup, not to redirect a scan). Separately, `scripts/little_loops/host_runner.py` parses a worktree's `.git` file's `gitdir:` line directly at three call sites (`:425-433`, `:719-727`, `:1041-1058`, landed via ENH-932) to set `GIT_DIR`/`GIT_WORK_TREE` for a subprocess — but stops at the object-store path and does not derive the main working-tree root either. Whichever mechanism is chosen, `.issues/` base-dir resolution is entirely filesystem-scoped today (`BRConfig.project_root = project_root.resolve()`, `scripts/little_loops/config/core.py:257`, no git awareness at all) and `get_next_issue_number()` (`scripts/little_loops/issue_parser.py:3196`) is the single choke point every allocation call site reaches through — see Integration Map → Dependent Files for the full call site list, including `issue_lifecycle.py:822`'s unguarded `create_issue_from_failure()` path, which is not named in the existing "Desired Behavior" candidates below but shares the same exposure.

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

**Option A**: Resolve the primary repo root (a worktree's `.git` file points at the main checkout's `gitdir`) and scan that `.issues/` tree in addition to the local one, taking the max.

> **Selected:** Option A — filesystem union scan reuses `get_next_issue_number()`'s existing `dirs_to_scan`/max-tracking loop and carries no staleness risk (unlike Option B's ref-based read, which cannot see uncommitted or unfetched issue files).

**Option B**: Scan git refs (`git ls-tree <default-branch> -- .issues` via the common git dir) so IDs allocated on main are visible regardless of checkout state.

**Option C**: Minimum viable guard — when running inside a linked worktree (`git rev-parse --git-common-dir` differs from `--git-dir`), also read the main working tree's `.issues/` max ID.

### Decision Rationale

**Selected: Option A** (filesystem union scan of the main working tree's `.issues/`, taking the max alongside the local scan).

**Reasoning**: `get_next_issue_number()` already builds a `dirs_to_scan` list and tracks a running `max_num` across per-category and legacy directories (`issue_parser.py:3196-3245`) — Option A extends that exact loop with the main tree's equivalent paths, rather than introducing a new read mechanism. Its only new logic is resolving the main working-tree root from a worktree's `gitdir:` pointer (`<main>/.git/worktrees/<name>` → `<main>`, three `.parent` hops: `<name>` → `worktrees` → `.git` → `<main>`), which is testable with the lightweight `.git`-file fixture already used in `test_host_runner.py`. Note the `.git` file's `gitdir:` value can be a *relative* path, and `git worktree move`/`repair` layouts exist — prefer `git rev-parse --path-format=absolute --git-common-dir` (then `.parent` of the returned `.git` dir) as the resolver, falling back to `.git`-file parsing only where a subprocess is undesirable. Critically, it reads live filesystem state, so it has no staleness gap: Option B's `git ls-tree <default-branch>` read is a snapshot of committed history only and would miss uncommitted or unfetched issue files on main — a correctness risk for the exact collision this bug documents. Option C targets the same resolved path as Option A but via `--git-common-dir` rather than gitdir-parsing, with an unhandled bare-repo edge case and no reusable guard-clause precedent in `issue_parser.py`/`config/core.py`; it also pulls testing toward the slower real-git fixture. Option A best matches the issue's own Implementation Steps sketch ("resolve main checkout path... union both `.issues/` scans").

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A (union scan) | 2 | 2 | 3 | 2 | **9/12** |
| B (git ls-tree ref) | 3 | 2 | 2 | 1 | 8/12 |
| C (min. viable guard) | 1 | 1 | 1 | 2 | 5/12 |

**Key evidence**: `get_next_issue_number()`'s existing max-scan loop (`issue_parser.py:3196-3245`); `test_host_runner.py`'s lightweight `.git`-file fixture (`(tmp_path / ".git").write_text(f"gitdir: {gitdir}\n")`); Option B's staleness gap confirmed via `detect_default_branch()`/`read_paths_at_ref()` precedent research (ref-based reads see committed history only).

### Sibling-Worktree Collision (must also be covered)

The worktree+main union scan alone leaves a residual collision path that is live today
(`parallel.epic_branches` enabled, `sprints.default_max_workers: 2`): worktree A
allocates ID N (the file exists only in A's tree), releases the lock; worktree B then
scans B + main, sees neither A's file nor N, and allocates N again. The relocated
cross-tree lock serializes *concurrent* allocation but does not make A's completed
allocation visible to B — same collision class as the FEAT-3117/3118 incident, different
trigger.

**Fix (adopted)**: maintain a high-water-mark file in the main tree's `.issues/`
(e.g. `.id-alloc-highwater`, a single integer), read and written **under the cross-tree
lock**: `next = max(union_scan_max, highwater) + 1`, then write `next` back. This makes
every allocation durable in the canonical namespace regardless of which tree the issue
file lands in. Treat a missing/corrupt high-water file as 0 (the union scan is the
floor, so recovery is automatic and monotonic). The alternative — scanning every linked
worktree via `git worktree list --porcelain` from the common dir — was rejected: it is
slower, races with worktree creation/removal, and fails on prunable/locked worktrees.
The high-water file is gitignored-by-location concern: it lives in the *main* tree's
`.issues/` and should be added to `.gitignore` (allocation state, not repo content).

### Graceful Degradation (required behavior)

The main-checkout resolver must fall back to the current local-only scan (today's
behavior, no error, at most a debug log) when any of: the process is not inside a git
repo at all; `.git` is a directory (primary checkout — no redirect needed); the resolved
common dir's parent has no `.issues/` (bare repo, or a main tree deleted while the
worktree survives); or the main tree path is unreadable. This is what AC3
("behavior unchanged in the primary checkout") depends on and must be tested explicitly.

### Reconciliation with ENH-1198

ENH-1198 was closed Invalid on the argument that `.issues/` is git-tracked, each
worktree has an isolated copy, and cross-tree locking "would break worktree isolation
entirely." The FEAT-3117/3118 incident falsifies the premise: isolation of the *files*
is exactly what makes the *ID namespace* collide, because the numeric ID is globally
unique across the repo (per `feedback_bare_numeric_frontmatter_id_supported`). This fix
supersedes ENH-1198's closing rationale for ID allocation only — issue file *content*
stays worktree-isolated; only the allocation counter and lock become canonical.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py:3196-3245` (`get_next_issue_number`) — the single choke point every allocation call site reaches through; scans only `config.project_root`-derived directories today
- `scripts/little_loops/config/core.py:251-257` (`BRConfig.__init__`) — sets `self.project_root = project_root.resolve()` verbatim with no git-boundary walk
- `scripts/little_loops/cli/issues/create.py:440-452` (`create_issue`) — `.id-alloc.lock` (line 446) lives inside the worktree-scoped `.issues/` dir, so it provides no cross-tree serialization

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py:3744` — `IssueParser._generate_id_from_filename` (decomposition/filename-fallback path, referenced in this issue's AC2)
- `scripts/little_loops/cli/issues/create.py:452` — `create_issue()`, the primary `ll-issues create` path
- `scripts/little_loops/cli/issues/scaffold_epic.py:87` — `scaffold_epic()`, has its own separate `.id-alloc.lock` (line 79), same worktree-scoped root, same exposure
- `scripts/little_loops/cli/issues/next_id.py:35` — `cmd_next_id` (`ll-issues next-id`), read-only preview, no lock
- `scripts/little_loops/cli/issues/normalize.py:302-308` — `_alloc()` closure, corpus-wide renumber pass
- `scripts/little_loops/sync.py:681` — GitHub-issue sync, local mirror issue creation
- `scripts/little_loops/issue_lifecycle.py:822` — `create_issue_from_failure()`, called from `IssueManager`'s automated processing loop (`issue_manager.py:1360`); **no lock and no collision retry at all**, a weaker-guarded surface than `create_issue()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:986` — top-level argparse dispatch: `config = BRConfig(project_root)` where `project_root = args.config or Path.cwd()`, before handing off to the `next-id`/`create`/`scaffold-epic` handlers above; this is where the worktree-scoped cwd first enters the allocation path [Agent 1 finding]

### Conventions in Force
- Shell-level worktree detection compares `git rev-parse --git-dir` vs `--git-common-dir` — evidence: `hooks/scripts/session-cleanup.sh:30-37` (the only existing use of `--git-common-dir` in this repo)
- Python-side worktree detection instead parses the `.git` file's `gitdir:` line directly, duplicated 3x with no shared helper — evidence: `scripts/little_loops/host_runner.py:425-433`, `:719-727`, `:1041-1058` (landed via ENH-932); neither this nor the shell version derives the main working-tree root, both stop at the object-store (`GIT_DIR`) path
- `git` subprocess calls in this codebase go through bare `subprocess.run(["git", ...])`, annotated `# ll-no-project:` when they are local git plumbing exempt from the host-CLI abstraction (`.claude/CLAUDE.md` § Host CLI Abstraction applies only to host CLIs, not `git`) — evidence: `scripts/little_loops/git_operations.py` (repeated)
- `find_project_root()` (`scripts/little_loops/paths.py:14-42`) already treats a worktree's `.git` file as a valid repo boundary via `.exists()` (not `.is_dir()`) — but it is not called anywhere in the `BRConfig`/allocation path, and it stops at the *nearest* `.git` boundary (the worktree's own root), so it cannot by itself redirect to a main tree beyond it

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/worktree_utils.py` (`setup_worktree`) is the module that *creates* the worktrees where this bug manifests, but it always takes `repo_path` (the main tree) as an explicit caller-supplied argument rather than discovering it from inside a worktree — confirmed no reusable "resolve main from inside a worktree" helper exists there; the fix introduces genuinely new resolution logic, not a centralization of scattered duplicates [Agent 2 finding]
- **Scope constraint**: `BRConfig.project_root` is read at ~54 call sites across 36 files (staging/`git add` in `create.py:484`, `design_tokens.py`, `sprint.py`, `mcp_server/resources.py`, `cli/artifact.py`, etc.) — the fix must NOT change what `project_root` itself resolves to; it must add a separate main-checkout-resolution helper consumed only by `get_next_issue_number()` and the lock-path construction in `create.py`/`scaffold_epic.py`, or those 54 call sites risk silently redirecting file writes/staging to the wrong tree [Agent 2 finding]
- **Prior-decision conflict to reconcile**: `.issues/enhancements/P3-ENH-1198-ll-issues-atomicity-under-worktree-mode.md` was closed **Invalid** with a closing rationale that directly conflicts with this fix's approach — it argues `.issues/` is git-tracked so each worktree has an isolated copy, "there is no runtime concurrency hazard," and that reaching into the main tree's `.issues/` for a shared lock "would break worktree isolation entirely." This fix's planned cross-tree lock + union scan does exactly what ENH-1198 argued against; the Proposed Solution or Root Cause section should explicitly reconcile with or supersede that closing note [Agent 2 finding]

### Tests
- `scripts/tests/test_issue_parser.py:971-1090` (`TestGetNextIssueNumber`) — existing ID-allocation coverage; no worktree scenario today
- `scripts/tests/test_ll_issues_create.py` — covers `create_issue()` allocation
- `scripts/tests/test_host_runner.py` — worktree fixture precedent: `(tmp_path / ".git").write_text(f"gitdir: {gitdir}\n")`, used for `GIT_DIR`/`GIT_WORK_TREE` env tests
- `scripts/tests/test_worktree_utils.py` — real `git init` + `git worktree add` fixture via `copy_git_template()` (`scripts/tests/helpers.py:44-74`), used when real git plumbing (branch resolution) matters

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_bug3150_issue_mutator_atomicity.py:89-95` (`test_lock_is_distinct_from_id_allocation_lock`) — existing coverage asserting `issue_lock_path(issue).name != ".id-alloc.lock"`; a filename-only assertion, unaffected by a lock-*location* fix but would break if the lock's file name (not just parent directory) changes — verify only [Agent 1 + Agent 3 finding]
- New test (worktree-vs-main collision, AC1): follow `scripts/tests/test_worktree_utils.py:44-52` (`_init_repo`) + `scripts/tests/helpers.py:44-76` (`copy_git_template`) + real `git worktree add` via `setup_worktree`, checking out a branch forked before main's max ID advances; assert `get_next_issue_number()` invoked from the worktree exceeds main's max, not just the worktree-local max [Agent 3 finding]
- New test (root-resolution unit coverage): if the main-checkout resolver shells to `git rev-parse --git-common-dir`, prefer the real-git fixture above; if it parses the `.git` file directly, the lightweight fixture in `scripts/tests/test_host_runner.py:974-982` (`(tmp_path / ".git").write_text(f"gitdir: {gitdir}\n")`) is a viable, faster alternative [Agent 3 finding]
- New test (cross-tree lock, no existing precedent found — grepped `id-alloc`/`id_alloc` repo-wide): `.id-alloc.lock` (`create.py:446`) cross-process/cross-tree serialization; place in `test_ll_issues_create.py` or a new dedicated `test_bug3303_*.py` file, matching this repo's convention (e.g. `test_bug3150_issue_mutator_atomicity.py`) [Agent 3 finding]
- New test: `create_issue_from_failure()` (`test_issue_lifecycle.py:822-943`, `TestCreateIssueFromFailure`) currently has zero lock/collision coverage of any kind (single-process assertions only) — add worktree-collision coverage for this weaker-guarded surface [Agent 3 finding]
- New test (sibling-worktree collision): two worktrees off the same main tree; allocate in A, then allocate in B without merging — assert B's ID > A's (exercises the high-water-mark file, since B's union scan cannot see A's file)
- New test (highwater recovery): delete/corrupt `.id-alloc-highwater`, assert next allocation falls back to the union-scan max and rewrites a valid highwater
- New tests (graceful degradation): non-git directory, primary checkout (`.git` is a dir), and worktree whose main tree lacks `.issues/` — all must produce today's local-only behavior with no error
- New test (`next-id` parity): `ll-issues next-id` from a worktree returns exactly the ID `ll-issues create` then allocates

### Documentation
- `docs/reference/API.md` — `issue_parser` / `ll-issues create` ID-allocation surfaces (already cited by this issue)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/scope-epic/SKILL.md:286` — asserts `ll-issues create`/`ll-issues scaffold-epic` "atomically handle ID allocation" for children created across a scan-codebase/scope-epic fan-out; this claim's truth depends on allocation actually being cross-tree-safe once workers run in worktrees — verify/update after the fix lands [Agent 2 finding]
- `scripts/little_loops/mcp_server/tools.py:295-296` — MCP tool-description string tells clients "The issue ID is allocated at apply time, under the `.issues/.id-alloc.lock`..." — user-facing prose encoding the *current* worktree-local lock path; update if the lock's resolved location changes [Agent 2 finding]
- `scripts/little_loops/file_utils.py:76` — docstring cross-references `.id-alloc.lock` as the sibling convention to `cli/issues/create.py`; keep accurate if the lock's resolved location changes [Agent 2 finding]
- `commands/scan-codebase.md:228,230`, `commands/scan-product.md:221,223`, `commands/find-dead-code.md:253` — each instructs running `ll-issues next-id` to assign new issue numbers; no worktree caveat today, verify unaffected by the fix [Agent 1 finding]

### Configuration
- N/A — no dedicated worktree-ID-allocation config keys found in `scripts/little_loops/config-schema.json`

## Implementation Steps

1. Locate the next-ID scan (`scripts/little_loops/cli/issues/create.py` / `issue_parser.py` next-id helper).
2. Add a canonical-namespace resolver: detect linked-worktree context, resolve the main checkout path via `git rev-parse --path-format=absolute --git-common-dir` (parent of the returned `.git` dir; fall back to `.git`-file parsing — three `.parent` hops from `gitdir:` — where a subprocess is undesirable), union both `.issues/` scans. Degrade gracefully per Proposed Solution → Graceful Degradation.
3. Add the high-water-mark file (Proposed Solution → Sibling-Worktree Collision): read/write `<main>/.issues/.id-alloc-highwater` under the cross-tree lock; `next = max(union_scan_max, highwater) + 1`. Add the filename to `.gitignore`.
4. Relocate the `.id-alloc.lock` used by `create.py:446` and `scaffold_epic.py:79` to the resolved main tree's `.issues/` (worktree-local when no main tree resolves), so allocation is serialized across trees.
5. Cover decomposition paths that allocate IDs (recursive decompose flows) via the same helper, plus the unguarded `create_issue_from_failure()` path (`issue_lifecycle.py:822`).
6. Ensure `ll-issues next-id` (`next_id.py:35`) previews through the identical union+highwater read path (minus the highwater *write*), so its preview matches what `create` will actually allocate — `commands/scan-codebase.md`/`scan-product.md`/`find-dead-code.md` instruct agents to trust it.
7. Tests: fixture repo + linked worktree on a stale branch; assert allocated ID exceeds main's max. Plus sibling-worktree, degradation, and highwater-recovery tests per Integration Map → Tests.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- Concrete anchor for step 1: `get_next_issue_number()` is `scripts/little_loops/issue_parser.py:3196-3245`; `BRConfig.project_root` is set in `scripts/little_loops/config/core.py:251-257`
- Every allocation call site reaches through `get_next_issue_number()` (single choke point, not duplicated scan logic): `scripts/little_loops/cli/issues/create.py:452` (`create_issue`, has `.id-alloc.lock` + retry), `scripts/little_loops/cli/issues/scaffold_epic.py:87` (`scaffold_epic`, its own separate `.id-alloc.lock` at line 79 — same worktree-scoped root, same exposure), `scripts/little_loops/cli/issues/next_id.py:35` (read-only preview, no lock), `scripts/little_loops/cli/issues/normalize.py:302-308`, `scripts/little_loops/sync.py:681`, `scripts/little_loops/issue_parser.py:3744` (`_generate_id_from_filename`, the decomposition/filename-fallback path)
- Additional surface not currently named in this section: `scripts/little_loops/issue_lifecycle.py:822` (`create_issue_from_failure`) calls `get_next_issue_number(config, "bugs")` directly with no lock and no collision retry at all (contrast `create_issue()`'s exclusive-create retry loop) — called from `IssueManager`'s automated processing loop (`issue_manager.py:1360`), which can itself run inside a worktree; this is a second, more weakly-guarded surface for the same collision class and should be covered by the same fix
- No existing helper resolves a main checkout root from a linked worktree anywhere in this repo. Closest precedent: `hooks/scripts/session-cleanup.sh:30-37` compares `git rev-parse --git-dir` vs `--git-common-dir` (only existing use of `--git-common-dir`); `host_runner.py` (three call sites: `:425-433`, `:719-727`, `:1041-1058`, landed via ENH-932) instead parses the `.git` file's `gitdir:` line directly — neither derives the main working-tree root, only the object-store path
- Test fixture precedent for step 4: a lightweight `.git`-file fixture (`(tmp_path / ".git").write_text(f"gitdir: {gitdir}\n")`) is used throughout `scripts/tests/test_host_runner.py` for worktree-env tests; a real `git init` + `git worktree add` fixture via `copy_git_template()` (`scripts/tests/helpers.py:44-74`) is used in `scripts/tests/test_worktree_utils.py` when real git plumbing matters — `scripts/tests/test_issue_parser.py:971-1090` (`TestGetNextIssueNumber`) has no worktree scenario today

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Scope the fix as a new helper (e.g. `resolve_main_checkout_root()`) consumed only by `get_next_issue_number()` and lock-path construction in `create.py`/`scaffold_epic.py` — do NOT change `BRConfig.project_root`'s own value; ~54 other call sites across 36 files (including `create.py:484`'s `git add` staging) depend on it staying worktree-local
- Reconcile with `.issues/enhancements/P3-ENH-1198-ll-issues-atomicity-under-worktree-mode.md`'s closing rationale (closed Invalid; argued cross-tree locking "would break worktree isolation entirely") — this fix takes the opposite approach and should note why in Proposed Solution or Root Cause
- Verify `scripts/little_loops/cli/issues/__init__.py:986` — top-level `BRConfig(project_root)` dispatch — is unaffected (cwd resolution happens here before handoff to `create`/`scaffold-epic`/`next-id`)
- Update `scripts/little_loops/mcp_server/tools.py:295-296` — MCP tool-description string documents the current `.id-alloc.lock` path
- Update `scripts/little_loops/file_utils.py:76` — docstring cross-reference to `.id-alloc.lock` convention, if the lock's resolved location changes
- Verify/update `skills/scope-epic/SKILL.md:286` — claim that ID allocation is "atomically" handled across worktree fan-out
- Write new tests per Integration Map → Tests: worktree-vs-main collision test (real-git fixture), cross-tree `.id-alloc.lock` test, `create_issue_from_failure()` worktree-collision coverage

## Impact

- **Priority**: P2 - Silent ID-namespace corruption in a live automation path (EPIC worktrees + parallel workers); already caused one real incident (FEAT-3117/3118), but a workaround (manual recovery + avoiding stale-branch decomposition) exists
- **Effort**: Medium - One new resolver helper + highwater file + lock relocation, ~7 call-site-adjacent touchpoints, but a single choke point (`get_next_issue_number`) and substantial new test fixtures (real-git worktree scenarios)
- **Risk**: Medium - Allocation is on every issue-creation path; mitigated by strict graceful-degradation fallback to today's behavior and no change to `BRConfig.project_root`
- **Breaking Change**: No - IDs only ever get larger; primary-checkout behavior is unchanged; new `.id-alloc-highwater` file is gitignored allocation state

## Root Cause

ID allocation is scoped to the working directory's checkout instead of the canonical issue namespace. Per `feedback_bare_numeric_frontmatter_id_supported` conventions, the numeric ID is the unique key across the whole repo history; a stale worktree checkout is not an authoritative view of allocated IDs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- **Lock scope**: `scripts/little_loops/cli/issues/create.py:446` — the `.id-alloc.lock` advisory lock lives inside the worktree-scoped `.issues/` directory itself, so it provides no cross-tree serialization between a worktree and the main checkout
- **Weaker parallel surface**: `scripts/little_loops/issue_lifecycle.py:822` (`create_issue_from_failure`) calls `get_next_issue_number(config, "bugs")` directly with no lock and no collision retry at all, called from `IssueManager`'s automated processing loop (`issue_manager.py:1360`), which can itself run inside a worktree

## Program Design

### Types
N/A — no new data shape; the fix changes where the existing scan reads from, not what it returns.

### Signatures
- `get_next_issue_number(config: BRConfig, category: str | None = None) -> int` — `scripts/little_loops/issue_parser.py:3196`, the single choke point every allocation call site reaches through
- `BRConfig.__init__(self, project_root: Path)` — `scripts/little_loops/config/core.py:251-257`; sets `self.project_root = project_root.resolve()` verbatim, no git-boundary walk
- `find_project_root(start: Path) -> Path | None` — `scripts/little_loops/paths.py:14-42`; already worktree-safe (`.git` checked via `.exists()`, not `.is_dir()`) but resolves the *nearest* `.git` boundary (the worktree's own root), not a main tree beyond it; not currently called anywhere in the `BRConfig`/allocation path

### Call Path
`ll-issues create` (`cli/issues/create.py:cmd_create`) -> `create_issue()` (`create.py:406`) -> `get_next_issue_number(config)` (`issue_parser.py:3196`) -> `config.get_issue_dir(category)` (`config/core.py:520`) -> `Path.glob("*.md")` scoped to `config.project_root`

### Decision Rules
N/A — no new gap kind, gate, or threshold; the fix changes an existing scan's root resolution, not its decision logic.

## Steps to Reproduce

1. Create a branch, then add new issues on main so main's max ID advances.
2. In a worktree attached to the stale branch, run `ll-issues create ...` (or any decomposition flow that allocates IDs).
3. The new issue receives an ID equal to one already allocated on main.

## Desired Behavior

ID allocation consults the canonical namespace even from a worktree. See Option A/B/C decision under Proposed Solution.

## Acceptance Criteria

- [ ] `ll-issues create` inside a linked worktree on a stale branch never allocates an ID <= the main tree's max allocated ID
- [ ] Two sibling worktrees allocating sequentially (no merge between) never receive the same ID (high-water-mark file exercised)
- [ ] Decomposition flows allocate through the same guarded path, including `create_issue_from_failure()` (`issue_lifecycle.py:822`)
- [ ] `ll-issues next-id` previews the same ID `ll-issues create` then allocates, from inside a worktree
- [ ] Behavior unchanged when running in the primary checkout, in a non-git directory, and in a worktree whose main tree lacks `.issues/` (graceful degradation, no errors)
- [ ] `python -m pytest scripts/tests/` passes

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| docs/reference/API.md | architecture | `issue_parser` / `ll-issues create` ID-allocation surfaces |
| .claude/CLAUDE.md | guidelines | Issue File Format — numeric ID is the canonical unique identifier |

## Status

**Open** | Created: 2026-08-23 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-23T21:46:40 - `472772e0-0d23-4f5c-8222-6df281b8269d.jsonl`
- `/ll:decide-issue` - 2026-08-23T20:54:12 - `b06a9731-b7f1-4cd3-ae8f-7c9209764607.jsonl`
- `/ll:confidence-check` - 2026-08-23T20:42:20 - `36a136c9-6c59-4cf6-b7d4-c0e4e7645a9e.jsonl`
- `/ll:wire-issue` - 2026-08-23T20:36:03 - `7746b0e5-5986-4ac4-ae25-f7097ddec171.jsonl`
- `/ll:refine-issue` - 2026-08-23T20:27:20 - `7bbdaa9b-79ec-4518-a9d5-5daf606989bc.jsonl`
- `/ll:capture-issue` - 2026-08-23T19:19:40 - `0e2d1ba2-9c47-49de-b246-1efb9ad7b60c.jsonl`
