---
id: BUG-3740
type: BUG
title: refine-to-ready-issue PLACEHOLDERS gate has no repair path (stub Impact exhausts
  refine budget, ends GATE_UNMET)
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T20:09:46Z'
labels:
- loops
- refine-to-ready-issue
---

# BUG-3740: refine-to-ready-issue PLACEHOLDERS gate has no repair path (stub Impact exhausts refine budget, ends GATE_UNMET)

## Summary

`refine-to-ready-issue` routed the `PLACEHOLDERS` obligation to `check_gate_refine_limit`, i.e. a `refine_followup` (`/ll:refine-issue --auto --gap-analysis`). That pass is additive-only and never fills an existing template placeholder, so a stub `## Impact` (`[Justification]`, `[Small/Medium/Large]`, ...) burned the run's single shared refine loopback on a no-op and the run ended `[GATE_UNMET]` (observed on BUG-3738, run `refine-to-ready-issue-20261005T130338`).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

The only state that fills placeholders is `/ll:format-issue --auto` (`format_issue_pre` / `format_issue_post`), but both are gated on `format-check`'s `directive_gaps`, which does not include `template_placeholders`. The `refine-to-ready-format-fallback` counter stayed `0` for the whole run.

## Resolution

New state `check_placeholder_format_fallback`: counter 0 -> set to 1 and run `format_issue_post` (rejoins the gate band via `clear_verify_verdict`); counter spent or unreadable -> `check_gate_refine_limit` as before. `PLACEHOLDERS` in `route_pre_score_obligation` now routes there. Route table test, new `TestPlaceholderFormatFallback` tests and `LOOPS_REFERENCE.md` updated.

## Status

**Open** | Created: 2026-10-05 | Priority: P3
