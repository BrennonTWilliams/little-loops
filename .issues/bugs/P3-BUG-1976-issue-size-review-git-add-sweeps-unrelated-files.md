---
id: BUG-1976
title: 'issue-size-review: final ''git add .issues/'' stages entire issues dir, sweeping
  unrelated untracked/modified files'
type: BUG
priority: P3
status: done
captured_at: '2026-06-06T00:00:00Z'
completed_at: '2026-06-06T04:26:24Z'
discovered_date: '2026-06-06'
discovered_by: audit-loop-run
relates_to:
- BUG-1800
- BUG-1975
labels:
- issue-size-review
- commit-hygiene
- skill-defect
confidence_score: 96
outcome_confidence: 82
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 22
---

# BUG-1976: issue-size-review stages the whole .issues/ dir, sweeping in unrelated files

> **Coordination (2026-06-06):** Independent of **ENH-1977** — ship standalone. ENH-1977's Fix 4 edits
> the same skill (`issue-size-review/SKILL.md`) but only to emit the `Decomposed from <parent>` marker;
> it does **not** touch the blanket `git add` line. Same file, different line, different behavior — no
> overlap and no sequencing constraint. Fix this whenever; it does not gate or get absorbed by ENH-1977.

## Summary

`skills/issue-size-review/SKILL.md` ends with a "Stage all changes" step that runs
`git add {{config.issues.base_dir}}/`. This recursively stages every untracked and modified file
under `.issues/`, not just the issue file the review actually touched. Any pre-existing
working-tree changes (recently captured drafts, edits from a concurrent skill) get swept into the
stage.

This is the same defect class as BUG-1800 (which fixed the identical over-broad `git add` in
`audit-issue-conflicts` Phase 5); BUG-1800 was scoped to that one skill, so `issue-size-review` is
still affected. It was surfaced indirectly in rn-implement run `2026-06-06T015949`: during
FEAT-1713's decomposition, the `run_size_review` LLM judge returned `partial` specifically because
the size review had staged pre-existing unrelated working-tree changes alongside its `size`
frontmatter update (see BUG-1975 for the routing fallout).

## Current Behavior

`skills/issue-size-review/SKILL.md` (final "Stage all changes" step):

```bash
git add {{config.issues.base_dir}}/
```

This stages all files under `.issues/`, including untracked/modified files the skill never touched.
(Note: the earlier per-issue stage at `skills/issue-size-review/SKILL.md:173`,
`git add "<issue-file-path>"`, is correctly scoped — only the final blanket stage is the problem.)

## Expected Behavior

The skill should stage only the issue file(s) it actually modified during the review — i.e., stage
each reviewed issue's path explicitly (as line 173 already does), not the whole base dir. After the
skill runs, `git status` should show only review-modified files staged.

## Steps to Reproduce

1. Have one or more untracked or unrelated-modified files under `.issues/` (e.g., a recently
   captured but uncommitted issue).
2. Run `/ll:issue-size-review <ID> --auto` (or via `rn-decompose`'s `run_size_review` state).
3. `git status` after the final stage shows the unrelated files staged (`A`/`M`) alongside the
   review's `size` frontmatter edit.

Observed indirectly in run `2026-06-06T015949`: the `run_size_review` evaluator returned `partial`
(confidence 0.82) because unrelated working-tree changes had been staged with the size update.

## Root Cause

- **File**: `skills/issue-size-review/SKILL.md`
- **Anchor**: final "Stage all changes" step (`git add {{config.issues.base_dir}}/`)
- **Cause**: A directory-level `git add` recursively stages everything under `.issues/`, including
  files outside the skill's change set. Same root cause as BUG-1800.

## Proposed Solution

Stage only the reviewed issue file(s) explicitly, mirroring the per-issue stage already at line 173:

```bash
# instead of: git add {{config.issues.base_dir}}/
git add "<each reviewed issue-file-path>"
```

If multiple issues are reviewed in one run, accumulate their paths and stage them individually rather
than staging the directory.

## Implementation Steps

1. Replace the blanket `git add {{config.issues.base_dir}}/` in `skills/issue-size-review/SKILL.md`
   with an explicit stage of only the reviewed issue file path(s).
2. Grep the rest of the skill set for the same anti-pattern
   (`git add {{config.issues.base_dir}}/` / `git add .issues/`) and file/fix any further instances —
   this may be a recurring pattern beyond BUG-1800 and this issue.
3. Verify: with an unrelated untracked file under `.issues/`, run the skill and confirm `git status`
   stages only the reviewed file.

## Impact

- **Priority**: P3 — commit-hygiene defect; surprises users and can pollute commits with draft issues,
  but no data loss or functional regression.
- **Effort**: Small — change one stage command in the skill.
- **Risk**: Low — narrows what is staged; does not change review logic.
- **Breaking Change**: No
- **Severity**: LOW–MEDIUM — pollutes commits and (via BUG-1975) can trigger spurious `partial`
  verdicts that skip decomposition.
- **Blast radius**: Every `issue-size-review` run with any pre-existing uncommitted change under
  `.issues/`, including all `rn-decompose` invocations.

## Resolution

- **Status**: Fixed
- **Completed**: 2026-06-06
- **Fix**: Replaced the blanket `git add {{config.issues.base_dir}}/` final stage in
  `skills/issue-size-review/SKILL.md` Phase 6 with explicit per-file staging (parent + each
  created child), mirroring the already-correct per-issue stage at line 173.
- **Anti-pattern sweep (Implementation Step 2)**: The same over-broad directory stage was
  found in six other harness artifacts and fixed in the same change rather than re-filed,
  since each was the identical trivial, low-risk defect:
  - `skills/debug-loop-run/SKILL.md` — explicit per-file stage of written issue files.
  - `skills/audit-docs/SKILL.md` — explicit stage of created/updated/reopened files.
  - `skills/audit-loop-run/SKILL.md` — explicit per-file stage of written proposals.
  - `commands/audit-architecture.md` — explicit stage of created/updated/reopened files.
  - `commands/tradeoff-review-issues.md` — explicit stage of modified/moved files.
  - `commands/find-dead-code.md` — explicit stage of written files (was a `.issues/enhancements/` subdir stage).
  - `skills/map-dependencies/SKILL.md` — special case: `ll-deps fix` rewrites backlinks
    across an open-ended set of *tracked* files, so narrowed to `git add -u <base_dir>/`
    (stage tracked modifications only; still avoids sweeping untracked drafts).
- **Verification**: `ll-verify-skills` passes (all SKILL.md within 500-line cap); no test
  asserts on the removed `git add .issues/` text. No Python changed — these are skill/command
  prose edits.

## Status

**Done** | Created: 2026-06-06 | Completed: 2026-06-06 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-06T04:23:21 - `e6c8c5c1-52dd-4095-af4d-e3b97689557e.jsonl`
- `/ll:capture-issue` - 2026-06-06 - from rn-implement-audit-2026-06-06.md (run 2026-06-06T015949, F3 root cause); clone of BUG-1800
- `/ll:manage-issue` - 2026-06-06T04:26:24 - `203547b0-824c-44a4-bb3a-b10dcd98b759.jsonl`
