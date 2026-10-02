---
id: EPIC-3694
title: Autodev Gate & Citation False-Failure Hardening
type: EPIC
priority: P3
status: open
captured_at: "2026-10-02T17:34:29Z"
discovered_date: 2026-10-02
discovered_by: link-epics
relates_to: []
---

# EPIC-3694: Autodev Gate & Citation False-Failure Hardening

## Summary

Group of related issues about autodev/refine gates failing on non-defects: env leakage into the quality gate's test run, transient corpus-ratchet test failures, verify-issues citation checking instability, and missing repair routes for citation-only / coverage-gap verify findings.

## Children

Recommended order (reviewed 2026-10-02 with an Opus second opinion): **BUG-3689 → ENH-3697 → BUG-3691 → ENH-3690**; BUG-3695 is independent.

1. **BUG-3689** — Autodev quality gate false-fails on env leakage (11 env-driven tests; shared `HERMETIC_ENV_VARS` constant + gate `unset` + `pin_terminal_size`) (open, P2)
2. **ENH-3697** — Make corpus-ratchet gate tests read the committed `.issues` tree, not the working tree (open, P3) — supersedes ENH-3692
3. **BUG-3691** — verify-issues citation checking is unstable across passes (open, P3) — **rescoped**: extend `ll-issues format-check` (defined-in vs imported-in rule, line-past-EOF, bare-filename resolution) and make `verify-issues` consume its keys; no new CLI
4. **ENH-3690** — refine-to-ready-issue: NON_VALID citation-only findings get a repair route (open, P3) — `blocked_by: BUG-3691`; Option B revised to gate on deterministic format-check keys
5. **BUG-3695** — refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue cannot add Acceptance Criteria (open, P3) — independent sibling of ENH-3690 (same "verdict has no working remedy" class); not part of this review round
- ~~**ENH-3692**~~ — baseline-aware code-run-gate (**cancelled**, won't-do): the two motivating "pre-existing" failures pass on a clean `main` and only went red from uncommitted `.issues/` working-tree state, so the mechanism could not have rescued them and carried High masking risk; superseded by ENH-3697.
- **BUG-3702** — refine_followup evidence-delta snapshot vanishes from shared scratch dir mid-state (open)


## Acceptance Criteria

- A rerun of the BUG-3688 scenario reaches the quality gate green: none of the 11 env-sensitive tests fail with `LL_PYTHON` and a wide `COLUMNS` set, and the two corpus-ratchet tests do not fail from uncommitted `.issues/` edits.
- Repeated `verify-issues --check` passes over an unchanged issue give identical citation verdicts (a citation defect such as the BUG-3689 pass-3 case surfaces on pass 1).
- A run whose only verify findings are deterministic citation-shaped findings is repaired in-loop rather than ending `GATE_UNMET`; premise-changing findings still persist as `NON_VALID`.