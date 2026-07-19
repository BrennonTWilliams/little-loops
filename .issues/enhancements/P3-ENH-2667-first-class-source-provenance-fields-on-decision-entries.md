---
id: ENH-2667
title: First-class source_session_id/source_issue_id fields on decision entries (YAML + CLI)
type: ENH
priority: P3
status: done
discovered_date: 2026-07-17
captured_at: '2026-07-17T00:00:00Z'
completed_at: '2026-07-18T03:04:47Z'
discovered_by: split-from-ENH-2464
parent: EPIC-2457
decision_needed: false
labels:
- enhancement
- decisions
- provenance
size: Small
relates_to:
- ENH-2464
---

# ENH-2667: First-class source_session_id/source_issue_id fields on decision entries

## Summary

The **YAML-side, DB-free** half of [[ENH-2464]], carved out so it can land without
touching the `history.db` schema or fighting the EPIC-2457 schema-version-slot race.

Add `source_session_id` and `source_issue_id` as **first-class, typed** fields on the
four decision dataclasses and expose them on `ll-issues decisions add` so any caller can
record decision provenance directly into `.ll/decisions.d/*.json` / `decisions.yaml`.

## Why split this out

- The four dataclasses already round-trip *unknown* keys via their `extra: dict` catch-all,
  so provenance in YAML technically survives today — but only as untyped, undiscoverable
  bag entries with no producer wiring. This issue makes them real fields with a real CLI.
- It has **zero** dependency on the DB mirror, schema migration, or `ll-session --kind
  decision` — those stay in the rescoped [[ENH-2464]], which is deferred pending a
  coordinated EPIC-2457 migration (≈10 siblings contend for the next `SCHEMA_VERSION` slot).
- The capture-bridge skill threading (`--source-session="$SESSION_ID"`) is **not** in
  scope here: no orchestrator session-id env var exists in skill bodies today (verified —
  only `improve-claude-md` self-computes `${SESSION_IDS}` from history). That producer
  wiring stays with [[ENH-2464]].

## Current Behavior

`RuleEntry` / `DecisionEntry` / `ExceptionEntry` / `CouplingEntry` have no typed
provenance fields. Provenance keys only survive via each dataclass's `extra: dict`
catch-all (untyped, undiscoverable), and `ll-issues decisions add` has no flag to set
them — so decision provenance is never actually recorded.

## Expected Behavior

Provenance is a first-class, typed field on every decision entry type and settable from
the CLI: `ll-issues decisions add ... --source-session S --source-issue-id I` writes both
into the entry; legacy entries without them load as `None`; unset fields are omitted from
serialized YAML.

## Scope (what landed)

- `scripts/little_loops/decisions.py` — `source_session_id: str | None = None` and
  `source_issue_id: str | None = None` on `RuleEntry`, `DecisionEntry`, `ExceptionEntry`,
  `CouplingEntry`, with `from_dict()` `.pop()` + omit-when-`None` `to_dict()` (matches the
  existing `issue` / `supersedes` / `outcome` pattern).
- `scripts/little_loops/cli/issues/decisions.py` — `--source-session` / `--source-issue-id`
  flags on the `add` subparser; threaded into all four `_cmd_add` constructors.

## Out of scope (see [[ENH-2464]])

- `decision_events` DB mirror table + `SCHEMA_VERSION` bump + `_KIND_TABLE` registration.
- `record_decision_event()` / `_backfill_decision_events()` in `session_store.py`.
- `history_reader` read API (`find_decisions_for_session` / `find_decisions_for_issue`).
- `ll-session recent/search --kind decision`.
- Skill/command capture-bridge threading of the current session id.

## Acceptance Criteria

- [x] Legacy YAML without the fields loads with `source_* == None` (backward compatible).
- [x] Fields round-trip through save/load on all four entry types.
- [x] Unset fields are omitted from serialized YAML (no bloat).
- [x] `ll-issues decisions add --source-session S --source-issue-id I` records both.
- [x] Tests cover all four dataclasses + CLI plumbing + legacy load.

## Tests

- `scripts/tests/test_decisions.py::TestSourceProvenanceFields` (6 tests).
- `scripts/tests/test_cli_decisions.py::TestDecisionsCLIAdd::test_add_rule_with_source_provenance`
  and `::test_add_rule_without_source_provenance_is_none`.

## Impact

- **Priority**: P3 — additive traceability; unblocks the deferred [[ENH-2464]] producer wiring.
- **Effort**: Small — 4 dataclass field pairs + 2 CLI flags + tests; no schema, no DB.
- **Risk**: Low — all fields optional/nullable; omit-when-`None` keeps legacy YAML unchanged.
- **Breaking Change**: No.

## Scope Boundaries

- Does not add the `decision_events` DB mirror, `SCHEMA_VERSION` migration, read API, or
  `ll-session --kind decision` — those remain in the deferred [[ENH-2464]].
- Does not thread the current session id from skill capture bridges — no orchestrator
  session-id env var exists in skill bodies today; that producer wiring stays with [[ENH-2464]].
- Does not retroactively populate provenance on existing decision entries.

## Status

**Done** | Completed: 2026-07-18T03:04:47Z

## Work Log (session of 2026-07-17 → 2026-07-18)

This issue records the completed slice of a review-and-split session on [[ENH-2464]]:

1. **Reviewed [[ENH-2464]]** ("Backlink decisions.yaml to session/issue") — found it was
   deferred by `rn-implement-20260717T165621` not for quality (readiness 100/100) but
   because it is Very Large and caught in EPIC-2457 `SCHEMA_VERSION`-slot contention
   (re-refined five times chasing 18→20→21→23→25 drift).
2. **Split decision** — carved the DB-free, value-carrying core out of ENH-2464 into this
   issue so it could land immediately without a schema migration.
3. **Implemented the core**:
   - `scripts/little_loops/decisions.py` — added `source_session_id` / `source_issue_id`
     first-class fields to `RuleEntry`, `DecisionEntry`, `ExceptionEntry`, `CouplingEntry`
     with omit-when-`None` round-trip.
   - `scripts/little_loops/cli/issues/decisions.py` — added `--source-session` /
     `--source-issue-id` flags, threaded into all four `_cmd_add` constructors.
4. **Tests**: `test_decisions.py::TestSourceProvenanceFields` (6) + two
   `test_cli_decisions.py::TestDecisionsCLIAdd` cases.
5. **Verified**: 121 passed across both modules; ruff + mypy clean; live-CLI smoke test
   wrote both provenance fields into a `.ll/decisions.d/*.json` fragment.
6. **Rescoped [[ENH-2464]]** to the DB-mirror half only (kept `deferred`), with a split
   banner and an explicit deferral rationale so it is not "invisibly" parked.

## Session Log
- split-from-ENH-2464 - 2026-07-17 - core YAML+CLI slice implemented + verified
- finalize - 2026-07-18T03:04:47Z - marked done, moved to completed/
