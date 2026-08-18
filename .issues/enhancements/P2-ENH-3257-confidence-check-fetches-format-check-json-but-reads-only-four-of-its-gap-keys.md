---
id: ENH-3257
type: ENH
title: confidence-check fetches format-check JSON but reads only four of its gap keys
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-18'
captured_at: '2026-08-18T20:48:37Z'
parent: EPIC-2856
testable: true
relates_to:
- BUG-3249
- ENH-3256
- ENH-3248
- ENH-3247
- ENH-3047
- ENH-2852
---

# ENH-3257: confidence-check fetches format-check JSON but reads only four of its gap keys

## Summary

`/ll:confidence-check` Phase 1.6 fetches the complete `format-check` JSON payload
once (`skills/confidence-check/SKILL.md:138`) and reuses it in Phase 1.8 rather
than re-invoking the CLI. Between the two phases it extracts exactly four keys:

| Phase | Key | Effect |
|---|---|---|
| 1.6 | `program_design_nonspecific` | `PD_GAP` display detail |
| 1.6 | (`ll-issues check-design` exit) | `PD_FAIL` — can force STOP |
| 1.8 | `missing_behavior_parity` | `PARITY_GAP` |
| 1.8 | `stale_symbol_ref` + `stale_cli_flag` | `CLAIM_GAP` — advisory only, explicitly cannot escalate to STOP (`:204-207`) |

`template_placeholders`, `boilerplate`, and `missing` are never read — grep
across the whole `skills/confidence-check/` directory returns no hits. The
payload containing them is already in `$FC_JSON`; the data is fetched and
discarded.

Observed on BUG-3249, which scored `confidence_score: 100` /
`outcome_confidence: 99` while `ll-issues format-check BUG-3249` reported:

```
  missing: Steps to Reproduce
  boilerplate: Impact
  template_placeholders: Motivation: [Why this issue matters - business value, ...]
  template_placeholders: Impact: [P0-P5]
  template_placeholders: Impact: [Justification]
  template_placeholders: Impact: [Small/Medium/Large]
  template_placeholders: Impact: [Low/Medium/High]
  template_placeholders: Impact: [Yes/No]
```

The sibling loop already treats one of these as routable: ENH-3248 added a
`check_placeholders` state (`scripts/little_loops/loops/refine-to-ready-issue.yaml:371-396`)
that reads `template_placeholders` via `--format json` and forces a refine. That
signal is gated in the *loop* but not in the *skill*, so a standalone
`/ll:confidence-check` sails past debris the loop would bounce.

Proposed direction: extract `template_placeholders` / `boilerplate` / `missing`
from the already-captured `$FC_JSON` in Phase 1.6 and feed them as a cap on
Criterion 4, mirroring exactly how `CLAIM_GAP` works today (advisory cap, not a
STOP escalation). No new CLI call and no re-derived predicate — `format-check`
stays the single source of truth.

Related: BUG-3249 (the instance), ENH-3248 (`check_placeholders`, the loop-side
precedent), ENH-3247 (`format-check --fix` repairing structural debris),
ENH-2852 (built the Phase 1.6 pre-fetch gate this extends), ENH-3047 (added the
Phase 1.8 keys, the pattern to follow).


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-08-18T20:48:47 - `fdfd9556-8841-4d2f-baeb-50bd68feb80e.jsonl`
