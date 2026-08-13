---
id: ENH-3086
type: ENH
title: ll-auto --only reports bare not_found with no did-you-mean for a wrong type
  prefix
priority: P4
status: open
captured_at: '2026-08-06T16:17:02Z'
discovered_date: 2026-08-06
discovered_by: capture-issue
labels:
- ll-auto
- cli-ux
- issue-management
verify_verdict: VALID
---

# ENH-3086: ll-auto --only reports bare not_found with no did-you-mean for a wrong type prefix

## Summary

`_id_matches()` (`cli_args.py:366-386`) matches a bare numeric pattern against
any type (`_id_matches("ENH-732", "732") is True`) but requires exact equality
for a fully-typed ID (`_id_matches("ENH-732", "BUG-732") is False`). That is
correct behavior — a typed ID is an assertion about the type. But when it fails,
`_unreachable_reason()` (`issue_manager.py:1714-1748`) returns the bare string
`"not_found"`, even though it has already loaded every issue in the project and
could see that the same number exists under a different type.

Observed 2026-08-06: `ll-auto --only "ENH-3066,..."` reported
`ENH-3066: not_found`. The issue exists as **BUG-3066**
(`P3-BUG-3066-otel-loop-span-never-marks-error-outcome-never-emitted.md`).
`--only 3066` would have resolved it.

## Current Behavior

```
[01:46:34]   ENH-3066: not_found
```

No indication that `BUG-3066` exists, and no hint that the numeric form matches
across types.

## Expected Behavior

```
ENH-3066: not_found (did you mean BUG-3066? bare `3066` matches any type)
```

## Motivation

`--only` is typed by hand or copied from notes, and the type prefix is the
easiest part to get wrong — the number is the identity, the type is a
classification that can change. The fix is nearly free: the data needed for the
suggestion is already in scope at the point the bare string is returned.

Low priority: no work is lost, and the run reports it clearly at the end. This
is a legibility win, not a correctness fix.

## Current Pain Point

The operator must go grep `.issues/` to find out whether the ID was mistyped,
already closed, or genuinely nonexistent — three quite different situations that
currently share one output string.

## Proposed Solution

In `_unreachable_reason()`, in the `if not terminal_matches:` branch
(issue_manager.py:1810), before returning `"not_found"`: if `requested_id`
parses as `<TYPE>-<NNN>`, re-match `all_issues` on the numeric suffix alone. If
exactly one issue shares the number under a different type, return a suggestion
string; otherwise fall back to `"not_found"` unchanged.

```python
if not terminal_matches:
    suffix = requested_id.rsplit("-", 1)[-1]
    if suffix.isdigit():
        cross = sorted(
            i.issue_id for i in all_issues if i.issue_id.rsplit("-", 1)[-1] == suffix
        )
        if cross:
            return f"not_found (did you mean {', '.join(cross)}?)"
    return "not_found"
```

Keep the leading `not_found` token intact — loops and tests may match on it.

## Scope Boundaries

- **In scope**: the suggestion string in `_unreachable_reason()`.
- **Out of scope**: changing `_id_matches()` semantics. A typed ID must keep
  meaning what it says; loosening it to match across types would silently
  process the wrong issue, which is far worse than a clear `not_found`.

## API/Interface

`_unreachable_reason()` returns a human-readable string already documented as
free-form (`"human-readable reason string"`). Verify no test asserts exact
equality with `"not_found"` before changing it — prefer `startswith` there.

## Integration Map

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/issue_manager.py` | `_unreachable_reason`, ~1810 | Cross-type suggestion |
| `scripts/tests/` | `not_found` assertions | Loosen exact-equality assertions if present |

## Implementation Steps

1. Grep the test suite for exact `"not_found"` assertions.
2. Add the cross-type lookup and suggestion.
3. Test: wrong prefix suggests the right ID; genuinely absent ID still returns
   plain `not_found`.

## Impact

Purely diagnostic. No behavior change to which issues are processed.

## Status

open

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: `_id_matches()`
confirmed in cli_args.py:380 matching description. `_unreachable_reason()`'s
`not_found` branch confirmed in issue_manager.py, but now around line 1806,
not the previously cited :1743/:1730-1748. Logic and shape unchanged, only
line numbers drifted.

**2026-08-12** (`/ll:verify-issues`): Re-verified VALID; refreshed the
`_unreachable_reason()` citation to the exact current line (issue_manager.py:1810)
in the Proposed Solution and Integration Map sections.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:12 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:28 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:capture-issue` - 2026-08-06T16:20:22 - `ee676905-966c-42aa-ac9d-d7d4aaeea91d.jsonl`
