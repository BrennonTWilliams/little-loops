---
id: ENH-2993
status: open
priority: P3
captured_at: "2026-08-02T13:43:01Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to: [ENH-2995, ENH-2992]
---

# Fold repeated Codebase Research Findings blocks into one per section

## Summary

Each `/ll:refine-issue` pass appends a fresh `### Codebase Research Findings`
subsection rather than merging into the one already present under the same H2.
Across repeated passes these accumulate — one issue carries **12** separate
blocks. Fold on write: one findings block per parent H2, with new bullets
merged into the existing block.

## Current Behavior

`commands/refine-issue.md` § Preservation Rule (lines 444-460) instructs each
pass to append a marked subsection:

```markdown
### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_
```

There is no instruction to detect an existing block under the same H2 and merge
into it, so every pass creates a new one.

Measured across `.issues/` (2026-08-02):

| refine+wire passes | issues | median lines | ≥ share in appended blocks |
|---|---|---|---|
| 0 | 1,175 | 123 | 0% |
| 1 | 152 | 156 | 0% |
| 2 | 176 | 182 | 7% |
| 3 | 126 | 192 | 8% |
| 4 | 146 | 205 | 8% |
| 5+ | 1,119 | 263 | 17% |

(The share column is a lower bound — the measurement stops each block at the
next heading, so nested content is undercounted.)

Worst offenders by block count:

| Blocks | Issue |
|---|---|
| 12 | `ENH-2500` per-run-dir pending file and scope for prompt-across-issues |
| 12 | `ENH-2514` ll-loop flush audit trail on forced termination |
| 10 | `ENH-2511` capture mcp tool call telemetry |
| 10 | `ENH-2495` record session lifecycle handoff events |
| 9 | `ENH-2492` capture orchestration run outcomes into history db |

`ENH-2500` alone carries 5 blocks under distinct H2s plus repeats, at 364 total
lines.

## Expected Behavior

Before appending, refine checks whether a `### Codebase Research Findings`
subsection already exists under the target H2. If so, it appends its new
bullets to that block instead of creating a sibling. Result: at most one
findings block per H2, regardless of pass count.

## Motivation

Two costs, both borne by the implementer:

1. **Reading cost.** Five sibling blocks under one section means the reader
   must hold all five to know the current state of a claim — and later blocks
   frequently supersede earlier ones (24% of refined issues contain correction
   language; see ENH-2995).
2. **Context cost.** A 263-line median at 5+ passes against a 123-line
   unrefined baseline is a real token load on every headless session that reads
   the issue, and on every subsequent refine/confidence-check pass that reads
   it back.

Folding is purely additive-safe: no bullet is dropped, only relocated into the
sibling block that already exists.

## Proposed Solution

In `commands/refine-issue.md` § Preservation Rule, replace "append a
subsection" with "append to the existing subsection under this H2, or create it
if absent."

The section-locating primitive already exists and is already cited by this
skill — `commands/refine-issue.md:546` points at
`scripts/little_loops/issue_history/doc_synthesis.py:_extract_section()` for H2
extraction. The same approach locates an existing H3 within a sliced H2.

Note the constraint from `.claude/CLAUDE.md` § Automation: Scratch Pad and from
`ll-verify-skill-prose`: if this becomes a real merge algorithm (dedup, bullet
ordering, provenance-marker handling), it belongs in
`scripts/little_loops/` behind an `ll-issues` subcommand, not as prose in the
skill. A plain "find the existing H3 and append under it" instruction is fine
as prose; anything with dedup logic is not.

Open questions for refinement:
- Whether the per-pass provenance line (`_Added by /ll:refine-issue …_`) is
  kept once per block, or per merged batch with a date. Keeping provenance
  matters — `/ll:reconcile-issue` and the correction-detection work in
  ENH-2992 read these blocks.
- Whether to apply the same folding to `/ll:wire-issue`'s
  `_Wiring pass added by …_` markers (a corpus-wide 9,377 bullets across 1,140
  issues, up to 17 marker blocks in one file). Likely yes, same mechanism.
- Whether existing issues get a one-time fold migration or are left alone.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — § Preservation Rule (lines 444-460); § 5c
  gap-analysis apply step (lines 600-612) uses the same subsection marker

### Dependent Files (Callers/Importers)
- `commands/reconcile-issue.md` — reads `### Codebase Research Findings`
  blocks as its input; must still parse correctly after folding
- TBD — use grep to find other readers of the marker string

### Similar Patterns
- `scripts/little_loops/issue_history/doc_synthesis.py:_extract_section()` —
  the H2 slicing primitive refine already cites for section parsing
- `skills/wire-issue/SKILL.md` Phase 8c — the parallel
  `_Wiring pass added by …_` marker with the same accumulation behavior

### Tests
- TBD — identify test files to update

### Documentation
- TBD — docs that need updates

### Configuration
- N/A

## Implementation Steps

TBD — requires codebase analysis

## Impact

- Reduces refined-issue length growth; the 5+-pass median (263 lines) should
  fall toward the 2-3 pass range.
- Makes the findings block a single readable statement of current knowledge per
  section rather than a chronological log.
- Improves the input quality for `/ll:reconcile-issue` and for ENH-2992's
  contradiction detection.

## Success Metrics

- No issue in `.issues/` accumulates more than one
  `### Codebase Research Findings` block per parent H2 after a refine pass.
- Zero bullets lost across a fold (verifiable by bullet count before/after).

## Scope Boundaries

- Does **not** delete, summarize, or dedupe findings content — folding is
  relocation only.
- Does **not** amend the Preservation Rule's overwrite prohibition
  (that is ENH-2995).
- A one-time migration of the existing corpus is optional and out of scope
  unless refinement decides otherwise.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/refine-issue.md` | Contains the append instruction being changed |
| `commands/reconcile-issue.md` | Downstream consumer of these blocks |

## Session Log
- `/ll:capture-issue` - 2026-08-02T13:45:57 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
