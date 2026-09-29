---
id: ENH-3653
type: ENH
title: Anchor the priority-regex allowlist on symbols, not line numbers
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T04:19:19Z'
---

# ENH-3653: Anchor the priority-regex allowlist on symbols, not line numbers

## Summary

`TestPriorityRegexCompletenessAllowlist` in `scripts/tests/test_issue_parser.py` keys its allowlist of raw priority regexes on file line numbers (for example `session_store/writers.py` at lines near 3100). Any edit above those lines shifts them and fails two tests at once (`test_no_unallowlisted_raw_priority_regex` and `test_allowlist_entries_still_exist`), even though nothing about the regex usage changed. It broke three times during FEAT-3535 from unrelated import and helper edits in `writers.py`.

## Current Behavior

The allowlist maps `path -> {line_number: justification}`. Adding or removing lines earlier in the file makes the recorded numbers stale, and the failure message lists the new numbers for a manual update.

## Expected Behavior

The allowlist identifies each entry by a stable anchor (the enclosing symbol name such as `_FILENAME_PRIORITY_RE`, or the enclosing function or class, plus the pattern text) so unrelated edits do not fail the gate. A genuinely new raw priority regex still fails; a removed one still reports a stale entry.

## Motivation

Two tests fail with a misleading "new regex" message on every edit above the pinned lines, costing a manual line-number edit each time and training contributors to update allowlists without reading them.

## Proposed Solution

Change the allowlist keys from line numbers to symbol anchors resolved via `ast` (module-level assignment target or enclosing `def`/`class`), keeping the justification strings. Keep the stale-entry check keyed on the anchor and pattern.

## Integration Map

### Files to Modify
- `scripts/tests/test_issue_parser.py` (`TestPriorityRegexCompletenessAllowlist`)

### Tests
- The same two tests; add one that shifts a line and confirms the gate still passes.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P4. Test-maintenance friction only.
- **Effort**: Small.
- **Risk**: Low.

## Acceptance Criteria

- [ ] Inserting or deleting lines above an allowlisted regex in `session_store/writers.py` does not fail the gate.
- [ ] A newly added raw priority regex outside the allowlist still fails.
- [ ] A removed allowlisted regex still reports a stale entry.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-09-29T04:19:25 - `4d45d755-73ff-4de3-8bd1-bb8e866143f2.jsonl`
