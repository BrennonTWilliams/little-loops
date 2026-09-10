---
id: BUG-3443
type: BUG
title: test_env_var_overrides_cpu_count asserts against host CPU count instead of
  patching os.cpu_count
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# BUG-3443: test_env_var_overrides_cpu_count asserts against host CPU count instead of patching os.cpu_count

## Summary

conftest.pytest_xdist_auto_num_workers clamps the PYTEST_XDIST_AUTO_NUM_WORKERS override to cpus-2, but test_env_var_overrides_cpu_count (test_conftest_cap.py ~50) is the only sibling that does not patch os.cpu_count, so it passes on 14 cores and fails 2==3 on the 4-core runner. Patch os.cpu_count like the siblings, correct the two stale docstrings describing pre-clamp behaviour, and add a case pinning the clamp itself (env=99, cpus=4 -> 2) (A2).

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
- `/ll:scope-epic` - 2026-09-10T21:15:18 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
