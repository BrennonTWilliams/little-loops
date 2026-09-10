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

## Steps to Reproduce

1. Push any commit to `main` (or re-run the `unit-tests` workflow).
2. The `unit-tests` job checks out with bare `actions/checkout@v4` — default `fetch-depth: 1`, a shallow clone with only the tip commit.
3. The test suite runs `TestRepoGate::test_no_new_unverifiable_evidence` (`scripts/tests/test_verify_evidence.py`), which invokes `ll-verify-evidence --all --json`; `HistoryIndex` builds its `path -> blob OIDs` map from one `git log --all --raw` pass.
4. Observe: every span quoted from history older than the tip commit is unverifiable — exactly 149 findings beyond baseline — so the gate test fails on every CI run regardless of corpus state.

## Current Behavior

CI's `unit-tests` job (`.github/workflows/ci.yml`) uses bare `actions/checkout@v4`, which defaults to `fetch-depth: 1`. The evidence gate test then runs `ll-verify-evidence --all` against that shallow clone: `HistoryIndex`'s single `git log --all --raw` pass sees only the tip commit, so spans quoted from any earlier artifact state resolve to nothing. The gate reports exactly 149 unverifiable spans and `TestRepoGate::test_no_new_unverifiable_evidence` always fails — the gate is always-red and provides zero regression signal.

## Expected Behavior

- The `unit-tests` checkout uses `fetch-depth: 0` (full history) so `HistoryIndex` sees all commits and the gate passes/fails on actual corpus regressions.
- If the repository is shallow anyway (local shallow clone or a future workflow regression), the gate test detects it up front via `git rev-parse --is-shallow-repository` and fails fast with a one-line diagnostic pointing at the missing fetch-depth, instead of a 149-item findings dump.

## Program Design

### Types

- None — no new data structures; this is a workflow-config change plus a precondition branch in an existing test.

### Signatures

- `test_no_new_unverifiable_evidence(gate_cli: str) -> None` — existing; gains the shallow-repo precondition inline. No new functions.

### Call Path

`pytest` -> `TestRepoGate::test_no_new_unverifiable_evidence` -> `git rev-parse --is-shallow-repository` (new precondition: skip-or-fail-fast with one-line diagnostic) -> `ll-verify-evidence --all --json` -> `HistoryIndex` (`git log --all --raw`)

Workflow side: `.github/workflows/ci.yml` `unit-tests` job, checkout step gains `with: fetch-depth: 0` plus a comment recording why (the gate needs full history).

## Impact

- **Priority**: P2 - The gate is structurally always-red on CI, so it provides zero regression signal there (the very thing it exists for), but local full checkouts are unaffected and no product behavior is wrong.
- **Effort**: Small - Two-line workflow change (`fetch-depth: 0`) plus a small `git rev-parse --is-shallow-repository` precondition in one test.
- **Risk**: Low - No product-code behavior change; full checkout slightly increases CI clone time. The precondition must skip (or fail with the one-line diagnostic) rather than silently pass, so a future fetch-depth regression stays loud.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-10T22:05:39 - `e4ad77c2-694f-4e6b-a115-46d679e823a4.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:18 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
