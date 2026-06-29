---
id: FEAT-2379
type: FEAT
title: 'Fleet loop-review runbook + `make` target — continuous improvement of built-in loops from cross-project logs'
priority: P3
status: open
captured_at: '2026-06-28T20:54:00Z'
discovered_date: 2026-06-28
discovered_by: user-report
labels:
- docs
- tooling
- ll-loop
- ll-logs
- meta-loop
- workflow
relates_to:
- BUG-2377
- ENH-2378
blocked_by:
- BUG-2377
- ENH-2378
decision_needed: false
confidence_score: 75
---

# FEAT-2379: Fleet loop-review runbook + repeatable target

## Goal

Make "use other projects' logs to continuously fix and improve this repo's built-in loops" a
**repeatable, documented cycle** rather than an ad-hoc investigation. Other projects on the
machine act as a *test fleet* for the 77 shipped loops; their run traces feed improvements
back here, and each fix is validated against the fleet's next-cycle failure delta.

## The cycle

```
HARVEST (cross-project, read-only)
  → ATTRIBUTE each failure/stall to a built-in loop
    → DIAGNOSE + FIX (in this repo)
      → RE-MEASURE (next harvest's failure delta = acceptance signal)
```

The final arrow is mandatory: per the meta-loop rules in `.claude/CLAUDE.md`, a harness
"improvement" is only proven when an *external* measure moves — here, the fleet's failure
rate for that loop. Other-projects' logs are the unbiased oracle a self-grade cannot be.

## Deliverables

1. **A runbook** at `docs/guides/FLEET_LOOP_REVIEW.md` documenting the cycle, the commands at
   each phase, how to attribute, how to record a baseline, and the in-scope rule (fix only
   built-ins here; other projects' own loops are fixed in place).
2. **A repeatable entry point** — a `make fleet-loop-review` / `just` target (or a thin
   `scripts/` wrapper) that chains:
   - `ll-logs loop-fleet -j` (ENH-2378) — run outcomes per built-in loop.
   - `ll-logs scan-failures --all --window-days N -j` — CLI-level failure clusters.
   - `ll-logs sequences --all` — how loops chain / where they stall.
   - `ll-logs dead-skills` — built-in loops with zero fleet invocations.
   - `ll-loop validate` / `diagnose-evaluators` / `calibrate-budget` over the flagged loops.
   The target writes a dated report under `.loops/diagnostics/fleet-review-<date>.md`.
3. **A baseline record** so re-measurement is mechanical: the report stores per-loop failure
   counts; the next run diffs against the prior report to show whether shipped fixes helped.

## Scope decisions (from capture conversation)

- **Mechanism**: repeatable runbook + harvester command, run on demand (not a scheduled
  cron, not a built-in meta-loop — those were the alternatives considered and deferred).
- **Target**: this repo's **built-in** loops only. Cross-project data is *evidence*; fixes to
  other projects' `.loops/` happen in those projects, not back-ported here.

## Acceptance criteria

- `make fleet-loop-review` (or documented equivalent) runs end-to-end and produces a dated
  diagnostic report with: per-built-in-loop fleet outcomes, flagged loops, and a baseline diff
  vs. the previous report.
- `docs/guides/FLEET_LOOP_REVIEW.md` documents the four phases and the re-measurement contract.
- The runbook explicitly states the in-scope rule and links the diagnose tools and
  `loop-specialist` agent.
- Running the cycle twice (before/after a deliberate built-in-loop fix) demonstrates the
  failure-delta acceptance signal.

## Dependencies

- **BUG-2377** — parseable `ll-logs` output (blocker).
- **ENH-2378** — `ll-logs loop-fleet` harvester (the HARVEST phase's core data source).

## Future extension (out of scope here)

If the on-demand runbook proves valuable, promote it to a scheduled capture
(`scan-failures --capture-foreign` on a cron) and/or a built-in `fleet-loop-improve.yaml`
meta-loop following `diagnose → propose → apply → measure-externally`. Captured here so the
path is recorded, not built.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-29T01:47:32 - `0f8f08b1-212f-4f62-9ad9-264556960322.jsonl`
