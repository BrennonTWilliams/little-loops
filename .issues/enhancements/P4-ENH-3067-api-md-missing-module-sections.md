---
discovered_commit: fc652df07b9234f2a79fb0663efd253590b170eb
discovered_branch: main
discovered_date: 2026-08-05
discovered_by: audit-docs
status: open
labels: [documentation]
verify_verdict: VALID
---

# ENH-3067: 13 modules listed in API.md's overview table have no reference section

## Summary

`docs/reference/API.md` opens with a Module Overview table and then documents each module
under a `## little_loops.<module>` heading. Thirteen modules appear in the table but have no
corresponding section, so the table promises a reference entry that does not exist.

## Current Behavior

The following have an overview row and no `## little_loops.<module>` section:

`pricing`, `stats`, `sft_formatter`, `ab_writer`, `subprocess_utils`, `file_utils`, `sync`,
`decisions`, `decisions_sync`, `output_parsing`, `output_cleaner`, `testing`,
`worktree_utils`.

Readers following the table land on nothing; the one-line table description is the entire
available reference for these modules.

## Expected Behavior

Each listed module either has a section documenting its public surface (classes, public
functions with signatures, and a short usage note), or the overview table marks it
explicitly as "no dedicated section — see source".

## Proposed Solution

Write a `## little_loops.<module>` section per module, following the shape of the existing
sections (e.g. `## little_loops.host_runner`): a one-paragraph purpose statement, then
subsections per public class/function with a fenced signature block.

These are all small, stable modules — `stats` is a single Wilson-interval helper,
`file_utils` is atomic-write wrappers, `worktree_utils` is worktree setup/cleanup. The work
is bounded but real: API.md is already ~10.4k lines and this would add roughly 1k more.

Consider splitting the deliverable per module cluster so it can land incrementally rather
than as one large diff.

## Impact

- **Priority**: P4 — documentation completeness. No user is blocked; the modules are
  discoverable from source and the overview table gives a one-line orientation.
- **Effort**: Medium — 13 sections of genuine reference prose, each requiring a read of
  the module to get signatures right.
- **Risk**: Low. Doc-only. Main risk is writing signatures from memory rather than
  from source and introducing new staleness — every signature must be copied from the
  module.

## Integration Map

- `docs/reference/API.md` — the Module Overview table (~lines 20–95) and the per-module
  section body
- The 13 modules under `scripts/little_loops/` named above — read for signatures
- `scripts/tests/test_doc_counts.py` — check whether any count claim in API.md is
  gated before/after adding sections

## Related Key Documentation

- `thoughts/audit-docs-reference-2026-08-05.md` — the docs audit that surfaced this
  (recorded there as a "low, completeness" finding)

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:11 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`

---

## Status

**Open** | Created: 2026-08-05 | Priority: P4
