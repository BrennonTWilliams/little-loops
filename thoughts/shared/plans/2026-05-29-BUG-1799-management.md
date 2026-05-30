# BUG-1799 Implementation Plan

## Summary

Replace Phase 1's bare `find` loop in `skills/audit-issue-conflicts/SKILL.md` with the awk-based status filter already proven in `skills/capture-issue/SKILL.md:167-178`. Add a regression test.

## Files to Modify

1. `skills/audit-issue-conflicts/SKILL.md:59-75` — Phase 1 collection block
2. `scripts/tests/test_audit_issue_conflicts_skill.py` — Add status-filter test

## Acceptance Criteria

- [x] Phase 1 filters to `open|in_progress|blocked` status only
- [x] Phase 1 logs both active and excluded terminal counts
- [x] Pytest fixture covers mixed-status filtering
