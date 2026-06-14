---
id: ENH-2072
title: Wire dead-skills to flag zero-invocation skills in backlog
type: ENH
priority: P4
status: deferred
discovered_date: '2026-06-10'
discovered_by: capture-issue
captured_at: '2026-06-10T15:59:33Z'
labels:
- ll-logs
- dead-skills
- backlog
- prioritize-issues
- telemetry
parent: EPIC-1918
relates_to:
- EPIC-1918
---

# ENH-2072: Wire dead-skills to flag zero-invocation skills in backlog

## Summary

`ll-logs dead-skills` currently lists skills with zero or low invocations in the window but the output is never connected to the issue backlog. As of 2026-06-10, ~30 skills have 0 invocations in the last 30 days (including `align-issues`, `analyze-workflows`, `create-sprint`, `loop-suggester`, `prioritize-issues`, `workflow-automation-proposer`). Open issues for these skills should be automatically deprioritized or flagged for review rather than sitting at P3 silently.

## Current Behavior

`ll-logs dead-skills` identifies skills with zero or low invocations over a configurable window and outputs the list (with `--json` flag for machine-readable output), but that output is never consumed programmatically. Open issues for dead skills remain at their original priority indefinitely — there is no automatic signal to the backlog that a skill is unused, so they consume review/refinement cycles silently.

## Expected Behavior

Running `ll-issues set-scores --from-dead-skills` (or an equivalent `--dead-skills` flag on `ll-prioritize-issues`) reads `ll-logs dead-skills --json` output, matches zero-invocation skills (absent ≥30 days) to open issues by skill name, and either: (a) bumps matched issues' priority down one notch (P3→P4, etc.) and appends `dead_skill_flag: true` to their frontmatter, or (b) surfaces a `## Dead Skill Signals` section in `ll-prioritize-issues` output for manual review. Skills listed in an exemption set (`dead_skill_exempt: true` in `SKILL.md`) are skipped.

## Motivation

Half the skill catalog being unused while carrying open issues is a backlog-hygiene problem. Issues for dead skills consume review/refinement cycles and distort priority ordering. Connecting usage data to issue priority makes the backlog self-correcting.

## Implementation Steps

1. **New `ll-issues` subcommand or `ll-logs` integration**: `ll-issues set-scores --from-dead-skills` (or a standalone script) that:
   - Runs `ll-logs dead-skills --project . --window-days 30 -j`
   - For each skill in the `never` tier, finds open issues whose title contains the skill name
   - Appends a `dead_skill_flag: true` frontmatter field and bumps priority down one notch (P3 → P4, etc.) if currently above P4
   - Logs which issues were adjusted
2. **Alternative (simpler)**: Add a `## Dead Skill Signals` section to `ll-prioritize-issues` output showing which open issues correspond to zero-invocation skills, without auto-modifying priorities
3. **Threshold**: Only flag skills absent for ≥ 30 days. Skills absent for < 14 days may just be dormant for a sprint.
4. **Exclusion list**: Some skills are intentionally rare (e.g., `init`, `manage-release`) — allow a `dead_skill_exempt: true` frontmatter field in SKILL.md to skip the flag

## Acceptance Criteria

- Running `ll-issues set-scores --from-dead-skills` (or equivalent) outputs a list of issues adjusted
- Issues for skills with 0 invocations over 30 days are at P4 or lower
- Skills in an exemption list are not flagged
- `ll-logs dead-skills` JSON output is consumed without modification (no new ll-logs changes needed)
- `/ll:find-dead-code` surfaces a "Skills never invoked (last 30 days)" section sourced from `ll-logs dead-skills` output, with exempt skills omitted (scope added 2026-06-12 — EPIC-1918's scope states dead-skills "feeds find-dead-code"; backlog flagging alone does not satisfy that consumer wiring)

## Success Metrics

- Open issues matching dead skills are at P4 or lower after running the command
- `ll-logs dead-skills --json` output consumed as-is (no ll-logs source changes required)
- Exempt skills (e.g., `init`, `manage-release`) are not flagged in any run

## Scope Boundaries

- **In scope**: Consuming `ll-logs dead-skills --json` output; matching skill names to open issue titles; deprioritizing or flagging matched issues; exemption list support via `dead_skill_exempt: true` in `SKILL.md`; 30-day absence threshold with 14-day dormancy grace period
- **Out of scope**: Modifying `ll-logs dead-skills` output format or internals; auto-closing issues (deprioritize/flag only, not close); changes to invocation tracking or session store; skills absent for < 14 days

## Impact

- **Priority**: P4 — backlog hygiene improvement, not blocking; low urgency
- **Effort**: Small — composes two existing CLI outputs with minimal new code
- **Risk**: Low — additive change (new subcommand or output section); no modification to existing behavior
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — add `set-scores --from-dead-skills` subcommand (primary entry point)
- `scripts/little_loops/issue_manager.py` — add priority-bump and `dead_skill_flag` frontmatter mutation logic

### Dependent Files (Callers/Importers)
- `ll-logs dead-skills` in `scripts/little_loops/cli/logs.py` — read-only consumer (no changes needed)
- `ll-issues` CLI entry point

### Similar Patterns
- `ll-issues set-status` — existing frontmatter mutation pattern to follow
- `ll-issues refine-status` — existing batch-update traversal pattern

### Tests
- `scripts/tests/test_issues_cli.py` and/or `scripts/tests/test_cli_issue_commands.py` — add tests for new `set-scores` subcommand
- Mock `ll-logs dead-skills --json` output for deterministic unit tests

### Documentation
- `docs/reference/API.md` — document new `ll-issues set-scores` subcommand
- `CLAUDE.md` CLI tools section — add entry for `ll-issues set-scores`

### Configuration
- `SKILL.md` frontmatter: `dead_skill_exempt: true` (new opt-out field for intentionally rare skills)

## Verification Notes (2026-06-13)

2026-06-13: Integration Map corrected. `scripts/little_loops/cli/issues.py` does not exist; correct path is `scripts/little_loops/cli/issues/__init__.py`. Test file references updated to `test_issues_cli.py` / `test_cli_issue_commands.py`.

## Session Log
- `/ll:verify-issues` - 2026-06-14T00:12:54 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:58 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:format-issue` - 2026-06-10T16:06:44 - `d19c37d7-acef-4974-bf90-d673d4b0ec70.jsonl`

- `/ll:capture-issue` - 2026-06-10T15:59:33Z - surfaced via `ll-logs dead-skills` showing ~30 zero-invocation skills with no backlog connection

## Status

**Open** | Created: 2026-06-10 | Priority: P4
