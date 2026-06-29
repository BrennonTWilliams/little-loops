---
id: ENH-2398
title: ensure_formatted gate should honor the `deprecated` section flag like is_formatted()
type: enhancement
status: open
priority: P4
discovered_date: 2026-06-29
discovered_by: BUG-2395 reconciliation
relates_to:
- BUG-2395
labels:
- rn-remediate
- format-guard
- hardening
decision_needed: false
confidence_score: 98
outcome_confidence: 92
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 25
---

# ENH-2398: ensure_formatted gate should honor the `deprecated` section flag like is_formatted()

## Summary

The `ensure_formatted` Phase-0 gate in `rn-remediate.yaml` builds its
required-section list from `ll-issues sections` but, unlike
`issue_parser.py:is_formatted()`, does **not** skip entries marked
`deprecated: true`. The two code paths are meant to agree on "what counts as
required" but only one honors the deprecated flag.

## Motivation

Without this guard, any future template author who marks a section
`deprecated: true` but forgets to also change `required: true` → `optional`
will silently reintroduce the BUG-2395 non-idempotency: `ensure_formatted` will
demand the deprecated section while `is_formatted()` ignores it, causing
`rn-remediate` to loop forever repairing issues that are already correctly
formatted. The one-time BUG-2395 fix (demoting the offending entry) is fragile;
this guard makes the gate self-healing against future template drift.

## Current Behavior

`is_formatted()` (`issue_parser.py:86,89`) excludes deprecated sections:

```python
if defn.get("required") is True and not defn.get("deprecated", False): ...
if defn.get("level") == "required" and not defn.get("deprecated", False): ...
```

The `ensure_formatted` inline Python (`rn-remediate.yaml`) has no such guard:

```python
if isinstance(meta, dict) and meta.get("required") is True:
    required.append(title)
if isinstance(meta, dict) and meta.get("level") == "required":
    required.append(title)
```

Today this is harmless only because BUG-2395 demoted the one offending
deprecated-but-required entry (`feat` `User Story`, `level: required`,
`deprecated: true`) to `optional`. Any future deprecated-but-`required` section
would re-introduce a non-idempotent format gate (the original BUG-2395 failure
mode) while `is_formatted()` stays correct — a silent divergence.

## Expected Behavior

The gate skips `deprecated: true` sections, matching `is_formatted()`. Add a
`if meta.get("deprecated"): continue` guard to both loops in the inline Python.

## Proposed Solution

In the `ensure_formatted` state of `loops/rn-remediate.yaml`, add a `deprecated`
guard before each `required` check — mirroring the guard already present in
`issue_parser.py:is_formatted()`:

```python
# Before (current):
if isinstance(meta, dict) and meta.get("required") is True:
    required.append(title)
if isinstance(meta, dict) and meta.get("level") == "required":
    required.append(title)

# After (with guard):
if isinstance(meta, dict) and meta.get("deprecated"):
    continue
if isinstance(meta, dict) and meta.get("required") is True:
    required.append(title)
if isinstance(meta, dict) and meta.get("level") == "required":
    required.append(title)
```

The single `continue` covers both check paths because it exits the iteration
before either `required.append` executes.

## Scope Boundaries

- In scope: the `deprecated` guard in `ensure_formatted`'s inline Python only.
- Out of scope: the `Labels`/`User Story` demotions (done in BUG-2395); any
  change to `is_formatted()` (already correct).

## Integration Map

### Files to Modify
- `loops/rn-remediate.yaml` — add `deprecated` guard in the `ensure_formatted` state inline Python

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — `is_formatted()` (reference implementation, no change needed)

### Similar Patterns
- N/A — the guard is already present in `is_formatted()`; this is a one-site alignment fix

### Tests
- `scripts/tests/test_rn_remediate.py` — add regression case in `TestEnsureFormatted` (line 1446): a deprecated-but-required section must not block `ensure_formatted`

_Wiring pass added by `/ll:wire-issue`:_
- New method `test_enh_deprecated_section_exits_0` in `TestEnsureFormatted`, following the pattern of `test_feat_frontmatter_labels_use_case_exits_0` (line 1487). Call `self._run_gate(body, "enh")` with a body containing all non-deprecated required ENH sections — common: `## Summary`, `## Current Behavior`, `## Expected Behavior`, `## Impact`, `## Status`; type: `## Scope Boundaries` — but intentionally **omitting** `## Current Pain Point`. Assert `result.returncode == 0`: the gate must not block because `enh-sections.json:"Current Pain Point"` has `level: required` + `deprecated: true` and is the one live deprecated+required entry across all four section templates.
- `scripts/tests/test_ll_issues_sections.py` — `TestBug2395TemplateGuards.test_required_set_non_empty_for_all_types` (line 272) already filters deprecated correctly for all four types; **no change needed**, listed for reference only.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Path correction**: The file to modify is `scripts/little_loops/loops/rn-remediate.yaml`, not bare `loops/rn-remediate.yaml`. The two loops without the `deprecated` guard are at lines 113–119.
- **Test file correction**: `TestEnsureFormatted` already exists in `scripts/tests/test_rn_remediate.py:1446` (added for BUG-2395) with `_run_gate()` at line 1465 — the regression test for ENH-2398 should be added there, not in `test_builtin_loops.py`. `_run_gate()` injects `SECTIONS_JSON` from the real template files and exercises the live shell action string.
- **Live active case**: `scripts/little_loops/templates/enh-sections.json` "Current Pain Point" section already has `"level": "required"` and `"deprecated": true` today. This means the divergence is not merely hypothetical — any ENH issue processed by `rn-remediate` today is subject to the non-idempotency if "Current Pain Point" is absent.

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate the `ensure_formatted` state in `scripts/little_loops/loops/rn-remediate.yaml` (lines 79–140; the two loops to patch are at lines 113–119)
2. Add `if meta.get("deprecated"): continue` before both `required` checks in the inline Python heredoc
3. Add regression test in `scripts/tests/test_rn_remediate.py` inside the existing `TestEnsureFormatted` class (line 1446), using the existing `_run_gate()` infrastructure (line 1465) — pass a body without "## Current Pain Point" with `issue_type="enh"` and assert exit 0 (the gate must not block it since that section is `deprecated: true`)
4. Run `ll-loop validate scripts/little_loops/loops/rn-remediate.yaml` to confirm no new warnings

## Impact

- **Priority**: P4 — Defensive hardening; no current section triggers the divergence
- **Effort**: Small — Single `continue` guard added to one inline Python block
- **Risk**: Low — Mirrors the existing `is_formatted()` logic exactly; no behavior change for non-deprecated sections
- **Breaking Change**: No

## Status

open


## Session Log
- `/ll:confidence-check` - 2026-06-29T00:00:00 - `57a23f87-8546-4859-a567-225b9e704bf1.jsonl`
- `/ll:wire-issue` - 2026-06-29T21:05:29 - `fdb615b1-e11f-4b21-ab3d-c73fca7ae7d3.jsonl`
- `/ll:refine-issue` - 2026-06-29T20:48:21 - `d2b99d55-ba8c-40e6-b265-f6b74db485ea.jsonl`
- `/ll:format-issue` - 2026-06-29T20:42:26 - `ed991f73-cf55-4af5-876f-ea05421417be.jsonl`
