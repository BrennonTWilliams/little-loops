---
id: ENH-3061
title: prose-dep gate flags example prose in issues that document the extractor
type: ENH
priority: P4
status: open
testable: true
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T16:06:39Z'
relates_to:
- BUG-3057
- FEAT-2849
- FEAT-2850
labels:
- issues
- gates
- authoring
---

# ENH-3061: prose-dep gate flags example prose in issues that document the extractor

## Summary

Writing an issue *about* the prose-dependency extractor requires quoting
dependency prose as examples, and the extractor charges those examples to the
issue as real dependency claims. `_in_fence` recognizes fenced code blocks but
not inline backticks, so the only escape hatch is a multi-line fence — heavy
markup for what is often a four-word phrase mid-sentence.

## Motivation

This is not hypothetical. BUG-3057, the issue documenting the attribution bug in
this very extractor, failed `format-check` on its own body during authoring and
needed two example phrases restructured into fenced blocks before it would pass.

The friction is narrow but self-inflicted: the subsystem's own documentation is
the corpus most likely to trip its gate, so the people best positioned to
maintain it hit the worst authoring experience.

## Current Behavior

`issues/prose_deps.py:64` builds fence spans from `_CODE_FENCE` only:

```python
fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(body)]
```

`_in_fence` (`issues/prose_deps.py:44`) then suppresses any match inside those
spans. Inline-backtick runs are not collected, so a phrase written as inline
code is still extracted and reported as `prose_dep_drift`.

BUG-3057's attribution fix helps only when the example names another issue as
its sentence subject. An example with no named subject — such as this one,
which had to be fenced for this very issue to pass its own gate:

```markdown
Depends on FEAT-109
```

is still attributed to the host.

## Expected Behavior

An issue ID inside an inline-backtick span is treated the same as one inside a
fenced block: not a dependency claim. Authors can write an example inline without
promoting it to a fenced block, and without the gate producing a finding that
must be worked around rather than fixed.

## Proposed Solution

Collect inline-code spans alongside fenced ones and pass both to `_in_fence`.

An inline span is a backtick run of length N delimiting content up to the next
run of exactly N backticks on the same line, matching CommonMark closely enough
for issue bodies. The existing `_CODE_FENCE` collection is unchanged; the two
span lists concatenate, and `_in_fence`'s containment test already generalizes
over any span list.

Worth confirming during implementation: whether this should live in
`text_utils` beside `_CODE_FENCE` rather than in `prose_deps`, since other gates
(`stale_file_ref`, `ambiguous_file_ref`) plausibly want the same treatment and
may already have the same latent defect.

Explicitly out of scope: relaxing the gate, adding a per-issue suppression key,
or exempting issues by label. The gate is correct to be strict — the problem is
only that the existing escape hatch is coarser than the common case.

## Program Design

### Signatures

- `_in_fence(start: int, end: int, fence_spans: list[tuple[int, int]]) -> bool` — existing, `issues/prose_deps.py:44`; unchanged, already generalizes over any span list.
- `extract_prose_deps(body: str, host_id: str | None = None) -> set[str]` — existing, `issues/prose_deps.py:48`; span collection at line 64 gains inline spans.
- `_CODE_FENCE: re.Pattern[str]` — existing, `text_utils.py`; unchanged.
- `_inline_code_spans(body: str) -> list[tuple[int, int]]` — new, location to be decided between `prose_deps` and `text_utils`.

### Call Path

`check_format_gaps` (`issue_parser.py:396`) -> `extract_prose_deps` (`issues/prose_deps.py:48`) -> `_in_fence` (`issues/prose_deps.py:44`). The new span collector feeds the same `fence_spans` list that `_CODE_FENCE.finditer` currently populates alone, so no call-site signature changes. Second consumer `unverified_prose_deps` (`cli/issues/sequence.py:16`) inherits the behavior unchanged.

## Scope Boundaries

**In scope**: inline-backtick span collection feeding the existing `_in_fence`
suppression, for `prose_dep_drift` and `stale_prose_dep`.

**Out of scope**: relaxing the gate's phrase list, per-issue suppression keys,
label-based exemptions, and any change to attribution (BUG-3057's concern).
Extending the same treatment to `stale_file_ref` / `ambiguous_file_ref` is a
plausible follow-up but should be confirmed as a real defect first, not assumed.

## Impact

Authoring friction on a narrow but recurring class of issue. No correctness
impact: the gate's findings on real dependency claims are unaffected, and the
current workaround (fenced blocks) does work.

Low priority because the corpus of affected issues is small — those documenting
`prose_deps`, `format-check`, and the issue-gate family. It earns capture because
the workaround is invisible to the next author, who will rediscover it the same
way.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/CLI.md` § format-check | Documents `prose_dep_drift` and its remedies |
| `docs/reference/API.md` § check_format_gaps | Gap-class reference including fence behavior |

## Status

**Open**

## Session Log
- `/ll:capture-issue` - 2026-08-05T16:09:36 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- `/ll:capture-issue` - 2026-08-05 - Captured from the ENH-3046 run forensics
  session, after BUG-3057 tripped its own gate during authoring.
