---
id: ENH-2666
type: ENH
priority: P3
status: open
captured_at: '2026-07-18T02:50:02Z'
discovered_date: '2026-07-18'
discovered_by: capture-issue
parent: EPIC-2663
relates_to: [ENH-2664, FEAT-2665]
labels:
- loops
- orchestration
---

# ENH-2666: Reconcile autodev vs rn-implement "not ready" handling

## Summary

The two autonomous processing paths handle the same conceptual event — "this
issue isn't ready to implement" — with opposite outcomes. Decide on and
implement a consistent policy so behavior is predictable regardless of which
orchestrator runs.

## Motivation

- `autodev.yaml` never sets `deferred`: a low-readiness issue is appended to a
  ledger file (`autodev-skipped.txt` reason `low_readiness` at 849-850, or
  `-gate-blocked.txt` at 507-509, `-decision-unresolved.txt` at 379-381) and its
  status is **left `open`** — so it's retried next run.
- `rn-implement.yaml` sets `status: deferred` (`mark_deferred`, 1330-1357) — the
  issue leaves active selection and is **not retried**.

Same input, divergent lifecycle. A user switching between `ll-auto` and
`rn-implement` gets surprising, inconsistent backlog behavior. Once ENH-2664
(reason discriminator) and FEAT-2665 (resurfacing) land, the two paths should
converge on a single documented policy for not-ready issues.

## Current Behavior

See Motivation — the two ledgers/status transitions above.

## Proposed Behavior

Pick and document one policy, e.g.:
- Both paths emit the same reason-tagged signal (ENH-2664 fields) and rely on the
  shared resurfacing surface (FEAT-2665); OR
- Both leave the issue `open` + ledgered with a retry-cap circuit-breaker, so
  neither silently strands the issue.

Decision to be finalized during refinement; capture the tradeoff (retry-loop risk
vs. invisibility) explicitly.

## Implementation Steps

1. Enumerate every not-ready exit in `autodev.yaml` and `rn-implement.yaml`.
2. Choose the unified policy; record the decision.
3. Align both loops to the chosen transition + reason tagging.
4. Document the policy in `.claude/CLAUDE.md` § Issue File Format.
5. Tests: parity fixtures asserting both paths produce the same lifecycle for an equivalent not-ready issue.

## Impact

- **Priority**: P3 — consistency/cleanup; the acute drop is fixed by FEAT-2665.
- **Effort**: Medium.
- **Risk**: Medium — changes retry behavior in one of the two paths.
- **Breaking Change**: No (behavioral alignment, documented).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-07-18T02:50:02Z

---

## Status

- **Current**: open
- **Last Updated**: 2026-07-18
