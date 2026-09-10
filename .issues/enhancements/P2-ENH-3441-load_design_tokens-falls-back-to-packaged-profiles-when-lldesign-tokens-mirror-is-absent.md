---
id: ENH-3441
type: ENH
title: load_design_tokens falls back to packaged profiles when .ll/design-tokens/
  mirror is absent
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
---

# ENH-3441: load_design_tokens falls back to packaged profiles when .ll/design-tokens/ mirror is absent

## Summary

Token resolution reads only config.project_root/.ll/design-tokens (design_tokens.py ~433), which is a gitignored local mirror of scripts/little_loops/templates/design-tokens/profiles/ (ENH-3275). Any clean checkout (CI, new contributor, fresh ll-init) silently renders design-token-aware artifacts with no tokens, and test_policy_builder_renders_byte_identically_to_golden_fixture fails at byte 299. Add a packaged-profile fallback plus a drift-gate test asserting mirror and packaged profiles agree (the objection ENH-3275 raised against committing the mirror). Do NOT regenerate the golden fixture in the degraded state (A5).

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
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
