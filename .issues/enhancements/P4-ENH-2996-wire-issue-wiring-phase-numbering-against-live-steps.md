---
id: ENH-2996
status: open
priority: P4
captured_at: "2026-08-02T13:43:01Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to: [ENH-2995]
---

# wire-issue's Wiring Phase numbers against live steps only

## Summary

`/ll:wire-issue` Phase 8b appends a `### Wiring Phase` whose entries continue
the numbering of the existing `## Implementation Steps` list. When some of
those earlier steps have been refuted by a prior `/ll:refine-issue` pass, the
continued numbering asserts a sequence that includes dead steps.

## Current Behavior

`skills/wire-issue/SKILL.md:383-396` (Phase 8b) instructs:

```markdown
### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

N. Update `path/to/caller.py` — adjust calls to `changed_function()` with new signature
N+1. Update `tests/test_affected.py` — adapt existing tests to new behavior
```

`N` continues from the existing list's last number, with no check on whether
those steps are still live.

Observed in `ENH-2500`
(`.issues/enhancements/P3-ENH-2500-per-run-dir-pending-file-and-scope-for-prompt-across-issues.md:287-298`):
the Wiring Phase is numbered 10-17, continuing a 1-9 list in which steps 1, 3,
6 and 7 are each explicitly refuted by an intervening
`### Codebase Research Findings` block ("Revised step 1: **omit entirely**",
"Step 6 target file is wrong"). The numbering presents a 17-step plan of which
four steps are dead.

## Expected Behavior

The Wiring Phase either:
- numbers against live steps only (skipping refuted ones), or
- uses an independent, unnumbered or letter-keyed list that makes no claim
  about position in the parent sequence.

The second is simpler and does not require wire-issue to re-derive which steps
are live.

## Motivation

Low severity on its own — the numbering is cosmetic and the wiring entries
themselves are sound (a corpus check found only 2% of 9,377 wiring bullets are
explicitly no-op, so wire-issue is not padding). The value is in not
compounding ENH-2995's contradiction problem with a numbering scheme that
implies the dead steps are part of the sequence.

## Proposed Solution

Two options, only one of which needs ENH-2995's superseded markers:

**Option A**: Wiring Phase entries become an unnumbered bulleted list, or
letter-keyed (`W1`, `W2`, …), making no positional claim. Zero dependency on
detecting live steps; shippable independently of ENH-2995.

**Option B**: wire-issue skips superseded-marked steps when computing `N`.
Requires ENH-2995's marker to exist and be parseable.

Option A is recommended — it removes the false claim rather than computing a
truer one, and the Wiring Phase is a distinct set of touchpoints that does not
genuinely need to interleave with the parent sequence.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 8b (lines 383-396)

### Dependent Files (Callers/Importers)
- `skills/wire-issue/output-report.md` — if the report template references
  step counts or numbering
- TBD — use grep to find references

### Similar Patterns
- `commands/refine-issue.md:425-442` — Implementation Steps enrichment rules
  and the "Constraints, Not Recipes" register guidance on when imperative
  sequencing is legitimate at all

### Tests
- TBD — identify test files to update

### Documentation
- TBD — docs that need updates

### Configuration
- N/A

## Implementation Steps

TBD — requires codebase analysis

## Impact

- Cosmetic correctness in issues that have been through both refine and wire.
- Small: affects the 1,140 issues carrying a wiring marker, only where refine
  also deposited a contradiction.

## Success Metrics

- A wire pass over an issue with refuted steps produces a Wiring Phase that
  makes no false positional claim.

## Scope Boundaries

- Does **not** change what wire-issue discovers or how it writes Integration
  Map entries — the coupling findings are sound and stay as-is.
- Does **not** address wiring-block accumulation (that is ENH-2993's optional
  second half).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/wire-issue/SKILL.md` | Contains Phase 8b, the section being changed |
| `commands/refine-issue.md` | Source of the refuted-step condition |

## Session Log
- `/ll:capture-issue` - 2026-08-02T13:45:57 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
