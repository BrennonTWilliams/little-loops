---
id: ENH-2939
title: Delete skill prose duplicating existing CLIs; codify flag-parse and session-log conventions
type: ENH
priority: P1
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
program_design_not_applicable: true
labels:
- skills
- cleanup
- determinism
---

# ENH-2939: Delete skill prose duplicating existing CLIs; codify flag-parse and session-log conventions

## Summary

Markdown-only cleanup (no Python changes) that removes prose which duplicates existing CLI/helper functionality and establishes two shared conventions the rest of EPIC-2938 adopts. Cheapest child; do first.

## Current Behavior

1. **decide-issue duplicates check-decidable**: `skills/decide-issue/SKILL.md` Phase 3 (L150–193) asks the LLM to run four literal regexes in precedence order to detect enumerable options, plus resolution-marker scans at L201–221. The file itself notes (L482–491) that FSM callers use `ll-issues check-decidable`, a pure-Python reimplementation of the same logic — so the algorithm lives twice and can diverge.
2. **Session-log JSONL hunting**: 7 files (`audit-claude-config`, `capture-issue`, `confidence-check`, `go-no-go`, `issue-size-review`, `manage-issue`, `scope-epic`) instruct the LLM to find the current session log by scanning `~/.claude/projects/` for the dash-encoded project dir and the most recently modified `.jsonl`. 11 other files already call `ll-issues append-log` or `little_loops.session_log.append_session_log_entry`.
3. **Flag-parse boilerplate**: an identical ~15-line block (`--dangerously-skip-permissions` / `LL_NON_INTERACTIVE` / `DANGEROUSLY_SKIP_PERMISSIONS` → `AUTO_MODE`, then `--auto`/`--check`/`--all`/`--sprint`) is duplicated in 17 files: skills `audit-issue-conflicts`, `audit-loop-run`, `confidence-check`, `decide-issue`, `debug-loop-run`, `go-no-go`, `init`, `format-issue`, `issue-size-review`, `map-dependencies`, `spike`, `wire-issue`; commands `normalize-issues`, `commit`, `prioritize-issues`, `refine-issue`, `verify-issues`.

## Expected Behavior

1. decide-issue Phase 3 replaced by a single `ll-issues check-decidable <ID>` call (and `check-open-questions` where the resolution-marker scan applies); the deleted prose is not restated anywhere. LLM retains Phase 4–5 (evidence gathering, 4-dimension scoring, winner selection).
2. All 7 JSONL-hunting blocks replaced with `ll-issues append-log <issue_path> "<command>"` (or a one-line pointer to `little_loops.session_log.append_session_log_entry` where a path-only variant is needed).
3. A single canonical flag-parse snippet (short — a few lines) defined once (e.g. in a shared companion doc or inline convention paragraph) and the 17 duplicated blocks replaced with it. This is a convention/prose consolidation, not a new mechanism or CLI.

## Proposed Solution

Pure markdown edits. Reuse points: `scripts/little_loops/cli/issues/check_decidable.py` (wraps `issue_parser.locate_enumerable_options`), `ll-issues check-open-questions`, `ll-issues append-log`, `scripts/little_loops/session_log.py::append_session_log_entry`.

## Implementation Steps

1. Rewrite `skills/decide-issue/SKILL.md` Phase 3/3b-i to delegate to the CLI gates; delete the regex prose (~60 lines).
2. Sweep the 7 session-log files; replace hunt-prose with the CLI/helper call.
3. Define the canonical flag-parse snippet; apply across the 17 files.
4. Run `ll-verify-skills` and `python -m pytest scripts/tests/` (no behavior change expected).

## Acceptance Criteria

- [ ] `skills/decide-issue/SKILL.md` contains no option-detection regexes; it calls `ll-issues check-decidable`
- [ ] No skill/command instructs scanning `~/.claude/projects/` for session JSONL files
- [ ] The ~15-line flag-parse block appears at most once (as the canonical definition), not 17 times
- [ ] `ll-verify-skills` passes; `python -m pytest scripts/tests/` green
- [ ] Net markdown reduction recorded in the PR/commit description

## Program Design

### Types

- N/A — markdown-only change; no Python types added or modified

### Signatures

Existing surfaces consumed (unchanged):
- `ll-issues check-decidable <ID>` → exit 0/1 (`cli/issues/check_decidable.py`, wraps `issue_parser.locate_enumerable_options`)
- `ll-issues check-open-questions <ID>` → exit 0/1
- `ll-issues append-log <issue_path> <log_command>`
- `little_loops.session_log.append_session_log_entry(...)`

## Scope Boundaries

- In scope: prose deletion/replacement in `skills/decide-issue/SKILL.md`, the 7 session-log files, and the 17 flag-parse sites; defining the canonical flag-parse snippet.
- Out of scope: any Python/CLI changes; altering decide-issue's Phase 4–5 judgment flow; new arg-parsing mechanisms.

## Impact

- **Priority**: P1 - Cheapest child; removes live prose/Python divergence and sets conventions the rest of EPIC-2938 adopts
- **Effort**: Small - Markdown edits only
- **Risk**: Low - No behavior change; verified by ll-verify-skills + existing tests

## Status

**Open** | Created: 2026-07-31 | Priority: P1

## Notes

If the 17-file flag-parse sweep balloons, split steps 1–2 from step 3 into a follow-up.
