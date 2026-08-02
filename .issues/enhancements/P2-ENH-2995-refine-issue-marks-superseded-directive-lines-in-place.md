---
id: ENH-2995
status: open
priority: P2
captured_at: "2026-08-02T13:43:01Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to: [ENH-2992, ENH-2993, ENH-2996]
---

# refine-issue marks superseded directive lines in place

## Summary

`/ll:refine-issue`'s Preservation Rule forbids overwriting any section with >2
lines of meaningful content. When codebase research discovers that the issue's
own `## Implementation Steps` (or `### Files to Modify`, or `## Acceptance
Criteria`) are *wrong*, refine's only available move is to append a rebuttal
underneath them. The refuted directive text stays in place, unmarked, and an
implementer reading top-down executes a plan the same file already disproved.

Add a narrow carve-out: refine may annotate a refuted directive line in place
with a superseded marker pointing at the finding that refutes it. Nothing is
removed or rewritten — only marked.

## Current Behavior

The Preservation Rule (`commands/refine-issue.md:444-460`) states:

> **Do NOT overwrite non-empty sections** with >2 lines of meaningful text
> - **Append** research findings as a subsection or additional bullets
> - **Do NOT replace** existing human-written or previously-refined content

This is correct as a default — it protects human prose from being bulldozed.
But it applies uniformly, including to the case where refine's own research
establishes that a directive line is factually false. The result is a file
that argues with itself.

**Measured across `.issues/` (2026-08-02):** of 1,295 issues containing a
`### Codebase Research Findings` block, **316 (24%)** contain correction
language inside that block — `is wrong`, `does not exist`, `will not work`,
`must be dropped`, `target file is wrong`, `is stale`, `omit entirely`.

Worst case is `ENH-2500`
(`.issues/enhancements/P3-ENH-2500-per-run-dir-pending-file-and-scope-for-prompt-across-issues.md`),
with 13 correction phrases. Its `## Implementation Steps` (line 264) opens:

> 1. Add `pending_file: "${context.run_dir}/pending.txt"` to the loop's `context:` block

and the `### Codebase Research Findings` subsection 16 lines below (line 280)
says:

> **Steps 1 + 3 are mutually incompatible with how context template resolution
> works** … Revised step 1: **omit entirely**.

Steps 6 and 7 are likewise refuted ("Step 6 target file is wrong … does not
exist"). Four of nine steps are dead, and nothing at the point of reading says
so.

## Expected Behavior

When a research finding directly refutes a specific directive line, refine
annotates that line in place:

```markdown
## Implementation Steps

1. Add `pending_file: "${context.run_dir}/pending.txt"` to the loop's `context:` block
   > ⚠ Superseded — see § Codebase Research Findings under Implementation Steps

2. Add `scope: ["${context.run_dir}"]` to the loop's top-level keys
```

Reading top-down, the refutation is visible at the point of the claim. The
original text survives verbatim; the finding remains the authority; no content
is deleted.

## Motivation

The primary consumer of a refined issue is a headless automation session with
no human present (`commands/refine-issue.md:28-31` says so explicitly). That
session reads the issue's directive sections as instructions. A refuted step
that carries no marker at the point of reading is a defect injected into the
issue by the very pass meant to improve it — refine is the only actor that
knows the step is dead, and the Preservation Rule is what stops it from saying
so where it counts.

24% of refined issues carry at least one such contradiction. Only 19 issues in
the entire corpus have ever been through `/ll:reconcile-issue`, the skill built
to resolve them (see ENH-2992) — so for practical purposes the contradiction is
permanent once written.

## Proposed Solution

Add a bounded exception to the Preservation Rule in
`commands/refine-issue.md` § Preservation Rule, permitting **annotation** (not
replacement) of a directive line when a finding in the same pass refutes it.

The mechanism already exists in the same file. Gap-analysis mode
(`commands/refine-issue.md:605-608`) writes exactly this shape for stale
anchors:

```
> ⚠ Anchor `old_function:N` no longer resolves — verify against current codebase.
```

The carve-out generalizes that one case. Constraints that keep it narrow:

- **Annotate only, never edit** the refuted line's own text.
- Applies only to directive sections: `## Implementation Steps`,
  `### Files to Modify`, `## Acceptance Criteria`. Never to `## Summary`,
  `## Motivation`, `## Proposed Solution`, or any `### Option …` /
  `### Decision Rationale` prose — the same preserve-list
  `commands/reconcile-issue.md` already enforces.
- Fires only when the refutation comes from **this pass's own research
  findings**, not from re-reading prior appended blocks.
- The marker is a blockquote line immediately following the refuted line, so
  list numbering and any downstream parser that keys on `^\d+\.` are unaffected.
- Idempotent: skip if an identical marker is already present under that line.

**Interaction with `/ll:reconcile-issue`**: this is complementary, not
competing. Reconcile *rewrites* directive sections wholesale on a plateau;
this marks them at write time so the contradiction is legible in the interim —
which, given 19 reconciles against 1,703 refines, is nearly always.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — § Preservation Rule (lines 444-460): add the
  annotation carve-out with its scope constraints; § 5a enrichment rules
  (lines 323-443) reference it where Implementation Steps are discussed
  (lines 425-442)

### Dependent Files (Callers/Importers)
- TBD — use grep to find references

### Similar Patterns
- `commands/refine-issue.md:605-608` — gap-analysis mode's stale-anchor
  warning is the exact marker shape and blockquote convention to reuse
- `commands/reconcile-issue.md` § Contract — the authoritative
  rewrite-eligible vs preserve-untouched section split; the carve-out's scope
  list should not exceed reconcile's rewrite list

### Tests
- TBD — identify test files to update

### Documentation
- TBD — docs that need updates

### Configuration
- N/A

## Implementation Steps

TBD — requires codebase analysis

## Impact

- Refined issues stop shipping self-contradicting instructions to headless
  implementers.
- Zero content loss — the rule stays append/annotate-only.
- Reduces the blast radius of reconcile-issue's starvation (ENH-2992) without
  depending on it.

## Success Metrics

- A refine pass that emits correction language against a directive line also
  emits a superseded marker on that line (verifiable by re-running refine
  against `ENH-2500` and checking steps 1/3/6/7).
- No marker appears on any preserved section (`## Summary`, `## Motivation`,
  `## Proposed Solution`, `### Option …`).

## Scope Boundaries

- Does **not** rewrite, reorder, or delete any directive text — that remains
  `/ll:reconcile-issue`'s job.
- Does **not** change when reconcile is invoked (ENH-2992).
- Does **not** touch `/ll:wire-issue`'s append behavior (ENH-2996).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/refine-issue.md` | Contains the Preservation Rule being amended |
| `commands/reconcile-issue.md` | Defines the rewrite-eligible / preserve-untouched split this carve-out must respect |

## Session Log
- `/ll:capture-issue` - 2026-08-02T13:45:56 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
