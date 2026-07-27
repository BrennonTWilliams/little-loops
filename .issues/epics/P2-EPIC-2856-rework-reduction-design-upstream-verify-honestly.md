---
id: EPIC-2856
title: "Rework reduction — design upstream, verify honestly"
type: EPIC
status: open
priority: P2
captured_at: '2026-07-27T00:00:00Z'
discovered_date: 2026-07-27
discovered_by: ll-product-promotion
relates_to:
- ENH-2852
- ENH-2853
- ENH-2854
- FEAT-2855
labels:
- epic
- rework
- verification
- refinement
- observability
---

# EPIC-2856: Rework reduction — design upstream, verify honestly

Origin: ll-product #EPIC-055

## Summary

little-loops' batch instruments (`ll-auto`, `ll-parallel`, `ll-sprint`) optimize
for how much work can be pushed through the queue. Nothing in the system
measures or reduces the share of that work that has to be redone.

This epic attacks rework from both ends: make an issue commit to its
program-level shape *before* an agent starts, and make a loop's "verified"
signal impossible to fake once it has.

The four children are independently shippable and share one premise: throughput
without a quality-adjustment term is a misleading number, and the cheapest
quality wins are deterministic, not model-graded.

## Motivation

Two failure modes recur in unattended batch runs:

1. **Design decided mid-implementation.** The refinement chain
   (`/ll:refine-issue` → `/ll:wire-issue` → `/ll:confidence-check`) researches
   the codebase and names integration points, but never forces an issue to
   state the types, method signatures, and call path a change will follow. The
   most rework-prone decisions get made by an agent under implementation
   pressure, with no human review of the plan.

2. **Verification that verifies nothing.** A loop that treats a green test
   suite as a transition predicate can be satisfied by a test that already
   passed before the change, or by an agent editing the test out of the way.
   Both are cheap to detect deterministically and neither is currently
   detected.

The observability child exists because neither fix is provable without a
measurement: a maintainability trend is the quantity that tells you whether any
of this worked.

## Goal

A batch run's output can be trusted without reading every line: each issue
entered implementation with its program design already fixed, each verification
claim survives a deterministic integrity check, and codebase health under
sustained agent activity is measurable.

## Scope

**In scope:** a program-design stage in the refinement chain and its confidence
gate; deterministic pre-patch test-failure checking; test-file tamper detection
during verification; maintainability-trend metrics over repo history joined
with `.ll/history.db`.

**Out of scope:** replacing semantic/LLM criteria in `ll-harness` — these checks
sit alongside them, not instead of them; new event transports; hosted or
multi-tenant reporting.

## Children

- **ENH-2852** — Add a program-design stage to issue refinement naming types,
  signatures, and call path
- **ENH-2853** — Deterministic pre-patch test-failure check in verification
  loops
- **ENH-2854** — Guard against agent edits to test files during verification
- **FEAT-2855** — Track codebase maintainability trend as an observability
  dimension

Suggested order: ENH-2853 and ENH-2854 first — both are small, deterministic,
and independently testable, and together they close the two cheapest holes in
the verification story. ENH-2852 next; FEAT-2855 last, as it is the largest and
benefits from the others being in place to measure.

**Baseline before intervention** (revised 2026-07-27): FEAT-2855's signals are
computed from `git log`, which is immutable — the tool can retroactively
compute any pre-intervention window once it ships. No manual signal sampling is
needed up front. What ENH-2852 must record before its gate is enabled is the
**cutover point**: a note under `thoughts/` with the SHA/date at which the
interventions begin (plus the caveat that `.ll/history.db` attribution for old
windows depends on manual retention). "Did any of this work" is then answered
by FEAT-2855 comparing windows either side of that stamp.

## Success Metrics

- `/ll:confidence-check` fails an issue that has no specific program-design
  section, and passes one that names concrete types, signatures, and a call
  path.
- A verification loop rejects a newly added test that passes against the
  pre-patch tree.
- A verification step that modified a test file either reverts the modification
  before scoring or fails the transition, and reports which files were touched.
- A maintainability trend is reportable across ≥2 sampling points from repo
  history without LLM judgment.

## Integration Map

- Refinement chain — `/ll:refine-issue`, `/ll:wire-issue`,
  `/ll:confidence-check`
- Verification — `ll-harness`, `/ll:verify-issue-loop`, embedded verification in
  FSM transitions, the verification escalation ladder, the verification-evidence
  bundle
- Observability — `.ll/history.db`, existing agent-quality reporting

## Impact

Converts batch throughput from a volume metric into a quality-adjusted one, and
closes the two cheapest holes in the verification story. Both verification
children are small, deterministic, and testable — the highest
confidence-per-effort items in the set.

## Status

**Open** | Created: 2026-07-27 | Priority: P2
