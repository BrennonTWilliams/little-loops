---
id: ENH-2472
title: Windows compatibility testing
type: ENH
priority: P4
status: open
captured_at: "2026-07-03T00:00:00Z"
discovered_date: 2026-07-03
discovered_by: capture-issue
parent: EPIC-1967
relates_to: []
labels:
  - testing
  - windows
  - portability
  - captured
---

# ENH-2472: Windows compatibility testing

## Summary

CHANGELOG's Planned section has carried "Windows compatibility testing" with no
backlog issue behind it. This is that issue. Establish what actually works on
Windows and add regression coverage for it: path handling (`pathlib` vs
hard-coded `/`), subprocess/shell assumptions (bash-isms in hooks and FSM
`shell` states), file locking (`.issues/.issue-id.lock`), and console encoding.

## Scope

- Inventory bash-dependent surfaces (hooks/, FSM `shell` states, scratch-pad redirects) and classify each as: works under Git Bash/WSL, needs a shim, or documented not-supported.
- Run `python -m pytest scripts/tests/` on a Windows environment (contributor machine or local VM — no hosted CI per Testing & CI Policy) and record the failure set.
- Fix cheap portability bugs (path separators, `tempfile` usage, encoding); file follow-ups for structural ones.
- Document the support tier in `docs/development/TROUBLESHOOTING.md` (supported / supported-under-WSL / unsupported).

## Current Behavior

Windows support is unknown and untested: no compatibility matrix, no documented support tier, and "Windows compatibility testing" existed only as an untracked CHANGELOG Planned line.

## Expected Behavior

A recorded test-suite matrix on Windows/WSL, cheap portability fixes landed, structural gaps filed as issues, and the support tier documented.

## Acceptance Criteria

- A recorded pass/fail matrix for the test suite on Windows (native and/or WSL).
- Portability quick-fixes landed; remaining gaps filed as issues with the matrix as evidence.
- Docs state the supported tier explicitly.
- CHANGELOG Planned line points at this issue.

## Scope Boundaries

- **In**: compatibility inventory, test-suite matrix on Windows/WSL, cheap portability fixes, support-tier docs.
- **Out**: hosted CI (prohibited by Testing & CI Policy); full native-Windows support for bash-dependent hooks (file follow-ups instead).

## Impact

- **Priority**: P4 — no known Windows users blocked; converts an untracked CHANGELOG line into real scope
- **Effort**: Medium — inventory + matrix run + cheap fixes
- **Risk**: Low — additive tests and docs
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-03 | Priority: P4

## Session Log

- backlog-grooming - 2026-07-03T00:00:00Z - Filed from CHANGELOG § Planned (previously untracked line).
