---
type: ENH
id: ENH-451
title: Add sprints, loops, and automation sections to init interactive wizard
priority: P2
status: open
created: 2026-02-22
---

# Add sprints, loops, and automation sections to init interactive wizard

## Summary

Three config-schema.json sections are completely absent from the init interactive wizard:

- **`sprints`**: `sprints_dir`, `default_timeout`, `default_max_workers` — users of `ll-sprint` must discover `/ll:configure` independently
- **`loops`**: `loops_dir` — users of `ll-loop` have no init-time configuration path
- **`automation`**: `timeout_seconds`, `max_workers`, `stream_output` — the sequential `ll-auto` counterpart to `parallel` is entirely skipped

## Proposed Change

Add these as options in Round 3's multi-select "Features" question, or as a new round. Since these are power-user features, the lightest approach would be:

1. Add "Sprint management", "FSM loops", and "Sequential automation (ll-auto)" as options in Round 3's feature multi-select
2. For each selected feature, add a follow-up question in Round 5 (or a new dynamic round) covering the key settings

Alternatively, mention these in the completion message as configurable via `/ll:configure`.

## Files

- `skills/init/interactive.md` (Round 3, lines ~128-148)
- `skills/init/SKILL.md` (summary display, lines ~86-142)
- `config-schema.json` (sprints: lines ~522-546, loops: lines ~547-558, automation: lines ~118-152)
