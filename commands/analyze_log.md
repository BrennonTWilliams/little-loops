---
description: Analyze ll-parallel/ll-auto log files to identify tool bugs and create/reopen issues
arguments:
  - name: log_file
    description: Path to the .log file to analyze
    required: true
---

# Analyze Log

You are tasked with analyzing log files from `ll-parallel` or `ll-auto` runs to identify bugs and issues in the ll tool itself, then creating or reopening issues in this plugin's `.issues/` directory.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
- **Completed directory**: `{{config.issues.completed_dir}}`

## Process

### 0. Initialize Progress Tracking

Create a todo list to track analysis progress:

```
Use TodoWrite to create:
- Parsing log file metadata
- Detecting log type and completion state
- Scanning for error patterns
- Grouping and categorizing findings
- Deduplicating against existing issues
- Presenting summary for approval
- Creating/reopening issues (pending approval)
```

Update todos as each phase completes to give the user visibility into progress.

### 1. Parse Log Metadata

Read the log file and extract metadata:

```bash
LOG_FILE="${log_file}"

# Verify file exists
test -f "$LOG_FILE" || echo "ERROR: Log file not found: $LOG_FILE"

# Get basic stats
wc -l "$LOG_FILE"                    # Total lines
head -1 "$LOG_FILE"                  # First line (may have timestamp)
tail -20 "$LOG_FILE"                 # Last lines (check for completion)
```

#### Detect Log Type

Search for identifying patterns:

| Pattern | Log Type |
|---------|----------|
| `Worker pool started with \d+ workers` | ll-parallel |
| `Starting automated issue management` | ll-auto |
| `Merge coordinator started` | ll-parallel |
| `Phase 1: Verifying issue` | ll-auto |

#### Detect Completion State

**ll-parallel completed**:
```
============================================================
PARALLEL ISSUE PROCESSING COMPLETE
============================================================

Total time: X.X minutes
Completed: N
Failed: N
```

**ll-auto completed**: No explicit marker - infer from final "State saved" and no mid-operation cutoff.

**In-progress indicators**:
- No completion marker
- Log ends mid-operation (e.g., "Running: claude...")
- Truncated output or control characters at end

#### Extract External Repo Path

The external repository being processed appears in worktree paths:

```bash
# Extract from worktree creation lines
grep -oE "Created worktree at ([^/]+(/[^/]+)*)/\.worktrees" "$LOG_FILE" | head -1

# Or from state file paths
grep -oE "State saved to ([^/]+(/[^/]+)*)/\.(auto|parallel)-manage-state" "$LOG_FILE" | head -1
```

Store extracted values:
- `LOG_TYPE`: "ll-parallel" or "ll-auto"
- `LOG_STATE`: "completed" or "in-progress"
- `EXTERNAL_REPO`: Path to the processed repository
- `TIME_RANGE`: First timestamp → Last timestamp
- `FINAL_STATS`: (if completed) Total time, Completed count, Failed count

### 2. Scan for Error Patterns

Search the log for patterns indicating ll tool bugs. These are issues with the tool itself, NOT issues in the external codebase being processed.

#### Pattern Definitions

| Category | Pattern (grep -E) | Type | Default Priority |
|----------|-------------------|------|------------------|
| `leaked_files` | `leaked \d+ file\(s\) to main repo` | BUG | P1 |
| `stash_pop_failed` | `Failed to pop stash` | BUG | P2 |
| `stash_failed` | `Failed to stash local changes` | BUG | P2 |
| `index_lock` | `Unable to create.*index\.lock.*File exists` | BUG | P2 |
| `critical_not_ready` | `NOT_READY.*\*\*Critical` | BUG | P1 |
| `auto_corrected` | `was auto-corrected during validation` | ENH | P3 |
| `pull_conflict` | `Pull failed due to local changes` | BUG | P2 |
| `only_excluded_files` | `failed:.*Only excluded files modified` | BUG | P2 |
| `git_mv_failed` | `git mv failed: fatal: destination exists` | BUG | P2 |
| `conflicted_stash_pop` | `Cleaned up conflicted stash pop` | BUG | P2 |

For each pattern, collect:
- **Occurrences**: Count of matches
- **Affected issues**: Issue IDs mentioned nearby (e.g., BUG-553, ENH-312)
- **Sample context**: First occurrence with 2-3 surrounding lines
- **Timestamps**: When errors occurred

```bash
# Example: Count leaked files occurrences
grep -c "leaked .* file(s) to main repo" "$LOG_FILE"

# Example: Get affected issue IDs for leaked files
grep -oE "\[[\d:]+\]\s+(\w+-\d+)\s+leaked" "$LOG_FILE" | grep -oE "\w+-\d+"

# Example: Get sample context
grep -B2 -A2 "leaked .* file(s) to main repo" "$LOG_FILE" | head -20
```

### 3. Group and Categorize Findings

For each pattern category with occurrences > 0:

1. **Aggregate by category** - Multiple occurrences of same pattern = 1 finding
2. **Collect all affected issue IDs** - Shows scope of the problem
3. **Adjust priority based on frequency**:
   - 1-2 occurrences: Keep default priority
   - 3-5 occurrences: Bump priority by 1 (P2 → P1)
   - 6+ occurrences: Bump priority by 2 (P2 → P0)

4. **Generate proposed issue title** based on category:

| Category | Proposed Title |
|----------|----------------|
| `leaked_files` | Worktree isolation: files leak to main repo during parallel processing |
| `stash_pop_failed` | Merge coordination: stash pop failure loses local changes |
| `stash_failed` | Git state management: stash operation fails before merge |
| `index_lock` | Git concurrency: index.lock collision in parallel workers |
| `critical_not_ready` | Issue validation: critical inconsistencies not caught during scan |
| `auto_corrected` | Issue quality: high auto-correction rate indicates scan accuracy issues |
| `pull_conflict` | State management: pull fails when local changes exist |
| `only_excluded_files` | Implementation validation: false positive on excluded-only changes |
| `git_mv_failed` | Issue lifecycle: git mv fails when destination already exists |
| `conflicted_stash_pop` | Merge coordination: stash conflicts not cleanly resolved |

### 4. Deduplicate Against Existing Issues

For each finding, check if a matching issue already exists:

#### Search Active Issues

```bash
# Search in .issues/ subdirectories (excluding completed/)
find {{config.issues.base_dir}} -name "*.md" -not -path "*/completed/*" | xargs grep -l "<keywords>"
```

Keywords to search for each category:
- `leaked_files`: "worktree", "leak", "isolation"
- `stash_pop_failed`: "stash", "pop", "merge"
- `index_lock`: "index.lock", "concurrent", "lock"
- etc.

#### Search Completed Issues (for reopening)

```bash
# Search completed/ for similar issues
find {{config.issues.base_dir}}/completed -name "*.md" | xargs grep -l "<keywords>"
```

#### Determine Action

For each finding:

| Condition | Action | Reason |
|-----------|--------|--------|
| High similarity match in active issues | **SKIP** | Already tracked |
| High similarity match in completed issues | **REOPEN** | Issue recurred |
| No significant match | **NEW** | Create new issue |

Similarity indicators:
- Title contains same keywords
- Description mentions same error pattern
- Same ll module implicated

### 5. Present Summary for Approval

Display analysis results before taking action:

```markdown
## Log Analysis Summary

**Log File**: `[LOG_FILE]`
**Log Type**: [ll-parallel | ll-auto]
**Log State**: [Completed ✓ | In-Progress ⚠️]
**External Repo**: `[EXTERNAL_REPO]`
**Time Range**: [FIRST_TIMESTAMP] → [LAST_TIMESTAMP]
```

If log is completed, show final stats:
```markdown
### Run Statistics
| Metric | Value |
|--------|-------|
| Total Time | X.X minutes |
| Completed | N |
| Failed | N |
| Success Rate | X.X% |
```

If log is in-progress:
```markdown
### ⚠️ Incomplete Log Warning
This log appears to be from an in-progress or interrupted run.
Statistics below are based on partial data.
```

Show findings:
```markdown
### Detected ll Tool Issues

| Category | Occurrences | Affected | Priority | Action |
|----------|-------------|----------|----------|--------|
| Leaked Files | 5 | BUG-553, BUG-326... | P1 | NEW |
| Stash Pop Failed | 3 | - | P2 | SKIP (BUG-042) |
| Index Lock | 2 | - | P2 | REOPEN (BUG-038) |
| Auto-corrected | 8 | ENH-375, ENH-370... | P2 | NEW |

### Actions to Take

**New Issues (2)**:
1. P1-BUG-XXX: Worktree isolation: files leak to main repo during parallel processing
2. P2-ENH-XXX: Issue quality: high auto-correction rate indicates scan accuracy issues

**Reopen Issues (1)**:
1. P2-BUG-038-index-lock-collision.md (from completed/)

**Skip (Already Tracked) (1)**:
1. Stash Pop Failed → matches BUG-042
```

#### Request Approval

Use AskUserQuestion:
- Question: "Proceed with creating/reopening these issues?"
- Options:
  - "Yes, create all" - Create new issues and reopen completed ones
  - "Create new only" - Only create new issues, skip reopens
  - "Skip" - Exit without changes

### 6. Execute Actions

After user approval:

#### Create New Issues

For each NEW finding, create an issue file:

```markdown
---
discovered_commit: [ll repo HEAD]
discovered_date: [SCAN_TIMESTAMP]
discovered_source: [LOG_FILE path]
discovered_external_repo: [EXTERNAL_REPO]
---

# [PREFIX]-[NUMBER]: [Title]

## Summary

[Description based on pattern category]

## Evidence from Log

**Log File**: `[LOG_FILE]`
**Log Type**: [ll-parallel | ll-auto]
**External Repo**: `[EXTERNAL_REPO]`
**Occurrences**: [COUNT]
**Affected External Issues**: [ISSUE_IDS]

### Sample Log Output

```
[First occurrence with context - up to 500 chars]
```

## Current Behavior

[What happens based on the error pattern]

## Expected Behavior

[What should happen instead]

## Affected Components

- **Tool**: [ll-auto | ll-parallel]
- **Likely Module**: [Inferred from pattern, e.g., "parallel/merge_coordinator.py"]

## Proposed Investigation

1. [Step based on pattern type]
2. [Additional investigation step]

## Impact

- **Severity**: [Based on adjusted priority]
- **Frequency**: [COUNT] occurrences in single run
- **Data Risk**: [High for leaked files/stash issues, Medium for others]

---

## Status
**Open** | Created: [DATE] | Priority: [P#]
```

Save to appropriate directory:
- BUG → `{{config.issues.base_dir}}/bugs/P[X]-BUG-[NUM]-[slug].md`
- ENH → `{{config.issues.base_dir}}/enhancements/P[X]-ENH-[NUM]-[slug].md`

Use globally unique sequential numbers (scan ALL .issues/ directories including completed/).

#### Reopen Completed Issues

For each REOPEN finding:

1. Read the completed issue file
2. Add a "Reopened" section:

```markdown
---

## Reopened

- **Date**: [TODAY]
- **By**: /ll:analyze_log
- **Reason**: Issue recurred in log analysis

### New Evidence

**Log File**: `[LOG_FILE]`
**Occurrences**: [COUNT]

```
[Sample context from new log]
```
```

3. Move file from `completed/` back to active category directory:

```bash
git mv "{{config.issues.base_dir}}/completed/[filename]" "{{config.issues.base_dir}}/[category]/[filename]"
```

### 7. Output Report

```markdown
# Log Analysis Report

## Log Metadata
- **File**: [LOG_FILE]
- **Type**: [LOG_TYPE]
- **State**: [LOG_STATE]
- **External Repo**: [EXTERNAL_REPO]
- **Lines Analyzed**: [LINE_COUNT]

## Actions Taken

### Issues Created
| File | Type | Priority | Title |
|------|------|----------|-------|
| P1-BUG-057-worktree-leak.md | BUG | P1 | Worktree isolation: files leak to main repo |
| P2-ENH-058-auto-correction-rate.md | ENH | P2 | Issue quality: high auto-correction rate |

### Issues Reopened
| File | From | New Occurrences |
|------|------|-----------------|
| P2-BUG-038-index-lock.md | completed/ | 2 |

### Skipped (Already Tracked)
| Category | Existing Issue |
|----------|----------------|
| Stash Pop Failed | BUG-042 |

## Patterns Summary
| Pattern | Count | Action |
|---------|-------|--------|
| leaked_files | 5 | Created BUG-057 |
| index_lock | 2 | Reopened BUG-038 |
| stash_pop_failed | 3 | Skipped (BUG-042) |
| auto_corrected | 8 | Created ENH-058 |

## Next Steps
1. Review created issues for accuracy
2. Run `/ll:prioritize_issues` if priority adjustments needed
3. Use `/ll:manage_issue bug fix` to start addressing issues
4. Consider running with `--dry-run` next time to catch issues earlier
```

---

## Examples

```bash
# Analyze a completed ll-parallel log
/ll:analyze_log ll-parallel-blender-agents-debug.log

# Analyze an in-progress log (will show warning)
/ll:analyze_log ~/logs/ll-parallel-current.log

# Analyze an ll-auto log
/ll:analyze_log ll-auto-lmc-voice-debug.log
```

---

## Pattern Reference

### High Priority (P1) Patterns

**Leaked Files** - Files created in worktree appear in main repo
- Indicates worktree isolation failure
- Risk: Uncommitted changes in wrong location, merge conflicts
- Module: `parallel/worker.py`, `parallel/merge_coordinator.py`

**Critical NOT_READY** - Validation finds critical issues
- Indicates scan created inaccurate issues
- Risk: Wasted processing time, incorrect fixes
- Module: `issue_parser.py`, scan commands

### Medium Priority (P2) Patterns

**Stash Failures** - Git stash operations fail
- Indicates merge coordination issues
- Risk: Lost local changes, failed merges
- Module: `parallel/merge_coordinator.py`

**Index Lock** - Concurrent git operations collide
- Indicates parallel git access issues
- Risk: Failed operations, corrupted state
- Module: `parallel/worker.py`, `parallel/orchestrator.py`

**Pull Conflicts** - Pull fails with local changes
- Indicates state management issues
- Risk: Stale branches, merge conflicts
- Module: `parallel/merge_coordinator.py`

### Lower Priority (P3) Patterns

**Auto-corrected** - Issues needed correction during validation
- Indicates scan quality issues (not blocking)
- Risk: Extra processing time, potential inaccuracies
- Module: Scan commands, issue creation

---

## Integration

After analyzing logs:
1. Review created issues for accuracy
2. Run `/ll:manage_issue bug fix` to address critical bugs
3. Consider patterns when planning ll tool improvements
4. Save logs with descriptive names for future reference
