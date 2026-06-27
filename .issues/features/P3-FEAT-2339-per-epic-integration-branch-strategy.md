---
id: FEAT-2339
title: Per-EPIC integration branch strategy for ll-parallel/ll-sprint
type: FEAT
priority: P3
status: open
captured_at: "2026-06-27T02:49:31Z"
discovered_date: 2026-06-27
discovered_by: capture-issue
labels: [parallel, sprint, epics, git, worktree]
relates_to: [ENH-665, BUG-2323, ENH-2176, FEAT-1737]
---

# FEAT-2339: Per-EPIC integration branch strategy for ll-parallel/ll-sprint

## Summary

little-loops currently has **no epic-awareness in its branching model**. When
ll-parallel (or ll-sprint resolving an EPIC into children) processes the children
of an EPIC, each child issue gets its own per-issue branch
(`feature/<id>-<slug>` or `parallel/<id>-<timestamp>`), forks off the single
global `base_branch` (default `main`), and merges back into `base_branch`
independently.

This FEAT proposes an opt-in **per-EPIC integration branch** strategy: when
processing children of an EPIC, create an integration branch (e.g.
`epic/EPIC-1389-<slug>`) off the base branch; each child forks from and merges
**into the epic branch** rather than `main`; the epic branch lands on `main` as a
single unit (or one PR) when the EPIC is complete.

## Current Behavior

- Branch names are derived per-issue only — `parallel/worker_pool.py:334-339`:
  ```python
  if self.parallel_config.use_feature_branches:
      branch_name = f"feature/{issue.issue_id.lower()}-{slugify(issue.title)}"
  else:
      branch_name = f"parallel/{issue.issue_id.lower()}-{timestamp}"
  ```
- `base_branch` is a single global value (`parallel/types.py:382`, default
  `"main"`) used as **both** the fork point and the merge target for every
  issue — `merge_coordinator.py:624,875`.
- No code in `parallel/` or `sprint.py` reads `issue.parent` / EPIC identity to
  influence branching or merge targets. `ll-sprint` *can* resolve an `EPIC-NNN`
  argument into an ephemeral sprint of its children (`sprint.py:287`), but those
  children still branch and merge per-issue.
- Net effect: sibling children of one EPIC each fork stale `main` and never see
  each other's work until it lands on `main`; an EPIC is delivered to `main` as
  N independent merges, never atomically.

## Expected Behavior

- A configurable branch strategy that, when an issue has an EPIC parent (or a
  run is scoped to an EPIC), routes the child's fork point and merge target to a
  shared per-EPIC integration branch instead of `base_branch`.
- The integration branch is created lazily (first child of the EPIC) off
  `base_branch`, reused by all subsequent children, and merged to `base_branch`
  as a single unit on EPIC completion (or surfaced as one PR when
  `open_pr_for_feature_branches` is enabled).
- Standalone (parentless) issues retain today's behavior unchanged.
- Default OFF — existing per-issue behavior is preserved unless explicitly
  enabled.

## Motivation

little-loops is heavily epic-oriented (`/ll:scope-epic`, `/ll:review-epic`,
`ll-issues epic-progress`, EPIC cascade closure, EPIC-as-sprint resolution).
Branching is the one orchestration surface that ignores EPICs entirely. A
per-EPIC branch unlocks workflow value that maps directly to how the project
already organizes work:

- **Atomic delivery** — `main` never carries a half-finished EPIC; the EPIC lands
  (or is reverted) as one coherent unit.
- **One PR per EPIC** for review instead of N noisy per-child PRs.
- **Intra-EPIC dependencies work** — children build on each other inside the
  integration branch instead of each forking stale `main` (today a child can't
  see a sibling's not-yet-merged change).

## Proposed Solution

Introduce a branch-strategy concept with three modes; epic mode is the new one:

- `per_issue` (today's default) — fork from / merge to `base_branch`.
- `per_epic` — children of an EPIC share `epic/<EPIC-ID>-<slug>`; EPIC branch
  merges to `base_branch` on completion.

Add config under the existing `parallel` namespace (or a new `epics.branch`
sub-object — see Edge Cases). Sketch:

```jsonc
"parallel": {
  "epic_branches": {
    "enabled": false,            // master switch for per-EPIC integration branches
    "prefix": "epic/",           // branch name prefix
    "merge_to_base_on_complete": true,  // auto-merge epic branch to base_branch when EPIC done
    "open_pr": false             // open one PR for the epic branch instead of auto-merge
  }
}
```

Key implementation insight — **the worktree plumbing is half-built already**:
`worker_pool.create_worktree(..., base_branch=...)` (`worker_pool.py:648`)
already accepts a per-call base/fork-point. The gap is on the merge side:
`merge_coordinator` hardcodes `self.config.base_branch` as the target
(`merge_coordinator.py:624,875`). The core change is making the *target* a
function of the issue's EPIC parent, not a global constant.

EPIC-completion detection should lean on `ll-issues epic-progress`. ⚠️ Note:
epic-progress counts only **direct** `parent:` children (non-recursive) — a
sub-EPIC's grandchildren will not roll up automatically, so nested EPICs need an
explicit decision (treat each EPIC level as its own branch, or flatten).

## Integration Map

- `scripts/little_loops/parallel/worker_pool.py` — branch-name derivation
  (`:334-339`) and `create_worktree` fork point (`:648`); resolve epic branch +
  fork point per issue.
- `scripts/little_loops/parallel/merge_coordinator.py` — merge target
  (`:624,875`); route to epic branch instead of `base_branch`; add epic-branch →
  base merge on completion.
- `scripts/little_loops/parallel/types.py` — `base_branch` field (`:382`) and
  `BrConfig`/parallel config (de)serialization (`:463,509`); add
  `epic_branches` config.
- `scripts/little_loops/parallel/orchestrator.py` — run scoping; rev-list/diff
  comparisons currently against `base_branch` (`:400,1122`) must be
  epic-branch-aware.
- `scripts/little_loops/sprint.py` — EPIC→children resolution (`:287`) is the
  natural place to flag a run as epic-scoped.
- `scripts/little_loops/init/tui.py` — surface the new flag in `ll-init`
  alongside `use_feature_branches` (`:343,378,664`).
- `config-schema.json` — add `parallel.epic_branches` (or `epics.branch`) block.
- Lifecycle: who creates/deletes the epic branch and when it merges to base —
  align with `worker_pool.py:736-744` branch-cleanup (currently only deletes
  `parallel/`-prefixed branches).

## Implementation Steps

1. Add `parallel.epic_branches` config to `config-schema.json` + parallel config
   dataclass in `types.py` (with (de)serialization round-trip).
2. Add a resolver: `issue → (fork_point, merge_target)` that returns the epic
   integration branch when `epic_branches.enabled` and the issue has an EPIC
   parent; otherwise `base_branch`.
3. Wire the resolver into `worker_pool` branch derivation + `create_worktree`
   fork point.
4. Wire the resolver into `merge_coordinator` merge target; lazily create the
   epic branch on first child.
5. Add EPIC-completion → epic-branch-merges-to-base step (or one-PR), gated on
   `merge_to_base_on_complete` / `open_pr`, using `ll-issues epic-progress`.
6. Make orchestrator rev-list/diff comparisons epic-branch-aware.
7. Surface the flag in `ll-init`/`/ll:configure`.
8. Tests: per-EPIC fork/merge routing, standalone-issue regression (unchanged),
   nested-EPIC behavior, completion-merge, PR-mode.
9. Docs: ARCHITECTURE parallel section + API reference.

## Use Case

A developer runs `ll-sprint EPIC-1389` to implement a 6-child EPIC. With
`epic_branches.enabled`, ll-parallel creates `epic/EPIC-1389-add-epic-type` off
`main`, processes the 6 children into worktrees that fork from and merge into the
epic branch, and on completion opens a single PR (or merges) `epic/EPIC-1389-…`
→ `main`. The reviewer sees one cohesive PR; `main` only ever gains the complete
EPIC, never a partial one.

## API/Interface

New config (additive, default-off, backward compatible):
`parallel.epic_branches.{enabled, prefix, merge_to_base_on_complete, open_pr}`
(exact placement — `parallel.*` vs new `epics.branch.*` — to be decided in
design; see Edge Cases). No breaking changes to existing `parallel.*` keys.

## Acceptance Criteria

- [ ] With `epic_branches.enabled: false` (default), branching/merge behavior is
      byte-for-byte identical to today (regression-tested).
- [ ] With it enabled, children of an EPIC fork from and merge into a single
      `epic/<EPIC-ID>-<slug>` branch; standalone issues still use `base_branch`.
- [ ] The epic integration branch is created once (first child) and reused.
- [ ] On EPIC completion, the epic branch merges to `base_branch` (or one PR is
      opened) per config.
- [ ] Nested-EPIC behavior is explicitly defined and tested.
- [ ] Config is documented in `config-schema.json`, ARCHITECTURE, and surfaced in
      `ll-init`/`/ll:configure`.

## Edge Cases

- **Config placement**: `parallel.epic_branches.*` keeps it near other
  worktree/branch knobs; `epics.branch.*` groups it with EPIC lifecycle. Decide
  in design.
- **Nested EPICs**: epic-progress is non-recursive — define whether each EPIC
  level gets its own branch or grandchildren flatten to the nearest EPIC.
- **Interaction with `use_feature_branches`**: epic mode supersedes per-issue
  feature branches for EPIC children; document precedence.
- **Reduced intra-EPIC parallelism**: children sharing one branch serialize more
  and concentrate merge conflicts on the epic branch — acceptable trade for
  atomicity but should be noted.
- **Partial failure**: if some children fail, the epic branch holds partial work
  — define whether completion-merge is blocked until all children are `done`.
- **`p0_sequential` / `base_branch` auto-detection** (BUG-2323) interplay.

## Impact

- **Scope**: Concentrated in `parallel/` (worker_pool, merge_coordinator, types,
  orchestrator) + `sprint.py` + `config-schema.json` + init/configure surfaces +
  tests/docs. Medium effort.
- **Risk**: Touches merge ordering and EPIC-completion semantics; the design
  (config placement, nested EPICs, partial-failure policy) should be written
  before implementation.
- **Backward compatibility**: Additive and default-off; no behavior change unless
  explicitly enabled.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | System design — parallel/worktree orchestration model that this feature extends |
| `docs/reference/API.md` | Python module reference for `little_loops.parallel.*` (worker_pool, merge_coordinator, types) |
| `.claude/CLAUDE.md` | Issue/EPIC conventions and parent/relates_to relationship rules |

## Session Log
- `/ll:format-issue` - 2026-06-27T02:52:25 - `7437556a-9bbe-47ca-9369-c97d741aff8f.jsonl`
- `/ll:capture-issue` - 2026-06-27T02:49:31Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c8ee06c-d91e-40b3-b5a3-a8f24925b3b7.jsonl`

---

## Status

- **Current**: open
- **Created**: 2026-06-27
