---
id: ENH-3064
title: 'stale_symbol_ref: exclude forward-reference sections from claim extraction'
type: ENH
priority: P3
status: open
discovered_by: manage-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T00:00:00Z'
relates_to:
- ENH-3047
- FEAT-3048
labels:
- issues
- gates
decision_needed: false
testable: true
---

# ENH-3064: Scope `stale_symbol_ref` extraction away from forward-looking sections

## Summary

`extract_symbol_claims()` (`scripts/little_loops/issues/symbol_claims.py:123`) scans an
issue's **entire body** with no section scoping. A measured sweep of all 72 active issues
(via `ll-issues format-check --all --format json`, recorded in ENH-3047) found
`stale_symbol_ref` fires on 46% of them (33/72), and spot-checks showed the dominant cause is
not a real false claim but a **forward reference**: symbols/functions an issue proposes to
*create* under `## Program Design § Signatures`, `### Files to Modify`, or
`## Implementation Steps`, which do not resolve yet by design.

Two concrete examples from ENH-3047's own research:

- FEAT-2942 reports `add_epic_consistency_parser` and `cmd_epic_consistency` as stale —
  both are functions FEAT-2942 proposes to add, not ones it claims already exist.
- ENH-3047 itself reported `missing_behavior_parity` as a stale symbol — it is a
  `FormatGaps` dataclass field name the issue's own test plan says to assert on, not a def-site
  claim.

## Current Behavior

`extract_symbol_claims()` has no concept of "planning" vs. "as-is" sections. Any symbol-shaped
token attributed to a file within `_MAX_ATTRIBUTION_DISTANCE` (80 chars) of a file reference is
extracted as a claim and checked against the current codebase, regardless of which section it
appears in.

## Expected Behavior

Reduce the false-positive rate on forward-looking sections, via one (or a combination) of:

- **Section scoping**: exclude `## Program Design § Signatures`, `### Files to Modify`, and
  `## Implementation Steps` (or a documented equivalent heading set) from extraction entirely.
- **Forward-reference discriminator**: detect verbs/phrasing that mark a symbol as
  prospective ("will add", "proposes to add", "to create", "new function") near the
  attribution and skip those matches.

Either approach should materially reduce the 46% `stale_symbol_ref` rate measured in
ENH-3047 § Why Claims Are a Cap, Not an Override, without suppressing genuine false claims
about existing code (e.g. FEAT-2942's real error citing a nonexistent function as already
present in a file it does not propose to change).

## Motivation

ENH-3047 wired `stale_symbol_ref`/`stale_cli_flag` into `/ll:confidence-check` as a
Criterion 4 **cap**, deliberately *not* a hard `STOP` override, specifically because this
detector's precision on forward-looking issues was too low to gate on. That issue named this
as the explicit follow-up: fix the false-positive class first, then revisit whether
`stale_cli_flag` (currently 10% of active issues, a sharper signal — "no such subcommand" is
less ambiguous than an unresolved symbol) is ready to become a hard override.

## Scope Boundaries

**In scope:** `extract_symbol_claims()` and its section/phrasing discrimination logic.

**Explicitly out of scope:**
- Any change to `/ll:confidence-check`'s cap/override wiring (ENH-3047's territory) — this
  issue only improves the detector's precision; whether that earns a stricter consumer gate
  is a separate future decision.
- `stale_cli_flag` detection logic, unless the same section-scoping fix naturally covers it.

## Acceptance Criteria

1. Re-running `ll-issues format-check --all --format json` after the fix shows a materially
   lower `stale_symbol_ref` rate than the 46% (33/72) baseline recorded in ENH-3047's Blast
   Radius table — record the new count/percentage in this issue on completion.
2. FEAT-2942's `add_epic_consistency_parser`/`cmd_epic_consistency` forward-reference gaps no
   longer appear in its `stale_symbol_ref` list.
3. A genuine false claim (an issue asserting an existing function that does not exist, outside
   any forward-looking section) still triggers `stale_symbol_ref` — add a regression test
   fixture for this so the fix does not overcorrect to silence.
4. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — improves detector precision behind an already-shipped soft cap; not
  blocking any other issue.
- **Effort**: Low-Moderate — scoped to `symbol_claims.py`'s extraction logic and its test file.

## Status

**Open** | Created: 2026-08-05 | Priority: P3
