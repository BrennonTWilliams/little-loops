---
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 86
---

# FEAT-719: ll-loop analyze synthesizes issues from loop history

## Summary

Add a new `/ll:` skill (or `ll-loop analyze` subcommand) that finds the most recently run or interrupted loop via `ll-loop list --running`, loads its execution history with `ll-loop history <name>`, analyzes the results, and synthesizes actionable issues (bugs, enhancements, features) to create or update.

## Current Behavior

- `ll-loop history <name>` shows raw execution events for a named loop
- `ll-loop list --running` lists active/interrupted loops
- No tool bridges loop execution data into the issue tracker
- Users manually inspect history output and decide whether to file issues

## Expected Behavior

A new command/skill that:
1. Runs `ll-loop list --running` (and optionally `--status interrupted`) to find recent loops
2. Selects the most recent loop (or prompts if multiple candidates exist)
3. Runs `ll-loop history <name>` to retrieve execution events
4. Analyzes the history for: repeated failures, stuck states, unexpected terminations, performance anomalies, or improvement patterns
5. Synthesizes findings into issue proposals (BUG/ENH/FEAT) with context from the loop run
6. Creates new issues or updates existing ones via the standard issue lifecycle

## Motivation

Loop execution produces rich diagnostic data — failed states, retry counts, stall events, unexpected transitions — but that data is currently siloed in the history output and never feeds back into the issue tracker. Closing this loop (pun intended) makes automation failures self-documenting and turns loop runs into a source of continuous improvement rather than a black box.

## Proposed Solution

Create a new skill `ll:analyze-loop` (or extend `ll-loop` with an `analyze` subcommand) that:

1. Enumerates candidate loops via `ll-loop list --running --json` (now fully supported as of BUG-725) and parses the JSON output; or falls back to reading `.loops/.running/*.state.json` directly
2. Selects the most recent by `updated_at` field from `LoopState` (or prompts if multiple candidates exist)
3. Loads event history via `ll-loop history <name> --json` (now supported as of BUG-725) — outputs raw event list as JSON without colorization; or call `get_loop_history(loop_name, loops_dir)` Python API directly
4. Classifies events into issue signals using event type + field analysis:
   - `action_complete` with `exit_code != 0` repeatedly on same state → BUG candidate
   - `loop_complete` with `terminated_by == "signal"` → BUG candidate (SIGKILL)
   - `state_enter` on same state N+ times (retry flood) → ENH candidate
   - `action_complete` with high `duration_ms` consistently → ENH candidate (performance)
   - `evaluate` with `verdict == "fail"` repeated → BUG/ENH depending on pattern
5. Deduplicates against existing active issues (same loop name + state)
6. Presents proposed issues to the user for confirmation
7. Creates issue files using `ll-issues next-id` for ID allocation, then writes files directly to `.issues/{bugs,features,enhancements}/` and runs `git add` (follow `commands/scan-codebase.md` pattern)

### SKILL.md Frontmatter (follow `skills/review-loop/SKILL.md` pattern)

```yaml
---
description: |
  Analyze loop execution history to synthesize actionable issues (bugs, enhancements)
  from failed states, SIGKILL terminations, retry floods, and performance anomalies.
  Trigger keywords: "analyze loop", "loop issues", "loop failures", "loop history issues"
argument-hint: "[loop-name]"
model: sonnet
allowed-tools:
  - Bash(ll-loop:*, ll-issues:*, python:*, git:*)
  - Read
  - Write
  - AskUserQuestion
arguments:
  - name: loop_name
    description: Loop name to analyze (optional — auto-selects most recent if omitted)
    required: false
---
```

## Integration Map

### Files to Create
- `skills/analyze-loop/SKILL.md` — skill definition and invocation instructions (no companion `.py` needed — no existing skill uses one; all logic goes in the SKILL.md itself)

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — exposes `get_loop_history()` (line 455) and `StatePersistence.read_events()` (line 198); no changes likely needed but this is the authoritative event source
- `skills/capture-issue/SKILL.md` — no changes needed; skill is a consumer

### Key Implementation Files (Read-Only)
- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` (line 40), `cmd_history()` (line 228), `_format_history_event()` (line 125); NOT `__init__.py` — the CLI subcommand logic lives here
- `scripts/little_loops/cli/loop/__init__.py` — argument parser and subcommand dispatch; defines `--running`, `--json`, `--tail` flags (lines 144, 148, 198, 203)
- `scripts/little_loops/fsm/signal_detector.py` — `HANDOFF_SIGNAL`, `ERROR_SIGNAL`, `STOP_SIGNAL` patterns; `SignalDetector` class — relevant to SIGKILL/ERROR event classification

### Dependent Files (Callers/Importers)
- N/A — new skill; nothing imports it yet. `ll-loop` CLI and FSM runner are consumed, not modified.

### Similar Patterns
- `commands/loop-suggester.md` — adjacent loop-analysis command (note: NOT `skills/loop-suggester/` — no such skill dir exists; it's a command)
- `commands/scan-codebase.md` — same "analyze → classify → deduplicate → create issues" pattern (note: NOT `skills/scan-codebase/` — no such skill dir exists)
- `skills/analyze-history/SKILL.md` — closest structural analog skill (analyze data → propose improvements)
- `skills/review-loop/SKILL.md` — only existing skill that uses `Bash(ll-loop:*)` in `allowed-tools`; pattern to follow for SKILL.md frontmatter

### Tests
- `scripts/tests/test_fsm_persistence.py` — mock `list_running_loops()` and `get_loop_history()` directly (NOT CLI subprocess); fixture pattern at lines 620-665 for building synthetic `.loops/.running/` trees
- `scripts/tests/test_ll_loop_commands.py` — tests `cmd_list`, `cmd_history`, `cmd_show`; shows mocking patterns

### Documentation
- `.claude-plugin/plugin.json` — register new `analyze-loop` skill
- `docs/reference/COMMANDS.md` — update command reference if maintained

### Configuration
- No new config keys; respects existing `issues.*` settings for duplicate detection and templates

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`ll-loop list --running --json` now works** (fixed by BUG-725, `info.py:46-71`):
- `cmd_list()` now checks `--json` at line 58 inside the `--running` branch and calls `print_json([s.to_dict() for s in states])`
- Safe to use directly: `ll-loop list --running --json` outputs JSON array of `LoopState` dicts

**`ll-loop history <name> --json` now works** (fixed by BUG-725, `info.py:247-249`):
- `cmd_history()` now checks `--json` at line 247 and calls `print_json(events[-tail:])` — outputs raw event dicts as JSON, no colorization
- Safe to use directly: `ll-loop history <name> --json` outputs a JSON array of event dicts with full field access

**State file location** (`persistence.py:147-149`): Loop state and events live at `.loops/.running/<loop_name>.{state.json,events.jsonl}` relative to the project root.

## Use Case

A developer runs a nightly `ll-loop run issue-fixer` loop. In the morning they run:
```
/ll:analyze-loop
```
The skill finds the interrupted `issue-fixer` loop, sees that state `verify` failed 3 times with SIGKILL before succeeding, and proposes BUG-720: "verify state killed by SIGKILL in issue-fixer loop". The developer approves and the bug is filed with the loop history snippet as context.

## Acceptance Criteria

- [x] Running `/ll:analyze-loop` with no args auto-selects the most recently run/interrupted loop via `ll-loop list --running --json` (now fully supported)
- [x] When multiple candidate loops exist, the user is prompted to select one
- [x] `ll-loop history <name> --json` output is parsed into a structured event list (timestamp, state, event type, exit code); `--verbose` flag may be combined for additional `action_output` events
- [x] `ERROR`/`SIGKILL` terminations produce BUG candidates; repeated retries produce ENH candidates; consistently slow states produce ENH candidates
- [x] Proposed issues are deduplicated against active issues using loop name + state as a key (no duplicate files created)
- [x] User must confirm before any issue files are written (interactive prompt with `[Y/n/select]`)
- [x] Approved issues are created with loop history excerpt as context via direct file write
- [x] Explicit loop name (`/ll:analyze-loop issue-fixer`) bypasses loop selection and goes directly to history analysis
- [x] `--tail N` flag limits history events analyzed to the N most recent entries

## API/Interface

```bash
# Skill invocation (auto-selects most recent loop)
/ll:analyze-loop

# Skill with explicit loop name
/ll:analyze-loop issue-fixer

# CLI subcommand alternative
ll-loop analyze
ll-loop analyze issue-fixer --tail 100
```

Expected output:
```
Analyzing loop: issue-fixer (last run: 2026-03-13 02:14)

Found 3 issue signals:

  [1] BUG P2 — verify state terminated by SIGKILL (3 occurrences)
  [2] ENH P3 — scan state retried 5x; consider raising retry limit
  [3] ENH P4 — fetch state avg 45s; caching may help

Create all 3 issues? [Y/n/select]
```

## Implementation Steps

1. **Load candidate loops**: Run `ll-loop list --running --json` and parse the JSON output; filter by `status in ("interrupted", "failed", "timed_out", "running")` and sort by `updated_at` descending. Fallback: read `.loops/.running/*.state.json` directly if CLI unavailable.
2. **Load event history**: Run `ll-loop history <loop_name> --json` (optionally with `--tail N`) and parse the JSON output — returns `list[dict]` where each event has `"event"` (type) and `"ts"` (ISO 8601); key fields: `action_complete.exit_code`, `action_complete.duration_ms`, `loop_complete.terminated_by`, `state_enter.state`, `state_enter.iteration`, `evaluate.verdict`, `evaluate.reason`
3. **Classify signals**: Implement rules against the structured event list (NOT CLI text output); consult `signal_detector.py` for existing SIGKILL/ERROR detection patterns; group events by `state_enter.state` to detect retry floods
4. **Deduplicate**: Compare signal title/loop-name+state key against active issues in `.issues/{bugs,enhancements,features}/`; use same Jaccard similarity approach as `capture-issue` (threshold 0.5 for similar, 0.8 for exact)
5. **Render proposals table** and collect confirmation via `AskUserQuestion`
6. **Allocate IDs**: Run `ll-issues next-id` for each approved issue
7. **Write issue files** to `.issues/{bugs,enhancements,features}/P[X]-[TYPE]-[NNN]-[slug].md`; include loop history excerpt (relevant events) as context in the issue body
8. **Stage files**: Run `git add .issues/` after writing
9. **Write tests** in `scripts/tests/test_analyze_loop.py`: mock `list_running_loops()` and `get_loop_history()` directly (NOT CLI subprocess); follow fixture patterns in `test_fsm_persistence.py:620-665`

## Impact

- **Priority**: P3 - High-value diagnostics tool; low user friction to install
- **Effort**: Medium - Event parsing and classification are the main complexity
- **Risk**: Low - Read-only loop interaction; only creates/updates issue files
- **Breaking Change**: No

## Verification Notes

**Verdict**: NEEDS_UPDATE — two file path references corrected. All CLI flags verified accurate.

**Verified accurate:**
- `ll-loop list --running --json` — both flags present in `scripts/little_loops/cli/loop/__init__.py` (lines 144, 148)
- `ll-loop history <name> --verbose` — exists (`--verbose`/`-v` on history subparser, line 191)
- `ll-loop history <name> --tail N` — exists as `--tail`/`-n`, default 50 (line 188)
- `skills/capture-issue/SKILL.md` — exists
- `.claude-plugin/plugin.json` — exists

**Corrected:**
- `scripts/little_loops/fsm/history.py` → does not exist; replaced with `persistence.py` which contains `get_loop_history()` (the actual event source)
- `scripts/skills/analyze_log/SKILL.md` → does not exist in repo; it's a plugin command, not a local file

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `issue-management`, `captured`

## Status

**Completed** | Created: 2026-03-13 | Completed: 2026-03-13 | Priority: P3

---

## Resolution

**Implemented**: Created `skills/analyze-loop/SKILL.md` with full 6-step pipeline:
1. Loop selection via `ll-loop list --running --json` (auto-selects most recent interrupted/failed loop; prompts if multiple)
2. Event history loading via `ll-loop history <name> --json --tail <N>` (default 200)
3. Signal classification — 6 rules covering action failures, SIGKILL, FATAL_ERROR, retry floods, slow states, eval failures
4. Grep-based deduplication against `.issues/{bugs,enhancements,features}/`
5. `AskUserQuestion` confirmation with `[Y/n/select]` interface
6. Issue file creation via `ll-issues next-id` + `Write` + `git add .issues/`

Also updated `docs/reference/COMMANDS.md` with the new command entry and quick reference row.

Note: No Python module was created (none needed per issue spec — all logic lives in SKILL.md instructions for Claude).

---

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1bce590-015a-4862-aabe-11dcbf71a389.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ece248e3-a7ba-4bdc-9a07-c3af61df2fe9.jsonl`
- `/ll:confidence-check` - 2026-03-13T18:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6989f534-c0f7-4db5-88e8-3b0c841b4cb2.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96ed1145-2e6e-4281-9ed9-a09eba03b35d.jsonl`
- `/ll:ready-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/18d1b634-9acb-408a-ba23-de0415681693.jsonl`
- `/ll:manage-issue` - 2026-03-13T21:10:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
