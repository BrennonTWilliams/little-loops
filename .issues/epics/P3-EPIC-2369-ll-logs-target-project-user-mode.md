---
id: EPIC-2369
title: "ll-logs Target-Project User Mode"
type: EPIC
priority: P3
status: open
captured_at: "2026-06-28T17:55:50Z"
discovered_date: 2026-06-28
discovered_by: create-epics-from-unparented
relates_to: [FEAT-2315, FEAT-2316, ENH-2317, ENH-2318]
---

# EPIC-2369: ll-logs Target-Project User Mode

## Summary

Transform `ll-logs` from a little-loops-maintainer debugging tool into a first-class surface for target-project users: CWD-scoped defaults, whole-session corpus visibility, per-project work digests, and user-owned failure mining. Includes: FEAT-2315 (ll-logs summary per-project work digest), FEAT-2316 (ll-logs whole-session corpus mode), ENH-2317 (CWD-default scoping and host-awareness), ENH-2318 (retarget scan-failures at user's own failures).

## Children

- **FEAT-2315** — ll-logs summary: user-facing per-project work digest for target projects
- **FEAT-2316** — ll-logs whole-session corpus mode: analyze non-ll tool activity
- **ENH-2317** — ll-logs: CWD-default scoping, --all opt-in privacy, finish host-awareness
- **ENH-2318** — Retarget ll-logs scan-failures at the user's own failures; keep current behavior behind a flag
