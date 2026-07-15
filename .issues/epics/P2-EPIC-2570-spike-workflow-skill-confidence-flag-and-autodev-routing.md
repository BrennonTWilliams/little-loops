---
id: EPIC-2570
title: Spike Workflow — Skill, Confidence Flag & Autodev Routing
type: EPIC
priority: P2
status: open
discovered_date: 2026-07-10
discovered_by: link-epics
labels: [epic, skills, confidence, autodev, risk-reduction, captured]
relates_to: [FEAT-2567, ENH-2569, ENH-2568, BUG-2654]
---

# EPIC-2570: Spike Workflow — Skill, Confidence Flag & Autodev Routing

## Summary

Close the last unhandled outcome-confidence failure mode — an unprecedented **internal** mechanism with no test coverage of its risky core — by giving the codebase a first-class spike workflow. The three children cover the full path from manual to automated: a `/ll:spike` skill that plans/implements/verifies a code spike (FEAT-2567), a `/ll:confidence-check` phase that detects this failure mode and sets `spike_needed: true` from frontmatter (ENH-2569), and autodev routing plus a reusable `spike-gate.yaml` wrapper loop that consumes that flag to gate implementation loops automatically (ENH-2568).

Together these mirror the existing external-API remediation lattice (`/ll:explore-api` + `assumption-firewall.yaml` + `proof-first-task.yaml`) for the internal-mechanism case, converting today's ad-hoc "you should spike this" coding-agent advice into a measured, machine-readable, and eventually automated remedy.

## Motivation

Captured 2026-07-10 from the ENH-2565 spike discussion (`rn-refine` `synth_pop` concurrency core, outcome-confidence 66/100). `triage_outcome_failure`'s existing remedies — decide / wire+refine / size-review — don't cover "zero precedent + no test of risky core," and `/ll:explore-api` covers only external-API assumptions. ENH-2565's spike plan is the golden template FEAT-2567 should generalize.

## Children

- **FEAT-2567** (P2) — `/ll:spike` skill: plan/implement/verify a code spike for unprecedented internal mechanisms; one-spike-per-issue via `spike_attempted`/`spike_completed` frontmatter.
- **ENH-2569** (P3, unblocked) — new Phase 4.10 in `/ll:confidence-check` sets `spike_needed: true` from Outcome Risk Factor signal phrases, with external-API suppression. Measurement-first: land alone, record backlog fire rate.
- **ENH-2568** (P3, blocked by FEAT-2567 + ENH-2569) — autodev `triage_outcome_failure` gains `check_spike_needed` → `run_spike` → `rerun_confidence_after_spike`; new `spike-gate.yaml` wrapper loop shaped on `proof-first-task.yaml`.
- **BUG-2654** (P3) — follow-up: the ENH-2640 spike gate is only wired on the no-decision (`triage_outcome_failure`) path, so a `decision_needed`+`spike_needed` issue on the decide path skips as `low_readiness` without ever reaching `run_spike`. Extend the gate to the decide/size-review skip path.

## Scope

### In scope

- `/ll:spike` skill and its plan/implement/verify contract (FEAT-2567)
- Phase 4.10 flag-detection logic in `/ll:confidence-check` (ENH-2569)
- Autodev triage routing and `spike-gate.yaml` wrapper loop (ENH-2568)

### Out of scope

- Changes to the external-API remediation lattice (`/ll:explore-api`, `assumption-firewall.yaml`) — already handled
- Retroactively spiking existing low-confidence issues outside of normal triage

## Implementation Order

1. **FEAT-2567** and **ENH-2569** land in parallel — the skill and the detection flag have no dependency on each other.
2. **ENH-2568** last, once both are in place and `spike_needed` fire rate has been observed, so routing complexity is justified by measured backlog data rather than assumption.
