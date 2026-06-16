---
id: ENH-2177
title: Document the feature-branch workflow end-to-end and add an integration test
type: ENH
status: done
priority: P4
parent: EPIC-2171
captured_at: '2026-06-15T17:30:00Z'
completed_at: '2026-06-16T20:16:27Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels:
- parallel
- feature-branches
- docs
- testing
- workflow
relates_to:
- BUG-2172
- ENH-2173
- ENH-2175
blocked_by:
- BUG-2172
- ENH-2173
- ENH-2175
- ENH-2176
- ENH-2182
confidence_score: 100
outcome_confidence: 87
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2177: Document the feature-branch workflow end-to-end and add an integration test

## Summary

EPIC-2171's Definition of Done says "Schema/docs describe the actual behavior,"
but only schema text (config-schema.json) is assigned anywhere across the
children. The narrative guides that already document the parallel/sprint workflow
get no update, and no test exercises the full toggle→branch→push→PR→frontmatter
chain end-to-end — each child only tests its own slice. This issue owns the prose
docs and the integration test that tie the EPIC together.

## Current Behavior

`docs/guides/SPRINT_GUIDE.md`, `docs/reference/CLI.md`, and
`docs/reference/CONFIGURATION.md` document the parallel workflow but contain no
end-to-end narrative for the feature-branch / PR-based workflow: the push/PR
sub-flags, the `gh` precondition, the `--feature-branches` CLI override, the
`branch:`/`pr_url:` frontmatter written by ENH-2175, or the single-issue-wave
coverage boundary from ENH-2176. No integration test exercises the full
toggle→branch→push→frontmatter chain composed across the EPIC's children — each
child only tests its own slice.

## Expected Behavior

After this issue lands, the three guide files together describe the complete
feature-branch workflow end-to-end, and one integration test asserts that the
toggle→branch→push→frontmatter chain composes correctly (with push/PR
shelled-out calls mocked). The EPIC's Definition of Done ("docs describe the
actual behavior") is satisfied, and the integration seam between BUG-2172 and
ENH-2175 is guarded against regressions.

## Motivation

- **Docs**: `ENH-2174` covers *discovery surfaces* (configure / init / templates)
  only. The prose workflow guides — `docs/guides/SPRINT_GUIDE.md`,
  `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md` — already document
  the parallel workflow and currently have no end-to-end story for the
  feature-branch / PR-based workflow (when to use it, the push/PR sub-flags from
  BUG-2172, the `gh` precondition, the `--feature-branches` CLI override from
  ENH-2173, the `branch:`/`pr_url:` frontmatter from ENH-2175, and the coverage
  boundary from ENH-2176).
- **Test**: BUG-2172 tests push args, ENH-2173 tests config resolution, ENH-2175
  tests the frontmatter write — but nothing asserts they compose. The seam
  between BUG-2172 (produces a pushed branch / PR URL) and ENH-2175 (records it,
  hands off to `/ll:open-pr`) is exactly where regressions will hide.

## Proposed Solution

1. **Docs**: add an end-to-end "Feature-branch / PR-based workflow" section to
   `docs/guides/SPRINT_GUIDE.md` (and cross-link from `CLI.md` /
   `CONFIGURATION.md`) covering: enabling via config or `--feature-branches`, the
   push/PR sub-flags and their defaults, the `gh` requirement, what gets recorded
   to the issue, and the single-issue-wave coverage boundary (ENH-2176).
2. **Test**: add one integration test that, with the flag enabled, runs a
   parallel (multi-issue) wave through a temp git repo and asserts the full
   chain: feature branch created → (push invoked with correct remote/branch,
   mocked) → branch (and `pr_url:` if PR enabled) written to issue frontmatter →
   `/ll:open-pr` would consume the recorded branch.

## Acceptance Criteria

1. `docs/guides/SPRINT_GUIDE.md` documents the feature-branch/PR workflow
   end-to-end with text matching the *implemented* behavior (no overstated
   "PR-ready" claims; coordinate with BUG-2172's final wording).
2. `docs/reference/CLI.md` and `docs/reference/CONFIGURATION.md` reference the
   `--feature-branches` flag and the parallel feature-branch sub-flags.
3. An integration test asserts the composed toggle→branch→push→frontmatter chain
   (push/PR shelled-out calls mocked) and passes in CI.
4. `ll-verify-docs` (or equivalent) is not broken by the additions.

## Scope Boundaries

- **In scope**: Prose additions to `docs/guides/SPRINT_GUIDE.md`,
  `docs/reference/CLI.md`, and `docs/reference/CONFIGURATION.md`; one
  end-to-end integration test covering the toggle→branch→push→frontmatter chain.
- **Out of scope**: Implementing any underlying feature-branch behavior (owned by
  BUG-2172, ENH-2173, ENH-2175, ENH-2176); updating ENH-2174's discovery-surface
  docs; schema changes to `config-schema.json`; any UI changes.

## Integration Map

### Files to Modify
- `docs/guides/SPRINT_GUIDE.md` — new end-to-end "Feature-branch / PR-based
  workflow" section (model on the existing `### Wave Execution` paragraph at
  line 258 and the `> **Coverage boundary**:` blockquote at line 260)
- `docs/reference/CLI.md` — `--feature-branches` flag entry; the `> Config tip:`
  blockquote at line 351 already exists but the flag row in the `ll-parallel` table
  (lines 325–366) is the insertion point
- `docs/reference/CONFIGURATION.md` — `push_feature_branches` and
  `open_pr_for_feature_branches` table rows missing from `### parallel` section
  (lines 316–336); `use_feature_branches` row at line 334 and `remote_name` at
  line 335 are already present

### Dependent Files (Callers/Importers)
- Doc-only changes have no callers. The integration test will import:
  - `little_loops.parallel.orchestrator` — `ParallelOrchestrator`
  - `little_loops.parallel.types` — `ParallelConfig`
  - `little_loops.config.core` — `BRConfig`
  - `little_loops.frontmatter` — `parse_frontmatter`

### Similar Patterns
- `docs/guides/SPRINT_GUIDE.md` lines 255–261 — model new feature-branch prose on
  the `### Wave Execution` heading + `> **Coverage boundary**:` blockquote shape
- `docs/reference/CLI.md` lines 325–366 — `ll-parallel` flag table format to
  follow; the `> **Config tip:**` blockquote at line 351 already cross-links to
  CONFIGURATION.md (good model for `--feature-branches` entry)
- `docs/reference/CONFIGURATION.md` lines 316–336 — `### parallel` table for the
  two missing rows (`push_feature_branches`, `open_pr_for_feature_branches`)
- `scripts/tests/test_orchestrator.py` `TestOnWorkerComplete` class (lines 1759–2214) —
  existing unit tests per feature-branch slice; model the new integration test on
  the `fake_subprocess_run` side-effect pattern (lines 1829–1868) and the
  `parse_frontmatter` assertion pattern (lines 2008–2043)

### Tests
- `scripts/tests/test_orchestrator.py` — existing unit tests in `TestOnWorkerComplete`
  class (lines 1759–2214); the new integration test should be added here or in a
  separate `test_feature_branch_e2e.py`; mock path:
  `patch("little_loops.parallel.orchestrator.subprocess.run", side_effect=fake_subprocess_run)`
- `scripts/tests/test_worker_pool.py` — `test_process_issue_uses_feature_branch_name_when_enabled()`
  at line 2131 for branch-naming slice (already covered, not duplicated)
- `scripts/tests/test_cli_sprint.py` — `TestFeatureBranchInPlaceWarning` class covers
  ENH-2176 warning behavior (already covered, not duplicated)

### Documentation
- `docs/reference/CLI.md` and `docs/reference/CONFIGURATION.md` cross-link to
  the new `SPRINT_GUIDE.md` section

### Configuration
- N/A — no config-schema changes; this issue only documents existing config keys

### Dependencies
- **BUG-2172**, **ENH-2173**, **ENH-2175** — this issue documents and
  integration-tests the behavior those land; sequence it last (capstone with
  ENH-2174).

## Implementation Steps

1. Confirm BUG-2172, ENH-2173, ENH-2175, ENH-2176 are merged (ENH-2182 is already
   done per commit c80f82f4); coordinate with final wording from BUG-2172 before
   writing the "PR-ready" language in docs
2. Add a `### Feature-Branch / PR-Based Workflow` H3 section inside
   `docs/guides/SPRINT_GUIDE.md` after the existing `### Wave Execution` paragraph
   (line 258); cover: enabling via config `parallel.use_feature_branches` or
   `--feature-branches` flag, the `push_feature_branches` / `open_pr_for_feature_branches`
   sub-flags and their defaults (both `false`), the `gh auth status` precondition,
   what gets recorded (`branch:` always, `pr_url:` only if PR opened), the
   single-issue-wave warning from `cli/sprint/run.py`, and the
   `status: in_progress` hold until PR merges
3. In `docs/reference/CLI.md` (lines 325–366), add `--feature-branches /
   --no-feature-branches` row to the `ll-parallel` flag table following the
   `BooleanOptionalAction` default-`None` semantics; mirror the row in the
   `ll-sprint` flag table; update the existing `> Config tip:` blockquote at
   line 351 to also mention `push_feature_branches` and `open_pr_for_feature_branches`
4. In `docs/reference/CONFIGURATION.md` `### parallel` section (lines 316–336),
   add the two missing table rows: `push_feature_branches` (default `false`) and
   `open_pr_for_feature_branches` (default `false`); cross-link both from the
   `use_feature_branches` row already at line 334
5. Write integration test in `scripts/tests/test_orchestrator.py` (or new
   `test_feature_branch_e2e.py`) using the `temp_repo_with_config` fixture
   (lines 50–88 in `test_orchestrator.py`) and a `fake_subprocess_run`
   side-effect (pattern: lines 1829–1868) that dispatches `git push` and
   `gh pr create` calls; assert via `parse_frontmatter()` that `branch:` is written
   and `pr_url:` is written only when `open_pr_for_feature_branches=True`; assert
   `status: in_progress` is held (not `done`)
6. Run `ll-verify-docs` to confirm no broken links introduced by the additions

## Impact

- **Priority**: P4 — capstone quality/docs work; no functional gap once the other
  children land, but required to satisfy the EPIC's DoD ("docs describe the actual
  behavior") and to guard the integration seams.
- **Effort**: Small–Medium.
- **Risk**: Low.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-06-16T20:07:47 - `c78fbd64-67b2-4313-b745-fc5bf1a97cb1.jsonl`
- `/ll:confidence-check` - 2026-06-16T20:00:00Z - `a62eab42-672d-4938-a889-8f7f41408abe.jsonl`
- `/ll:refine-issue` - 2026-06-16T19:59:32 - `9b87a7ff-f929-468a-be7c-8ddc441b752e.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00Z - `98177882-cbdf-4d87-8f9e-d9221da608a5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:51:38 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:22 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T20:17:30 - `6bcffe20-05d5-4d4e-9464-920433a7db90.jsonl`
- `/ll:capture-issue` - 2026-06-15T17:30:00Z - added to EPIC-2171 for docs + e2e coverage
