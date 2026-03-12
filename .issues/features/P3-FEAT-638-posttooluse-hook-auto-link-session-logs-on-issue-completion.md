---
discovered_date: 2026-03-07
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 79
---

# FEAT-638: PostToolUse Hook to Auto-Link Session Logs on Issue Completion

## Summary

Add a `PostToolUse` hook that detects when an issue file is moved to the `completed/` directory via `git mv` (through a Bash tool call) and automatically appends a `## Session Log` entry to the issue file. This ensures session provenance is captured for every issue completion path, not just those managed by the `manage-issue` skill.

## Context

**Direct mode**: User description: "Add a PostToolUse hook that detects when an issue file is moved to the completed/ directory via git mv (via a Bash tool call) and automatically appends a Session Log entry to the issue file with the current session JSONL path and timestamp. This ensures session logs are linked to completed issues regardless of which path completed them (manage-issue skill, ll-auto, ll-parallel, ll-sprint, or manual). Currently only manage-issue does this in Phase 5 Step 1.5, leaving other completion paths untracked."

## Current Behavior

Session Log entries are only appended to issue files when:
- `manage-issue` skill executes Phase 5, Step 1.5

The following completion paths produce **no session log**:
- `ll-auto` (sequential batch processing)
- `ll-parallel` (concurrent worktree processing)
- `ll-sprint` (dependency-ordered sprint execution)
- `ready-issue`, `verify-issues`, `tradeoff-review-issues`, `issue-size-review` skills moving issues to `completed/` (partially addressed by ENH-524, but only via skill-level instructions, not enforced at infrastructure level)
- Manual `git mv` operations

## Expected Behavior

Any time a Bash tool call containing `git mv ... completed/` is detected, a `PostToolUse` hook fires and:

1. Parses the `git mv` command to extract the destination file path
2. Confirms the destination is within the `completed/` directory
3. Finds the most recently modified `.jsonl` file in `~/.claude/projects/<encoded-project-path>/` (excluding `agent-*` prefixed files)
4. Appends a `## Session Log` entry to the moved issue file:

```markdown
## Session Log
- `hook:posttooluse-git-mv` - [ISO timestamp] - `[path to session JSONL]`
```

If `## Session Log` already exists, the new entry is appended below the header. If it doesn't exist, the section is inserted before the `---` / `## Status` footer.

## Motivation

- **Coverage gap**: `manage-issue` is not the only path that completes issues. Automation tools (`ll-auto`, `ll-parallel`, `ll-sprint`) and direct skill invocations bypass the skill's Phase 5 step.
- **Infrastructure reliability**: A hook fires at the tool call level regardless of which skill, command, or user action triggered it — no per-skill implementation needed.
- **Audit trail completeness**: Session logs are the only way to trace which Claude session produced a completed issue, critical for debugging and retrospection.
- **Complementary to ENH-524**: ENH-524 added session log steps to specific skills via instructions. This hook provides a safety net that cannot be accidentally omitted.

## Proposed Solution

### Dual Implementation Approach

This feature requires changes in two separate layers to cover all completion paths:

**Layer 1 — Python (covers ll-auto, ll-parallel, ll-sprint)**

Call the existing `append_session_log_entry()` from `session_log.py` at the Python completion call sites:

1. In `scripts/little_loops/issue_lifecycle.py:complete_issue_lifecycle()` (~line 646, after `_move_issue_to_completed()` returns `True`):
   ```python
   from little_loops.session_log import append_session_log_entry
   # ... after _move_issue_to_completed() succeeds:
   append_session_log_entry(completed_path, "ll-auto")
   ```

2. In `scripts/little_loops/parallel/orchestrator.py:_complete_issue_lifecycle_if_needed()` (~line 1096, after git mv succeeds):
   ```python
   from little_loops.session_log import append_session_log_entry
   # ... after git mv at line 1096 succeeds:
   append_session_log_entry(completed_path, "ll-parallel")
   ```

**Layer 2 — Hook (covers manage-issue Bash tool path, as safety net)**

### New Hook Script: `hooks/scripts/issue-completion-log.sh`

```bash
#!/usr/bin/env bash
# PostToolUse hook: append session log to issues moved to completed/ via Bash tool

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Read JSON input from stdin (NOT $1 — hooks receive input via stdin)
INPUT=$(cat)

# Only process Bash tool calls
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
[ "$TOOL_NAME" != "Bash" ] && exit 0

# Extract the command from tool_input
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Check if this is a git mv to completed/
echo "$CMD" | grep -qE 'git mv .+completed/' || exit 0

# transcript_path is provided directly in PostToolUse stdin — no path lookup needed
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""')
[ -z "$TRANSCRIPT_PATH" ] && exit 0

# Extract destination path from git mv command
# Handles: git mv "src" "dest" or git add ... && git mv "src" "dest"
DEST_PATH=$(echo "$CMD" | grep -oE 'git mv [^ ]+ [^ ]+' | tail -1 | awk '{print $NF}' | tr -d '"')
[ -z "$DEST_PATH" ] && exit 0

# Append session log entry using Python (leverages existing session_log module)
python3 -c "
import sys
from pathlib import Path
from little_loops.session_log import append_session_log_entry
dest = Path('$DEST_PATH')
jsonl = Path('$TRANSCRIPT_PATH')
if dest.exists():
    append_session_log_entry(dest, 'hook:posttooluse-git-mv', session_jsonl=jsonl)
" 2>/dev/null || true

exit 0
```

### Hook Registration in `hooks/hooks.json`

Add a new `PostToolUse` hook with matcher `Bash`:

```json
{
  "matcher": "Bash",
  "hooks": [
    {
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/issue-completion-log.sh",
      "timeout": 5,
      "statusMessage": "Logging session to completed issue..."
    }
  ]
}
```

## Use Case

A developer runs `ll-auto` to batch-process a sprint of 10 issues overnight. Each issue is completed by the automation moving it to `completed/` via `git mv`. In the morning, the developer reviews completed issues and finds every one has a `## Session Log` entry pointing to the exact session JSONL that produced it — enabling them to trace decisions, reproduce context, or diagnose issues without knowing which automation run handled each issue.

## Acceptance Criteria

- [ ] New hook script `hooks/scripts/issue-completion-log.sh` exists and is executable
- [ ] Hook is registered in `hooks/hooks.json` under `PostToolUse` with matcher `Bash`
- [ ] Hook fires when a Bash tool call contains `git mv ... completed/`
- [ ] Hook does NOT fire for unrelated Bash tool calls
- [ ] Appended entry follows the `## Session Log` format used by other commands
- [ ] If `## Session Log` already exists, new entry is appended (not duplicated or replaced)
- [ ] If `## Session Log` does not exist, section is inserted before `## Status` footer
- [ ] Hook exits cleanly (non-blocking) if JSONL cannot be found
- [ ] Hook handles multi-command Bash strings (e.g., `git add ... && git mv ...`)
- [ ] `manage-issue` Phase 5 Step 1.5 session log step can be simplified or removed (hook covers it)
- [ ] `issue_lifecycle.py:complete_issue_lifecycle()` calls `append_session_log_entry(completed_path, "ll-auto")` after `_move_issue_to_completed()` returns `True`
- [ ] `orchestrator.py:_complete_issue_lifecycle_if_needed()` calls `append_session_log_entry(completed_path, "ll-parallel")` after git mv succeeds
- [ ] `scripts/tests/test_issue_lifecycle.py` has a test verifying the session log call (with mock)
- [ ] `scripts/tests/test_orchestrator.py` has a test verifying the session log call (with mock)

## Implementation Steps

1. **Python: `issue_lifecycle.py:complete_issue_lifecycle()`** (~line 646)
   - Import `append_session_log_entry` from `little_loops.session_log`
   - After `_move_issue_to_completed()` returns `True`, call `append_session_log_entry(completed_path, "ll-auto")` — non-blocking (returns `False` on failure)
   - This covers the `ll-auto` path and any direct caller of `complete_issue_lifecycle()`

2. **Python: `orchestrator.py:_complete_issue_lifecycle_if_needed()`** (~line 1096)
   - Import `append_session_log_entry` from `little_loops.session_log`
   - After the git mv succeeds (and after `completed_path.write_text(content)`), call `append_session_log_entry(completed_path, "ll-parallel")`
   - This covers `ll-parallel` and `ll-sprint` (which both use `ParallelOrchestrator`)

3. **Hook script: `hooks/scripts/issue-completion-log.sh`**
   - Use `INPUT=$(cat)` for stdin (not `$1`)
   - Source `lib/common.sh` following `context-monitor.sh` pattern
   - Read `transcript_path` from stdin JSON via `jq -r '.transcript_path'` (no path-encoding needed)
   - Extract destination path from `git mv` command string
   - Call `python3 -c "... append_session_log_entry(...)"` using the existing `session_log` module
   - Mark executable: `chmod +x hooks/scripts/issue-completion-log.sh`

4. **Hook registration: `hooks/hooks.json`**
   - Add new entry to `PostToolUse` array (alongside existing `context-monitor.sh` entry):
     ```json
     {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/issue-completion-log.sh", "timeout": 5, "statusMessage": "Logging session to completed issue..."}]}
     ```

5. **Tests**
   - `scripts/tests/test_issue_lifecycle.py` — add test verifying `complete_issue_lifecycle()` calls `append_session_log_entry` when move succeeds; mock `session_log.append_session_log_entry`
   - `scripts/tests/test_orchestrator.py` — add test verifying `_complete_issue_lifecycle_if_needed()` appends session log after successful git mv
   - Bash unit tests for `issue-completion-log.sh` (pattern matching, no-op on non-git-mv commands)

6. **Update `manage-issue` SKILL.md Phase 5 Step 1.5** — add note that the hook provides a safety net; leave the manual step in place

7. **Update `docs/ARCHITECTURE.md`** — document both the hook and the Python-level session log integration

## Impact

- **Priority**: P3 - Session log coverage gap affects all automation paths (`ll-auto`, `ll-parallel`, `ll-sprint`); only `manage-issue` currently logs, leaving the majority of completions untracked
- **Effort**: Small - New bash script (~50 lines) + one JSON hook registration entry + two Python call sites in existing functions (~4 lines each)
- **Risk**: Low - Hook exits cleanly on any failure (non-blocking); worst case is a missing log entry, not data loss or broken functionality
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `hooks/hooks.json` — add `PostToolUse` hook entry with `Bash` matcher (for `manage-issue` path)
- `scripts/little_loops/issue_lifecycle.py` — call `append_session_log_entry()` from `complete_issue_lifecycle()` after `_move_issue_to_completed()` succeeds (line ~646); covers `ll-auto` path
- `scripts/little_loops/parallel/orchestrator.py` — call `append_session_log_entry()` from `_complete_issue_lifecycle_if_needed()` after git mv at line ~1096; covers `ll-parallel`/`ll-sprint` path

### New Files
- `hooks/scripts/issue-completion-log.sh` — hook script to detect `git mv ... completed/` and append session log (covers `manage-issue` Bash tool path only)

### Dependent Files (Callers/Importers)
- `skills/manage-issue/SKILL.md:385-389` — Phase 5 Step 1.5 session log step; can be noted as now covered by hook (but leave in place as belt-and-suspenders)
- `scripts/little_loops/issue_lifecycle.py:285-346` — `_move_issue_to_completed()` does the subprocess `git mv`; then `complete_issue_lifecycle()` at line 603 orchestrates the full flow
- `scripts/little_loops/parallel/orchestrator.py:1035-1134` — `_complete_issue_lifecycle_if_needed()` handles the orchestrator's git mv at line 1096
- `scripts/little_loops/issue_manager.py:584-649` — `ll-auto`'s verification/fallback completion logic calls `complete_issue_lifecycle()`

### Reusable Infrastructure (already exists, just needs to be called)
- `scripts/little_loops/session_log.py:85-131` — `append_session_log_entry(issue_path, command, session_jsonl)` — already handles both "Session Log exists" and "insert before Status footer" cases; returns `False` on failure (non-blocking)
- `scripts/little_loops/session_log.py:62-82` — `get_current_session_jsonl(cwd)` — finds most-recently-modified `*.jsonl` excluding `agent-*` in `~/.claude/projects/<encoded-path>/`
- `scripts/little_loops/user_messages.py:318-344` — `get_project_folder(cwd)` — encodes project path as `str(cwd.resolve()).replace("/", "-")`

### Similar Patterns
- `hooks/scripts/context-monitor.sh` — full PostToolUse hook template: stdin via `INPUT=$(cat)`, jq field extraction, exit 0/2 semantics
- `hooks/scripts/check-duplicate-issue-id.sh:28-69` — PreToolUse hook extracting `tool_input.file_path`; pattern for checking if a file path is under a specific directory
- `hooks/hooks.json:42-54` — existing PostToolUse entry (matcher `"*"`, `${CLAUDE_PLUGIN_ROOT}`, 5s timeout)

### Tests
- `scripts/tests/test_session_log.py` — existing tests for `append_session_log_entry` and `get_current_session_jsonl`; add tests for new call sites
- `scripts/tests/test_issue_lifecycle.py` — add test verifying `complete_issue_lifecycle()` appends session log
- `scripts/tests/test_orchestrator.py` — add test verifying `_complete_issue_lifecycle_if_needed()` appends session log
- New unit tests for `issue-completion-log.sh` bash logic (pattern matching, input parsing)

### Documentation
- `docs/ARCHITECTURE.md` — document new `PostToolUse` hook and Python-level session log integration in hook/lifecycle sections

### Configuration
- `hooks/hooks.json` — hook registration (matcher: `Bash`, type: `command`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Completion path inventory** (with session log status):
| Path | Git mv mechanism | Session log? | PostToolUse fires? |
|---|---|---|---|
| `manage-issue` skill | Claude Bash tool (`SKILL.md:396-402`) | Yes — Phase 5 Step 1.5 (`SKILL.md:385-389`) | Yes |
| `ll-auto` / `AutoManager` | `subprocess.run()` in `issue_lifecycle.py:319-324` | No | No |
| `ll-parallel` / `ll-sprint` orchestrator | `self._git_lock.run(["mv", ...])` in `orchestrator.py:1096` | No | No |
| Orchestrator `close_issue()` | `_move_issue_to_completed()` via `subprocess.run()` | No | No |

**PostToolUse stdin schema** (from `docs/claude-code/hooks-reference.md:899-916`): The payload includes `transcript_path` — the full absolute path to the active session JSONL — meaning the hook script can read `jq -r '.transcript_path'` directly rather than doing the `~/.claude/projects/` path-encoding lookup. This simplifies the hook script significantly.

**Correct stdin convention**: `INPUT=$(cat)` (not `$1` as shown in the proposed bash script). Confirmed by `context-monitor.sh:17`.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Hook system design and lifecycle |
| config | hooks/hooks.json | Hook registration format |
| skill | skills/manage-issue/SKILL.md | Phase 5 Step 1.5 session log step this complements |

## Labels

`feature`, `hooks`, `session-log`, `captured`

---

## Verification Notes

Re-verified 2026-03-08 (auto). Verdict: **VALID**.

- `hooks/hooks.json` exists; PostToolUse section confirmed ✓
- `hooks/scripts/` directory exists with reference scripts ✓
- `skills/manage-issue/SKILL.md` Phase 5 Step 1.5 confirmed (line 385) ✓
- `issue-completion-log.sh` does not yet exist — expected for a new feature ✓
- `ll-parallel` orchestrator confirmed to use `git mv` for completions (`orchestrator.py:1095`) ✓
- Coverage gap verified: no session log appended outside `manage-issue` Phase 5 ✓
- **Minor note**: Proposed bash script uses `TOOL_INPUT="$1"` but actual hook convention is stdin (`INPUT=$(cat)`), as seen in `context-monitor.sh`. Implementation should use stdin.
- **Parser note**: The `## Session Log` heading in the Expected Behavior code block (line 40) causes the session log regex to match that example instead of the real Session Log section at the bottom, reporting 0 commands in `ll-issues refine-status`. This is a known parser quirk for issues whose body contains `## Session Log` at column 0 inside a code block.
- **Implementation note**: `ll-auto`, `ll-parallel`, and `ll-sprint` complete issues via Python subprocess `git mv` (see `scripts/little_loops/issue_lifecycle.py:291` and `parallel/orchestrator.py`), **not** via Claude's Bash tool call. A PostToolUse hook on `Bash` would NOT fire for those paths. Only `manage-issue` (which uses the Bash tool for `git mv`) would be covered. Implementation should consider a Python-level callback in `issue_lifecycle.py` or a separate approach (e.g., a git post-move hook or lifecycle callback) to cover all paths.

## Session Log
- `/ll:refine-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e25ef1f-a191-43bd-9b43-c3291051d8a0.jsonl`
- `/ll:capture-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T16:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T17:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T18:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T19:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:confidence-check` - 2026-03-07T18:01:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T20:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T23:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T23:01:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T23:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T23:35:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-08T00:01:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-08T00:02:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-08T00:03:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-08T00:04:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-08T00:05:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T21:49:47Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T21:53:22Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/10327983-1fed-40b5-b8f8-5574c5ed03c4.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `issue-completion-log.sh` still doesn't exist; Python-level `append_session_log_entry()` calls still absent from `issue_lifecycle.py` and `orchestrator.py`; dual-layer implementation approach confirmed accurate
- `/ll:verify-issues` - 2026-03-07T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da7dc305-837f-4e45-9a7f-90e7eae114d2.jsonl`
- `/ll:verify-issues` - 2026-03-07T22:49:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee47df1b-807c-445b-b4e4-0c30e5296355.jsonl`
- `/ll:confidence-check` - 2026-03-07T23:59:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/62b97a68-6d3e-4460-993f-59940ca0029c.jsonl`
- `/ll:verify-issues` - 2026-03-08T00:06:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001bb4dd-80ce-42a1-916a-56a833487d5b.jsonl`
- `/ll:verify-issues` - 2026-03-08T00:07:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fec81786-b516-44bf-9948-e40b47c082de.jsonl`

---

## Status

**Open** | Created: 2026-03-07 | Priority: P3


## Blocked By
- FEAT-565
- ENH-665
## Blocks
- ENH-668
- ENH-493
- ENH-494
