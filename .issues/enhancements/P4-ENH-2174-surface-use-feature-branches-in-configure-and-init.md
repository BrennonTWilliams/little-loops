---
id: ENH-2174
title: Surface use_feature_branches in /ll:configure and init templates
type: ENH
status: open
priority: P4
parent: EPIC-2171
captured_at: '2026-06-15T16:51:50Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, configure, init, feature-branches, dx, discoverability]
depends_on: [ENH-2176]
relates_to: [ENH-2175]
---

# ENH-2174: Surface use_feature_branches in /ll:configure and init templates

## Summary

`parallel.use_feature_branches` switches `ll-parallel` (and `ll-sprint`) to a branch-per-issue / PR-based workflow, but it is invisible everywhere a user would discover it — not in `/ll:configure`, `ll-init`, or any config template. This enhancement adds the flag to those discovery surfaces so users can find and enable it without hand-editing JSON.

## Motivation

`parallel.use_feature_branches` is defined in the config schema and honored by
the runtime, but it is invisible everywhere a user would actually discover it:
it does not appear in `/ll:configure`, in `ll-init`, or in the config
`templates/`. The only way to enable it is to know it exists and hand-edit
`.ll/ll-config.json`. For a flag whose whole purpose is to change the default
development workflow (branch-per-issue / PR-based), discoverability matters.

## Current Behavior

- `grep -rln "use_feature_branches" templates/ scripts/little_loops/cli/init* /ll:configure`
  → no matches in templates, init, or the configure surface.
- A user reading `/ll:configure` output has no way to learn the flag exists.

## Expected Behavior

- `/ll:configure` lists `use_feature_branches` under parallel settings with an accurate one-line description and lets the user toggle it.
- Config templates include a documented (commented or `false`-defaulted) `use_feature_branches` entry in the parallel block.
- `ll-init` optionally prompts for the flag when the user indicates a PR-based / CI workflow.
- All description text reflects actual implemented behavior (coordinated with BUG-2172 outcome).

## Proposed Solution

1. Add `use_feature_branches` (and, once BUG-2172 lands, any push/PR sub-flags)
   to the `parallel` section presented by `/ll:configure`, with a one-line
   description of the PR-based workflow it enables.
2. Surface it in the parallel block of the relevant config `templates/` (commented
   default `false`) so generated configs document its existence.
3. Optionally prompt for it during `ll-init` when the user opts into a
   PR-based / CI workflow.

## Acceptance Criteria

1. `/ll:configure` lists `use_feature_branches` under parallel settings with an
   accurate description and lets the user toggle it.
2. Config templates include a documented (commented or default-false) entry.
3. Description text matches actual behavior (kept in sync with BUG-2172 outcome —
   do not advertise push/PR unless implemented).
4. The toggle's description states its **coverage boundary**: feature-branch mode
   applies to parallel (multi-issue) waves; it does not apply to `ll-auto`
   (sequential, in-place) and — pending ENH-2176 — single-issue / contention
   sub-waves in `ll-sprint`. Users should not be surprised that the flag no-ops
   for some paths.

## Scope Boundaries

- **In scope**: Adding `use_feature_branches` to `/ll:configure` parallel settings display; adding a documented entry in config templates; optional `ll-init` prompt under a PR-workflow opt-in.
- **Out of scope**: Implementing push/PR behavior itself (owned by BUG-2172 and ENH-2173); changing the flag's default value; adding new sub-flags beyond `use_feature_branches`.

## Integration Map

### Files to Modify
- `skills/configure/` — add the flag to the parallel settings the skill presents
- `templates/` — add a documented `use_feature_branches` entry to the parallel block of relevant config templates
- (optional) `ll-init` flow — prompt under a PR-workflow opt-in

### Dependencies
- Coordinate description text with **BUG-2172**: only describe push/PR behavior
  if that issue implements it; otherwise describe local-branch retention.

## Implementation Steps

1. Audit `skills/configure/` to locate where parallel settings are presented; add `use_feature_branches` with a one-line description of the PR-based workflow it enables.
2. Add a documented `use_feature_branches` entry (commented or `false`-defaulted) to the `parallel` block in relevant `templates/`.
3. (Optional) Add a PR-workflow opt-in prompt to the `ll-init` flow.
4. Coordinate description text with BUG-2172 outcome — only describe push/PR behavior if that issue has landed.
5. Verify `/ll:configure` output and generated config templates include the new entry.

## Impact

- **Priority**: P4 — discoverability/polish; no functional gap once ENH-2173 and
  BUG-2172 land, but completes the "expose it" capstone of the EPIC.
- **Effort**: Small.
- **Risk**: Low.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P4

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-15T20:47:56 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:23 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T16:57:30 - `bbf7e27c-ea9f-4af6-b201-de02c8065217.jsonl`
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): [ENH-2176] is the canonical source for the coverage-boundary prose explaining that `use_feature_branches` does not apply to single-issue / contention sub-waves. The toggle description this issue adds to `/ll:configure` and config templates should reference or quote ENH-2176's `docs/guides/SPRINT_GUIDE.md` coverage-boundary paragraph rather than authoring independent text. Sequence ENH-2174's description wording after ENH-2176's SPRINT_GUIDE paragraph is finalized to keep the two surfaces consistent.
