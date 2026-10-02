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

Group of 4 related issues about autodev/refine gates failing on non-defects: Autodev quality gate false-fails on env leakage and pre-existing test failures, code-run-gate baseline-aware failure, verify-issues citation checking instability, and a repair route for NON_VALID citation-only findings.

## Children

- **BUG-3689** — Autodev quality gate false-fails on env leakage and pre-existing test failures (open)
- **ENH-3692** — code-run-gate: fail only on test failures new relative to the base SHA (baseline-aware gate) (open)
- **BUG-3691** — verify-issues citation checking is unstable across passes (open)
- **ENH-3690** — refine-to-ready-issue: give NON_VALID citation-only findings a repair route (open)
- **BUG-3695** — refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue cannot add Acceptance Criteria (open)
- **ENH-3697** — Make corpus-ratchet gate tests read the committed .issues tree, not the working tree (open)
