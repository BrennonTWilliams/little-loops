---
type: ENH
id: ENH-455
title: Expand parallel, commands, and issues coverage in init wizard
priority: P3
status: open
created: 2026-02-22
---

# Expand parallel, commands, and issues coverage in init wizard

## Summary

Several config sections are only partially covered by the init wizard:

### parallel (only `worktree_copy_files` asked)
Missing: `max_workers`, `timeout_per_issue`, `p0_sequential`, `max_merge_retries`, `stream_subprocess_output`

### commands (only `confidence_gate` asked)
Missing: `pre_implement`, `post_implement`, `custom_verification`

### issues (only `base_dir` asked)
Missing: `completed_dir`, `templates_dir`, `priorities` customization, custom `categories`

## Current Behavior

The init wizard partially covers several config sections:

- **parallel**: Only `worktree_copy_files` is asked; `max_workers`, `timeout_per_issue`, `p0_sequential`, `max_merge_retries`, `stream_subprocess_output` are not configurable via init
- **commands**: Only `confidence_gate` is asked; `pre_implement`, `post_implement`, `custom_verification` are not surfaced
- **issues**: Only `base_dir` is asked; `completed_dir`, `templates_dir`, `priorities`, custom `categories` are not surfaced

Users must manually edit `ll-config.json` or use `/ll:configure` for these fields.

## Expected Behavior

The most commonly-needed parallel settings (`max_workers`, `timeout_per_issue`) are asked when parallel processing is selected in Round 3. The `completed_dir` is asked alongside `base_dir` in Round 2. Power-user settings remain configure-only but are mentioned in the completion message.

## Motivation

Users who enable parallel processing frequently need to set `max_workers` based on their machine's CPU count and `timeout_per_issue` based on typical issue complexity. These are the two most likely parallel settings to need non-default values, yet init doesn't ask for them.

## Motivation

Users who enable parallel processing commonly need to set `max_workers` based on their machine's CPU count and `timeout_per_issue` based on typical issue complexity, but init silently applies defaults without surfacing these options. Similarly, `completed_dir` alongside `base_dir` is a natural pairing that users expect to configure together. The gap between what init configures and what users typically need forces manual `ll-config.json` editing as a first step after onboarding.

## Proposed Solution

For each section, add key questions when the feature is selected:

1. **parallel** (when selected in Round 3): Add `max_workers` (2/3/4) and `timeout_per_issue` (1h/2h/4h) to Round 5
2. **commands**: Add `pre_implement`/`post_implement` as an option in Round 7 (Project Advanced) since they're power-user settings
3. **issues**: Add `completed_dir` question to Round 2 alongside `base_dir`

Less critical fields (`p0_sequential`, `max_merge_retries`, `custom_verification`, `templates_dir`, `priorities`) can remain configure-only.

## Scope Boundaries

- **In scope**: Adding `max_workers` and `timeout_per_issue` to Round 5 when parallel is selected; adding `completed_dir` to Round 2; adding `pre_implement`/`post_implement` to Round 7
- **Out of scope**: `p0_sequential`, `max_merge_retries`, `custom_verification`, `templates_dir`, `priorities`, custom categories — these remain configure-only

## Integration Map

### Files to Modify
- `skills/init/interactive.md` — Round 2 (add completed_dir question); Round 5 (add max_workers and timeout_per_issue when parallel selected); Round 7 (add pre_implement/post_implement)
- `config-schema.json` — reference for field defaults and valid values

### Similar Patterns
- Existing Round 3 → Round 5 pattern for worktree_copy_files question

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `completed_dir` question to Round 2 of `interactive.md` alongside `base_dir`
2. Add `max_workers` (2/3/4 option select) and `timeout_per_issue` (1h/2h/4h) to Round 5 when parallel is selected
3. Add `pre_implement`/`post_implement` as an optional question pair in Round 7 (Project Advanced)
4. Verify Round 5 question count stays within 4-question limit (or applies overflow splitting from BUG-449 fix)
5. Update SKILL.md config summary display to show newly configurable fields

## Impact

- **Priority**: P3 — Most parallel users want non-default max_workers; init silently applies defaults
- **Effort**: Small-Medium — Extending existing round patterns; no structural changes
- **Risk**: Low — Additive questions; existing behavior unchanged when questions are skipped
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `interactive-wizard`, `parallel`, `config`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`

## Blocked By

- BUG-449
- ENH-451
- ENH-452

---

## Status

**Open** | Created: 2026-02-22 | Priority: P3
