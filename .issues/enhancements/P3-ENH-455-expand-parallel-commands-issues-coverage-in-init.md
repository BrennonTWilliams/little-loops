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

## Proposed Change

For each section, add key questions when the feature is selected:

1. **parallel** (when selected in Round 3): Add `max_workers` (2/3/4) and `timeout_per_issue` (1h/2h/4h) to Round 5
2. **commands**: Add `pre_implement`/`post_implement` as an option in Round 7 (Project Advanced) since they're power-user settings
3. **issues**: Add `completed_dir` question to Round 2 alongside `base_dir`

Less critical fields (`p0_sequential`, `max_merge_retries`, `custom_verification`, `templates_dir`, `priorities`) can remain configure-only.

## Files

- `skills/init/interactive.md` (Rounds 2, 5, 7)
- `config-schema.json` (reference for all fields)
