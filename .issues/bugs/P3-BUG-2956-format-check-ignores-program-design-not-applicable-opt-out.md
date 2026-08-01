---
id: BUG-2956
title: format-check reports Program Design missing despite program_design_not_applicable opt-out
type: BUG
priority: P3
status: open
captured_at: "2026-08-01T01:11:34Z"
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to: [ENH-2852, ENH-2870, ENH-2937]
labels:
- issue-parser
- confidence-check
---

# BUG-2956: `format-check` reports `Program Design` missing despite the `program_design_not_applicable` opt-out

## Summary

`ll-issues format-check` lists `Program Design` under `"missing"` even when the
issue sets `program_design_not_applicable: true` in frontmatter. The opt-out
suppresses only the `program_design_nonspecific` gap class, not the
missing-section check — so an issue that has legitimately opted out carries a
permanent, unclearable gap.

## Steps to Reproduce

1. Take an issue with `program_design_not_applicable: true` in frontmatter and no
   `## Program Design` section — e.g. ENH-2937.
2. Run `ll-issues format-check ENH-2937 --format json`.
3. Output includes `"missing": ["Program Design"]`.

## Current Behavior

```json
{
  "missing": ["Program Design"],
  "program_design_nonspecific": []
}
```

The `nonspecific` class is correctly empty (the opt-out is honored there), but
`missing` is not consulted against the flag. Per the docstring at
`scripts/little_loops/issue_parser.py:264-269`, the opt-out is documented as
applying to `program_design_nonspecific` only:

> Only reported when the project has armed the gate with a
> `.ll/program-design-cutover.json` stamp and the issue is not grandfathered or
> opted out via `program_design_not_applicable`.

That qualifier sits on `program_design_nonspecific`'s description; the
missing-section path has no equivalent.

## Expected Behavior

With `program_design_not_applicable: true` set, `format-check` omits
`Program Design` from `"missing"` — the same way `testable: false` fully skips
the test phase rather than half-skipping it. An opted-out issue should be able
to reach a clean `format-check`.

## Motivation

`/ll:confidence-check` surfaces the missing section as a **hard-override "Gaps to
Address — STOP"** item. It did exactly this on ENH-2937: the issue set the
opt-out flag, and the gate still reported a blocking gap that no remedy could
clear, because the only remedies offered are "populate the section" or "set the
flag" — and the flag was already set. A permanently unclearable gap caps the
issue's Readiness and feeds the dishonest `readiness_stagnated` /
`low_readiness` deferral class the surrounding work (ENH-2870, FEAT-2751) exists
to eliminate.

ENH-2852 explicitly designed this flag on the `testable: false` precedent —
"full skip, auto-inferable for trivial issues, checked by the new mechanical
gate" (ENH-2852 line 101). A half-honored opt-out is a defect against that
stated design, not a scope question.

## Root Cause

The missing-section check in `scripts/little_loops/issue_parser.py` compares the
issue's headings against the type template without consulting
`program_design_not_applicable`. The flag is read only on the
`program_design_nonspecific` path (docstring at lines 264-269). Exact function
anchor needs confirming during implementation.

## Proposed Solution

In the missing-section computation, skip `Program Design` when the issue's
frontmatter has `program_design_not_applicable: true` — reusing whatever helper
the `nonspecific` path already uses to read the flag, so the two classes cannot
drift apart again.

Worth checking in the same pass whether grandfathering (the
`.ll/program-design-cutover.json` stamp) is likewise honored by `nonspecific`
but not by `missing`; if so, fix both exemptions together.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — the `FormatGaps` missing-section
  computation (docstring at lines 264-269 documents the intended opt-out scope)

### Dependent Files (Callers)
- `skills/confidence-check/` — consumes `format-check --format json` and
  escalates `missing` entries to a hard-override STOP
- `scripts/little_loops/cli/issues/format_check.py` — CLI surface

### Similar Patterns
- `testable: false` — the full-skip escape hatch ENH-2852 cites as the model for
  this flag's intended behavior

### Tests
- A fixture issue with `program_design_not_applicable: true` and no
  `## Program Design` section, asserting `Program Design` is absent from
  `missing`. Should also assert the flag does **not** suppress genuinely missing
  sections of other kinds.

## Impact

- **Priority**: P3 — narrow, but it defeats an escape hatch that exists
  specifically to unblock issues, on a gate that hard-stops confidence-check.
- **Effort**: Small — one condition, plus a regression test.
- **Risk**: Low — strictly loosens a check for issues that explicitly opted out.

## Status

**Open** | Created: 2026-08-01 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-08-01T01:11:34Z - `eae1dd1c-2379-4edd-a323-b6c99ede585d.jsonl`
