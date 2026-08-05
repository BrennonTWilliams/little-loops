---
id: BUG-3057
title: prose_dep_drift charges another issue's dependency phrase to the host issue
type: BUG
priority: P2
status: done
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-05
captured_at: '2026-08-05T05:42:22Z'
completed_at: '2026-08-05T05:42:22Z'
relates_to:
- FEAT-2849
- FEAT-2850
- ENH-3046
- BUG-3059
labels:
- issues
- gates
- false-positive
---

# BUG-3057: prose_dep_drift charges another issue's dependency phrase to the host issue

## Summary

`extract_prose_deps()` scans an issue body for dependency phrasings with no
notion of *whose* dependency is being described. An EPIC that enumerates its
children in a bullet like this one:

```markdown
- **FEAT-3044** — Advisor core ... (depends on FEAT-3042, FEAT-3043)
```

is read as declaring its *own* dependency, and the repo-wide drift gate demands
the edge appear in the EPIC's frontmatter.

This left `main` red: `test_no_prose_dependency_drift_in_repo` failed on
correct data.

## Steps to Reproduce

1. On a clean checkout, run:
   ```
   python -m pytest scripts/tests/test_prose_dep_sweep_gate.py
   ```
2. Observe:
   ```
   AssertionError: prose-dependency drift found: {'EPIC-3041': ['FEAT-3042']}
   ```
3. Confirm the data is correct: `.issues/epics/P3-EPIC-3041-host-agnostic-advisor.md`
   is unmodified since commit `25b7d900`, and both flagged lines describe
   FEAT-3044's dependencies, not the EPIC's — one inside `## Children`, one in a
   narration paragraph ("FEAT-3044 already correctly depends on FEAT-3042").

## Current Behavior

`scripts/little_loops/issues/prose_deps.py:68-71` (pre-fix):

```python
for m in _PHRASE_RE.finditer(body):
    if _in_fence(m.start(), m.end(), fence_spans):
        continue
    deps.add(_normalize(m.group(1), m.group(2)))
```

Every match anywhere in the body is attributed to the host issue. `_PHRASE_RE`
also captures only a single trailing ID, which is why the two-ID phrase in the
EPIC surfaced just the first of them — the second was never matched at all.

This is systematically wrong for two shapes that occur routinely: EPIC bodies
enumerating children and their edges, and session-log narration describing edits
made to *other* issues.

## Expected Behavior

A dependency phrase belongs to the subject of its own sentence or list item. When
that subject is an issue other than the host, the phrase describes that issue and
is excluded. When no other issue is named, the phrase belongs to the host and is
extracted as before.

Scoping to the sentence rather than the paragraph is load-bearing. Given:

```markdown
This work builds on BUG-5. Depends on FEAT-109.
```

the host's own dependency must still be found, because the earlier ID sits in a
different sentence and is therefore not the subject of the phrase.

## Root Cause

FEAT-2849 specified the extractor as deliberately conservative about *which
phrasings* count, but never modeled attribution — an implicit assumption that any
dependency phrase in a body is a first-person claim. That holds for BUG/FEAT/ENH
bodies and breaks for EPICs, which exist to describe other issues.

## Program Design

### Signatures

- `extract_prose_deps(body: str, host_id: str | None = None) -> set[str]` — `issues/prose_deps.py:48`, new trailing kwarg.
- `_scope_subject(body: str, match_start: int) -> str | None` — new, `issues/prose_deps.py`.
- `_SCOPE_BOUNDARY_RE: re.Pattern[str]` — new module constant.

### Call Path

`check_format_gaps` (`issue_parser.py:396`) -> `extract_prose_deps` (`issues/prose_deps.py:48`) -> `_scope_subject`, populating `FormatGaps.prose_dep_drift`; second caller `unverified_prose_deps` (`cli/issues/sequence.py:16`). Both pass the host ID they already hold. Fence filtering via `_in_fence` (`issues/prose_deps.py:44`) is unchanged.

`_SCOPE_BOUNDARY_RE` alternates three scope openers: a sentence terminator
(`[.!?]` followed by whitespace, `)`, or a quote), a blank line, and a markdown
list-item marker (`[-*+]` or `\d+.`) at line start under `re.MULTILINE`. The list
marker matters independently — a new bullet starts a new subject even with no
period on the preceding one.

`_scope_subject` walks boundaries up to `match_start`, takes the last one as the
scope start, and returns the last issue ID appearing between there and the
phrase, or `None`.

`host_id` defaults to `None`, which disables attribution entirely and preserves
the original behavior for any caller that does not pass it. Comparison is
case-insensitive via `host_id.upper()`.

## Implementation Steps

1. Add `_SCOPE_BOUNDARY_RE` and `_scope_subject` to
   `scripts/little_loops/issues/prose_deps.py`.
2. Add the `host_id` parameter to `extract_prose_deps`; skip a match whose
   subject is a different issue.
3. Pass `host_id` at both production call sites: `issue_parser.py` (`own_id`)
   and `cli/issues/sequence.py` (`issue.issue_id`).
4. Add `TestSubjectAttribution` to `scripts/tests/test_prose_deps.py` covering
   the EPIC-children shape, narration, host's own dependency, the prior-sentence
   negative case, list-item scope reset, case-insensitive host matching, and the
   `host_id`-omitted legacy path.

The `## Blocked By` section scan is deliberately left unchanged: that section is
by definition the host's own blocker list.

## Impact

`main` was red — the repo-wide prose-dependency gate, which exists to enforce
issue-metadata correctness, failed on metadata that was correct. Left in place it
trains maintainers to either ignore the gate or corrupt EPIC bodies to appease
it, and it would have blocked any subsequent `ll-auto` or sprint run that gates
on a green suite.

## Resolution

Fixed in `scripts/little_loops/issues/prose_deps.py` with attribution wired at
both call sites. Post-fix, a sweep of every active issue reports zero
`prose_dep_drift` and zero `stale_prose_dep` entries, and
`test_no_prose_dependency_drift_in_repo` passes.

## Status

**Completed** — 2026-08-05

## Session Log
- `hook:posttooluse-status-done` - 2026-08-05T05:44:40 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- run-forensics - 2026-08-05 - Found while verifying an unrelated fix; root-caused
  and fixed with attribution tests.
