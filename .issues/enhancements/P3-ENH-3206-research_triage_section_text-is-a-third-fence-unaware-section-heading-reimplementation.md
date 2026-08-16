---
id: ENH-3206
type: ENH
title: research_triage._section_text is a third fence-unaware section-heading reimplementation
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T23:12:33Z'
confidence_score: 98
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 25
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

Change site: `_section_text` (`scripts/little_loops/issues/research_triage.py:124-137`).

### Signatures

- `_section_text(content: str, heading: str) -> str` — `research_triage.py:124`; signature
  unchanged, body converges onto the shared helper.
- `fence_spans(content: str) -> list[tuple[int, int]]` — `text_utils.py:64` (exported by
  BUG-3202); consumed, not modified.
- `in_fence(start: int, end: int, spans: list[tuple[int, int]]) -> bool` —
  `text_utils.py:97`; consumed, not modified.

### Call Path

`triage_research_axes` (`research_triage.py:259`) → `_axis_refs` (`:157`) →
`_section_text` (`:124`) → `fence_spans`/`in_fence` heading + terminator filtering →
`_has_symbol` (`:140`) consumes the returned section text.

### Decision Rules

Converge `_section_text` onto `fence_spans`/`in_fence`, mirroring the fix already applied
to `_section_body_with_offset` — exclude fenced heading matches and make the end-boundary
scan fence-aware. Decide explicitly whether `_section_text` keeps stripping fences from
its returned text via `strip_code_fences` (its current contract — likely correct, since
`_has_symbol` scans for prose-level symbol mentions and fence content would inflate
matches) or switches to slicing the original content like `_section_body_with_offset` now
does — this is a design call specific to `_section_text`'s callers, not automatically
inherited from BUG-3202.

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
- **Breaking Change**: No — narrows what resolves as a section heading; fenced matches
  were never intentionally relied on.

## Current Behavior

`_section_text` (`research_triage.py:123-137`) resolves `## <heading>` via its own regex
with `matches[-1]` and a fence-blind `^##\s` terminator scan. A `##`-shaped line quoted
inside a code fence can win heading resolution or truncate the enclosing section — the
same symptom class BUG-3202 fixed in `_section_body_with_offset`.

## Expected Behavior

`_section_text` resolves headings and end boundaries fence-aware via the shared
`text_utils.fence_spans`/`in_fence` helper (landed with BUG-3202), matching
`_section_body_with_offset`'s behavior. Whether its return stays fence-*stripped*
(current contract, via `strip_code_fences`) or switches to slicing the original content
is decided explicitly against its callers (`_has_symbol` et al.) per Program Design.

## Scope Boundaries

Explicitly **out of scope**:

- **Changing `_section_text`'s last-occurrence-wins pick.** `matches[-1]` matches the
  deliberate contract `_section_body_with_offset` kept post-BUG-3202; only fence-awareness
  changes here.
- **Any other fence-unaware site.** BUG-3202 covered `issue_parser.py`/`session_log.py`;
  this issue covers `research_triage.py` only. A fourth site, if found, is its own issue.
- **Changing `triage_research_axes`'s axis semantics or coverage-fraction math** — only
  which text `_section_text` hands it.

## Status

**Open** | Created: 2026-08-15 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-16T00:17:33 - `64e9e21e-d2d6-44cd-97cd-d980a3cc037d.jsonl`
