# FEAT-081: Add /ll:cleanup_worktrees command - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-081-cleanup-worktrees-command.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- Worktrees are created in `.worktrees/worker-{issue-id}-{timestamp}` directories (`scripts/little_loops/parallel/worker_pool.py:219-223`)
- Associated branches use pattern `parallel/{issue-id}-{timestamp}` (`worker_pool.py:218`)
- Existing cleanup logic in `orchestrator._cleanup_orphaned_worktrees()` (`orchestrator.py:178-227`)
- CLI already has `ll-parallel --cleanup` flag (`cli.py:238-246`) that calls `worker_pool.cleanup_all_worktrees()`
- Session cleanup hook exists at `hooks/scripts/session-cleanup.sh:14-19`
- Worktree base directory is configurable via `config.parallel.worktree_base` (default: `.worktrees`)

### Existing Cleanup Mechanisms
1. **Automatic startup cleanup**: `orchestrator._cleanup_orphaned_worktrees()` removes orphans on ll-parallel start
2. **After-merge cleanup**: `merge_coordinator._cleanup_worktree()` removes worktrees after successful merge
3. **Normal shutdown cleanup**: `worker_pool.cleanup_all_worktrees()` runs on graceful exit
4. **Session hook cleanup**: `session-cleanup.sh` cleans worktrees when Claude Code session ends
5. **Manual CLI cleanup**: `ll-parallel --cleanup` flag (requires Python environment)

### Gap Identified
No user-facing command exists within Claude Code to manually clean worktrees without invoking `ll-parallel --cleanup` from the CLI. Users need a simple `/ll:cleanup_worktrees` command.

## Desired End State

A `/ll:cleanup_worktrees` command that:
1. Lists all git worktrees in the repository
2. Identifies which are ll-parallel worktrees (pattern: `worker-*` in `.worktrees/`)
3. Shows user what will be cleaned before taking action
4. Safely removes orphaned worktrees and their associated branches
5. Reports what was cleaned

### How to Verify
- Run `/ll:cleanup_worktrees` when orphaned worktrees exist - they should be removed
- Run `/ll:cleanup_worktrees --dry-run` - should show what would be cleaned without removing
- Run when no worktrees exist - should report "No worktrees to clean"

## What We're NOT Doing

- Not creating Python CLI changes - the command will use bash/git commands directly
- Not adding `--all` flag to clean non-ll-parallel worktrees (risk of cleaning user's worktrees)
- Not adding `--force` flag - the command already uses `--force` with git worktree remove
- Not modifying existing Python cleanup logic - just wrapping existing patterns in a command

## Solution Approach

Create `commands/cleanup_worktrees.md` following the established command pattern (YAML frontmatter + markdown instructions). The command will use bash and git commands directly, similar to `session-cleanup.sh`.

## Implementation Phases

### Phase 1: Create cleanup_worktrees.md Command

#### Overview
Create the command file with support for `--dry-run` mode.

#### Changes Required

**File**: `commands/cleanup_worktrees.md`
**Changes**: Create new file with command definition

```markdown
---
description: Clean orphaned git worktrees from interrupted ll-parallel runs
arguments:
  - name: mode
    description: Execution mode (run|dry-run)
    required: false
---

# Cleanup Worktrees

You are tasked with cleaning up orphaned git worktrees that may remain after interrupted or failed ll-parallel runs.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Worktree base**: `{{config.parallel.worktree_base}}` (default: `.worktrees`)

## Process

### 1. Parse Mode

```bash
MODE="${mode:-run}"
WORKTREE_BASE=".worktrees"

echo "========================================"
echo "WORKTREE CLEANUP"
echo "========================================"
echo ""
echo "Mode: $MODE"
echo "Worktree base: $WORKTREE_BASE"
echo ""
```

### 2. Check for Worktrees

First, check if the worktree base directory exists:

```bash
if [ ! -d "$WORKTREE_BASE" ]; then
    echo "No worktree directory found at $WORKTREE_BASE"
    echo "Nothing to clean."
    exit 0
fi
```

### 3. List ll-parallel Worktrees

Find all worktrees matching the ll-parallel pattern:

```bash
# Get list of worker worktrees
WORKTREES=$(find "$WORKTREE_BASE" -maxdepth 1 -type d -name "worker-*" 2>/dev/null || true)

if [ -z "$WORKTREES" ]; then
    echo "No ll-parallel worktrees found in $WORKTREE_BASE"
    echo "Nothing to clean."
    exit 0
fi

# Count worktrees
COUNT=$(echo "$WORKTREES" | wc -l | tr -d ' ')
echo "Found $COUNT ll-parallel worktree(s):"
echo ""
echo "$WORKTREES" | while read -r w; do
    if [ -n "$w" ]; then
        echo "  - $(basename "$w")"
    fi
done
echo ""
```

### 4. Execute Cleanup (or Dry Run)

#### Mode: dry-run

If dry-run mode, just show what would be cleaned:

```bash
if [ "$MODE" = "dry-run" ]; then
    echo "DRY RUN - No changes will be made"
    echo ""
    echo "Would remove the following worktrees:"
    echo "$WORKTREES" | while read -r w; do
        if [ -n "$w" ]; then
            BRANCH_NAME="parallel/$(basename "$w" | sed 's/^worker-//')"
            echo "  - Worktree: $w"
            echo "    Branch: $BRANCH_NAME"
        fi
    done
    echo ""
    echo "Run '/ll:cleanup_worktrees' (without dry-run) to execute cleanup."
    exit 0
fi
```

#### Mode: run

Execute the actual cleanup:

```bash
if [ "$MODE" = "run" ]; then
    echo "Cleaning up worktrees..."
    echo ""

    CLEANED=0
    FAILED=0

    echo "$WORKTREES" | while read -r w; do
        if [ -n "$w" ] && [ -d "$w" ]; then
            WORKTREE_NAME=$(basename "$w")
            BRANCH_NAME="parallel/$(echo "$WORKTREE_NAME" | sed 's/^worker-//')"

            echo "Removing: $WORKTREE_NAME"

            # Try git worktree remove first
            if git worktree remove --force "$w" 2>/dev/null; then
                echo "  [OK] Worktree removed"
            else
                # Fallback: force delete directory
                rm -rf "$w" 2>/dev/null || true
                if [ ! -d "$w" ]; then
                    echo "  [OK] Directory removed (fallback)"
                else
                    echo "  [FAIL] Could not remove directory"
                fi
            fi

            # Try to delete the associated branch
            if git branch -D "$BRANCH_NAME" 2>/dev/null; then
                echo "  [OK] Branch deleted: $BRANCH_NAME"
            else
                echo "  [SKIP] Branch not found or already deleted"
            fi

            echo ""
        fi
    done

    # Prune git worktree references
    echo "Pruning git worktree references..."
    git worktree prune 2>/dev/null || true
    echo ""
fi
```

### 5. Summary Report

```bash
echo "========================================"
echo "CLEANUP COMPLETE"
echo "========================================"
echo ""

# Check what's left
REMAINING=$(find "$WORKTREE_BASE" -maxdepth 1 -type d -name "worker-*" 2>/dev/null | wc -l | tr -d ' ')

if [ "$REMAINING" = "0" ]; then
    echo "All ll-parallel worktrees have been cleaned."
else
    echo "Warning: $REMAINING worktree(s) could not be removed."
    echo "These may require manual cleanup."
fi
```

---

## Arguments

$ARGUMENTS

- **mode** (optional, default: `run`): Execution mode
  - `run` - Execute the cleanup (default)
  - `dry-run` - Preview what would be cleaned without making changes

---

## Examples

```bash
# Clean all orphaned worktrees
/ll:cleanup_worktrees

# Preview what would be cleaned
/ll:cleanup_worktrees dry-run
```
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `commands/cleanup_worktrees.md`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] `/ll:cleanup_worktrees dry-run` shows worktrees without removing them
- [ ] `/ll:cleanup_worktrees` removes orphaned worktrees

---

## Testing Strategy

### Manual Testing
1. Create a test worktree manually:
   ```bash
   mkdir -p .worktrees/worker-test-001-20260117-120000
   git worktree add -b parallel/test-001-20260117-120000 .worktrees/worker-test-001-20260117-120000
   ```
2. Run `/ll:cleanup_worktrees dry-run` - should list the test worktree
3. Run `/ll:cleanup_worktrees` - should remove the test worktree
4. Run `/ll:cleanup_worktrees` again - should report "No worktrees to clean"

## References

- Original issue: `.issues/features/P3-FEAT-081-cleanup-worktrees-command.md`
- Session cleanup hook pattern: `hooks/scripts/session-cleanup.sh:14-19`
- Python cleanup logic: `scripts/little_loops/parallel/orchestrator.py:178-227`
- Existing CLI flag: `scripts/little_loops/cli.py:238-246`
- Command pattern: `commands/check_code.md`
