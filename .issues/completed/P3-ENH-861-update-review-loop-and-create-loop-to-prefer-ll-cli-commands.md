---
id: ENH-861
type: ENH
priority: P3
status: completed
title: "Update review-loop and create-loop skills to prefer ll- CLI commands"
discovered_date: "2026-03-23"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-861: Update review-loop and create-loop skills to prefer ll- CLI commands

## Summary

The `/ll:review-loop` and `/ll:create-loop` skills should prefer using the project's native `ll-` CLI commands (e.g., `ll-issues`, `ll-sprint`, `ll-loop`) over ad-hoc bash/grep approaches where possible, especially for issue management operations.

## Current Behavior

`create-loop/loop-types.md` and `create-loop/reference.md` contain raw bash/grep patterns for operations the `ll-` CLI already handles:
- `loop-types.md:557` — skill discovery uses `ls skills/*/SKILL.md | sed ...` instead of the Glob tool
- `loop-types.md:795` and `:861` — filter issues with `status == 'open'` (broken: actual active-status value is `'active'`)
- `reference.md:715` — YAML example uses `ll-issues list --status open --format ids` (both flags are invalid)

## Expected Behavior

All issue-management and skill-discovery steps in `create-loop/` use `ll-` CLI commands or Claude-native tools:
- Skill discovery uses the Glob tool with pattern `skills/*/SKILL.md`
- Issue listing uses `ll-issues list --json` with no invalid status filter
- `ll-issues list` flag usage matches the actual CLI interface (`--json`, `--flat`, `--limit`, `--status active`)

## Motivation

The `ll-` CLI tools are purpose-built for this project's data structures and provide consistent, tested behavior. Using them in skills instead of raw bash commands reduces fragility, improves consistency with how users interact with the project, and keeps skill instructions aligned with the documented toolchain described in CLAUDE.md.

Currently, `review-loop` and `create-loop` may instruct the agent to use raw bash/grep for operations like listing issues or inspecting issue state, when commands like `ll-issues list`, `ll-issues next-id`, or `ll-sprint show` already do this reliably.

## Scope Boundaries

- **In scope**: `skills/create-loop/loop-types.md` (lines 557, 795, 861); `skills/create-loop/reference.md` (line 715)
- **Out of scope**: `skills/review-loop/SKILL.md` (already uses `ll-loop` CLI exclusively); `skills/create-loop/SKILL.md` (already compliant); `skills/create-loop/templates.md` (no raw issue-management patterns); Python CLI tools; `scripts/` directory

## Integration Map

### Files to Modify
- `skills/create-loop/loop-types.md` — **Primary target**. Contains the raw bash patterns that need updating (lines 557, 795, 861). This file is loaded by `create-loop/SKILL.md` via the Read tool.

### Files Already Compliant (No Changes Needed)
- `skills/review-loop/SKILL.md` — Already uses `ll-loop list` (line 36), `ll-loop validate` (lines 93, 350). `allowed-tools` frontmatter at line 3–4 restricts bash to `Bash(ll-loop:*)` exclusively.
- `skills/review-loop/reference.md` — Contains no bash patterns; pure quality-check catalog.
- `skills/create-loop/SKILL.md` — Already uses `ll-loop validate` (line 201) and `ll-loop test` (line 222). The `mkdir` (line 175) and `test -f` (line 180) are legitimate filesystem ops with no CLI equivalent.
- `skills/create-loop/templates.md` — No raw bash issue management patterns.

### Also Needs Fix
- `skills/create-loop/reference.md:715` — Uses `ll-issues list --status open --format ids`. Both flags are wrong: `--status open` should be omitted or `--status active`; `--format ids` does not exist in `ll-issues list` (valid flags: `--json`, `--flat`).

### Dependent Callers
- `scripts/little_loops/cli/issues/__init__.py` — Entry point for `ll-issues`; registers `list`, `next-id`, `show`, `count`, `search`, `append-log` subcommands.
- `scripts/little_loops/cli/issues/list_cmd.py` — The `ll-issues list` implementation. Supports `--json`, `--status`, `--limit`, `--flat` flags. Default status is `"active"` (not `"open"`).

### Similar Patterns to Follow
- `skills/analyze-history/SKILL.md:1–11` — Skill that wraps a single ll- CLI tool with `allowed-tools: [Bash(ll-history:*)]` pattern.
- `skills/map-dependencies/SKILL.md:1–11` — Same pattern with `Bash(ll-deps:*)`.
- `skills/review-loop/SKILL.md:32–60` — `ll-loop list` → AskUserQuestion selection flow (model for how to use ll- CLI output in skills).

### Tests
- `scripts/tests/` — Run `python -m pytest scripts/tests/` to verify no regressions.

## Specific Changes Required

### `skills/create-loop/reference.md` — One location

**Line 715** — Example YAML state with invalid flags:
```bash
# Current (invalid — --status open and --format ids don't exist):
action: "ll-issues list --status open --format ids"
# Correct (use --json since capture stores full output; default status is already active):
action: "ll-issues list --json"
```

### `skills/create-loop/loop-types.md` — Three locations

**1. Line 557** — Skill discovery:
```bash
# Current (raw bash):
ls skills/*/SKILL.md 2>/dev/null | sed 's|skills/||' | sed 's|/SKILL.md||'
# Replacement: Use Glob tool (Claude-native) instead of bash:
# Replace the bash block with a note to use the Glob tool pattern: skills/*/SKILL.md
```
Note: No `ll-` CLI command covers skill listing. The preferred approach for Claude-executed steps is the Glob tool. The bash block at line 556–558 should be replaced with a Glob tool instruction.

**2. Line 795** — Discovery commands table (broken filter):
```bash
# Current (buggy — 'open' never matches; actual status value is 'active'):
ll-issues list --json | python3 -c "import json,sys; issues=[i for i in json.load(sys.stdin) if i.get('status')=='open']; print(issues[0]['id']) if issues else sys.exit(1)"
# Correct (remove redundant filter since ll-issues list defaults to active):
ll-issues list --json | python3 -c "import json,sys; issues=json.load(sys.stdin); print(issues[0]['id']) if issues else sys.exit(1)"
```

**3. Line 861** — Template example (same bug):
```bash
# Current (same 'open' filter bug in embedded YAML template):
ll-issues list --json | python3 -c "
import json, sys
issues = json.load(sys.stdin)
open_issues = [i for i in issues if i.get('status') == 'open']
if not open_issues:
    sys.exit(1)
print(open_issues[0]['id'])
"
# Correct:
ll-issues list --json | python3 -c "
import json, sys
issues = json.load(sys.stdin)
if not issues:
    sys.exit(1)
print(issues[0]['id'])
"
```

## Implementation Steps

1. Read `skills/create-loop/reference.md:715` — fix `--status open --format ids` → `--json` (default status is already active)
2. Read `skills/create-loop/loop-types.md` (confirm lines 557, 795, 861)
3. Fix line 557: Replace `ls skills/*/SKILL.md | sed ...` bash block with a Glob-tool instruction (e.g., _"Use the Glob tool with pattern `skills/*/SKILL.md`"_)
4. Fix line 795: Remove `if i.get('status') == 'open'` filter from the discovery command table entry — `ll-issues list --json` already returns only active issues
5. Fix line 861: Apply the same fix to the `discover` state in the embedded harness-refine-issue YAML template
6. Verify `review-loop/SKILL.md` (already clean — confirm no additional changes needed)
7. Run `python -m pytest scripts/tests/ -q` to check no regressions

## Acceptance Criteria

- [x] Both skills explicitly prefer `ll-` CLI commands for issue-related operations
- [x] No raw `ls .issues/` or manual grep for issue state where a CLI equivalent exists
- [x] CLI command usage is consistent with documented interface in CLAUDE.md and `docs/reference/API.md`
- [x] `review-loop/SKILL.md` confirmed compliant (no changes needed)
- [x] `create-loop/loop-types.md:795` and `:861` discovery commands use `ll-issues list --json` without broken `status=='open'` filter
- [x] `create-loop/loop-types.md:557` skill discovery uses Glob tool instead of `ls | sed`
- [x] `create-loop/reference.md:715` example uses valid `ll-issues list` flags (`--json` instead of `--status open --format ids`)

## Success Metrics

- Zero raw `ls .issues/` or grep-for-status patterns remain in `create-loop/loop-types.md` and `create-loop/reference.md`
- All `ll-issues list` usages in skill files pass valid flags (`--json`, `--flat`, `--limit`, or `--status active`)
- Skill discovery at `loop-types.md:557` instructs use of the Glob tool, not `ls | sed`
- All 4 identified locations corrected (3 in `loop-types.md`, 1 in `reference.md`)

## API/Interface

N/A — No public API changes. Modifications are to skill instruction markdown files only, not Python code.

## Impact

- **Priority**: P3 — Improves toolchain consistency and prevents broken examples from propagating into FSM loops; not blocking
- **Effort**: Small — Four targeted text edits across two markdown files
- **Risk**: Low — Changes are to skill instruction text, not executable code; no Python modifications
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `cli`

## Resolution

Fixed 4 locations across 2 files:
- `skills/create-loop/loop-types.md:556–558` — Replaced `ls skills/*/SKILL.md | sed ...` bash block with Glob tool instruction
- `skills/create-loop/loop-types.md:795` — Removed broken `status=='open'` filter; `ll-issues list --json` already returns only active issues
- `skills/create-loop/loop-types.md:861–868` — Same fix in embedded YAML template example
- `skills/create-loop/reference.md:715` — Fixed invalid flags `--status open --format ids` → `--json`

All 3863 tests pass.

## Session Log
- `/ll:ready-issue` - 2026-03-23T18:29:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa97f181-0c89-48a7-90d1-c20a0ffe9cd8.jsonl`
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7754065d-d79f-4df1-9b8e-8e6c7e070b2c.jsonl`
- `/ll:format-issue` - 2026-03-23T18:09:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4be9bd15-4ea4-4d36-846c-df93dbbf77e9.jsonl`
- `/ll:refine-issue` - 2026-03-23T17:13:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ce5d0bc6-5ac2-4aae-8e31-43ca6876d26e.jsonl`
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06fdc033-986b-4b59-b280-3505ad02d65c.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P3
