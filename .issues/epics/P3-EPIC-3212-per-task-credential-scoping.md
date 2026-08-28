---
id: EPIC-3212
title: Per-Task Credential Scoping
type: EPIC
priority: P3
status: open
captured_at: "2026-08-16T16:53:55Z"
discovered_date: 2026-08-16
discovered_by: link-epics
relates_to: []
---

# EPIC-3212: Per-Task Credential Scoping

## Summary

Group of 3 related issues: Declare and enforce per-task credential scope via deny-by-default env projection, Record the credential scope a run was granted for after-the-fact audit, Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation.

## Children

- **ENH-3203** — Declare and enforce per-task credential scope via deny-by-default env projection (done — decomposed into ENH-3233/3234/3235)
  - **ENH-3233** — Deny-by-default env projection core: chokepoint, credential-scope registry, and baseline (open)
  - **ENH-3234** — ActionSpec credential scope declaration and runner_spec.py wiring (open, blocked by ENH-3233)
  - **ENH-3235** — FSM StateConfig credential scope declaration and fsm/runners.py wiring (open, blocked by ENH-3233)
- **ENH-3204** — Record the credential scope a run was granted for after-the-fact audit (open, blocked by ENH-3233/3234/3235)
- **ENH-3205** — Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation (open, blocked by ENH-3233/3235)
