---
id: BUG-2766
title: Legacy .issues/completed/ directory kept being recreated by recursive-refine, issue-staleness-review, and manage-issue guidance
type: BUG
status: done
priority: P2
captured_at: '2026-07-24T19:50:16Z'
completed_at: '2026-07-24T19:50:16Z'
discovered_date: '2026-07-24'
discovered_by: session-audit
labels:
- issues
- loops
- skills
relates_to:
- BUG-2732
- ENH-2615
- ENH-1418
---

# BUG-2766: Legacy `.issues/completed/` directory kept being recreated by recursive-refine, issue-staleness-review, and manage-issue guidance

## Summary

Despite the ENH-1418 in-place-close convention (status lives only in frontmatter;
issues never leave their type directory), the legacy `.issues/completed/`
directory kept reappearing after being deleted. Its presence is an active
footgun: grep-based consumers (subagents, scripts, humans) infer "not in
completed/ → open", which caused six `done` issues to be misreported as open
backlog during an audit this session.

autodev was suspected but is innocent — it already closes decomposed parents in
place via `ll-issues finalize-decomposition` (BUG-2732/ENH-2615), and the CLI's
`--move` flag defaults off.

## Root Cause

Three recreators were found:

1. **`scripts/little_loops/loops/recursive-refine.yaml`** (mechanical, primary):
   both decomposition sites (`enqueue_children`, `enqueue_or_skip` children-found
   branch) ran `mkdir -p .issues/completed && git mv "$PARENT_FILE"
   .issues/completed/`. Since rn-* loops wrap recursive-refine, every
   decomposition recreated the directory.
2. **`scripts/little_loops/loops/issue-staleness-review.yaml`** (LLM-driven):
   the `close_issue` prompt instructed "Move the reviewed stale issue to
   .issues/completed/".
3. **`skills/manage-issue/SKILL.md`** (latent, LLM-driven): the "Directory
   Structure" section still taught `completed/`/`deferred/` as sibling homes for
   closed issues ("ALL completed issues go here"), contradicting the skill's own
   completion step (~line 448) that forbids the move. Every autodev/ll-auto
   session read that contradiction.

## Fix

- `recursive-refine.yaml`: both sites replaced with
  `ll-issues finalize-decomposition "${captured.input.output}"` (same in-place
  close autodev/rn-decompose use), with a WARN fallback on failure.
- `issue-staleness-review.yaml`: `close_issue` prompt rewritten to set
  `status: cancelled`/`done` in place via `ll-issues set-status`, with an
  explicit "do NOT move the file" instruction.
- `skills/manage-issue/SKILL.md`: directory-structure section rewritten to the
  frontmatter-only lifecycle (no `completed/`/`deferred/` in the diagram);
  removed the `completed_dir` config reference; fixed stale "Before moving the
  issue file" phrasing.
- `skills/manage-issue/templates.md`: `defer`/`undefer` actions now described as
  in-place `ll-issues set-status` transitions, not file moves.
- `scripts/tests/test_builtin_loops.py`: the two tests that *pinned* the old
  move behavior (`test_enqueue_children_moves_parent_to_completed`,
  `test_enqueue_or_skip_moves_parent_to_completed_when_children_found`) were
  inverted to `test_enqueue_children_closes_parent_in_place` /
  `test_enqueue_or_skip_closes_parent_in_place_when_children_found` — they now
  assert `finalize-decomposition` is present and `.issues/completed` is absent,
  so a regression fails the suite.
- The empty `.issues/completed/` directory itself was already absent by fix
  time (untracked empty dir).

## Verification

- `python -m pytest scripts/tests/test_builtin_loops.py` — 1257 passed.
- `ll-loop validate recursive-refine` / `ll-loop validate issue-staleness-review`
  — valid, no ERRORs (pre-existing MR-10/MR-8 warnings in untouched states).

## Left Alone Deliberately

- Read-only `.issues/completed/` references that tolerate absence:
  `backlog-flow-optimizer.yaml` exclusion filter, `examples-miner.yaml`,
  `audit-docs` repair example, `ll-issues show/search` legacy-dir readers
  (BUG-2733 compat).
- Deprecated opt-ins nothing invokes: `issues.completed_dir` config key,
  `ll-issues finalize-decomposition --move`.

## Known Caveat / Follow-up

`auto-refine-and-implement.yaml` still uses a `.issues/completed/` diff as one
of its decomposed-umbrella detection signals (lines ~77–83, ~717–723). It
degrades gracefully (`2>/dev/null` guards) but that detection path is now
permanently empty; if the loop remains in active use it should migrate to a
frontmatter-based signal (e.g. `status: done` + decomposition note).

## Context

Found while auditing the `ll-init` first-run UX: a docs-audit subagent inferred
issue status from directory location and misreported six `done` init-related
issues as open. The frontmatter-only rule is now also recorded as an agent
memory (feedback-issue-status-frontmatter-only).


## Session Log
- `hook:posttooluse-status-done` - 2026-07-24T19:50:46 - `5b6de21b-a6ae-4d0e-8f5a-bd43dda17977.jsonl`
