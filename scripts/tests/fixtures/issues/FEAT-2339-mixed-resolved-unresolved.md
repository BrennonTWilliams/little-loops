---
id: FEAT-2339
title: Example feature with mixed resolved/unresolved decision surface (ENH-2446)
type: feature
status: open
priority: P3
decision_needed: true
---

# FEAT-2339: Example feature with mixed resolved/unresolved decision surface

## Summary

Snapshotted fixture for the coverage-aware decidability probe (ENH-2446). Two options
already resolved (`> **Selected:**` / `### Decision Rationale` markers present, each followed by
its own `### Decision Rationale` subsection) PLUS
free-form open questions in `## Edge Cases` and `## Confidence Check Notes`. The
count-based `count_enumerable_options` returns 2; the coverage-aware
`count_unresolved_options` + `count_open_questions_in_sections` return 0 + 2
respectively, so this fixture must route to `deposit_options`, not `decide`.

## Current Behavior

N/A — fixture only.

## Expected Behavior

N/A — fixture only.

## Proposed Solution

### Option A: Inline rewriting

> **Selected:** A — chosen because it preserves the existing public API.

### Decision Rationale

Inline rewriting is the lowest-risk path; the public API stays identical.

### Option B: Adapter wrapper

A wrapper module translates between the legacy and modern shapes. Kept on the
back-burner in case Option A's perf profile proves unworkable.

### Decision Rationale

Option B's wrapper indirection would help if Option A's perf profile is
unworkable, but the upfront complexity isn't worth the optionality today.

### Implementation Outline

Wire the new module into the existing call site.

## Edge Cases

- **Q: How do we handle malformed JSON payloads?** Open question — see confidence-check.
- **Q: What happens when the upstream service is down for >5 minutes?** Needs decision.
- **Q: Should retry policy live in caller or library?** Open question.

## Confidence Check Notes

- `confidence-check` flagged: "open question: retry policy ownership" — decision needed.
- `confidence-check` flagged: "open decision: backoff strategy" — no current option block.

## Implementation Status

None yet — pending the resolved questions above.

## Labels

`feature`, `fixture`

---

## Status
**Open** | Created: 2026-07-08 | Priority: P3