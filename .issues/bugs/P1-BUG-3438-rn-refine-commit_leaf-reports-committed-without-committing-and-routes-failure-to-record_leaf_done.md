---
id: BUG-3438
type: BUG
title: rn-refine commit_leaf reports COMMITTED without committing and routes failure
  to record_leaf_done
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# BUG-3438: rn-refine commit_leaf reports COMMITTED without committing and routes failure to record_leaf_done

## Summary

commit_leaf (rn-refine.yaml ~602-616) has no set -e and ends in `|| true`, so a failed `git commit` (no identity, pre-commit reject, index lock) still echoes COMMITTED, exits 0, and writes the pre-leaf HEAD to leaf-baseline-commit.txt. Worse, its on_error already routes to record_leaf_done, which marks the leaf `verified`, so `set -euo pipefail` alone is insufficient: the error path must go to record_failure (or a new record_leaf_commit_failed state). Audit sibling actions for the same `echo SUCCESS; ... || true` shape. Test: give the ephemeral repo an explicit git identity (hermetic) and add a failing-commit case asserting non-zero exit and no COMMITTED marker (B2).

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


## Session Log
- `/ll:scope-epic` - 2026-09-10T21:15:16 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
