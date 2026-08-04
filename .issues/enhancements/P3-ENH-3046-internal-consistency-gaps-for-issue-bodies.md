---
id: ENH-3046
title: Internal-consistency gap kinds in format-check + AC-vs-design pass in refine-issue
type: ENH
priority: P3
status: open
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T20:47:11Z'
relates_to:
- ENH-2946
- FEAT-3048
- FEAT-2942
- ENH-3049
labels:
- cli
- issues
- gates
---

# ENH-3046: Internal-consistency gaps for issue bodies

## Summary

Refine and wire both look *outward* at the codebase; nothing checks an issue **against itself**.
Two statements in one file can flatly contradict each other and pass every gate. Add the
mechanical half as `format-check` gap kinds (successor to ENH-2946's pattern), and fold the
judgment half into `/ll:refine-issue` as one focused prompt.

## Current Behavior

No gate compares sections of an issue to each other. Two live contradictions in FEAT-2942, both
of which survived refine, wire, and confidence-check:

1. **AC vs. scope.** AC 1 requires *"no writes without `--apply`"* for both modes, while AC 5
   forbids EPIC creation in this subcommand — but EPIC creation is the only thing synthesize
   mode could write. An implementer resolving AC 1 literally would build exactly what AC 5
   forbids.
2. **Frontmatter vs. body.** Frontmatter declares `blocked_by: [FEAT-2947]` (open), while the
   body says *"Soft dep on FEAT-2947 … If FEAT-2947 has not landed, synthesize mode still ships
   proposal-only."* The hard edge keeps automation from selecting the issue for a dependency the
   body says is optional — and `deferred`/`open` blockers never resolve, so it sits there.

## Expected Behavior

Two mechanical gap kinds in `check_format_gaps()`:

- `soft_dep_hard_edge` — an ID in `blocked_by` that the body describes with soft-dependency
  language ("soft dep", "optional", "if … has not landed", "nice to have"). Cheap: reuse
  `prose_deps.py`'s ID regex + fence handling, add a phrase list.
- `ac_flag_drift` — an acceptance criterion referencing a flag or mode absent from the CLI
  signature stated elsewhere in the same issue. Overlaps FEAT-3048's argparse work but is
  purely intra-document: compare ACs against the issue's own stated signature, no codebase
  lookup.

Plus one judgment pass in `/ll:refine-issue`: a single focused prompt — *"read only the
Acceptance Criteria and Program Design sections; list any pair of statements that cannot both be
satisfied"* — reported as findings, not auto-applied.

## Motivation

Contradictions are the cheapest defect class to catch (no codebase knowledge needed, the
evidence is entirely in one file) and among the most expensive to hit during implementation,
because they surface only when someone tries to satisfy both statements at once. The mechanical
half is small and lands in machinery that already exists.

## Proposed Solution

Follow ENH-2946 exactly: new fields on `FormatGaps`, populated in `check_format_gaps()`,
printed by `format_check.py`, listed in `--kinds` help, covered by `scripts/tests/`.

The refine prompt is a bounded addition to `commands/refine-issue.md` (987 lines) — keep it to a
single step near the existing Step 6.7 prose/design gate rather than a new phase, and emit
findings into the report rather than rewriting sections.

Scope boundary vs. FEAT-3048: that issue verifies claims against the **codebase**; this one
verifies an issue against **itself**. They share the extractor conventions but not the lookups,
and neither blocks the other.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `FormatGaps` fields + `check_format_gaps()`
- `scripts/little_loops/cli/issues/format_check.py` — printer + `--kinds` help
- `scripts/little_loops/issues/prose_deps.py` — reuse ID regex / `_in_fence` for the soft-dep
  phrase scan
- `commands/refine-issue.md` — one AC-vs-Program-Design consistency step
- `scripts/tests/` — per-gap-kind coverage
- `docs/reference/CLI.md` — document the new gap kinds

### Similar Patterns
- `ENH-2946` — the direct precedent for extending `format-check` with gap kinds
- `FEAT-2849` — extractor + gap taxonomy shape

## Implementation Steps

1. `soft_dep_hard_edge` gap kind + phrase list + tests.
2. `ac_flag_drift` gap kind + tests.
3. `format-check` reporting/`--kinds` wiring.
4. Refine-issue AC-vs-Program-Design prompt step.
5. Validate against FEAT-2942: both contradictions reported.

## Impact

- **Priority**: P3 — real but narrower than FEAT-3048/ENH-3045
- **Effort**: Low — two gap kinds in existing machinery plus one prompt step
- **Risk**: Low — reporting only; no auto-fix

## Related Key Documentation

- `.claude/CLAUDE.md` § Issue File Format — status enum and dependency semantics
- `docs/reference/DEFERRAL_CODES.md` — `deferred` is non-terminal for dependency edges

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-04T20:50:27 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
