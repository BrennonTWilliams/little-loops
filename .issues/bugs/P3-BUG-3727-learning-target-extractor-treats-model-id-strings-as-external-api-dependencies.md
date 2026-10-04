---
id: BUG-3727
type: BUG
title: learning-target extractor treats model-ID strings as external-API dependencies
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T17:31:16Z'
---

# BUG-3727: learning-target extractor treats model-ID strings as external-API dependencies

## Summary

`extract_learning_targets()` (`scripts/little_loops/learning_tests/extractor.py`) asks an LLM to list external dependencies from issue prose. It returned `claude-sonnet-5-5` for BUG-3726, where the model ID only names the model used in a live evaluation. `/ll:explore-api` then wrote a `refuted` record (the installed SDK's `Model` literal lacks the ID; no auth for a live call), and `ll-auto` reported "Learning gate blocked: unproven external-API deps".

Proposed: add a deterministic post-filter (like `_STDLIB_EXCLUDED`) that drops targets matching Claude/other model-ID patterns (e.g. `^claude-[a-z0-9.-]+$`), and tighten the prompt to exclude model names used as test fixtures or evaluation subjects.

Related: the frontmatter `learning_tests_required: []` escape hatch was broken because `IssueParser` collapsed `[]` to `None`; fixed alongside this issue's filing.


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
