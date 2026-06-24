---
id: FEAT-2263
title: omp hook-event parity audit
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
parent: EPIC-2258
depends_on: [FEAT-1850]
labels: [host-compat, omp, hooks, parity]
relates_to: [FEAT-2261]
---

# FEAT-2263: omp hook-event parity audit

## Summary

Audit oh-my-pi's hook-event surface against the ll intent set and record which
ll intents (`pre_tool_use`, `post_tool_use`, `user_prompt_submit`, `stop`,
`session_end`, …) omp can fire natively vs. which are absent. Absorbs the intent
of the cancelled vanilla-Pi parity issue FEAT-1715, adapted to omp's richer
event model.

## Motivation

omp's SDK exposes more lifecycle events than vanilla pi-mono, so the parity gap
should be narrower — but it must be measured, not assumed, before
`HOST_COMPATIBILITY.md` claims any omp hook cell. This audit feeds FEAT-2261's
event mapping.

## Acceptance Criteria

- `thoughts/research/omp-hook-event-parity.md` records the omp→ll event mapping
  and any gaps (events with no omp equivalent).
- `HOST_COMPATIBILITY.md` omp hook-intent rows are populated (✓ / ✗-linked / N/A)
  — no unknown cells.
- `hooks/adapters/omp/README.md` parity matrix matches the audit (cross-check
  with FEAT-2261).

## Reference

- FEAT-1715 (cancelled) — canonical Pi parity-audit framework to mirror.
- `thoughts/research/gemini-cli-surface.md` — analogous host-surface research doc.

## Impact

- **Effort**: S–M (research + matrix update).
- **Risk**: Low — research/docs; may surface upstream oh-my-pi gaps.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-24 | Priority: P4
