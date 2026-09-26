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
reconcile_attempted: true
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
- ENH-3611's `PROOF` re-entry guard (same cap term; specified as prose only, no shared code)
- `check_lifetime_limit`'s config read (`commands.max_refine_count`, env-var fallback from
  `context.max_refine_count` — a key autodev lacks, so the fallback is hardcoded 5 here)

### Tests
- `scripts/tests/test_autodev_decision_gate.py`: `TestObligationSelectorStructural` and
  `TestObligationSelectorBehavior`; extend `_StubIssues` to answer `refine-status --json`
  (see `## Tests` below)
- `scripts/tests/test_autodev_scores_freshness.py::test_dequeue_clears_markers_for_reentry`:
  must keep passing (regression check)

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` (autodev section): mention the lifetime-cap term on
  re-entry, if the selector re-entry cap is documented there

### Configuration
- N/A (reads the existing `commands.max_refine_count`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Cap-resolution convention**: the cap is `commands.max_refine_count` from `.ll/ll-config.json`, read in a quoted `python3 << 'PYEOF'` heredoc that receives its fallback through an env var (`LL_ARG_MAX_REFINE_COUNT=${context.max_refine_count:shell}`), so no context value is interpolated into Python source. `refine_count` comes from `ll-issues refine-status "<ID>" --json | python3 -c "...int(d.get('refine_count', 0))..."` with `except: print(0)` / `|| echo 0`, compared with `-ge`. Evidence: `refine-to-ready-issue.yaml:check_lifetime_limit` (lines ~226-258). The `:shell` suffix is the convention for interpolated IDs/values.
- **Default-5 source**: the default lives in a loop `context:` key (`refine-to-ready-issue.yaml:137`, `recursive-refine.yaml:40`). `autodev.yaml` has no such key (only a comment near line 2625), so a selector that needs a fallback either hardcodes 5 or reads a key that does not exist — the two-layer default cannot be copied as-is. No shared cap-check helper exists in `loops/lib/`; both `check_lifetime_limit` copies and the two selector DECISION blocks are inline duplicates.
- **Selector DECISION block is duplicated byte-for-byte** in `select_obligation_post_refine` (~733-780) and `select_obligation_pre_implement` (~782-827): `check-flag <ID> decision_needed`; on exit 0, un-stage the ID (`grep -vxF` on `autodev-staged.txt`); read marker `${context.run_dir}/autodev-reentry-DECISION-<ID>`; `N>=1` prints `DECISION_EXHAUSTED`, else write `N+1` and print `DECISION`; then `exit 0` so `next-obligation` never runs while the flag is set. Route tables for `DECISION` (→ `refine_current`) and `DECISION_EXHAUSTED` (→ `record_reentry_exhausted`) are identical in both. Ordering constraint: a cap term evaluated after the marker write would consume the one-shot re-entry marker for an issue that is never re-entered.
- **`record_reentry_exhausted`** (~829-852) hardcodes the `decision_unresolved` ledger reason and defers via `set-status deferred --by automation --reason decision_unresolved` (skipped if already done/completed/cancelled), then `dequeue_next`; `dequeue_next` clears `autodev-reentry-*-<ID>` markers (line ~127).
- **Interpolation-baseline ratchet**: `TestInterpSweepBaseline.test_completeness_guard` (`test_builtin_loops.py`) diffs `scan_corpus` against `scripts/tests/data/loop_interpolation_baseline.json` in both directions, and scans only embedded Python bodies (heredocs, `python3 -c`). Neither selector has an embedded Python body today and neither is baselined, so a new Python snippet interpolating `${context.*}` in a selector is a new unbaselined site. Passing values by env var with a quoted heredoc (as `check_lifetime_limit` does) avoids it.
- **Brace escape**: selectors currently use bare `$ID`/`$N`/`$F`; any new bash `${VAR:-x}` in an FSM action must be written `$${VAR:-x}` (only the summary state uses it today).
- **ENH-3611 guard is prose-only**: it is specified (ENH-3611 "Shared re-entry guard") as a per-selector shell block with no shared code artifact, and PROOF has no `_EXHAUSTED` token (an exhausted PROOF defers as `blocked_by_gate`). The "one idiom or helper" expectation therefore has nothing implemented to reuse; the two caps can only be kept aligned by matching the `check_lifetime_limit` resolution rule.

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

1. In both selectors' `DECISION` branch (duplicated byte-for-byte), read `refine_count` via
   `ll-issues refine-status <ID> --json` and the cap from `commands.max_refine_count` in
   `.ll/ll-config.json` (hardcoded fallback 5, since autodev has no `max_refine_count` context
   key). If `refine_count >= cap`, print `DECISION_EXHAUSTED`. Keep the un-staging before the
   route, and evaluate the cap term **before** the `autodev-reentry-DECISION-<ID>` marker write so
   an issue that is never re-entered does not consume the one-shot marker.
2. Keep ENH-3610's exit-code contract: a `refine-status` failure must not break the
   `check-flag` → `next-obligation` fall-through. Treat an unreadable count as "under the cap"
   (current behaviour).
3. Follow `check_lifetime_limit`'s idiom: a quoted `python3 << 'PYEOF'` heredoc with any
   fallback passed via env var, never interpolating `${context.*}` (incl. `run_dir`) into Python
   source (interpolation-baseline ratchet). Write any new bash `${VAR:-x}` as `$${VAR:-x}`.
4. ENH-3611's guard is prose-only (no shared code artifact), so implement the cap term inline in
   each selector and keep it aligned with ENH-3611 by matching `check_lifetime_limit`'s
   resolution rule.
5. Update the comment above each selector's `DECISION` branch (the re-entry cap now has two
   terms) and add tests in `scripts/tests/test_autodev_decision_gate.py`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Selector tests live in `scripts/tests/test_autodev_decision_gate.py`, not `test_builtin_loops.py` (which only has structural checks such as `test_required_states_exist`). Two layers: `TestObligationSelectorStructural` (exact `route` dict equality, substring presence in the action, `load_and_validate`) and `TestObligationSelectorBehavior` (runs the real action under `bash -c` against `_StubIssues`).
- `_StubIssues` handles only `check-flag`, `next-obligation`, `show`; every other subcommand (including `refine-status`) hits `*) exit 0` and prints nothing, and the test cwd has no `.ll/ll-config.json`. Under-cap and capped behavioral cases therefore need the stub to answer `refine-status --json`; the "unreadable count = under cap" contract is exactly what the current stub exercises by default.
- `_interp()` substitutes `${...}` through a fixed dict (`context.run_dir`, `captured.input.output[:shell]`, thresholds); a new `${context.X}` reference in a selector raises `KeyError` unless added there.
- `test_autodev_scores_freshness.py::test_dequeue_clears_markers_for_reentry` covers marker clearing and must keep passing.

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
- `/ll:reconcile-issue` - 2026-09-26T07:01:39 - `7d8d5da2-5970-46c4-a7de-295402f96f22.jsonl`
- `/ll:refine-issue` - 2026-09-26T06:59:52 - `83a53e9a-c833-443d-91cf-22a5699e1980.jsonl`
- `/ll:capture-issue` - 2026-09-26T06:53:45 - `06522881-acec-4007-9c05-e417309eaff8.jsonl`
