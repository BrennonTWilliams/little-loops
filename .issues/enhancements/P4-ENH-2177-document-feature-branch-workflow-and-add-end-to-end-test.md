---
id: ENH-2177
title: Document the feature-branch workflow end-to-end and add an integration test
type: ENH
status: open
priority: P4
parent: EPIC-2171
captured_at: '2026-06-15T17:30:00Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, feature-branches, docs, testing, workflow]
relates_to: [BUG-2172, ENH-2173, ENH-2175]
---

# ENH-2177: Document the feature-branch workflow end-to-end and add an integration test

## Summary

EPIC-2171's Definition of Done says "Schema/docs describe the actual behavior,"
but only schema text (config-schema.json) is assigned anywhere across the
children. The narrative guides that already document the parallel/sprint workflow
get no update, and no test exercises the full toggle→branch→push→PR→frontmatter
chain end-to-end — each child only tests its own slice. This issue owns the prose
docs and the integration test that tie the EPIC together.

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

## Integration Map

### Files to Modify
- `docs/guides/SPRINT_GUIDE.md` — new end-to-end workflow section
- `docs/reference/CLI.md` — `--feature-branches` override entry
- `docs/reference/CONFIGURATION.md` — `use_feature_branches` + push/PR sub-flags

### Tests
- `scripts/tests/test_parallel_orchestrator.py` (or a new
  `test_feature_branch_workflow.py`) — end-to-end composed assertion

### Dependencies
- **BUG-2172**, **ENH-2173**, **ENH-2175** — this issue documents and
  integration-tests the behavior those land; sequence it last (capstone with
  ENH-2174).

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
- `/ll:capture-issue` - 2026-06-15T17:30:00Z - added to EPIC-2171 for docs + e2e coverage
