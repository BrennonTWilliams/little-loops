---
id: BUG-3614
type: BUG
title: Autodev DECISION re-entry routes lifetime-capped issues to breakdown
priority: P3
status: open
discovered_by: capture-issue
discovered_date: '2026-09-26'
captured_at: '2026-09-26T06:53:39Z'
parent: EPIC-3565
relates_to:
- ENH-3610
- ENH-3611
---

# BUG-3614: Autodev DECISION re-entry routes lifetime-capped issues to breakdown

## Summary

Autodev's ENH-3610 `DECISION` re-entry sends an issue that has used up its lifetime refine
budget back into `refine-to-ready-issue`. That child run routes the issue to
`breakdown_issue` before it reaches any decision-resolution state. The issue is then
decomposed instead of being deferred as `decision_unresolved`.

## Current Behavior

- `select_obligation_post_refine` and `select_obligation_pre_implement` (`autodev.yaml`)
  print `DECISION` → `refine_current` whenever `ll-issues check-flag <ID> decision_needed`
  exits 0. `autodev-reentry-DECISION-<ID>` caps this at one re-entry per issue. The only
  guard is that re-entry cap.
- Every child run starts `resolve_issue` → `check_issue_resolved` → `check_epic_id` →
  `check_lifetime_limit`. `check_lifetime_limit` routes `on_no` → `breakdown_issue` once
  `ll-issues refine-status <ID> --json` `refine_count` (the session-log `/ll:refine-issue`
  count) reaches `commands.max_refine_count` (default 5).
- So a capped issue that is re-entered for `DECISION` never reaches
  `check_decision_before_done` / `resolve_decision_pre_breakdown`. `route_refine_success`
  sees `DECOMPOSED` → `detect_children`, not a `decision_unresolved` deferral.
- Every re-entry also runs `/ll:refine-issue` unconditionally (`precheck_format` →
  `refine_issue`), which adds one to `refine_count`. Re-entry itself therefore moves issues
  toward the cap.

## Steps to Reproduce

1. Take an issue with `decision_needed: true` whose session log already records
   `max_refine_count` (default 5) `/ll:refine-issue` runs.
2. Run `ll-loop run autodev` so that the issue reaches `select_obligation_pre_implement` or
   `select_obligation_post_refine`.
3. The selector prints `DECISION` → `refine_current`. The child's `check_lifetime_limit` exits
   `on_no` → `breakdown_issue`.
4. Observe: autodev routes `DECOMPOSED` → `detect_children`. The issue is not ledgered as
   `decision_unresolved`.

## Expected Behavior

- The `DECISION` re-entry guard also requires `refine_count` < `max_refine_count`. Resolve the
  cap the way the child's `check_lifetime_limit` does: `commands.max_refine_count` in
  `.ll/ll-config.json`, default 5. Autodev has no `max_refine_count` context key, so read the
  config and do not add one.
- When the cap is reached, the selector prints `DECISION_EXHAUSTED` → `record_reentry_exhausted`,
  which ledgers `decision_unresolved` and defers the issue. It never reaches `breakdown_issue`
  through a `DECISION` re-entry.
- The guard mirrors the one ENH-3611 adds for `PROOF` re-entry (ENH-3611 "Shared re-entry
  guard"). Both selectors should use one idiom or helper, so the two cap checks cannot drift.

## Motivation

Heavily refined issues are the most exposed: several passes that did not converge are what
leave `decision_needed` set. At the pre-implement site the issue already passes readiness and
outcome, so the current behaviour decomposes a high-scoring issue that only needed a decision.
A spurious breakdown creates child issues and hides the real reason, an unresolved decision.

## Proposed Solution

Add a lifetime-cap term to the `DECISION` branch of both obligation selectors. When the cap is
reached, reuse the existing `DECISION_EXHAUSTED` → `record_reentry_exhausted` route. No new
state and no new token are needed.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`: `select_obligation_post_refine` and
  `select_obligation_pre_implement` `DECISION` branch; update both comments (the re-entry cap
  now has two terms).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: `check_lifetime_limit` (read-only
  reference; the cap resolution must match it)
- `little_loops.cli.issues.refine_status`: source of `refine_count`

### Similar Patterns
- ENH-3611's shared `PROOF` re-entry guard (same cap term)
- `check_lifetime_limit`'s config read (`commands.max_refine_count`, default from
  `context.max_refine_count`)

### Tests
- `scripts/tests/test_builtin_loops.py`: selector structural/real-FSM tests (see `## Tests`
  below)

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` (autodev section): mention the lifetime-cap term on
  re-entry, if the selector re-entry cap is documented there

### Configuration
- N/A (reads the existing `commands.max_refine_count`)

## Program Design

### Types

- No new types

### Signatures

- `cmd_refine_status(config: BRConfig, args: argparse.Namespace) -> int` — existing; the selectors read `refine_count` from its `--json` output
- `cmd_check_flag(config: BRConfig, args: argparse.Namespace) -> int` — existing; the `DECISION` probe that the new cap term extends

### Call Path

`autodev.yaml:select_obligation_pre_implement` -> `cmd_check_flag` -> `cmd_refine_status` -> `autodev.yaml:record_reentry_exhausted`

`autodev.yaml:select_obligation_post_refine` -> `cmd_check_flag` -> `cmd_refine_status` -> `autodev.yaml:refine_current`

## Implementation Steps

1. In both selectors' `DECISION` branch, read `refine_count` via `ll-issues refine-status <ID>
   --json` and the cap from config. If `refine_count >= cap`, print `DECISION_EXHAUSTED`.
   Keep the un-staging before the route.
2. Keep ENH-3610's exit-code contract: a `refine-status` failure must not break the
   `check-flag` → `next-obligation` fall-through. Treat an unreadable count as "under the cap"
   (current behaviour).
3. Keep `${context.run_dir}` out of heredocs (interpolation-baseline ratchet).
4. If ENH-3611 lands first, reuse its guard idiom instead of duplicating it.

## Impact

- **Priority**: P3 - wrong outcome (spurious decomposition) but only for issues at the
  lifetime refine cap; no data loss
- **Effort**: Small - one guard term in two selectors plus tests
- **Risk**: Low - only narrows when a re-entry fires; the fallback route already exists
- **Breaking Change**: No (loop-internal)

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `select_obligation_post_refine`, `select_obligation_pre_implement` (ENH-3610)
- **Cause**: the re-entry guard checks only the per-run re-entry marker. It ignores the child's
  own lifetime entry gate (`check_lifetime_limit` in `refine-to-ready-issue.yaml`), which runs
  before any decision state.

## Tests

- Real-FSM test: a `decision_needed` issue with `refine_count == max_refine_count` reaches
  `select_obligation_pre_implement` and is deferred `decision_unresolved` via
  `record_reentry_exhausted`. `breakdown_issue` never runs.
- Same for `select_obligation_post_refine`.
- Under the cap, behaviour is unchanged: one `DECISION` re-entry → `refine_current`.

## Acceptance Criteria

- [ ] Neither selector re-enters the child for `DECISION` once `refine_count` >= `max_refine_count`
- [ ] A capped decision-flagged issue defers as `decision_unresolved`, never decomposes
- [ ] Under-cap behaviour and ENH-3610's exit-code contract are unchanged

## Related

Found during the ENH-3611 review (2026-09-26); ENH-3611 lists this as out of scope.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-26T06:53:45 - `06522881-acec-4007-9c05-e417309eaff8.jsonl`
