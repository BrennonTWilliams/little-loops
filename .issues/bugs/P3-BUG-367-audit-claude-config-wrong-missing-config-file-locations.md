---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# BUG-367: audit_claude_config references wrong/missing config file locations

## Summary

The `/ll:audit_claude_config` command and its sub-agents reference incorrect or incomplete config file locations when compared to the official Claude Code settings documentation. Three specific file path issues cause the audit to miss important configuration files and look in wrong locations.

## Current Behavior

1. **CLAUDE.md audit** (audit_claude_config.md:96-98) only checks `~/.claude/CLAUDE.md`, `.claude/CLAUDE.md`, and `./CLAUDE.md` - missing `CLAUDE.local.md` entirely
2. **Config files auditor** (audit_claude_config.md:183-208) lists `.claude/settings.local.json` but omits `.claude/settings.json` (the shared project settings file)
3. **MCP config** (audit_claude_config.md:34) references `~/.claude/.mcp.json` for user MCP config, but per official docs user-scope MCP is stored in `~/.claude.json`, not a separate file

## Expected Behavior

1. CLAUDE.md audit should also check `CLAUDE.local.md` (local-scope memory file per settings docs)
2. Config files auditor should include `.claude/settings.json` as a primary audit target
3. MCP user location should reference `~/.claude.json` (which contains user/local scope MCP configs), not `~/.claude/.mcp.json`

## Steps to Reproduce

1. Run `/ll:audit_claude_config`
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
- `/ll:capture_issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00ffa686-5907-4ed1-8765-93f478b14da2.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
