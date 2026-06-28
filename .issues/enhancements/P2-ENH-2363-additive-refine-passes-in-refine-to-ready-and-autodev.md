---
id: ENH-2363
title: 'refine-to-ready-issue + autodev: stop using --full-rewrite on first/repair refine passes'
type: ENH
priority: P2
status: done
captured_at: '2026-06-28T04:24:39Z'
completed_at: '2026-06-28T04:24:39Z'
discovered_date: '2026-06-28'
discovered_by: conversation
relates_to:
- ENH-2037
- ENH-2247
- ENH-2364
labels:
- loops
- issue-management
- refine-issue
- autodev
- refine-to-ready-issue
confidence_score: 95
outcome_confidence: 85
---

# ENH-2363: Use additive refine passes in refine-to-ready-issue and autodev

## Summary

Both the built-in `refine-to-ready-issue` loop and `autodev` invoked
`/ll:refine-issue ... --auto --full-rewrite` in places where `--full-rewrite`
(the legacy, destructive, budget-consuming mode) was unwarranted — on the
**first** refine of a backlog issue and on **repair/retry** passes. Observed in
practice (running the loop across multiple projects on this machine) as
full-rewrite firing far too early and far too often. This change brings both
loops in line with the established ENH-2247 house policy already used by
`rn-remediate`: reserve `--full-rewrite` for a confirmed content diagnosis;
use lighter additive modes for first-pass and repair work.

## Background: the three refine modes

From `commands/refine-issue.md`:

- `--full-rewrite` — legacy mode; rewrites sections; **consumes** `max_refine_count`
  budget; destructive (can remove content).
- plain `--auto` (no mode flag) — default mode; lighter but still rewrite-capable;
  consumes budget. Can reshape wrong/sparse content.
- `--auto --gap-analysis` — additive-only (never removes content); does **not**
  consume budget; designed for repeated iterative patching.

`rn-remediate.yaml` had already converged on this policy across BUG-2007 /
ENH-2223 / ENH-2247: `refine_first` and `refine_light` use plain `--auto`,
`refine_followup` uses `--auto --gap-analysis`, and only a confirmed
`diagnose → REFINE` content diagnosis retains `--full-rewrite`. The two loops
fixed here had never been brought up to that policy.

## Current Behavior (before fix)

- **`scripts/little_loops/loops/refine-to-ready-issue.yaml`** — a single
  `refine_issue` state ran `--auto --full-rewrite` and was the target of **both**
  entry points: the first refine (from `check_lifetime_limit`) and the retry
  (from `check_refine_limit`, `on_yes`). So every refine the loop ever issued was
  a full rewrite, and the retry bulldozed the first pass's output.
- **`scripts/little_loops/loops/autodev.yaml`** — `run_refine` ran
  `--auto --full-rewrite`. This state is reachable only as a post-wire repair
  (`triage_outcome_failure → check_missing_artifacts → run_wire → run_refine`),
  so the full rewrite could overwrite the integration edits `run_wire` had just
  made — exactly the hazard `rn-remediate`'s `wire`/`refine_followup` comments
  warn about.
- Corroborating signal: `restore_best` (ENH-2037) exists in
  `refine-to-ready-issue` purely as a band-aid to undo "a late --full-rewrite
  regression … persisting over a better prior iteration" — evidence the
  maintainers already knew full-rewrite caused regressions.

## Resolution

- **`refine-to-ready-issue.yaml`**
  - Split `refine_issue` into two states (mirroring `rn-remediate` ENH-2247):
    - `refine_issue` (first pass, from `check_lifetime_limit`) → `--auto`
      (dropped `--full-rewrite`). Can still reshape wrong/sparse content; no
      longer the heaviest legacy mode on first touch. Fixes "too early."
    - `refine_followup` (retry, from `check_refine_limit`) → `--auto --gap-analysis`.
      Additive-only; does not re-bulldoze the first pass or burn budget. Fixes
      "too often."
  - Re-pointed `check_refine_limit.on_yes` from `refine_issue` to `refine_followup`.
  - Updated the routing-summary header comment.
- **`autodev.yaml`**
  - `run_refine` → `--auto --gap-analysis` (additive post-wire repair; will not
    overwrite the wiring `run_wire` just applied). Updated the state comment to
    reference the ENH-2247 / rn-remediate rationale.
- Validated both loops with `ll-loop validate` (both report valid; the
  pre-existing `verify-confidence-scores` oracle-resolution warning is unrelated).

## Files Changed

- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `scripts/little_loops/loops/autodev.yaml`

## Acceptance Criteria

- [x] `refine-to-ready-issue` no longer uses `--full-rewrite` on the first refine.
- [x] `refine-to-ready-issue` retry path uses additive `--auto --gap-analysis`.
- [x] `autodev` `run_refine` (post-wire repair) uses additive `--auto --gap-analysis`.
- [x] Both loops pass `ll-loop validate`.

## Out of Scope / Follow-ups

- **ENH-2364** — retire or downscope `restore_best` (ENH-2037) in
  `refine-to-ready-issue`, now that refines are no longer destructive full
  rewrites and the band-aid triggers far less often.

## Impact

- **Priority**: P2 — corrects wasteful and destructive refine behavior on every
  autodev / refine-to-ready run; user-reported across multiple projects.
- **Effort**: Small — three YAML edits across two loops plus a comment refresh.
- **Risk**: Low — additive/lighter modes are strictly safer than the destructive
  full rewrite they replace; routing topology unchanged except the retry target.
- **Breaking Change**: No — behavioral change to refine aggressiveness only.

---
**Done** | Created: 2026-06-28 | Completed: 2026-06-28 | Priority: P2

## Session Log
- `hook:posttooluse-status-done` - 2026-06-28T04:25:51 - `9700da75-4d89-428f-a70d-0c905fa3f564.jsonl`
- conversation - 2026-06-28T04:24:39Z - refine-to-ready-issue + autodev full-rewrite review and fix
