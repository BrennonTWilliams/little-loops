---
id: ENH-2199
type: ENH
priority: P3
status: done
captured_at: 2026-06-16 18:21:36+00:00
discovered_date: 2026-06-16
discovered_by: scope-epic
parent: EPIC-2196
labels:
- hermes
- cli
- json
- contract
---

# Document and guarantee `--json` output contract stability

## Summary

Hermes consumes the `--json` output of `ll-loop list`, `ll-loop status`, and
`ll-issues list` for portfolio sync and the `ll_status`/`ll_portfolio` tools.
These `--json` outputs exist but have no documented schema or stability
guarantee, so a future field rename or shape change would silently break the
integration. Document the JSON shape for each of these three surfaces and add
snapshot tests that fail on unannounced breaking changes. Source:
`PRD-Hermes-Integration-v4.md` (EG-3).

## Current Behavior

`ll-loop list --json`, `ll-loop status --json`, and `ll-issues list --json` produce JSON output consumed by Hermes, but:

- No schema or field documentation exists for any of these surfaces.
- No stability guarantee is defined — field renames, removals, or type changes can be made without warning.
- Hermes consumers have no way to detect breaking changes at integration time; failures surface silently at runtime.

## Expected Behavior

- The JSON output shape for `ll-loop list --json`, `ll-loop status --json`, and
  `ll-issues list --json` is documented (fields, types, semantics) in a reference doc.
- Snapshot tests assert the JSON shape for each command and fail when a field is
  removed, renamed, or retyped.
- A short stability note states what callers (e.g. Hermes) may rely on and how
  additive vs. breaking changes are signaled.

## Motivation

Hermes depends on `--json` CLI output for portfolio sync and the `ll_status`/`ll_portfolio` tools. Without a documented contract and snapshot test coverage, any refactor of the CLI handlers can silently break the Hermes integration — regressions only surface at integration test time or in production. This is a blocking gap for the Hermes Integration Enablement epic (EPIC-2196, EG-3 from `PRD-Hermes-Integration-v4.md`).

## Proposed Solution

1. Audit the current JSON output of `ll-loop list --json`, `ll-loop status --json`, and `ll-issues list --json` to capture the de-facto schema for each surface.
2. Document each schema in `docs/reference/json-output-contracts.md` with field names, types, and semantics.
3. Add a stability policy: additive fields (new keys) are non-breaking; removals, renames, and retypes are breaking changes requiring a migration note.
4. Add snapshot tests in `scripts/tests/` for each command that assert the JSON shape and fail on breaking changes.

Wiring points: list/status handlers under `scripts/little_loops/cli/loop/`, `scripts/little_loops/cli/issues/__init__.py`, and reference doc under `docs/reference/`.

## API/Interface

Three JSON surfaces to document and snapshot-test:

- **`ll-loop list --json`** — handlers in `scripts/little_loops/cli/loop/`
- **`ll-loop status --json`** — handlers in `scripts/little_loops/cli/loop/`
- **`ll-issues list --json`** — handler in `scripts/little_loops/cli/issues/__init__.py`

Stability contract:
- **Non-breaking**: additive new fields
- **Breaking** (requires announcement): field removal, rename, or type change

## Implementation Steps

1. Run all three commands and capture their current JSON output to establish the baseline schema.
2. Create `docs/reference/json-output-contracts.md` documenting each surface's fields, types, semantics, and stability policy.
3. Add snapshot tests in `scripts/tests/` for each command's `--json` output.
4. Verify tests fail on a simulated breaking change (e.g., rename or remove a field in a local branch).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/` — list/status handlers (source of truth for JSON shape)
- `scripts/little_loops/cli/issues/__init__.py` — list handler (source of truth for issues JSON shape)
- `docs/reference/json-output-contracts.md` — new reference doc to create

### Dependent Files (Callers/Importers)
- Hermes integration tools (`ll_status`, `ll_portfolio`) — primary consumers of this JSON output
- Portfolio sync logic in Hermes — depends on `ll-loop list --json` and `ll-issues list --json`

### Similar Patterns
- `scripts/little_loops/cli/` — other `--json` output handlers for consistency reference

### Tests
- `scripts/tests/` — new snapshot tests for each of the three `--json` surfaces

### Documentation
- `docs/reference/json-output-contracts.md` — primary deliverable

### Configuration
- N/A

## Scope Boundaries

- **In scope**: documenting and snapshot-testing the JSON output of the three named commands (`ll-loop list`, `ll-loop status`, `ll-issues list`).
- **Out of scope**: changing the JSON schema itself (document current shape only); versioning infrastructure or semver enforcement; other CLI commands not consumed by Hermes; runtime validation of Hermes tool inputs.

## Impact

- **Priority**: P3 — Hermes integration is ongoing; missing contract stability is a latent risk that grows as more Hermes tooling is added.
- **Effort**: Small — audit + doc + snapshot tests; no behavioral changes to existing code.
- **Risk**: Low — documentation and test-only additions; no changes to runtime behavior.
- **Breaking Change**: No

**Open** | Created: 2026-06-16 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-16T18:29:03 - `652072f2-a11c-4dd7-9a33-67f1e5b1a03c.jsonl`
