---
id: ENH-2847
type: ENH
priority: P3
status: open
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- issues-cli
- dependency-graph
- dx
blocked_by:
- FEAT-2846
relates_to:
- BUG-2848
---

# ENH-2847: `ll-issues sequence` should surface unverified prose dependencies

## Summary

`ll-issues sequence` prints `no blockers` for any issue with no structured
`blocked_by` edge, including issues whose bodies state a dependency in prose.
Annotate those rows with the suspected edge instead of asserting the issue is
unblocked — at the point of failure, where the misleading output is actually
read.

## Current Behavior

`cli/issues/sequence.py:74-78`:

```python
blockers = graph.blocked_by.get(issue.issue_id, set())
if blockers:
    rationale = f"blocked by: {', '.join(sorted(blockers))}"
else:
    rationale = "no blockers"
```

`no blockers` is an unqualified positive claim derived from the absence of a
frontmatter key. It reads identically whether the issue genuinely has no
prerequisites or whether an edge was simply never recorded. In the
`sketch-storyboards` case that produced:

```
[P2, no blockers] FEAT-110: Smoke tests, .gitignore, plan tree sync, ...
```

for an issue whose body names ENH-109 as a blocker, with ENH-109 still open.

`--json` (`sequence.py:56-69`) has the same gap — consumers get
`"blocked_by": []` with no signal that a prose claim exists.

## Expected Behavior

Using FEAT-2846's `extract_prose_deps()`, annotate rather than reorder:

```
[P2, no blockers ⚠ prose dep FEAT-109 (open), not in blocked_by] FEAT-110: ...
```

and add to `--json`:

```json
{"id": "FEAT-110", "blocked_by": [], "unverified_prose_deps": ["FEAT-109"]}
```

**Prose must never change topological order.** Extraction has false positives;
letting it constrain the sort trades a silent false negative for a silent false
positive, which is not an improvement. The annotation prompts a human check;
the structured field remains the only ordering input. Automation that wants to
gate hard can read `unverified_prose_deps` and decide for itself.

Prose references to `done`/`cancelled` issues are not annotated here — those are
`stale_prose_dep` and belong to `format-check` (FEAT-2846), not to sequence
output.

A `--strict` flag that exits non-zero when any shown issue has an unverified
prose dep would make this usable as an automation gate; worth considering but
not required for the core fix.

## Root Cause

`sequence` was written to report the graph faithfully and does so. The gap is
that "the graph has no edge" was rendered as "the issue has no blockers" — a
stronger claim than the data supports.

## Implementation Steps

1. Built on FEAT-2846's `extract_prose_deps()` — this issue should not ship a
   second extractor. (Recorded as `blocked_by: [FEAT-2846]`, which is exactly the
   invariant FEAT-2846 exists to enforce.)
2. In `sequence.py`, for each shown issue with an empty `blocked_by` set,
   extract prose deps, drop those already in `blocked_by`/`depends_on` and those
   whose referenced issue is terminal, and annotate the remainder.
3. Extend the `--json` record with `unverified_prose_deps`.
4. Keep the extraction lazy/bounded — only for the issues actually shown
   (`ordered[:limit]`), not the whole backlog, so `sequence` stays fast.
5. Consider `--strict`.
6. Tests: annotated row for a drifting issue, no annotation when the edge is
   structured, no annotation when the referenced issue is `done`, ordering
   unchanged in all cases.

## Scope Boundaries

**In scope**: `ll-issues sequence` output only — text rationale and the `--json`
record.

**Out of scope**: the extractor itself (FEAT-2846), the `stale_prose_dep`
classification and `--fix` backfill (FEAT-2846), the `depends_on`/
`topological_sort` asymmetry (BUG-2848), and any change to ordering. Other
consumers of the graph — `next-issue`, `clusters`, wave planning — are not
touched; if the annotation proves useful there, that is a follow-up.

## Acceptance Criteria

- [ ] An issue with a prose dep and no structured edge is annotated in both text
      and `--json` output.
- [ ] Topological order is byte-identical to today's for every input — a test
      pins that prose never affects ordering.
- [ ] Prose references to terminal issues produce no annotation.
- [ ] Extraction cost scales with `--limit`, not with backlog size.

## Impact

- **Users**: the misleading `no blockers` claim becomes a visible prompt to
  check. This alone would have caught the FEAT-110 case at the moment it misled
  a reader.
- **Risk**: Low. Presentation-only; ordering is untouched.
- **Effort**: Small, once FEAT-2846 lands.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/cli/issues/sequence.py:54-82` | Output paths to extend |
| `FEAT-2846` | Provides the extractor and the drift/stale distinction |
| `BUG-2848` | The other source of `no blockers` false negatives (`depends_on`) |

## Context

Traced from a `sketch-storyboards` `ll-issues sequence` run that reported a
blocked issue as `[P2, no blockers]`.

---

## Status

open
