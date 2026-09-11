---
id: BUG-3448
type: BUG
title: 'main suite red: priority-regex allowlist drift in mcp_server/tools.py and
  corpus baseline 569>562'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-11'
captured_at: '2026-09-11T06:12:59Z'
---

# BUG-3448: main suite red: priority-regex allowlist drift in mcp_server/tools.py and corpus baseline 569>562

## Summary

[Description extracted from input]

## Current Behavior

`python -m pytest scripts/tests/` on `main` (verified 2026-09-11 at f1905f8e1^, with and
without unrelated working-tree changes) fails 3 tests in `scripts/tests/test_issue_parser.py`:

- `TestPriorityRegexCompletenessAllowlist::test_no_unallowlisted_raw_priority_regex` —
  `new raw priority regex not in the allowlist: {'mcp_server/tools.py': [846, 1001]}`
- `TestPriorityRegexCompletenessAllowlist::test_allowlist_entries_still_exist` —
  `stale allowlist entries: ['mcp_server/tools.py:795', 'mcp_server/tools.py:941']`
- `TestBug3295ContainmentCorpusDifferential::test_total_report_count_does_not_exceed_post_bug_3413_baseline` —
  `corpus report total 569 exceeds post-BUG-3413 baseline 562`

## Expected Behavior

- The authoritative local gate (`python -m pytest scripts/tests/`) exits 0 on `main`.
- The priority-regex allowlist matches HEAD's `scripts/little_loops/mcp_server/tools.py`
  (new raw regexes at lines 846/1001 either allowlisted with justification or converted
  to `resolve_priority`; stale entries at 795/941 removed).
- The corpus differential baseline accounts for the current `.issues/` corpus size (569).

## Impact

- **Priority**: P2 — the authoritative CI gate (`python -m pytest scripts/tests/`, run by
  the self-hosted runner on every push to `main`) is red for reasons unrelated to any
  individual change, masking real regressions.
- **Effort**: Small — allowlist line-number refresh + baseline bump (or making the
  baseline corpus-relative).
- **Risk**: Low — test-infra only.

Discovered during BUG-3443's full-suite verification (failures reproduced with the
BUG-3443 edit stashed, proving pre-existence on `main`).

## Steps to Reproduce

1. `python -m pytest scripts/tests/test_issue_parser.py -k "Allowlist or total_report_count"`
2. Observe the 3 failures above.

## Root Cause

- `scripts/little_loops/mcp_server/tools.py` moved/grew (most recently 3fe6a1dac
  `feat(mcp): add skills_list`) without updating the raw-priority-regex allowlist in
  `test_issue_parser.py` — line drift made entries 795/941 stale and exposed 846/1001.
- The `.issues/` corpus grew past the hard-coded `_POST_BUG_3413_TOTAL_REPORTS = 562`
  baseline; the count is a corpus-size function, so recent issue creation (BUG-3443
  session-log appends, BUG-3447 edits) trips it.

## Status

**Open** | Created: 2026-09-11 | Priority: P2
