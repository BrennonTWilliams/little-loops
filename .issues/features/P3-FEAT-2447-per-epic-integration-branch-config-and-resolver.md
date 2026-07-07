---
id: FEAT-2447
title: "per-EPIC integration branch \u2014 config schema, dataclasses, resolver, and\
  \ serialization"
type: FEAT
priority: P3
status: open
captured_at: '2026-07-02T22:30:00Z'
discovered_date: 2026-07-02
discovered_by: issue-size-review
labels:
- parallel
- sprint
- epics
- git
- worktree
- config
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- FEAT-2448
- FEAT-2449
- FEAT-2450
decision_needed: false
confidence_score: 99
outcome_confidence: 81
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 20
---

# FEAT-2447: per-EPIC integration branch — config schema, dataclasses, resolver, and serialization

## Summary

First of four sequenced children decomposed from FEAT-2339. This child
introduces the **config surface** (schema entry, dataclass, automation
mirror, `BRConfig` passthrough), the **epic-branch resolver** that
maps an `IssueInfo` to a `(fork_point, merge_target)` pair, and the
**9-template `epic_branches:{enabled:false}` stamp** mandated by
Decision ARCHITECTURE-096 (selected via `/ll:decide-issue` Option A
on 2026-07-07). No worker_pool, merge_coordinator, orchestrator,
CLI, or TUI changes — those land in FEAT-2448 / FEAT-2449 / FEAT-2450.

Children of one EPIC share a single integration branch
`epic/<EPIC-ID>-<slug>` (fork point **and** merge target — same string
by construction, per Decision Rationale #1 in FEAT-2339: "flatten to
nearest EPIC ancestor"). Standalone (parentless) issues retain today's
behavior unchanged. Default OFF.

## Current Behavior

When `ll-parallel` or `ll-sprint` processes multiple children of a single
EPIC, each child issue creates an independent worker worktree that:

1. **Branches** off `parallel.base_branch` directly (typically `main`).
2. **Merges** its worktree changes back to `parallel.base_branch` on
   completion.

For a 4-child EPIC this produces four separate merge commits on the base
branch with no intermediate integration surface — there is no way to
inspect the in-progress EPIC as a coherent unit before its pieces land
on `main`.

The existing config schema (`config-schema.json` `parallel.*`) has no
epic-branch concept. `ParallelConfig`, `ParallelAutomationConfig`, and
`BRConfig` round-trip only flat per-worker settings (max_workers,
base_branch, host_cli, auto_resume, learning_test_gate). `WorkerPool`
has no notion of a parent EPIC at branch-creation time, and
`merge_coordinator.py` resolves merge targets from per-worker worktrees
only.

## Expected Behavior

When `parallel.epic_branches.enabled=true` and an issue has a parent EPIC:

- All children of that EPIC share a single integration branch
  `epic/<EPIC-ID>-<slug>` (fork point **and** merge target — same string
  by construction per Decision Rationale #1 in FEAT-2339: "flatten to
  nearest EPIC ancestor").
- For nested EPICs, children flatten to the **nearest** EPIC ancestor's
  branch (a grandchild of EPIC-A through sub-EPIC-B uses EPIC-B's
  branch, not EPIC-A's).
- The branch is created lazily off `base_branch` on first call per
  `epic_id`; subsequent calls are idempotent (skip if the branch
  exists locally or on remote).
- Default behavior is **OFF** (`enabled: false`) and parentless issues
  fall back to today's `(base_branch, base_branch)` no-op return, so
  existing `merge_coordinator.py` consumer sites remain unchanged.

No public API changes outside the new `EpicBranchesConfig` dataclass and
the new `WorkerPool._resolve_branch_targets()` private method. No new
CLI flags, no TUI changes (all deferred to FEAT-2450). Templates
**ARE** part of this child per Option A (Decision ARCHITECTURE-096)
— see Configuration → Template parity below.

## Motivation

- **Coherent EPIC review surface**: A 4-child EPIC today produces 4
  independent merge commits on the base branch with no intermediate
  branch to inspect. An EPIC integration branch gives reviewers one
  branch/PR to review per EPIC rather than 4 unrelated commits.
- **Safer partial-failure recovery**: If the 3rd child of an EPIC
  fails, the EPIC branch carries the first 2 children's work and can
  be merged, branched from, or rebased without losing their progress
  to ephemeral worktrees.
- **Sprint/PR granularity matches epic granularity**: Today
  `ll-sprint`'s "one PR per issue" rule forces reviewers to mentally
  assemble an EPIC from N sibling PRs; the EPIC branch realigns that
  boundary.
- **Foundation for future automation**: A stable EPIC branch is the
  prerequisite for in-place progress checks, EPIC-completion merge
  coordination (FEAT-2449), and rev-list deltas in the orchestrator.

Trade-off accepted: default OFF keeps the change fully opt-in; no
existing user behavior changes until `epic_branches.enabled=true` is
explicitly set.

## Use Case

**Who**: A project maintainer running `ll-parallel` (or `ll-sprint`)
against a multi-child EPIC.

**Context**: They have an EPIC with 4 children (FEAT-2447, FEAT-2448,
FEAT-2449, FEAT-2450) decomposed from FEAT-2339. They want all 4 to
land on a single integration branch so they can review the EPIC's
progress in one place before merging to `main`, instead of four
scattered merge commits.

**Goal**: Coalesce the EPIC's work onto
`epic/EPIC-2451-per-epic-integration-branch-strategy` so the
integration surface is one branch, one PR, one merge.

**Outcome**: Each child worker worktree branches off
`epic/EPIC-2451-...` instead of `main`, and merges back to
`epic/EPIC-2451-...` on completion. After the last child finishes, the
EPIC branch is itself merged to `main` (FEAT-2449).

**Setup**: Set `parallel.epic_branches.enabled: true` in
`.ll/ll-config.json` (default OFF preserves today's behavior).

## Proposed Solution

Build the **foundation only** (no `worker_pool._setup_worktree()`
wiring, no `merge_coordinator` consumption, no CLI/TUI surface —
those land in FEAT-2448/2449/2450):

1. Add `parallel.epic_branches` block to `config-schema.json` (4
   sub-keys: `enabled`, `prefix`, `merge_to_base_on_complete`,
   `open_pr`).
2. Add `EpicBranchesConfig` dataclass to
   `scripts/little_loops/parallel/types.py`, mirror in
   `ParallelAutomationConfig`, wire keyword passthrough in
   `BRConfig.create_parallel_config()` and serialization in
   `BRConfig.to_dict()`.
3. Export `EpicBranchesConfig` from
   `scripts/little_loops/parallel/__init__.py` (`__all__`).
4. Add `WorkerPool._resolve_branch_targets(issue) -> tuple[str, str]`
   private method that returns `(base_branch, base_branch)` for
   parentless or epic-off cases, and
   `(epic/<EPIC-ID>-<slug>, epic/<EPIC-ID>-<slug>)` otherwise. Uses
   `IssueInfo.parent` and depth-aware nearest-EPIC-ancestor resolution
   (cycle-guarded, modeled on the shape of `_issue_descends_to()` in
   `scripts/little_loops/issue_progress.py:67-80`).

See **Scope** below for the full 5-item implementation breakdown and
**Files Touched** for the 8-file change list. The **API/Interface**
section documents the resulting public-surface additions.

### Codebase Research Findings

_Added by `/ll:refine-issue` — anchor drift and pattern corrections from codebase analysis:_

- **Anchor drift — `commands.py` does not exist.** This issue cites
  `ConfidenceGateConfig` as living in
  `scripts/little_loops/config/commands.py`. That file does not exist.
  `ConfidenceGateConfig` is actually declared in
  `scripts/little_loops/config/automation.py` at line 103 (with
  `from_dict` at line 111). `CommandsConfig` (which composes it as a
  field) also lives there. The new `EpicBranchesConfig` should follow
  the pattern at `automation.py:103-119`, not in a non-existent
  `commands.py`.
- **Anchor drift — `BRConfig.create_parallel_config()` line.** The
  issue says "around line 496". The actual signature starts at line
  413; the `ParallelConfig(...)` constructor body runs lines 461–507.
  The natural insertion point for `epic_branches=self._parallel.epic_branches`
  is the `feature_branches`/`base_branch` cluster around lines 488–506.
- **Anchor drift — `BRConfig.to_dict()` parallel block.** The issue
  cites lines 555–574; the actual `parallel` dict literal runs lines
  557–576 (off by 2 lines).
- **Anchor drift — `test_to_dict_parallel_schema_aligned_keys` line.**
  The issue cites lines 776–797; the test is at line 750 (ends ~772).
  Lines 776–797 are actually `test_to_dict_confidence_gate_schema_aligned_keys`
  (the precedent for the new assertion).
- **Anchor drift — `test_roundtrip_serialization` constructor block.**
  The issue cites 1017–1059; the actual constructor call runs
  lines 998–1028 and assertions run lines 1030–1059.
- **Better pattern match discovered.** The issue models the resolver's
  nearest-EPIC-ancestor walk on `_issue_descends_to()` in
  `scripts/little_loops/issue_progress.py:67-80`, which returns a
  *boolean*. A closer precedent already exists:
  `_find_epic_ancestor()` in
  `scripts/little_loops/cli/issues/list_cmd.py:195-203` walks the
  same parent chain with the same cycle-guard but **returns the
  matching ancestor's ID** (`current.split("-", 1)[0] == "EPIC"` →
  `return current`). The new `_resolve_branch_targets()` should
  mirror this exact shape — it already returns the ID rather than a
  boolean.
- **`ParallelConfig` has no existing nested-dataclass field** (only
  flat fields and lists). The closest precedent for nested composition
  is `CommandsConfig.confidence_gate` /
  `CommandsConfig.rate_limits` in `automation.py:172-194`, using
  `field(default_factory=Cls)` and `SubConfig.from_dict(data.get("sub", {}))`
  in the parent's `from_dict()`.
- **`test_roundtrip_serialization` precedent for nested config.** No
  existing nested-dataclass field in `ParallelConfig`, so the new test
  assertion can model on
  `test_to_dict_confidence_gate_schema_aligned_keys`
  (`scripts/tests/test_config.py:773`) — a flat key check on a
  parent-dict that contains a nested sub-dict.

#### Resolver implementation guidance (added by `/ll:refine-issue` 2026-07-06)

_Concrete primitives for the lazy-create + slug-source logic, surfaced
from codebase pattern analysis (Agent 3 findings):_

- **Slug source for `epic/<EPIC-ID>-<slug>` is the EPIC's title, not
  the issue's title.** The canonical `slugify()` function lives at
  `scripts/little_loops/issue_parser.py:287-298` (already imported by
  `scripts/little_loops/parallel/worker_pool.py:336` for the existing
  `feature/<id>-<slug>` template at line 338). The new EPIC branch
  name composes as
  `f"{self.parallel_config.epic_branches.prefix}{epic_id.lower()}-{slugify(epic_title)}"`,
  where `epic_title` is read from the EPIC ancestor's frontmatter
  (load the EPIC's `IssueInfo` via `scripts/little_loops/issue_parser.py`
  — same module `IssueInfo` already provides `title`). **The current
  issue body shows `<slug>` but does not pin its source** — implementer
  must resolve this. Fallback when EPIC title is unavailable: use a
  slug of the EPIC ID alone (e.g. `epic/epic-2451`).

- **No existing idempotent branch-create helper — the resolver must
  compose its own.** `setup_worktree()` at
  `scripts/little_loops/worktree_utils.py:63-159` fails if the branch
  already exists (uses `git worktree add -b <name>`, which errors on
  duplicate). The new resolver's lazy-create sequence:
  1. Local check:
     `self._git_lock.run(["rev-parse", "--verify", branch_name], cwd=self.repo_path, timeout=10)` —
     returncode 0 means branch exists locally (existing precedent at
     `worktree_utils.py:95-102`).
  2. Remote check:
     `self._git_lock.run(["ls-remote", "--heads", self.parallel_config.remote_name, branch_name], cwd=self.repo_path, timeout=30)` —
     non-empty stdout means branch exists on remote. **NEW idiom** —
     `git ls-remote` has no existing usage in `scripts/little_loops/`;
     introduction here is in scope (sub-feature surface, not net-new
     infra). The only existing remote-aware git calls are
     `git fetch <remote> <base>` at `worker_pool.py:1115-1121` and
     `git symbolic-ref --short refs/remotes/origin/HEAD` at
     `worktree_utils.py:51-53`.
  3. Create:
     `self._git_lock.run(["branch", branch_name, base_branch], cwd=self.repo_path, timeout=30)` —
     creates branch off base only when both checks above failed.
  4. Cache per-`epic_id`: add
     `self._epic_branches_created: set[str] = set()` to
     `WorkerPool.__init__` (init at line 169-188 cluster) to short-circuit
     subsequent calls within the same WorkerPool instance lifetime
     without re-hitting git.

- **`EpicBranchesConfig` should NOT define its own `to_dict()` —
  inline fields in `BRConfig.to_dict()` following the
  `commands.confidence_gate` precedent at
  `scripts/little_loops/config/core.py:581-585`:
  ```python
  "confidence_gate": {
      "enabled": self._commands.confidence_gate.enabled,
      "readiness_threshold": self._commands.confidence_gate.readiness_threshold,
      "outcome_threshold": self._commands.confidence_gate.outcome_threshold,
  },
  ```
  Apply the same shape for the new `parallel.epic_branches` block
  (4 fields inlined: `enabled`, `prefix`, `merge_to_base_on_complete`,
  `open_pr`). The alternative `loops.glyphs` precedent (delegates to
  `LoopsGlyphsConfig.to_dict()` at `core.py:610`) is **less** consistent
  with the existing `parallel.*` block style and would break the
  convention established by the `commands.confidence_gate` /
  `commands.rate_limits` sub-blocks. Add the `epic_branches` literal
  between line 573 (`open_pr_for_feature_branches` close) and line 574
  (`base_branch` open) per Agent 1's confirmed slot.

- **`worktree_utils._is_ll_branch()` does NOT detect `epic/*`.** At
  `scripts/little_loops/worktree_utils.py:213-223`, the cleanup-classifier
  only matches `parallel/*` or `^\d{8}-\d{6}-*` patterns. Not required
  in FEAT-2447 (cleanup deferred to FEAT-2449), but flagged so
  FEAT-2449 can add `or branch_name.startswith("epic/")` if/when
  auto-cleanup of merged EPIC branches lands.

- **Wiring site pinpoint** (FEAT-2448 will consume here, FEAT-2447
  adds only the method):
  `WorkerPool._process_issue()` at
  `scripts/little_loops/parallel/worker_pool.py:335-340` computes
  `branch_name` today; the `_setup_worktree()` call at line 361
  currently passes `base_branch=self.parallel_config.base_branch` —
  the resolver's `fork_point` will override that argument in FEAT-2448.
  The `branch_name` computation at line 338 (`feature/<id>-<slug>`)
  is independent and not affected by epic-mode unless FEAT-2448 also
  wires that. The resolver output `(epic/..., epic/...)` will flow
  through `_setup_worktree(..., base_branch=fork_point)`,
  causing worktree creation to fork off the EPIC branch rather than
  `main`.

## Parent Issue

Decomposed from FEAT-2339: Per-EPIC integration branch strategy for
ll-parallel/ll-sprint.

## Scope

This child covers the **foundation** only:

1. **Config schema + dataclasses (4-location pattern)** — add
   `parallel.epic_branches.*` nested object to `config-schema.json`
   inside the `"parallel"` properties block (before
   `additionalProperties: false` at line 408). Sub-keys: `enabled` (bool,
   default false), `prefix` (string, default `"epic/"`),
   `merge_to_base_on_complete` (bool, default true), `open_pr` (bool,
   default false). Add matching dataclass field + `to_dict()` +
   `from_dict()` to `scripts/little_loops/parallel/types.py:ParallelConfig`.
   Mirror in `scripts/little_loops/config/automation.py:ParallelAutomationConfig`
   and its `from_dict()`. Add explicit keyword passthrough in
   `scripts/little_loops/config/core.py:BRConfig.create_parallel_config()`
   (~line 496).
2. **`EpicBranchesConfig` dataclass** — modeled on
   `ConfidenceGateConfig` in `commands.*`. Export from
   `scripts/little_loops/parallel/__init__.py` (mirrors how
   `ConfidenceGateConfig` is re-exported from `config/__init__.py`):
   add the import + `__all__` entry alongside `ParallelConfig`.
3. **`BRConfig.to_dict()` serialization** — add `epic_branches`
   sub-object to the explicit `parallel` key enumeration in
   `scripts/little_loops/config/core.py:555-574`. Omitting it causes
   `ll-issues decisions sync` / config round-trip to silently lose the
   setting.
4. **Epic-branch resolver** — add
   `_resolve_branch_targets(issue: IssueInfo) -> tuple[str, str]`
   (fork_point, merge_target) to `WorkerPool` (in
   `scripts/little_loops/parallel/worker_pool.py`). Uses
   `issue.parent` (from `scripts/little_loops/issue_parser.py:IssueInfo.parent`,
   line ~437, drifted from 251 per FEAT-2339 anchor corrections) and
   `self.parallel_config.epic_branches.enabled`. Resolves to the
   **nearest EPIC ancestor** via a depth-aware helper (reuses the
   `_issue_descends_to()` cycle-guard shape from `issue_progress.py:67-80`,
   but returns the nearest ancestor ID, not just a boolean). Lazily
   creates `epic/<EPIC-ID>-<slug>` off `base_branch` on first call
   per epic_id (idempotent: skip if branch already exists locally or
   on remote). Returns `(self.parallel_config.base_branch,
   self.parallel_config.base_branch)` (i.e. today-equivalent no-op) when
   epic mode is disabled or `issue.parent` is None — keeps
   `merge_coordinator.py` consumer sites trivially unchanged.
5. **Tests** —
   - `scripts/tests/test_parallel_types.py:test_roundtrip_serialization`
     (lines 1017–1059) — add `epic_branches=EpicBranchesConfig(enabled=True, ...)`
     to constructor and assert.
   - `scripts/tests/test_config_schema.py` — add
     `test_parallel_epic_branches_in_schema()` asserting
     `"epic_branches" in parallel["properties"]` with sub-properties
     `enabled`/`prefix`/`merge_to_base_on_complete`/`open_pr`.
   - `scripts/tests/test_config.py:TestParallelAutomationConfig`
     (lines 340–412) — add `epic_branches` counterpart test modeled on
     `TestConfidenceGateConfig` (lines 415–443).
   - `scripts/tests/test_config.py:test_to_dict_parallel_schema_aligned_keys`
     (lines 776–797) — add `"epic_branches" in parallel` assertion.
   - `scripts/tests/test_worker_pool.py` — new
     `test_resolve_branch_targets_*` tests modeled on the
     `_make_issue(tmp_path, issue_id, parent=...)` helper from
     `scripts/tests/test_issue_progress.py:12-64`. Cover:
     - epic_mode off → returns `(base_branch, base_branch)`
     - epic_mode on, parentless issue → returns `(base_branch, base_branch)`
     - epic_mode on, issue with EPIC parent → returns
       `(epic/<EPIC-ID>-<slug>, epic/<EPIC-ID>-<slug>)`
     - nested-EPIC flatten-to-nearest (grandchild with intermediate
       sub-EPIC parent) → returns nearest ancestor's branch, not
       grandchild's direct parent.
     - idempotent lazy creation: second call for same epic_id does
       not error if branch already exists.

## Out of Scope (deferred to follow-on children)

- `worker_pool.py:_setup_worktree()` actually using the resolver's
  fork point — **FEAT-2448**.
- `merge_coordinator.py` using the resolver's merge target — **FEAT-2448**.
- `WorkerResult.epic_branch` field threading — **FEAT-2448**.
- `_get_changed_files()` / `_update_branch_base()` epic-mode variants
  — **FEAT-2448**.
- EPIC-completion → epic-branch merge logic — **FEAT-2449**.
- Orchestrator / sprint-runner epic-branch awareness (rev-list
  comparison, in-place warning) — **FEAT-2449**.
- CLI flags (`--epic-branches`), TUI surface, configure skill updates
  — **FEAT-2450**.
- Docs (ARCHITECTURE, API, CONFIGURATION, CLI, SPRINT_GUIDE), 9
  templates parity — **FEAT-2450**.

## Acceptance Criteria

- [ ] `EpicBranchesConfig` dataclass exists in `parallel/types.py`
      with the 4 documented sub-fields and correct defaults.
- [ ] `ParallelConfig` carries `epic_branches: EpicBranchesConfig`
      with `to_dict()` / `from_dict()` roundtrip preservation.
- [ ] `ParallelAutomationConfig` mirrors the same field with
      `from_dict()` parsing.
- [ ] `BRConfig.create_parallel_config()` passes the new field through
      (~line 496).
- [ ] `BRConfig.to_dict()` serializes `epic_branches` inside
      `parallel` (lines 555–574).
- [ ] `EpicBranchesConfig` is exported from
      `scripts/little_loops/parallel/__init__.py` (`__all__` entry).
- [ ] `WorkerPool._resolve_branch_targets(issue)` exists with the
      documented semantics (parentless / epic-off → no-op return;
      epic-on with EPIC parent → nearest ancestor branch tuple;
      nested-EPIC flatten-to-nearest; idempotent lazy creation).
- [ ] All new tests pass; full
      `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation:**
- `config-schema.json` (add `parallel.epic_branches` block)
- `scripts/little_loops/parallel/types.py` (`EpicBranchesConfig` +
  `ParallelConfig` field + `to_dict`/`from_dict`)
- `scripts/little_loops/parallel/__init__.py` (export)
- `scripts/little_loops/config/automation.py`
  (`ParallelAutomationConfig` mirror)
- `scripts/little_loops/config/core.py` (`BRConfig.create_parallel_config`
  + `BRConfig.to_dict`)
- `scripts/little_loops/parallel/worker_pool.py`
  (`_resolve_branch_targets` method)

**Tests:**
- `scripts/tests/test_parallel_types.py`
- `scripts/tests/test_config_schema.py`
- `scripts/tests/test_config.py` (`TestParallelAutomationConfig` +
  `test_to_dict_parallel_schema_aligned_keys`)
- `scripts/tests/test_worker_pool.py` (new `_resolve_branch_targets_*`
  block, modeled on `_make_issue` helper from `test_issue_progress.py`)

**Estimated file count:** 4 implementation + 4 test = **8 files**.

## Implementation Steps

1. **Config surface** — add `parallel.epic_branches` to
   `config-schema.json` (sub-keys: `enabled`, `prefix`,
   `merge_to_base_on_complete`, `open_pr`); add `EpicBranchesConfig`
   dataclass to `parallel/types.py`; mirror in
   `ParallelAutomationConfig`; wire `BRConfig.create_parallel_config()`
   keyword passthrough and `BRConfig.to_dict()` serialization.
2. **Export** — add `EpicBranchesConfig` to `parallel/__init__.py`
   `__all__` alongside `ParallelConfig`.
3. **Resolver** — implement `WorkerPool._resolve_branch_targets(issue)`
   with nearest-EPIC-ancestor flattening, idempotent lazy branch
   creation off `base_branch`, and no-op fallback for parentless or
   epic-off paths. Cycle-guard modeled on the
   `_issue_descends_to()` shape from
   `scripts/little_loops/issue_progress.py`.
   - **Slug source**: read the EPIC ancestor's `title` from its
     frontmatter via `IssueInfo.title` (parsed by
     `scripts/little_loops/issue_parser.py`); apply
     `slugify()` (`issue_parser.py:287-298`). Branch name composes as
     `f"{self.parallel_config.epic_branches.prefix}{epic_id.lower()}-{slugify(epic_title)}"`.
     Fallback to slug of EPIC ID alone if EPIC title cannot be
     resolved.
   - **Lazy-create primitives**: local check via
     `git rev-parse --verify <branch>`, remote check via
     `git ls-remote --heads <remote> <branch>`, create via
     `git branch <branch> <base>` — all routed through
     `self._git_lock.run([...], cwd=self.repo_path, timeout=...)`.
     Cache per-`epic_id` in a new
     `self._epic_branches_created: set[str]` initialized in
     `WorkerPool.__init__`.
4. **Tests** — extend `test_parallel_types.py` roundtrip case, add
   `test_parallel_epic_branches_in_schema()` to `test_config_schema.py`,
   add `epic_branches` counterpart to `TestParallelAutomationConfig`
   and `test_to_dict_parallel_schema_aligned_keys`, and add a new
   `_resolve_branch_targets_*` block to `test_worker_pool.py` (5 cases:
   no-op, parentless, EPIC-parent, nested-EPIC flatten, idempotent
   re-call).
5. **Verify** — `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the implementation:_

6. **Re-export `EpicBranchesConfig` from `config/__init__.py`** — mirror
   the `parallel/__init__.py` re-export. Without this,
   `from little_loops.config import EpicBranchesConfig` will
   `ImportError` even though `parallel/__init__.py` exposes the class.
7. **Resolve the template-parity scope conflict** — pick option
   (A) stamp the 9 project-type templates in this child per
   `ARCHITECTURE-096` (small mechanical edits) **or** option (B)
   land them in FEAT-2450 alongside the TUI/configure surface. The
   rationale for option (A) is consistency: the schema accepts
   `epic_branches` from day 1, so init-using projects get the same
   defaults as config-file users. The rationale for (B) is keeping
   this child strictly "foundation only" with no init template
   coupling. The current "Out of Scope" deferral matches (B); the
   decision rule mandates (A). Resolve before implementation.
8. **Verify `init/core.py` schema-default parity** —
   `scripts/tests/test_init_core.py:707` asserts schema-default ↔
   literal parity; either add `parallel.epic_branches: {enabled:
   false}` to `init/core.py:build_config()` defaults, OR confirm
   the test is schema-permissive on missing keys (Agent 1 finding).
9. **Verify hardcoded `"parallel"` test fixtures against new
   schema** — if any of the 5 fixtures listed under
   `Tests → Hardcoded "parallel" test fixtures` reject the new
   schema, add `"epic_branches": {"enabled": false}` to each.
10. **Audit `feature_config = ParallelConfig(**...to_dict(),
    "use_feature_branches": True)` at
    `scripts/tests/test_worker_pool.py:2201`** — the new
    `epic_branches` field will appear in `to_dict()`. Either set
    it explicitly on both configs in the diff or rely on
    `default_factory` equality.

### Wiring Phase (re-wire added by `/ll:wire-issue`)

_Re-wire after `/ll:decide-issue` selected Option A (land the 9-template
`epic_branches:{enabled:false}` stamps in this child on 2026-07-07).
These touchpoints were identified by a second wiring pass that ran
the 3-agent fan-out against the previously-wired surface._

11. **Add `TestBRConfig.test_create_parallel_config_epic_branches_*`
    family** (new tests, not in the prior wiring pass) — modeled on
    `test_create_parallel_config_feature_branches_explicit_true` at
    `scripts/tests/test_config.py:881`. Cover at minimum:
    `test_create_parallel_config_epic_branches_explicit_true`,
    `test_create_parallel_config_epic_branches_explicit_false`,
    `test_create_parallel_config_epic_branches_none_falls_back_to_config`.
    These exercise the `BRConfig.create_parallel_config()`
    `epic_branches=self._parallel.epic_branches` passthrough newly
    added in step 1.

12. **Extend `TestParallelConfig.test_default_values` at
    `scripts/tests/test_parallel_types.py:755`** (new assertion site,
    not in the prior wiring pass) — add
    `assert config.epic_branches.enabled is False` immediately after
    the existing `assert config.use_feature_branches is False`
    precedent at line 755. Adjacent precedent for adding one new
    dataclass default value to the existing pattern.

13. **Audit `test_build_config_emits_no_null_leaves` at
    `scripts/tests/test_init_core.py:636–662`** (new audit site,
    not in the prior wiring pass) — adding `EpicBranchesConfig` with
    its 4 sub-fields (each has a non-`None` default) must not
    produce any `None` leaf in the emitted config. The dataclass
    defaults (`False`, `"epic/"`, `True`, `False`) are all concrete,
    so this audit should pass without edit; it is a verify-only
    step, just like step 8.

14. **Verify kwargs-spread robustness across 11+ test sites** (advisory,
    not edits) — these sites construct
    `ParallelConfig(**dict_spread, **kwargs)` from `to_dict()` output
    and will receive the new `epic_branches` kwarg automatically. The
    `default_factory` produces equal defaults on both sides, so no edit
    is needed. Verify by running the full test suite after step 1
    lands. Sites:
    `scripts/tests/test_worker_pool.py:65, 2200, 3276`;
    `test_merge_coordinator.py:67`; `test_orchestrator.py:79, 785`;
    `test_issue_workflow_integration.py:236`; `test_cli_e2e.py:402`;
    `test_cli_loop_worktree.py:540`; `test_subprocess_mocks.py:593,
    650, 694, 736, 759, 785, 814, 859`.

15. **Exclude the `config/features.py:593` false-positive** (correction,
    not an edit) — the prior wiring pass listed this as a
    parallel-config round-trip concern. Agent 1 verified
    `scripts/little_loops/config/features.py:593` is
    `"parallel": self.parallel` on `LoopsGlyphsConfig` (an unrelated
    glyph badge field), NOT the `BRConfig.parallel` /
    `ParallelConfig` accessor. Remove from any reviewer checklist; no
    edit required. The real `BRConfig.parallel` accessor lives at
    `scripts/little_loops/config/core.py:256` and round-trips
    `EpicBranchesConfig` via the `from_dict()` patch in step 1.

## Integration Map

### Files to Modify
See **Files Touched** for the 8-file breakdown (4 implementation + 4
test). Implementation files: `config-schema.json`,
`scripts/little_loops/parallel/types.py`,
`scripts/little_loops/parallel/__init__.py`,
`scripts/little_loops/config/automation.py`,
`scripts/little_loops/config/core.py`,
`scripts/little_loops/parallel/worker_pool.py`. Test files:
`scripts/tests/test_parallel_types.py`,
`scripts/tests/test_config_schema.py`, `scripts/tests/test_config.py`,
`scripts/tests/test_worker_pool.py`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` —
  `WorkerPool.__init__` / `_setup_worktree` (FEAT-2448 will consume
  `_resolve_branch_targets`; this child only adds the method).
- `scripts/little_loops/parallel/merge_coordinator.py` —
  `_get_changed_files()` / `_update_branch_base()` (FEAT-2448 will
  consume; this child does not).
- `scripts/little_loops/parallel/orchestrator.py` —
  sprint/epic-aware comparison paths (FEAT-2449).
- `scripts/little_loops/cli/parallel.py` and `cli/sprint.py` — CLI
  flag surface (FEAT-2450).
- `.ll/ll-config.json` consumers via `ll-config validate` —
  schema-driven round-trip; `decisions sync` writes the new key
  automatically once the schema entry exists.
- `scripts/little_loops/config/__init__.py` — [Agent 1 finding] re-exports
  `ParallelAutomationConfig` and the new `EpicBranchesConfig` must be
  re-exported alongside it (mirrors the `parallel/__init__.py`
  re-export of `EpicBranchesConfig`).

#### Re-wire additions (added by `/ll:wire-issue` re-wire 2026-07-07)

_Fan-out found these touchpoints after the prior wire-issue + decide-issue
pass. They are the delta between what was already captured and what 3
parallel agents surfaced against the current source state._

- `scripts/tests/test_parallel_cli.py:39` — [Agent 1, new] hardcoded
  `"parallel": {...}` dict in `temp_project` fixture; flagged for the
  same schema-tolerance audit as the prior 5 fixtures. Per Agent 2's
  verification, `additionalProperties: false` rejects unexpected
  keys (not missing keys), so this fixture is schema-tolerant on the
  absent `epic_branches` and no stamp is required.
- `scripts/tests/test_issue_discovery.py:65` — [Agent 1, new] hardcoded
  `"parallel": {...}` block running through ~line 80, includes
  `command_prefix`/`ready_command`/`manage_command` plus parallel
  flags; same audit-only treatment as above, no stamp required.
- `scripts/tests/test_cli_loop_worktree.py:739, 775, 822` — [Agent 1,
  new] mock-attribute pattern `mock_cfg.return_value.parallel.*` (NOT
  dict literals); these touch the namespace via `MagicMock` attribute
  assignment rather than literal dict construction, so they need no
  change for `epic_branches` to be silently dropped at the
  `cfg.parallel` lookup. Audit-only — confirm on re-run.
- `scripts/little_loops/init/tui.py:680–689` — [Agent 1, audit-only]
  emits `config["parallel"] = parallel_section` on user-save with
  ONLY the keys the user explicitly changed
  (`max_workers`/`worktree_copy_files`/`use_feature_branches`); no
  `epic_branches` write today (default-False is schema-derived, not
  emitted). Acceptable for foundation; FEAT-2450 adds the TUI round
  for an `epic_branches` question if it materializes.
- `scripts/little_loops/cli/sprint/run.py:522, 581`,
  `scripts/little_loops/cli/parallel.py:241`, and
  `scripts/little_loops/cli/loop/run.py:395` — [Agent 1, audit-only]
  these read `config.parallel.use_feature_branches` /
  `config.parallel.base_branch` / `config.parallel.worktree_copy_files`
  (the existing accessor); none reads `parallel.epic_branches` today,
  so no edit is needed in this child. FEAT-2448/2449/2450 may extend
  these to honor `epic_branches` and will then need updates.

#### False-positive removal

- `scripts/little_loops/config/features.py:593` — REMOVE from
  dependent-files consideration. Agent 1's second pass verified this
  line is `"parallel": self.parallel` on `LoopsGlyphsConfig` (an
  unrelated glyph badge field used for skill/command badge metadata),
  NOT the `BRConfig.parallel` / `ParallelConfig` accessor. The prior
  wiring pass surfaced this incorrectly. The actual
  `BRConfig.parallel` accessor lives at
  `scripts/little_loops/config/core.py:256` and round-trips
  `EpicBranchesConfig` via the `from_dict()` patch in step 1.

### Similar Patterns
- `ConfidenceGateConfig` in `scripts/little_loops/config/automation.py:103-119`
  is the precedent for the nested config-object pattern (issue
  originally cited `commands.py` which does not exist — see Codebase
  Research Findings under **Proposed Solution** for the correction);
  mirror its `to_dict()` / `from_dict()` shape.
- `_issue_descends_to()` in
  `scripts/little_loops/issue_progress.py:67-80` is the cycle-guard
  shape for the nearest-EPIC-ancestor traversal.
- `_find_epic_ancestor()` in
  `scripts/little_loops/cli/issues/list_cmd.py:195-203` is the **closer
  precedent** for the resolver — it returns the nearest EPIC
  ancestor's ID (not a boolean), using the same `seen` cycle-guard
  and `parent_map.get(current)` walk. Mirror its `current.split("-", 1)[0] == "EPIC"`
  → `return current` shape.
- `_make_issue()` helper in `scripts/tests/test_issue_progress.py:12-64`
  is the test-fixture pattern for synthesizing `IssueInfo` with parent
  links (used for parsed-issue-semantics tests).
- `mock_issue` MagicMock fixture in
  `scripts/tests/test_worker_pool.py:110-117` is sufficient for
  `_resolve_branch_targets` unit tests since the resolver only needs
  `.issue_id` and `.parent`.

### Tests
See **Files Touched** — 4 test files, ~5 new test cases total.
The existing `mock_issue` MagicMock fixture at
`test_worker_pool.py:110-117` can be reused for `_resolve_branch_targets_*`
tests since the resolver only consumes `.issue_id` and `.parent`
(no filesystem-dependent semantics). For nested-EPIC flatten tests
requiring real parent_chain semantics, use `_make_issue()` from
`test_issue_progress.py:12-64` (it synthesizes an `IssueInfo` with a
real `parent` field that the resolver can traverse).

#### Hardcoded `"parallel"` test fixtures — verify under new schema

_Wiring pass added by `/ll:wire-issue` — Agent 1 surfaced these test
fixtures that hard-code a `"parallel"` dict block. Once the schema
adds the nested `epic_branches` sub-object under
`additionalProperties: false` (config-schema.json `parallel` block),
each fixture must continue to validate. Verify during implementation
by re-running the affected test files after the schema edit:

- `scripts/tests/conftest.py:284-296` — `sample_config["parallel"]`
  fixture (the docstring below notes no change needed unless the
  schema is strict on missing keys).
- `scripts/tests/test_cli.py:479` — hardcoded `"parallel": {...}` block.
- `scripts/tests/test_cli.py:1642` — hardcoded `"parallel": {...}` block.
- `scripts/tests/test_cli_e2e.py:105` — hardcoded `"parallel": {...}` block.
- `scripts/tests/test_issue_workflow_integration.py:197` — hardcoded
  `"parallel": {...}` block.

If any of these are rejected by the new schema (`additionalProperties:
false` is strict on missing keys), add `"epic_branches": {"enabled":
false}` to each. None of these existing fixtures should need the
nested key for behavior reasons — the addition is purely a
schema-parity stamp.

##### Re-wire additions (added by `/ll:wire-issue` re-wire 2026-07-07)

_Agent 1's second pass surfaced these additional hardcoded `"parallel"`
test fixtures the prior wire-issue missed (delta vs. the 5 listed above).
Per Agent 2's verification:_

- `scripts/tests/test_parallel_cli.py:39` — hardcoded `"parallel":
  {...}` block in the `temp_project` fixture. Schema-tolerant on
  absent `epic_branches` (same argument as the 5 listed above); no
  stamp required.
- `scripts/tests/test_issue_discovery.py:65` — hardcoded
  `"parallel": {...}` block running through ~line 80; includes
  `command_prefix`/`ready_command`/`manage_command` and parallel
  flags. Same audit treatment.
- `scripts/tests/test_cli_loop_worktree.py:739, 775, 822` — mock-
  attribute pattern (`mock_cfg.return_value.parallel.worktree_copy_files
  = []`), NOT a literal dict. `MagicMock` attribute assignment is
  unrelated to schema validation; no change needed.

##### Schema-tolerance verification (Agent 2 confirmed)

_Added by `/ll:wire-issue` re-wire 2026-07-07 — Agent 2 verified the
JSON Schema semantics behind the prior-pass hedging: `additionalProperties:
false` rejects **unexpected** keys at validation time; it does NOT
require existing data to enumerate every property. Concretely:_
_The `parallel` block in `config-schema.json:305-409` has
`additionalProperties: false` at line 408, but adding a new
`properties.epic_branches` sub-object with `required: false` /
`default: false` does NOT cause fixtures that omit `epic_branches`
to fail validation. Per Agent 2's read, ALL 7 fixtures listed
across both passes (conftest.py:284; test_cli.py:479, 1638; test_cli_e2e.py:105;
test_issue_workflow_integration.py:197; test_parallel_cli.py:39;
test_issue_discovery.py:65) are schema-tolerant on the new key._
_The implementation step 9 hedging ("add `epic_branches: {"enabled":
false}` to each if rejected") can be downgraded to a verify-only run:
`python -m pytest scripts/tests/test_config_schema.py
scripts/tests/test_config.py scripts/tests/conftest.py
scripts/tests/test_cli.py scripts/tests/test_cli_e2e.py
scripts/tests/test_issue_workflow_integration.py
scripts/tests/test_parallel_cli.py scripts/tests/test_issue_discovery.py`
should pass without fixture edits. Add stamps only if a fixture
surfaces a rejection in CI._

#### `feature_config = ParallelConfig(**default_parallel_config.to_dict(), "use_feature_branches": True)` pattern

_Wiring pass added by `/ll:wire-issue` — Agent 2 flagged
`scripts/tests/test_worker_pool.py:2201` which diffs `to_dict()` output
across two configs. With the new `epic_branches` field included in
`to_dict()`, this pattern will compare the full nested dict. Either
the test must explicitly set `epic_branches=` to both configs for
equality, or rely on `default_factory` producing equal defaults.
Verify during implementation; the natural fix is to ensure both
configs omit or both configs set `epic_branches` identically.


### Documentation
No doc updates in this child. ARCHITECTURE, API, CONFIGURATION, CLI,
and SPRINT_GUIDE updates are deferred to FEAT-2450.

#### Doc placeholders for FEAT-2450 (wiring-pass flagged)

_Wiring pass added by `/ll:wire-issue` — these files mention the
`parallel` config surface or `WorkerPool` and will need
`epic_branches.*` mentions in FEAT-2450 (Agent 2 findings — audit-only,
no edits in this child):_

- `docs/reference/CONFIGURATION.md:53-69, 338-361` — `parallel` JSON
  example + field-table; will need an `epic_branches.*` block.
- `docs/reference/API.md:251-278, 300-310, 447-491, 4365` —
  `create_parallel_config` signature/parameters/example + `ParallelConfig`
  class table; will need an `epic_branches` row.
- `docs/reference/COMMANDS.md:45` — `parallel` listed as config area.
- `docs/ARCHITECTURE.md:803` — `+create_parallel_config()` narrative
  (low-priority).
- `CONTRIBUTING.md:39` — `ll-parallel --help` snippet; may want to
  forward-reference `--epic-branches` (FEAT-2450).
- `docs/development/TROUBLESHOOTING.md:271, 698` — parallel config
  examples.
- `skills/configure/SKILL.md:14, 103, 136, 221` — `parallel` area
  registration table.
- `skills/configure/areas.md:184-269` — Round-2 question on
  `feature_branches` is the shape-mirror to copy for an epic-branches
  round.
- `skills/configure/show-output.md:38-56` — `--show parallel`
  output listing.
- `commands/describe-pr.md:3`, `commands/open-pr.md:48`,
  `commands/resume.md:185`, `commands/review-sprint.md` —
  `ll-parallel`/`ll-sprint` cross-refs.
- `CHANGELOG.md` — once shipped, an entry under the next
  released version (NOT `[Unreleased]`, per
  `feedback_changelog_no_unreleased.md` rule) following the
  `feat(parallel): ...` convention.

### Configuration
`config-schema.json` (additive — `parallel.epic_branches.*`) and
`.ll/ll-config.json` (opt-in `parallel.epic_branches.enabled: true`
when the user wants EPIC integration branches).

#### Template parity (Decision ARCHITECTURE-096)

_Wiring pass added by `/ll:wire-issue` — Decision
`ARCHITECTURE-096` (`.ll/decisions.yaml:3829-3843`) mandates stamping
`parallel.epic_branches: {enabled: false}` explicitly in all 9
project-type templates, matching the existing `use_feature_branches:
false` convention. NOTE: this contradicts the **Out of Scope**
deferral above (which assigns templates to FEAT-2450). Pick one of:

- **(A) Land the template stamps in this child (FEAT-2447) per the
  decision rule — 9 small mechanical edits.**
  > **Selected:** (A) — Decision ARCHITECTURE-096 (`scope: issue` tied to FEAT-2339) verbatim mandates the 9-template stamp; this reuses the existing `use_feature_branches` precedent (commit `795160cb`) across the same 9 files.
- (B) Land in FEAT-2450 with the rest of the TUI/configure surface —
  accepts that init/TUI parity will lag schema acceptance by one
  child._

The 9 templates (Agent 2 findings):

- `scripts/little_loops/templates/typescript.json:69-70`
- `scripts/little_loops/templates/python-generic.json:71-72`
- `scripts/little_loops/templates/javascript.json:71-72`
- `scripts/little_loops/templates/java-maven.json:64-65`
- `scripts/little_loops/templates/java-gradle.json:66-67`
- `scripts/little_loops/templates/rust.json:63-64`
- `scripts/little_loops/templates/go.json:64-65`
- `scripts/little_loops/templates/dotnet.json:67-68`
- `scripts/little_loops/templates/generic.json:39-40`

#### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-06.

**Selected**: (A) — Land the 9 project-type template stamps in this child (FEAT-2447).

**Reasoning**: Decision ARCHITECTURE-096 (`.ll/decisions.yaml:3829-3843`, `scope: issue` tied to FEAT-2339) explicitly mandates stamping `parallel.epic_branches: {enabled: false}` across all 9 project-type templates, and its `alternatives_rejected` field enumerates the "schema-default fallback" path that Option B takes — i.e., Option B isn't a parallel choice, it requires amending a binding decision. The same 9-template `use_feature_branches: false` stamp already exists (commit `795160cb`) and provides a direct, identical-shape precedent. Test-init parity (`test_init_core.py:707`) is non-blocking because `init/core.py:build_config()` never emits `parallel` from the no-choices baseline (verified at `init/core.py:104-121`); the 5 hardcoded `"parallel"` fixtures survive `additionalProperties: false` because the new key is not in any `required` array (verified at `config-schema.json:305-408`). The issue's "Out of Scope" deferral to FEAT-2450 is silently overruled by the `scope: issue` decision rule.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| (A) Land stamps in FEAT-2447 | 3/3 | 3/3 | 3/3 | 3/3 | **12/12** |
| (B) Defer to FEAT-2450 | 0/3 | 2/3 | 3/3 | 1/3 | **6/12** |

**Key evidence**:
- **(A)**: Decision ARCHITECTURE-096 (`scope: issue`, `alternatives_rejected`) mandates the stamp; identical 9-template `use_feature_branches` precedent already in repo (commit `795160cb`); non-blocking parity/fixture concerns (verified via `init/core.py:104-121` and `test_init_core.py:680-708`).
- **(B)**: Violates a binding architecture decision (`scope: issue`); `init/core.py:build_config()` ignores template `parallel` block, so deferring is technically feasible but provides no compensating benefit; creates a one-child cycle of init/TUI parity drift.

#### `init/core.py` schema-default parity guard

_Wiring pass added by `/ll:wire-issue` —_ `scripts/tests/test_init_core.py:707`
enforces schema-default ↔ `init/core.py` literal parity. Adding
`parallel.epic_branches` defaults to `config-schema.json` without
matching `init/core.py` literals (or vice-versa) will fail this guard.
Verify during implementation that the `init/core.build_config` defaults
include `parallel.epic_branches: {enabled: false}` (or are tolerant
of the absence — depends on whether the test is schema-strict).

#### `sample_config` fixture (`scripts/tests/conftest.py:284-296`)

_Wiring pass added by `/ll:wire-issue` —_ `sample_config["parallel"]`
exerts no new key (only `use_feature_branches` and friends), so with
`default_factory=EpicBranchesConfig()` semantics it will accept the
default and round-trip fine. No fixture change required **unless** the
schema's `additionalProperties: false` is strict on missing keys
(verify by running
`python -m pytest scripts/tests/test_config_schema.py` after the schema
edit).

## API/Interface

### Config schema (`config-schema.json` — `parallel.epic_branches`)

```json
{
  "epic_branches": {
    "type": "object",
    "description": "Per-EPIC integration branch configuration for ll-parallel/ll-sprint",
    "properties": {
      "enabled": { "type": "boolean", "default": false },
      "prefix": { "type": "string", "default": "epic/" },
      "merge_to_base_on_complete": { "type": "boolean", "default": true },
      "open_pr": { "type": "boolean", "default": false }
    }
  }
}
```

### Dataclass (`scripts/little_loops/parallel/types.py`)

```python
@dataclass
class EpicBranchesConfig:
    enabled: bool = False
    prefix: str = "epic/"
    merge_to_base_on_complete: bool = True
    open_pr: bool = False


@dataclass
class ParallelConfig:
    # ... existing fields ...
    epic_branches: EpicBranchesConfig = field(default_factory=EpicBranchesConfig)
```

### Resolver (`scripts/little_loops/parallel/worker_pool.py`)

```python
def _resolve_branch_targets(self, issue: IssueInfo) -> tuple[str, str]:
    """Return (fork_point, merge_target) for ``issue``.

    - epic-off (``self.parallel_config.epic_branches.enabled is False``)
      or parentless (``issue.parent is None``) → returns
      ``(base_branch, base_branch)`` — no-op, identical to today's
      behavior so ``merge_coordinator.py`` consumer sites are unchanged.
    - epic-on with an EPIC parent → returns
      ``(epic/<EPIC-ID>-<slug>, epic/<EPIC-ID>-<slug>)``, flattened to
      the nearest EPIC ancestor (cycle-guarded).
    - The branch is created lazily off ``base_branch`` on first call per
      ``epic_id``; subsequent calls are idempotent.
    """
```

### Public API impact
- **New**: `EpicBranchesConfig` dataclass (exported from
  `scripts/little_loops/parallel/__init__.py`).
- **New field**: `ParallelConfig.epic_branches` (default factory
  `EpicBranchesConfig()`, backward compatible).
- **New field**: `ParallelAutomationConfig.epic_branches` (default
  factory `EpicBranchesConfig()`, backward compatible).
- **New private method**: `WorkerPool._resolve_branch_targets()`
  (leading underscore — internal API, no public surface change).

## Impact

- **Priority**: P3 — enhancement with no current user-visible
  breakage; existing per-worker merge flow is functional, this adds
  a cohesion surface for EPICs. Frontmatter `priority: P3` and
  `outcome_confidence: 60` agree: bounded value, modest payoff.
- **Effort**: Medium — 4 implementation files + 4 test files, but
  each change is localized (single field addition, single private
  method, single schema block). `score_complexity: 6` per
  frontmatter. Reuses existing patterns (`ConfidenceGateConfig`,
  `_issue_descends_to()`, `_make_issue()`), so no green-field design.
- **Risk**: Low — default OFF (`enabled: false`); parentless or
  epic-off paths are explicit no-op returns; no consumer site in
  `merge_coordinator.py` is touched until FEAT-2448.
  `score_change_surface: 0` per frontmatter (additive only).
- **Breaking Change**: No — additive config key, additive dataclass
  field with safe defaults, additive private method.


## Blocks

- FEAT-2448

## Status

**Open** | Created: 2026-07-02 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-06_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- **Open decision: Option A vs B template parity (wiring step 7)** — the issue body defers templates to FEAT-2450, but Decision `ARCHITECTURE-096` (`.ll/decisions.yaml:3829-3843`) mandates stamping `parallel.epic_branches: {enabled: false}` across all 9 project-type templates. Resolve before implementation: pick (A) land 9 mechanical template stamps in this child, or (B) explicitly amend ARCHITECTURE-096 to defer to FEAT-2450. Choosing one eliminates the surface ambiguity and unblocks implementation.
- **Verify during implementation: 5 hardcoded `"parallel"` test fixtures** — `scripts/tests/conftest.py:284`, `scripts/tests/test_cli.py:479`, `scripts/tests/test_cli.py:1642`, `scripts/tests/test_cli_e2e.py:105`, `scripts/tests/test_issue_workflow_integration.py:197` may each need `"epic_branches": {"enabled": false}` appended if `config-schema.json`'s `additionalProperties: false` is strict on missing keys. Run the affected test files after the schema edit to confirm.
- **Verify during implementation: `test_init_core.py:707` schema-default ↔ `init/core.py:build_config()` parity guard** — adding `parallel.epic_branches` defaults to `config-schema.json` without matching `init/core.py` literal defaults (or vice versa) fails this guard. Confirm parity after the schema/dataclass edits.
- **Verify during implementation: `feature_config = ParallelConfig(**default_parallel_config.to_dict(), "use_feature_branches": True)` at `scripts/tests/test_worker_pool.py:2201`** — once `to_dict()` includes `epic_branches`, the comparison diffs the full nested dict. Both configs use `default_factory` so default values should be equal; confirm with a test run.

## Session Log
- `/ll:wire-issue` - 2026-07-07T04:41:11 - `08c3c392-5522-400b-a7aa-43391d6f41ee.jsonl`
- `/ll:refine-issue` - 2026-07-07T04:36:04 - `95f88292-612e-4892-933e-81358f655580.jsonl`
- `/ll:decide-issue` - 2026-07-07T04:22:00 - `8f30824a-c88d-4846-8634-8ea4b2ddbbb7.jsonl`
- `/ll:confidence-check` - 2026-07-06 - `b148c016-4bc6-4a95-b7d6-210fceb04d5a.jsonl`
- `/ll:confidence-check` - 2026-07-06 - `d9ef45e8-703c-4197-81b7-c23a28a9cee7.jsonl`
- `/ll:verify-issues` - 2026-07-07T04:08:53 - `d7a68ca8-d2b9-42d9-9ec1-b78d0c5c5841.jsonl`
- `/ll:wire-issue` - 2026-07-06T23:09:05 - `21cbc8bc-ce15-4912-bb93-e3574c91e49c.jsonl`
- `/ll:refine-issue` - 2026-07-06T19:14:35 - `a621374e-67ee-4d36-8474-5106e009ded9.jsonl`
- `/ll:format-issue` - 2026-07-03T02:25:51 - `4b4fed19-776f-4701-9732-113c091c2f49.jsonl`
- `/ll:issue-size-review` - 2026-07-02T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6e2b9d4e-1bf7-4b43-940f-7c8cc95fcaf4.jsonl`