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
2. Add a canonical-namespace resolver: detect linked-worktree context, resolve the main checkout path from `git-common-dir`, union both `.issues/` scans.
3. Cover decomposition paths that allocate IDs (recursive decompose flows) via the same helper.
4. Tests: fixture repo + linked worktree on a stale branch; assert allocated ID exceeds main's max.

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

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

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

ID allocation consults the canonical namespace even from a worktree — candidates:

- Resolve the primary repo root (a worktree's `.git` file points at the main checkout's `gitdir`) and scan that `.issues/` tree in addition to the local one, taking the max.
- And/or scan git refs (`git ls-tree <default-branch> -- .issues` via the common git dir) so IDs allocated on main are visible regardless of checkout state.
- Minimum viable guard: when running inside a linked worktree (`git rev-parse --git-common-dir` differs from `--git-dir`), also read the main working tree's `.issues/` max ID.

## Acceptance Criteria

- [ ] `ll-issues create` inside a linked worktree on a stale branch never allocates an ID <= the main tree's max allocated ID
- [ ] Decomposition flows allocate through the same guarded path
- [ ] Behavior unchanged when running in the primary checkout
- [ ] `python -m pytest scripts/tests/` passes

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| docs/reference/API.md | architecture | `issue_parser` / `ll-issues create` ID-allocation surfaces |
| .claude/CLAUDE.md | guidelines | Issue File Format — numeric ID is the canonical unique identifier |

## Status

**Open** | Created: 2026-08-23 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-23T20:42:20 - `36a136c9-6c59-4cf6-b7d4-c0e4e7645a9e.jsonl`
- `/ll:wire-issue` - 2026-08-23T20:36:03 - `7746b0e5-5986-4ac4-ae25-f7097ddec171.jsonl`
- `/ll:refine-issue` - 2026-08-23T20:27:20 - `7bbdaa9b-79ec-4518-a9d5-5daf606989bc.jsonl`
- `/ll:capture-issue` - 2026-08-23T19:19:40 - `0e2d1ba2-9c47-49de-b246-1efb9ad7b60c.jsonl`
