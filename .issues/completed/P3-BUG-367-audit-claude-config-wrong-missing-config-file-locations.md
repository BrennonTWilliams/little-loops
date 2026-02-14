---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# BUG-367: audit_claude_config references wrong/missing config file locations

## Summary

The `/ll:audit-claude-config` command and its sub-agents reference incorrect or incomplete config file locations when compared to the official Claude Code settings documentation. Three specific file path issues cause the audit to miss important configuration files and look in wrong locations.

## Current Behavior

1. **CLAUDE.md audit** (audit_claude_config.md:96-98) only checks `~/.claude/CLAUDE.md`, `.claude/CLAUDE.md`, and `./CLAUDE.md` - missing `CLAUDE.local.md` entirely
2. **Config files auditor** (audit_claude_config.md:183-208) lists `.claude/settings.local.json` but omits `.claude/settings.json` (the shared project settings file)
3. **MCP config** (audit_claude_config.md:34) references `~/.claude/.mcp.json` for user MCP config, but per official docs user-scope MCP is stored in `~/.claude.json`, not a separate file

## Expected Behavior

1. CLAUDE.md audit should also check `CLAUDE.local.md` (local-scope memory file per settings docs)
2. Config files auditor should include `.claude/settings.json` as a primary audit target
3. MCP user location should reference `~/.claude.json` (which contains user/local scope MCP configs), not `~/.claude/.mcp.json`

## Steps to Reproduce

1. Run `/ll:audit-claude-config`
2. Observe that `CLAUDE.local.md` is never checked even if it exists
3. Observe that `.claude/settings.json` (project shared settings) is not audited
4. Observe that MCP user config is searched at wrong path

## Actual Behavior

The audit produces incomplete results - missing entire configuration files from its scope.

## Root Cause

- **File**: `commands/audit_claude_config.md`
- **Anchor**: in "Configuration Files to Audit" section and "Task 1: CLAUDE.md Auditor" / "Task 3: Config Files Auditor"
- **Cause**: The file locations were written before the official docs documented `CLAUDE.local.md` and the correct MCP storage location. The `.claude/settings.json` omission appears to be an oversight since `.claude/settings.local.json` is listed.

## Location

- **File**: `commands/audit_claude_config.md`
- **Lines**: 19-34 (config file list), 96-98 (CLAUDE.md auditor), 183-208 (config files auditor)
- **Anchor**: in CLAUDE.md Files section, Task 1, and Task 3

## Proposed Solution

1. Add `CLAUDE.local.md` to the CLAUDE.md Files list (line 22) and to Task 1's file list (line 98)
2. Add `.claude/settings.json` to Configuration Files list and Task 3's files to audit
3. Change `~/.claude/.mcp.json` to `~/.claude.json` with a note that it contains user-scope MCP among other configs

## Implementation Steps

1. Edit `commands/audit_claude_config.md` to fix all three file location references
2. Verify consistency between the overview list (lines 19-34) and the task prompts

## Impact

- **Priority**: P3 - Causes incomplete audit results but not a crash
- **Effort**: Small - Three targeted edits to one file
- **Risk**: Low - Only affects documentation/prompts, no code changes
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Lists config file locations |
| architecture | docs/ARCHITECTURE.md | Plugin component structure |

## Labels

`bug`, `captured`, `audit`, `config`

## Session Log
- `/ll:capture-issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00ffa686-5907-4ed1-8765-93f478b14da2.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3

---

## Verification Notes

- **Verified**: 2026-02-12
- **Verdict**: NEEDS_UPDATE
- Claim #1 (CLAUDE.local.md missing): **RESOLVED** — `audit_claude_config.md` line 26 now includes `CLAUDE.local.md` and Task 1 file list at line 108 also includes it
- Claim #2 (settings.json omitted): **PARTIALLY RESOLVED** — overview section (line 36) now lists `~/.claude/settings.json`, but Task 3 agent prompt (lines 210-214) still omits it from "Files to find and validate"
- Claim #3 (MCP path wrong): **STILL VALID** — line 40 still references `~/.claude/.mcp.json`
- Line numbers in the issue (19-34, 96-98, 183-208) are stale — file has been significantly expanded
- Consider narrowing scope to remaining claims #2 (partial) and #3, or closing if effort doesn't justify

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-02-12
- **Reason**: Low utility relative to implementation complexity

### Tradeoff Review Scores
- Utility: LOW
- Implementation Effort: LOW
- Complexity Added: LOW
- Technical Debt Risk: LOW
- Maintenance Overhead: LOW

### Rationale
Verification notes show claims #1 and #2 are already mostly resolved, leaving only the MCP path issue which is a minor documentation fix with low user impact. Not worth keeping open for the remaining marginal improvement.
