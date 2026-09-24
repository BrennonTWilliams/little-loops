---
id: ENH-3575
type: ENH
title: Structured policy gate field replacing prose gate-phrase grep in autodev
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
blocks:
- ENH-3577
---

# ENH-3575: Structured policy gate field replacing prose gate-phrase grep in autodev

## Summary

Autodev detects policy-gated issues by grepping the **whole issue file** for gate phrases
(e.g. "evidence gate", "gate opens", "do not implement before"). It does this in
`check_gate_at_dequeue` (ENH-3148) and again, duplicated inline, in
`recheck_after_size_review`'s `GATE_MARKER` (BUG-3147). A match defers the issue as
`blocked_by_gate` without checking whether the gate is already satisfied, or whether a spike
or learning test could satisfy it. Historical findings, quoted requirements and resolved-gate
notes keep matching, so an issue can stay parked forever unless someone deletes useful
history just to change a routing verdict.

ENH-3148 explicitly left a structural frontmatter gate field out of scope, naming it the
preferred signal.

## Current Behavior

Any occurrence of a gate phrase, current or historical, parks the issue.

## Expected Behavior

Gate state is explicit and routable. External or manual prerequisites park the issue. Proof
obligations that a spike or `explore-api` can satisfy route to that remedy. Satisfied gates do
not block.

## Motivation

False-positive gate matches park good issues indefinitely, and the only workaround (deleting history) destroys useful context.

## Proposed Solution

Add a structured frontmatter field, e.g.
`gate: {kind: external|manual|proof, satisfied: bool, evidence: <ref>, owner: <who>}` (or a
list). Autodev reads the field first and falls back to the prose grep only when the field is
absent. Extract the duplicated phrase regex into one shared helper (a new `ll-issues` gate-check subcommand), which is the extraction BUG-3147 and ENH-3148 deferred.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `check_gate_at_dequeue`, `recheck_after_size_review`
- `scripts/little_loops/cli/issues/` — new gate helper
- `scripts/little_loops/config-schema.json` / frontmatter validation if the field is schema'd

### Dependent Files (Callers/Importers)
- `defer_gated`, `mark_gate_blocked` ledgers

### Similar Patterns
- `ll-issues check-flag`, `ll-issues check-readiness`

### Tests
- `scripts/tests/test_autodev_loop.py` — `TestCheckGateAtDequeueMarkerLiterals`

### Documentation
- `docs/reference/DEFERRAL_CODES.md` (`blocked_by_gate`)

### Configuration
- N/A

## Implementation Steps

1. Define the frontmatter `gate` schema (and validation in `ll-issues`)
2. Add a shared gate-check helper that reads structured first, then falls back to prose
3. Replace both inline regexes in autodev
4. Route `proof` gates to spike/explore-api
5. Tests for satisfied, external and proof gates

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low. The fallback keeps today's behavior for issues without the field.

## Scope Boundaries

- In scope: autodev's two gate detectors and the new field.
- Out of scope: migrating existing issues' prose gates to the field (the fallback covers them); rn-* loops' gate handling.

## Acceptance Criteria

- [ ] A satisfied structured gate does not defer the issue
- [ ] A `proof` gate routes to spike/explore-api rather than parking
- [ ] One shared gate-detection helper; no duplicated phrase regex in autodev

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
