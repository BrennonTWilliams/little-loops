---
id: ENH-3733
type: ENH
title: Snapshot export and dashboard usage qualification
priority: P2
status: open
discovered_by: issue-size-review
discovered_date: '2026-10-05'
parent: ENH-3723
decision_needed: false
testable: true
blocked_by:
- ENH-3731
relates_to:
- ENH-3732
- ENH-3543
- ENH-3730
---

# ENH-3733: Snapshot export and dashboard usage qualification

## Summary

Make shareable snapshots and the built-in dashboard honor the shared usage qualification policy. This child routes `_snapshot_usage_selection` and `usage_coverage_audit` through `qualify_usage`, preserves qualification label/reason and a policy version in the export under the privacy allowlist, and updates the built-in dashboard query, visible reasons and custom-SQL guidance. Blocked by ENH-3731.

## Parent Issue

Decomposed from ENH-3723: Canonical usage qualification across source and snapshot consumers. Recorded parent Decision (commit `01747bb96`) applies: legacy NULL/unknown is audit-only; complete estimated rows are labeled numeric consumption; cache rates measured-only.

## Current Behavior

`_snapshot_usage_selection` selects canonical components whenever coverage is non-overlapping, and `usage_coverage_audit` has no qualification/provenance label. A partial/unknown OpenCode-shaped row (input 10, output 2, cache-read 4, cache-creation NULL) is stored as canonical input 10, output 2, cache-read 4; the same holds for a measured partial row with stored cost $1. The dashboard's predefined query and guidance don't distinguish unavailable from observed zero.

## Expected Behavior

- Source and snapshot canonical fields agree under the shared policy. Explicit unknown/partial audit-only rows retain raw values and labeled audit subtotals, but dependent canonical totals/rates are NULL/unavailable with a visible reason; numeric stored cost cannot bypass token/provenance prerequisites.
- Reconcile overlap on the full identity group before filtering; apply provenance/component qualification to the contributors in the requested figure after filtering. An out-of-window audit-only row alone does not taint a different window's figure, while an overlapping counterpart outside the window still prevents coverage certification. Preserve the in-filter population when building grouped totals (model/channel); silently dropping audit-only contributors cannot make the remaining subset a complete figure. A channel subtotal cannot recertify an incomplete model: canonical fields carry the scope (currently model-wide with channel contributions) used for eligibility.
- Coverage-selected rows/counts (including audit-only rows in `selected_usage_events`) stay intact; selection certifies overlap only. No selected observations is unavailable/empty; a qualified observed zero stays numeric zero; a zero rate denominator is unavailable.
- Extend `_SHAREABLE_COLUMNS` and schema only as needed to preserve the qualification label/reason; export only bounded accounting reason codes — never source paths, native request/session identities, credentials or source-derived diagnostic text. Record a safe qualification-policy version in snapshot metadata so retained snapshots don't imply a later policy. Computed columns/metadata don't require a source-history migration (any needed schema extension takes the next append-only version). Keep existing public numeric keys; expose audit subtotals distinctly; provenance pointers, availability, text suffixes and reason codes agree with the JSON values.
- Built-in dashboard queries expose qualification codes/reasons and distinguish unavailable from observed zero. Custom SQL stays an audit tool: document that a bare `SUM` of selected rows or NULLs does not establish completeness, without rewriting user SQL or adding a query engine. Correct the existing dashboard guidance.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/queries.py` — `_snapshot_usage_selection`, `usage_coverage_audit`, `_SHAREABLE_COLUMNS`, policy-version metadata.
- `scripts/little_loops/templates/dashboard.llat/template.html.j2` — predefined `usage_coverage_audit` query, qualification/reason display, custom-SQL guidance; inspect `cli/artifact/dashboard.py` if generated metadata changes require it.

### Dependent Files

- `scripts/little_loops/token_provenance.py`, `history_reader/usage.py` — consumed from ENH-3731; no changes here.

### Tests

- `scripts/tests/test_enh3543_snapshot_usage.py`, export allowlist/privacy tests, `test_feat3304_artifact_dashboard.py`, runtime tests under `scripts/tests/js/feat3304/`. Source/snapshot filter tests distinguish an out-of-window audit-only row from an out-of-window overlapping counterpart; model/channel aggregates pass the same matrix as ENH-3731; exercise actual consumers.

### Documentation

- `docs/reference/API.md` (snapshot contract, policy version, custom-SQL guidance), `docs/reference/CLI.md` where snapshot figures are described.

## Acceptance Criteria

- [ ] Source and snapshot canonical fields agree under the shared policy; audit-only partial rows keep raw values and audit subtotals with unavailable canonical totals/rates and a visible reason.
- [ ] Source and snapshot preserve coverage reconciliation before report filters; an excluded overlapping counterpart cannot make the remaining group canonical; empty selection is unavailable/empty while a qualified all-zero returns zero; zero denominator leaves its rate unavailable.
- [ ] Snapshot export carries safe qualification metadata and a policy version, passes allowlist/privacy tests, and introduces no native IDs, source paths or credentials; coverage-selected rows/counts remain intact with qualification evaluated separately; provenance pointers, availability, text suffixes and reason codes agree with JSON.
- [ ] Built-in snapshot/dashboard aggregates preserve the requested population, show qualification/reasons and distinguish empty/unavailable from observed zero; model/channel aggregates cannot recertify an incomplete model; custom-SQL guidance documents that arbitrary subset sums don't certify totals, with no SQL rewriting or new query engine.
- [ ] Source readers, built-in snapshots/dashboard and the stored session reader agree, allowing only documented stricter measured-only rates; derived sums preserve missingness.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **Out of scope:** qualification core, selectors and source readers (ENH-3731), quality (ENH-3732), a source-history migration, rewriting custom SQL, ENH-3730's gate redesign.

## Session Log

- `/ll:issue-size-review` - 2026-10-05T00:00:00 - `<session-dir>/session.jsonl`

## Status

**Open** | Created: 2026-10-05 | Priority: P2
