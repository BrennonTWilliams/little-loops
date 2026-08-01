---
id: BUG-2956
title: format-check reports Program Design missing despite program_design_not_applicable
  opt-out
type: BUG
priority: P3
status: open
captured_at: '2026-08-01T01:11:34Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2852
- ENH-2870
- ENH-2937
labels:
- issue-parser
- confidence-check
confidence_score: 50
outcome_confidence: 60
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 0
score_change_surface: 10
size: Large
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **This bug does not reproduce against current `main`.** Running the exact
  repro command, `ll-issues format-check ENH-2937 --format json`, on
  2026-08-01 returns `"missing": []` — `"Program Design"` is absent, contrary
  to the Steps to Reproduce / Current Behavior sections above.
- `check_format_gaps()` (`scripts/little_loops/issue_parser.py:293`) computes
  `required = _gate_program_design(_required_sections(sections_data),
  issue_path, content)` at line 396 — **before** either `gaps.missing`
  (line 399: `sorted(required - headings)`) or
  `gaps.program_design_nonspecific` (lines 419-436) is derived. Both gap
  classes already share this single upstream filter; there is no separate,
  unfiltered path that feeds `missing` directly from `_required_sections()`.
- `_gate_program_design()` (`issue_parser.py:116`) drops `"Program Design"`
  from `required` whenever `program_design_gate_active()`
  (`scripts/little_loops/issues/program_design.py:366`) returns `False` —
  covering all three exemptions: no cutover stamp, `program_design_not_applicable:
  true` (this issue's opt-out), and grandfathering
  (`issue_design_timestamp() < cutover`). `_gate_program_design` is called
  from both known consumers, `is_formatted()` (line 174) and
  `check_format_gaps()` (line 396) — so `missing` and `program_design_nonspecific`
  cannot drift apart; they're two views of the same already-filtered `required`
  set.
- Existing regression tests in `scripts/tests/test_program_design_gate.py::TestFormatGapsWiring`
  already assert this exact scenario against `gaps.missing`:
  `test_escape_hatch_skips_the_gate` (line 629, opt-out flag),
  `test_grandfathered_issue_reports_no_program_design_gap` (line 542,
  grandfathering), `test_unstamped_project_reports_no_program_design_gap`
  (line 530, unarmed gate). The converse (gate genuinely active) is covered by
  `test_post_cutover_missing_section_reports_missing` (line 568).
- The shared-filter design was introduced by commit `cb022145`
  ("feat(issues): add Program Design specificity gate to format-check",
  2026-07-27) — before this bug was captured (2026-08-01). The docstring
  qualifier this issue's Root Cause section quotes (lines 264-269, describing
  when `program_design_nonspecific` fires) describes that field's own
  semantics; it does not imply `missing` is computed on an unfiltered
  `required` set, and the code was never written that way.
- **Recommendation**: re-verify with `/ll:ready-issue BUG-2956` against the
  exact repro steps; if it likewise fails to reproduce, close as
  not-reproducible/invalid rather than proceeding to implementation. No code
  change appears warranted — `Files to Modify` and `Tests` below are left
  in place for that verification pass but the underlying claim they're built on
  does not hold against current `main`.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — the `FormatGaps` missing-section
  computation (docstring at lines 264-269 documents the intended opt-out scope)

### Dependent Files (Callers)
- `skills/confidence-check/` — consumes `format-check --format json` and
  escalates `missing` entries to a hard-override STOP
- `scripts/little_loops/cli/issues/format_check.py` — CLI surface

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/autodev.yaml` — three independent inline-Python
  blocks (lines ~1094-1113, 1593-1619, 1757-1783) each shell out to
  `ll-issues format-check "$ID" --format json` and re-derive their own
  `DESIGN_FAIL` boolean by OR-ing `program_design_nonspecific`,
  `'Program Design' in missing`, and `'Program Design' in empty`. This is a
  duplicated re-implementation of the same predicate `issue_parser.py` already
  computes once — a future fix to gap-class semantics must keep these three
  shell blocks in sync (they consume the same JSON field, so they pick up a
  fix automatically, but any change to the *shape* of that field breaks them
  silently). [Agent 1/2 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` gate
  (line 114) invokes `ll-issues format-check "$ID"` directly [Agent 1 finding]
- `commands/ready-issue.md` (lines 233-237) — documents the same
  OR-of-`program_design_nonspecific`/`missing`/`empty` pattern as a
  surface-only (non-blocking) check, explicitly to avoid "two gates enforcing
  the same requirement with different remedies" — re-read if the `missing`
  semantics change [Agent 2 finding]
- `.kimi-code/skills/confidence-check/SKILL.md` and
  `.gemini/skills/confidence-check/SKILL.md` — `ll-adapt`-generated mirrors of
  `skills/confidence-check/SKILL.md`'s Phase 1.6 Program Design gate logic.
  These are generated artifacts, not hand-maintained — if the canonical
  skill's logic changes as part of a real fix, re-run `ll-adapt --host
  kimi-code --apply` / `--host gemini --apply` to keep them in sync; nothing
  currently tests their sync [Agent 2 finding]

### Similar Patterns
- `testable: false` — the full-skip escape hatch ENH-2852 cites as the model for
  this flag's intended behavior

### Tests
- A fixture issue with `program_design_not_applicable: true` and no
  `## Program Design` section, asserting `Program Design` is absent from
  `missing`. Should also assert the flag does **not** suppress genuinely missing
  sections of other kinds.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py::TestFormatCheckProgramDesign`
  (line 748) — a second, CLI-level test class (independent of
  `test_program_design_gate.py`'s unit-level tests) that already exercises
  this exact scenario: `test_missing_section_surfaces_after_cutover` (line
  798, genuinely-active gate, no opt-out) and
  `test_escape_hatch_passes_after_cutover` (line 824, opt-out set,
  post-cutover, asserts exit code 0). Both currently pass on `main`,
  corroborating the non-reproduction finding above from a second test suite.
  [Agent 1/3 finding]

## Impact

- **Priority**: P3 — narrow, but it defeats an escape hatch that exists
  specifically to unblock issues, on a gate that hard-stops confidence-check.
- **Effort**: Small — one condition, plus a regression test.
- **Risk**: Low — strictly loosens a check for issues that explicitly opted out.

## Status

**Open** | Created: 2026-08-01 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 50/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 60/100 → LOW

### Gaps to Address
- **Program Design gate (hard override, ENH-2852)**: `ll-issues format-check BUG-2956 --format json` reports `"Program Design"` in `missing` — this issue itself has no `## Program Design` section and no `program_design_not_applicable` opt-out set, so the gate this issue is *about* is currently failing on the issue itself.
- **Non-reproduction (primary gap)**: the issue's own `/ll:refine-issue` findings, corroborated by direct verification in this check (`ll-issues format-check ENH-2937 --format json` → `"missing": []`), show the described bug does not reproduce against current `main`. `_gate_program_design()` already filters `required` upstream of both `missing` and `program_design_nonspecific`, so the two gap classes cannot drift apart as described. 14 existing regression tests (`test_program_design_gate.py::TestFormatGapsWiring`, `test_ll_issues_format_check.py::TestFormatCheckProgramDesign`) already cover exactly this scenario and pass on `main`.
- **Recommended remedy**: run `/ll:ready-issue BUG-2956` to close as not-reproducible/invalid rather than proceeding to implementation, per the issue's own Codebase Research Findings recommendation.

### Outcome Risk Factors
- Root cause as stated does not hold against current code — the docstring qualifier the issue's Root Cause section cites describes `program_design_nonspecific`'s own semantics, not an unfiltered `missing` path. Implementing against this issue as written risks a no-op or speculative change with no failing test to guide it.

## Session Log
- `/ll:refine-issue` - 2026-08-01T06:28:57 - `dd366005-a4ec-42a7-b2b1-b6c17816eb93.jsonl`
- `/ll:confidence-check` - 2026-08-01T06:27:20 - `ff0d368e-0996-4704-ad52-f8bfb6d12bde.jsonl`
- `/ll:wire-issue` - 2026-08-01T06:25:10 - `120c4924-8996-4805-bfa5-e10953e99aa8.jsonl`
- `/ll:refine-issue` - 2026-08-01T06:19:27 - `6afeb18a-5999-4b7d-a508-fb190e28f9fc.jsonl`
- `/ll:capture-issue` - 2026-08-01T01:11:34Z - `eae1dd1c-2379-4edd-a323-b6c99ede585d.jsonl`
