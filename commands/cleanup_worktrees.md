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
WORKTREE_BASE="{{config.parallel.worktree_base}}"

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
