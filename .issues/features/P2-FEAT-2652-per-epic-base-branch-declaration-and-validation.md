---
discovered_commit: 6f81ca029f3c40a05520d5f1d8536fdd0a8723cc
discovered_branch: main
discovered_date: 2026-07-15T00:00:00Z
discovered_by: capture-issue
status: open
relates_to: [ENH-2653, BUG-2651]
labels: [epic-branches, parallel, worktree, sprint]
---

# FEAT-2652: Per-EPIC base-branch declaration + sprint-creation validation

## Summary

An EPIC integration branch is **always** forked from the global
`parallel.base_branch` (default `main`). There is no way for an EPIC whose child
issues reference symbols living on an unmerged feature branch (e.g.
`refactor/tableau-third-revision`) to declare that branch as its base. When such
an EPIC is sprinted from the wrong base, every child that cites the not-yet-merged
symbols fails readiness *correctly-but-misleadingly* — the symbols really are
absent from the worktree, but they exist exactly where the EPIC intends them.
The loop then degrades silently to `verdict: partial` and holds the epic merge
open, with no signal the base was wrong.

Add an optional `base_branch:` / `target_branch:` frontmatter field to EPIC
issues, teach worktree creation to honor it, and validate at sprint-creation time
that the declared base exists (and, ideally, that the EPIC's cited symbols
resolve there) — refusing to dispatch a wrong-base EPIC rather than letting it
degrade to `partial`.

## Current Behavior

- `worker_pool.py:_ensure_epic_branch()` (~line 1739) hardcodes the fork point:

  ```python
  self._git_lock.run(
      ["branch", branch, self.parallel_config.base_branch],
      cwd=self.repo_path, timeout=30,
  )
  ```

- `_resolve_branch_targets()` returns either `parallel.base_branch` (standalone)
  or `epic/<EPIC-ID>-<slug>` (EPIC child) — and the EPIC branch itself was created
  off `parallel.base_branch`. No per-EPIC override anywhere in the call chain.
- `config-schema.json` exposes `parallel.base_branch` as a **global** setting only.
- The EPIC template (`epic-sections.json`) declares Goal / Scope / Children /
  Success Metrics plus common sections — **no branch field**.
- `epic_branches.verify_before_merge: true` only enforces the *merge-time*
  contract (lint/coverage on the EPIC branch before merge-back); it does **not**
  check the *sprint-creation-time* contract "does the child content exist on the
  branch this EPIC was sprinted against?"

Result: an EPIC created while the user is on `main` (or whenever the sprint logic
picks `main`) produces a worktree lacking any unmerged-branch symbols, and the
false readiness rejections are only visible in the per-issue verifier transcript.

## Expected Behavior

- An EPIC may declare its intended base, e.g.:

  ```yaml
  base_branch: refactor/tableau-third-revision
  ```

- `_ensure_epic_branch()` forks the EPIC integration branch from the EPIC's
  declared `base_branch` when present, falling back to `parallel.base_branch`
  when absent (fully backward-compatible — no field means today's behavior).
- Sprint creation (`sprint-refine-and-implement` → `auto-refine-and-implement`
  path, i.e. the orchestrator/WorkerPool that reads the EPIC) **validates** the
  declared base:
  - the ref exists (local or remote); if not, refuse to dispatch with a clear
    error naming the missing branch.
  - optionally, spot-check that a sample of the EPIC's children's cited symbols
    resolve on that base (via `git show <base>:<file>`); if the base is clearly
    wrong, abort rather than emit a run-full of false `NOT_READY`s and finish
    `partial`.
- Escalation: a wrong-base condition should be a **hard stop**, not folded into a
  soft `partial`. (Absorbs the "partial masks a false NOT_READY" side-finding —
  the mismatch was noticed and classified as a `concern`, then swallowed.)

## Use Case

A developer is iterating a large redesign on a long-lived feature branch
(`refactor/tableau-third-revision`) that has not yet merged to `main`. They scope
an EPIC whose child issues cite symbols introduced by that redesign, then run
`sprint-refine-and-implement`. Today, if the sprint is created off `main`, every
redesign-referencing child is falsely rejected as `NOT_READY` and the run ends
`partial` with the epic merge held open. With this feature, the EPIC declares
`base_branch: refactor/tableau-third-revision`; the worktree forks from the right
tree, children reach `READY`, and a genuinely wrong/missing base is rejected up
front with a clear error instead of a silent degrade.

## Acceptance Criteria

- [ ] EPIC issues accept an optional `base_branch:` (alias `target_branch:`)
      frontmatter field, documented in the EPIC section schema.
- [ ] When an EPIC declares `base_branch`, its integration branch is forked from
      that ref; when absent, it forks from `parallel.base_branch` (unchanged
      today's behavior — verified by test).
- [ ] Sprint dispatch validates that a declared base ref exists (local or
      remote); a missing ref aborts dispatch with an error naming the branch, and
      does **not** produce a `partial` verdict.
- [ ] A wrong-base condition is surfaced as a hard stop, not folded into a soft
      `partial`.
- [ ] Tests cover: valid declared base forks correctly; missing base ref aborts;
      no field preserves `parallel.base_branch` behavior.

## Implementation Steps

1. Add `base_branch` (alias `target_branch`) to the EPIC section schema
   (`epic-sections.json`) as an optional frontmatter field; document it.
2. Thread the EPIC's declared base into `WorkerPool._ensure_epic_branch()` /
   `_resolve_branch_targets()`; fall back to `parallel.base_branch` when unset.
3. Add a validation step at sprint dispatch: assert the declared base ref exists;
   optionally sample-check cited symbols via `git show <base>:<file>`.
4. On validation failure, abort the dispatch (hard error), do not degrade to
   `partial`.
5. Tests: EPIC with a valid declared base forks from it; EPIC with a missing
   base ref aborts; EPIC with no field preserves current `parallel.base_branch`
   behavior.

## Integration Map

- `scripts/little_loops/parallel/worker_pool.py` — `_ensure_epic_branch()`,
  `_resolve_branch_targets()`
- `scripts/little_loops/parallel/orchestrator.py` — EPIC-aware base resolution
  (already switches comparison base for EPIC children, FEAT-2562)
- `scripts/little_loops/templates/.../epic-sections.json` — new field
- `config-schema.json` — document interaction with global `parallel.base_branch`
- Pairs with ENH-2653 (`ready-issue` should also learn the target branch so its
  symbol checks run against the right tree).

## Impact

High. This is the root cause of the wrong-base false-negative class. Without it,
any EPIC whose children reference unmerged-branch symbols will keep silently
degrading to `partial` and holding merges open, and the only diagnosis path is
reading per-issue transcripts. Backward-compatible (opt-in field).

## Status

open — captured from consumer-project run findings. Root-cause fix; pairs with
ENH-2653 (guardrail) and BUG-2651 (independent triage bug surfaced in same run).
