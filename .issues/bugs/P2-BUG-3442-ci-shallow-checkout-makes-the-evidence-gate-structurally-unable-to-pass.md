---
id: BUG-3442
type: BUG
title: CI shallow checkout makes the evidence gate structurally unable to pass
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# BUG-3442: CI shallow checkout makes the evidence gate structurally unable to pass

## Summary

ci.yml unit-tests uses bare actions/checkout@v4 (fetch-depth 1), collapsing the `git log --all --raw` HistoryIndex 65x so ll-verify-evidence reports exactly 149 unverifiable spans and TestRepoGate::test_no_new_unverifiable_evidence always fails, providing zero signal. Add fetch-depth: 0 with a comment recording why, and add a `git rev-parse --is-shallow-repository` precondition to the gate test that fails loudly with a one-line diagnostic instead of a 149-item mystery (A1).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]


## Session Log
- `/ll:scope-epic` - 2026-09-10T21:15:18 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
