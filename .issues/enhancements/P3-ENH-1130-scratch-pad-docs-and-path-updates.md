---
id: ENH-1130
type: ENH
priority: P3
status: open
parent: ENH-1111
size: Small
---

# ENH-1130: Documentation and Path Updates for Scratch-Pad Hook

## Summary

Update all documentation and inline references for the scratch-pad enforcement feature: correct `/tmp/ll-scratch/` → `.loops/tmp/scratch/` everywhere, update CLAUDE.md to describe automatic enforcement, document new `scratch_pad` config properties in CONFIGURATION.md and ARCHITECTURE.md. Independent of ENH-1128/ENH-1129 — can be done in any order.

## Parent Issue

Decomposed from ENH-1111: Scratch-Pad Enforcement via PreToolUse Hook

## Motivation

BUG-817 migrated the active scratch path to `.loops/tmp/scratch/` but CLAUDE.md still references `/tmp/ll-scratch/`. Additionally, once the hook ships (ENH-1129), the prose convention text in CLAUDE.md can be replaced with a pointer to the `scratch_pad` config keys.

## Acceptance Criteria

- `.claude/CLAUDE.md:122-130` (`## Automation: Scratch Pad` section) updated to:
  - Describe automatic enforcement via the hook
  - Correct path from `/tmp/ll-scratch/` → `.loops/tmp/scratch/`
  - Point at `scratch_pad` config keys (`enabled`, `threshold_lines`, `automation_contexts_only`, etc.)
  - Remove prose instructions the hook now enforces
- `docs/reference/CONFIGURATION.md:155,474-481` updated with the four new `scratch_pad` properties (`automation_contexts_only`, `tail_lines`, `command_allowlist`, `file_extension_filters`) and their defaults
- `docs/ARCHITECTURE.md:90-95` (hook scripts directory listing) gains `scratch-pad-redirect.sh` entry
- `docs/guides/LOOPS_GUIDE.md:556` — correct `/tmp/ll-scratch` → `.loops/tmp/scratch` in `scratch_dir` CLI override example
- After editing CLAUDE.md, run `python -m pytest scripts/tests/test_create_extension_wiring.py -v` to confirm `"ll-create-extension"` and `"ll-generate-schemas"` string assertions still pass (low-risk but verify; test reads CLAUDE.md at `scripts/tests/test_create_extension_wiring.py:83-87,162-166`)

## Files to Modify

- `.claude/CLAUDE.md:122-130`
- `docs/reference/CONFIGURATION.md:155,474-481`
- `docs/ARCHITECTURE.md:90-95`
- `docs/guides/LOOPS_GUIDE.md:556`

## Session Log
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fc25386-a9f0-4e75-8434-c659db481895.jsonl`
