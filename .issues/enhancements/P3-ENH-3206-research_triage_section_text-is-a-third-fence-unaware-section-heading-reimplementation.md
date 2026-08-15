---
id: ENH-3206
type: ENH
title: research_triage._section_text is a third fence-unaware section-heading reimplementation
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T23:12:33Z'
---

# ENH-3206: research_triage._section_text is a third fence-unaware section-heading reimplementation

## Summary

`_section_text` (`scripts/little_loops/issues/research_triage.py:123-137`) is a third,
independent reimplementation of the fence-unaware, last-occurrence-wins heading-resolution
pattern found in `_section_body_with_offset` (BUG-3202): same regex shape
(`^##\s+{heading}\s*$`), same `matches[-1]` last-match pick, and the same fence-blind
terminator scan (`re.search(r"^##\s", ...)`).

It then pipes its result through `text_utils.strip_code_fences`, the offset-shifting
variant BUG-3202's Deliverable table explicitly flags as unusable for offset-preserving
lookups — not a concern for `_section_text` itself (it returns fence-*stripped* text, not
an offset), but it means `_section_text` cannot simply delegate to
`_section_body_with_offset` without a design decision about whether the stripped-vs-sliced
distinction matters for `_section_text`'s callers.

BUG-3202 deliberately left this site out of scope to contain blast radius (its own
Integration Map calls this out by name), landing a single exported fence-span helper
(`little_loops.text_utils.fence_spans`/`in_fence`) that `_section_text` should converge on.

## Steps to Reproduce

Write an issue whose body quotes a markdown block containing a `## <heading>`-shaped line
inside a code fence, where `<heading>` is a section name `_section_text` is called with
(backs `triage_research_axes`'s `_axis_refs`, `research_triage.py:157-168`). The fenced
copy wins section resolution / truncates the enclosing section, same symptom class as
BUG-3202's Finding 4/Current Behavior.

## Program Design

Change site: `_section_text` (`scripts/little_loops/issues/research_triage.py:123-137`).

Converge it onto the shared fence-span helper BUG-3202 exports
(`little_loops.text_utils.fence_spans`/`in_fence`), mirroring the fix already applied to
`_section_body_with_offset` — exclude fenced heading matches and make the end-boundary
scan fence-aware, same as `_section_body_with_offset`. Decide explicitly whether
`_section_text` should keep stripping fences from its returned text (its current contract)
or switch to slicing the original content like `_section_body_with_offset` now does — this
is a design call specific to `_section_text`'s callers (`_has_symbol` et al.), not
automatically inherited from BUG-3202.

## Acceptance Criteria

- [ ] `_section_text` excludes fenced `##`-shaped lines from heading resolution via the
      shared `fence_spans`/`in_fence` helper — no new fifth/sixth fence idiom.
- [ ] The end-boundary scan is fence-aware: a fenced `##`-shaped line does not terminate
      the section that encloses it.
- [ ] A test pins the fenced-heading-does-not-win and fenced-heading-does-not-truncate
      behaviors for `_section_text`, mirroring BUG-3202's `TestSectionBodyFenceAware`.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — same defect class as BUG-3202 but on a narrower, less-gated call
  path (`triage_research_axes`'s `_axis_refs` only, not `format-check`'s five gated
  skills).
- **Effort**: Small — reuses the helper BUG-3202 already exports.
- **Risk**: Low.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
