---
discovered_date: 2026-03-07
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 78
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

### New Hook Script: `hooks/scripts/issue-completion-log.sh`

```bash
#!/usr/bin/env bash
# PostToolUse hook: append session log to issues moved to completed/

TOOL_INPUT="$1"  # JSON with tool_name and tool_input fields

# Only process Bash tool calls
TOOL_NAME=$(echo "$TOOL_INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_name',''))" 2>/dev/null)
[ "$TOOL_NAME" != "Bash" ] && exit 0

# Extract the command
CMD=$(echo "$TOOL_INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)

# Check if this is a git mv to completed/
echo "$CMD" | grep -qE 'git mv .+completed/' || exit 0

# ... extract dest path, find JSONL, append session log entry
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

## Implementation Steps

1. Create `hooks/scripts/issue-completion-log.sh`
   - Parse `$CLAUDE_TOOL_INPUT` (or stdin JSON) for tool name and command
   - Detect `git mv` pattern targeting `completed/` directory
   - Resolve the destination file path
   - Locate current session JSONL via `~/.claude/projects/<encoded-path>/`
   - Append `## Session Log` entry to the destination file
2. Register hook in `hooks/hooks.json` under `PostToolUse`
3. Add tests for the hook script (unit test the bash logic)
4. Update `manage-issue` SKILL.md Phase 5 Step 1.5 to note hook covers this (optionally simplify)
5. Update `docs/ARCHITECTURE.md` to document the new hook

## Impact

- **Priority**: P3 - Session log coverage gap affects all automation paths (`ll-auto`, `ll-parallel`, `ll-sprint`); only `manage-issue` currently logs, leaving the majority of completions untracked
- **Effort**: Small - New bash script (~50 lines) + one JSON hook registration entry; no Python changes required
- **Risk**: Low - Hook exits cleanly on any failure (non-blocking); worst case is a missing log entry, not data loss or broken functionality
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `hooks/hooks.json` — add `PostToolUse` hook entry with `Bash` matcher

### New Files
- `hooks/scripts/issue-completion-log.sh` — hook script to detect `git mv ... completed/` and append session log

### Dependent Files (Callers/Importers)
- `skills/manage-issue/SKILL.md` — Phase 5 Step 1.5 session log step can be noted as now covered by hook

### Similar Patterns
- `hooks/scripts/` — existing hook scripts for reference on input parsing conventions

### Tests
- New unit tests for `issue-completion-log.sh` bash logic (pattern matching, JSONL lookup, append behavior)

### Documentation
- `docs/ARCHITECTURE.md` — document new `PostToolUse` hook in hook system section

### Configuration
- `hooks/hooks.json` — hook registration (matcher: `Bash`, type: `command`)

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

Re-verified 2026-03-07. Verdict: **VALID**.

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
- `/ll:verify-issues` - 2026-03-07T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/da7dc305-837f-4e45-9a7f-90e7eae114d2.jsonl`

---

## Status

**Open** | Created: 2026-03-07 | Priority: P3
