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
blocked_by: [BUG-2172, ENH-2173, ENH-2175, ENH-2176, ENH-2182]
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
  workflow" section
- `docs/reference/CLI.md` — `--feature-branches` override entry and push/PR
  sub-flag entries
- `docs/reference/CONFIGURATION.md` — `use_feature_branches` + push/PR sub-flags

### Dependent Files (Callers/Importers)
- N/A — doc-only changes; the test file imports `ll_parallel` orchestrator under
  test, not a new public API

### Similar Patterns
- Existing parallel-workflow section in `docs/guides/SPRINT_GUIDE.md` — model
  the new feature-branch section on the same heading/subsection structure
- Existing flag reference entries in `docs/reference/CLI.md` — follow the same
  flag-description table format

### Tests
- `scripts/tests/test_parallel_orchestrator.py` (or a new
  `test_feature_branch_workflow.py`) — end-to-end composed assertion (push/PR
  calls mocked via `unittest.mock.patch`)

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

1. Confirm BUG-2172, ENH-2173, ENH-2175, ENH-2176 are merged (capstone — depends
   on final wording/flags from those issues)
2. Draft "Feature-branch / PR-based workflow" section in `docs/guides/SPRINT_GUIDE.md`
   covering: enabling via config or `--feature-branches`, push/PR sub-flags and
   their defaults, `gh` requirement, what gets recorded (`branch:` / `pr_url:`),
   and the single-issue-wave boundary
3. Add `--feature-branches` and push/PR sub-flag entries to `docs/reference/CLI.md`
   and `use_feature_branches` + sub-flags to `docs/reference/CONFIGURATION.md`;
   cross-link to the new SPRINT_GUIDE section
4. Write end-to-end integration test in a temp git repo with mocked push/PR calls
   asserting: branch created → push invoked with correct args → `branch:`/`pr_url:`
   written to issue frontmatter
5. Run `ll-verify-docs` to confirm no broken links introduced by the additions

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
- `/ll:audit-issue-conflicts` - 2026-06-15T20:51:38 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:22 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T20:17:30 - `6bcffe20-05d5-4d4e-9464-920433a7db90.jsonl`
- `/ll:capture-issue` - 2026-06-15T17:30:00Z - added to EPIC-2171 for docs + e2e coverage
