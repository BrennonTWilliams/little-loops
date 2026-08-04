---
id: EPIC-3041
title: Host-agnostic advisor
type: EPIC
priority: P3
status: open
discovered_date: 2026-08-04
labels:
- planning-hub
---

# EPIC-3041: Host-agnostic advisor

## Summary

Four-slice rollout of a host-agnostic advisor consult path: a one-shot
escalation to a second, stronger — possibly different-provider — model that
returns a structured verdict (`{recommendation, risks[], confidence,
dissent}`) before the primary model commits to an approach.

## Children

- **FEAT-3037** — Host-agnostic advisor: invocation mechanism, config,
  capability floor, and `ll-doctor` check (slice 1)
- **FEAT-3038** — Advisor signal-gated auto-consults and per-task budget:
  wires `confidence_gate`/`pre_done` triggers and `max_consults_per_task`
  (slice 2)
- **FEAT-3039** — Advisor FSM stall escalation and routable verdicts: lets
  FSM loops escalate on stall and route on the verdict (slice 3)
- **FEAT-3040** — Advisor consult telemetry in `history.db`: persists
  consults for `ll-ctx-stats` and downstream analytics (slice 4)
