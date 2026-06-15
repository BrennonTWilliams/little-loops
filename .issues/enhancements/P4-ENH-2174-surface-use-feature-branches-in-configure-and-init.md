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
---

# ENH-2174: Surface use_feature_branches in /ll:configure and init templates

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

## Integration Map

### Files to Modify
- `skills/configure/` — add the flag to the parallel settings the skill presents
- `templates/` — add a documented `use_feature_branches` entry to the parallel block of relevant config templates
- (optional) `ll-init` flow — prompt under a PR-workflow opt-in

### Dependencies
- Coordinate description text with **BUG-2172**: only describe push/PR behavior
  if that issue implements it; otherwise describe local-branch retention.

## Impact

- **Priority**: P4 — discoverability/polish; no functional gap once ENH-2173 and
  BUG-2172 land, but completes the "expose it" capstone of the EPIC.
- **Effort**: Small.
- **Risk**: Low.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-15 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-06-15T16:51:50Z - `5b1dd63b-714f-41e9-b9c2-f55f8ebd0e98.jsonl`
