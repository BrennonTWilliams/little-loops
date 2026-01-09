# Design: `/ll:analyze_log` Command

**Date**: 2026-01-09
**Status**: Draft - Pending Review

## Overview

New slash command to analyze `.log` files from `ll-parallel` or `ll-auto` runs, identifying bugs/issues in the ll tool itself.

## Requirements

1. **Focus**: Only ll plugin issues (not external codebase issues)
2. **Mode**: Interactive batch - present findings, approve all at once
3. **Repo Detection**: Parse external repo path from log content
4. **Log State**: Handle both in-progress (incomplete) and completed logs

## Log State Detection

The command must detect whether the log is from a completed or still-running process:

### Completed Log Indicators
```
============================================================
PARALLEL ISSUE PROCESSING COMPLETE
============================================================

Total time: X.X minutes
Completed: N
Failed: N
```

### In-Progress Log Indicators
- No "PARALLEL ISSUE PROCESSING COMPLETE" marker
- No "Total time:" summary line
- May end abruptly mid-operation

### State-Aware Behavior

| Log State | Summary Shows | Metrics Available |
|-----------|---------------|-------------------|
| **Completed** | Final counts, success rate, speedup | Yes - from final report |
| **In-Progress** | "Analysis based on incomplete log" warning, counts so far | Partial - computed from patterns |

**Detection regex**:
```python
# ll-parallel completion
PARALLEL_COMPLETION = r"PARALLEL ISSUE PROCESSING COMPLETE"
PARALLEL_STATS = r"Total time:.*\nCompleted: (\d+)\nFailed: (\d+)"

# ll-auto completion (processes issues sequentially, no final summary block)
# Detect by checking for "State saved" as last meaningful line
AUTO_STATE_SAVED = r"\[[\d:]+\]\s+State saved to"

# Log type detection
IS_PARALLEL = r"Worker pool started with \d+ workers"
IS_AUTO = r"Starting automated issue management"
```

**In-progress handling**:
- Warn user: "Log appears to be from an in-progress or interrupted run"
- Show stats computed from detected patterns only
- Skip success rate calculation (incomplete data)
- Still allow issue creation for detected problems

## Command File

**Path**: `commands/analyze_log.md`

```yaml
---
description: Analyze ll-parallel/ll-auto log files to identify tool bugs and create/reopen issues
arguments:
  - name: log_file
    description: Path to the .log file to analyze
    required: true
---
```

## Log Patterns to Detect

| Category | Pattern | Type | Priority | Description |
|----------|---------|------|----------|-------------|
| `leaked_files` | `XXX leaked N file(s) to main repo` | BUG | P1 | Worktree isolation failure |
| `stash_pop_failed` | `Failed to pop stash` | BUG | P2 | Merge coordination issue |
| `stash_failed` | `Failed to stash local changes` | BUG | P2 | Git state management |
| `index_lock` | `Unable to create...index.lock` | BUG | P2 | Git concurrency collision |
| `critical_not_ready` | `NOT_READY - **Critical` | BUG | P1 | Validation gap |
| `auto_corrected` | `was auto-corrected` | ENH | P3 | Issue quality improvement |
| `pull_conflict` | `Pull failed due to local changes` | BUG | P2 | State management |
| `only_excluded_files` | `Only excluded files modified` | BUG | P2 | Implementation validation |

## Phases

### Phase 1: Parse Log Metadata
- Extract log type (ll-auto vs ll-parallel)
- **Detect log state** (completed vs in-progress)
- Extract external repo path from worktree paths
- Get timestamp range and line count
- If completed: extract final stats (Completed: N, Failed: N, Total time)

### Phase 2: Pattern Detection
- Match each line against pattern regexes
- Count occurrences per category
- Extract affected issue IDs
- Capture sample context

### Phase 3: Group & Categorize
- Aggregate by pattern category
- Adjust priority based on frequency:
  - 1-2 occurrences: default priority
  - 3-5 occurrences: bump 1 level
  - 6+ occurrences: bump 2 levels

### Phase 4: Deduplication
- Search `.issues/` for existing matches (skip)
- Search `.issues/completed/` for reopening candidates
- Use title/content similarity matching

### Phase 5: Present Summary
```markdown
## Log Analysis Summary

**Log File**: `path/to/file.log`
**Log Type**: ll-parallel
**Log State**: Completed | In-Progress (⚠️ incomplete data)
**External Repo**: `/path/to/processed/repo`
**Time Range**: 15:12:06 → 21:36:14

### Final Stats (completed logs only)
| Metric | Value |
|--------|-------|
| Total Time | 42.5 minutes |
| Completed | 15 |
| Failed | 2 |
| Success Rate | 88.2% |

### Detected Issues

| Category | Occurrences | Affected Issues | Action | Priority |
|----------|-------------|-----------------|--------|----------|
| Leaked Files | 5 | BUG-553, BUG-326 | NEW | P1 |
| Stash Failures | 3 | - | EXISTS | - |
| Index Lock | 2 | - | REOPEN | P2 |
```

### Phase 6: Interactive Approval
Use AskUserQuestion:
- "Yes, create all" - proceed with all
- "Create new only" - skip reopens
- "Review individually" - per-finding approval
- "Cancel" - exit

### Phase 7: Execute
- Create new issues in `.issues/bugs/` or `.issues/enhancements/`
- Reopen completed issues with "Reopened" section
- Report actions taken

## Issue Template

```markdown
---
discovered_commit: [ll repo HEAD]
discovered_date: [timestamp]
discovered_source: [log_file]
discovered_external_repo: [repo path]
---

# {PREFIX}-{NUMBER}: {Title}

## Summary
{Pattern description}

## Evidence from Log
**Log File**: `{log_file}`
**Occurrences**: {count}
**Affected Issues**: {issue_ids}

### Sample Output
```
{first 500 chars of context}
```

## Current Behavior
{What happens}

## Expected Behavior
{What should happen}

## Affected Components
- **Tool**: {ll-auto|ll-parallel}
- **Module**: {inferred module}

## Impact
- **Severity**: {priority-based}
- **Frequency**: {count} in single run

## Status
**Open** | Created: {date} | Priority: {P#}
```

## Key Patterns (Regex)

```python
PATTERNS = {
    "leaked_files": r"\[[\d:]+\]\s+(\w+-\d+)\s+leaked\s+(\d+)\s+file\(s\)\s+to\s+main\s+repo",
    "stash_pop_failed": r"\[[\d:]+\]\s+Failed to pop stash",
    "stash_failed": r"\[[\d:]+\]\s+Failed to stash local changes",
    "index_lock": r"Unable to create.*index\.lock.*File exists",
    "critical_not_ready": r"ready_issue verdict: NOT_READY.*\*\*Critical",
    "auto_corrected": r"\[[\d:]+\]\s+(\w+-\d+)\s+was auto-corrected",
    "pull_conflict": r"\[[\d:]+\]\s+Pull failed due to local changes",
    "only_excluded_files": r"(\w+-\d+)\s+failed:.*Only excluded files modified",
}

# External repo extraction
REPO_PATH = r"Created worktree at (/[^/]+(?:/[^/]+)*?)/\.worktrees/"
```

## Open Questions

1. Should we also detect successful patterns to calculate success rate?
2. Should findings link to specific ll-parallel source files?
3. Should we add a `--dry-run` flag for testing?

## Related Files

- `scripts/little_loops/issue_discovery.py` - `find_existing_issue()`, `reopen_issue()`
- `scripts/little_loops/issue_parser.py` - `get_next_issue_number()`, `slugify()`
- `commands/scan_codebase.md` - Pattern for phase-based commands
- `commands/verify_issues.md` - Pattern for approval flows
