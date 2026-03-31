---
description: Find and fix issue filenames with missing or duplicate IDs across types (e.g., BUG-007 and FEAT-007)
allowed-tools:
  - Read
  - Glob
  - Edit
  - Bash(git:*, ll-issues:*)
arguments:
  - name: flags
    description: "Optional flags: --auto (non-interactive), --check (check-only for FSM evaluators)"
    required: false
---

# Normalize Issues

You are tasked with finding issue files that lack valid issue IDs OR have cross-type duplicate IDs, and renaming them to follow the standard naming convention with globally unique IDs.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
- **Valid priorities**: `{{config.issues.priorities}}`

## Problem This Solves

Issue files must follow the naming pattern `P[0-5]-[PREFIX]-[NNN]-[slug].md` where:
- `P[0-5]` is the priority prefix
- `[PREFIX]` is the category prefix (BUG, FEAT, ENH)
- `[NNN]` is a 3+ digit **globally unique** sequential ID (e.g., 001, 042, 1234)
- `[slug]` is a descriptive slug

**Files without valid IDs** (like `P0-split-base-builder-god-class.md`) cannot be:
- Referenced by ID in automation scripts (`ll-auto`, `ll-parallel`)
- Tracked by the duplicate ID prevention hook
- Properly associated with their category

**Cross-type duplicate IDs** (like BUG-007, FEAT-007, ENH-007 all existing) violate the global uniqueness constraint. Issue IDs must be unique across ALL types—if BUG-005 exists, no FEAT-005 or ENH-005 should exist.

**Invalid directory structure** can occur when:
- Issues are manually moved to `bugs/completed/` instead of `.issues/completed/`
- Sub-folders are created in `completed/` (e.g., `completed/bugs/`)
- This breaks automation tools that expect a flat completed/ sibling directory

## Process

### -1. Parse Flags

```bash
FLAGS="${flags:-}"
AUTO_MODE=false
CHECK_MODE=false

# Auto-enable auto mode in automation contexts
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; AUTO_MODE=true; fi
```

### -0.5. Check Mode Behavior (--check)

**When `CHECK_MODE` is true**: Scan for directory structure violations (step 0), invalid filenames (step 1), duplicate IDs (step 1b), and type misclassifications (step 1c) without applying fixes. For each violation, print one line:
- `[dir] structure: [violation description]` for directory violations
- `[filename] normalize: missing valid ID` for missing IDs
- `[ID] normalize: duplicate across [types]` for duplicate IDs
- `[ID] normalize: type mismatch ([current-type] → [inferred-type])` for type misclassifications

After scanning, if any violations found: print `N normalization issues found`, then `exit 1`. If clean: print `All issues normalized`, then `exit 0`. This integrates with FSM `evaluate: type: exit_code` routing (0=success, 1=failure, 2+=error).

### 0. Validate Directory Structure

Before normalizing filenames, verify the `.issues/` directory follows the correct structure.

#### 0a. Check Type Folders for Invalid completed/ Sub-directories

Type-specific folders should NEVER have their own `completed/` sub-directory. All completed issues go to the sibling `.issues/completed/` folder.

```bash
# Check for invalid nested completed/ directories
for category_dir in bugs features enhancements; do
    nested_completed="{{config.issues.base_dir}}/$category_dir/completed"
    if [ -d "$nested_completed" ]; then
        echo "VIOLATION: $nested_completed exists (should not)"
        # List files that need to be moved
        ls -la "$nested_completed"/*.md 2>/dev/null
    fi
done
```

**Auto-fix**: Move any files found to `.issues/completed/` and remove the invalid directory.

#### 0b. Check completed/ is Flat (No Sub-folders)

The completed directory should contain only `.md` files, no sub-directories.

```bash
# Check for sub-directories in completed/
completed_dir="{{config.issues.base_dir}}/{{config.issues.completed_dir}}"
if [ -d "$completed_dir" ]; then
    subdirs=$(find "$completed_dir" -mindepth 1 -maxdepth 1 -type d)
    if [ -n "$subdirs" ]; then
        echo "VIOLATION: Sub-directories found in completed/:"
        echo "$subdirs"
    fi
fi
```

**Auto-fix**: Move any `.md` files from sub-directories to completed/ root and remove empty sub-directories.

#### 0c. Auto-Fix Directory Structure Violations

For each violation found:

**Nested completed/ in type folder:**
```bash
# Move files from .issues/bugs/completed/ to .issues/completed/
for file in {{config.issues.base_dir}}/bugs/completed/*.md; do
    git mv "$file" "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/"
done
# Remove empty invalid directory
rmdir {{config.issues.base_dir}}/bugs/completed
```

**Sub-folders in completed/:**
```bash
# Move files from sub-folders to completed/ root
for subdir in {{config.issues.base_dir}}/{{config.issues.completed_dir}}/*/; do
    for file in "$subdir"*.md; do
        git mv "$file" "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/"
    done
    rmdir "$subdir"
done
```

### 1. Scan for Invalid Filenames

```bash
# Find all issue files
for dir in {{config.issues.base_dir}}/*/; do
    if [ -d "$dir" ] && [[ "$dir" != *"/completed/"* ]] && [[ "$dir" != *"/deferred/"* ]]; then
        echo "Checking $dir..."
        ls "$dir"*.md 2>/dev/null | while read file; do
            basename=$(basename "$file")
            # Check if filename contains valid ID pattern: PREFIX-NNN
            if ! echo "$basename" | grep -qE '(BUG|FEAT|ENH)-[0-9]{3,}'; then
                echo "  INVALID: $basename"
            fi
        done
    fi
done
```

### 1b. Detect Cross-Type Duplicate IDs

Issue IDs must be **globally unique** across all types (BUG, FEAT, ENH) and all directories (including `completed/`). Scan for ID numbers used by multiple files:

```bash
# Build a map of ID numbers to files (include completed/ to catch reused IDs)
mkdir -p .loops/tmp
find {{config.issues.base_dir}} -name "*.md" -type f | while read file; do
    basename=$(basename "$file")
    # Extract the numeric ID (e.g., 007 from BUG-007 or FEAT-007)
    id_num=$(echo "$basename" | grep -oE '(BUG|FEAT|ENH)-[0-9]{3,}' | grep -oE '[0-9]{3,}')
    if [ -n "$id_num" ]; then
        echo "$id_num:$file"
    fi
done | sort -t: -k1,1n > .loops/tmp/issue_id_map.txt

# Find duplicate ID numbers (same number across any files/directories)
cut -d: -f1 .loops/tmp/issue_id_map.txt | uniq -d | while read dup_id; do
    echo "DUPLICATE ID $dup_id:"
    grep "^$dup_id:" .loops/tmp/issue_id_map.txt | cut -d: -f2
done
```

**Duplicate IDs** — whether cross-type (BUG-007 vs FEAT-007) or active-vs-completed (active ENH-310 vs completed ENH-310) — violate global uniqueness and must be renumbered. The completed/older file keeps its ID; active duplicates get reassigned.

### 1c. Detect Type Misclassifications

For each active issue file (skip `completed/` and `deferred/`), read its content and check whether the type prefix in the filename matches the actual nature of the issue.

**Pattern**: Follows the content-reading approach from Step 7b — use the `Read` tool on each issue file, then apply heuristics inline.

**Heuristics** — extract signals from the issue's Summary, Motivation/Current Behavior, and Root Cause sections:

| Signal keywords | Suggests type |
|-----------------|---------------|
| "broken", "regression", "error", "crash", "fails", "wrong behavior", "should not", "defect", "incorrect", "unexpected" | BUG |
| "new capability", "users can't currently", "add support for", "implement", "missing feature", "not yet possible" | FEAT |
| "improve", "optimize", "enhance", "refactor", "better UX", "reduce", "increase performance", "simplify" | ENH |

**For each issue file:**

1. Use the `Read` tool to read the file content
2. Extract the current type prefix from the filename (BUG, FEAT, or ENH)
3. Also read the `type:` field from YAML frontmatter — if the frontmatter type disagrees with the filename prefix, that is a secondary signal of misclassification
4. Count signal keywords in Summary, Motivation/Current Behavior, and Root Cause sections for each candidate type (BUG, FEAT, ENH)
5. Compute a confidence score: `(signals_for_top_type) / (total_signals + 1)` (add 1 to avoid division by zero)
6. If the top-inferred type differs from the filename prefix AND confidence ≥ **0.7**: flag as a type mismatch

**Confidence threshold note**: The 0.7 default is conservative to avoid false positives on issues with ambiguous signals. If signals are mixed or weak, do not flag.

**Build the mismatch list:**
```
TYPE_MISMATCHES=[]
for each issue file:
    current_type = extract prefix from filename (BUG|FEAT|ENH)
    inferred_type = top-scoring type from heuristics
    confidence = score for inferred_type
    frontmatter_type = read from YAML 'type:' field

    if inferred_type != current_type AND confidence >= 0.7:
        add to TYPE_MISMATCHES:
            file: path
            current_type: current_type
            inferred_type: inferred_type
            confidence: confidence
            # also note: target_dir changes (e.g., enhancements/ → bugs/)
```

**In `--check` mode**: For each mismatch, print `[ID] normalize: type mismatch ([current-type] → [inferred-type])` and count toward violation total. Do not apply fixes.

### 2. Determine Category Mapping

Map directories to category prefixes based on configuration:

| Directory | Prefix | Pattern |
|-----------|--------|---------|
| `bugs/` | BUG | `P[X]-BUG-[NNN]-[slug].md` |
| `features/` | FEAT | `P[X]-FEAT-[NNN]-[slug].md` |
| `enhancements/` | ENH | `P[X]-ENH-[NNN]-[slug].md` |

### 3. Find Next Available ID (Global)

Get the next globally unique issue number:

```bash
ll-issues next-id
```

**Important**: Issue IDs are globally unique across all types. If BUG-005, FEAT-007, and ENH-003 exist, the next ID for ANY type should be 008.

### 4. Generate New Filenames

For each file needing normalization (missing ID OR duplicate ID):

1. **Extract priority** - If filename starts with `P[0-5]-`, preserve it. Otherwise, default to `P3-` (Medium).

2. **Determine prefix** from directory:
   - `bugs/` → `BUG`
   - `features/` → `FEAT`
   - `enhancements/` → `ENH`

3. **Assign next ID** - Use the next globally unique sequential number (not per-category).
   - For **missing IDs**: Assign the next available global ID
   - For **duplicate IDs**: Keep ONE file with the original ID (oldest by git history or alphabetically first), reassign others to new global IDs

4. **Generate slug** from existing filename:
   - Remove any existing `P[0-5]-` prefix
   - Remove any existing `PREFIX-NNN-` pattern
   - Convert to lowercase
   - Keep alphanumeric and hyphens

### 5. Request User Approval

Before making any changes, present the rename plan:

```markdown
## Normalization Plan

### Issues Missing IDs

| Current Filename | New Filename | Change |
|------------------|--------------|--------|
| `P0-split-base-builder-god-class.md` | `P0-ENH-004-split-base-builder-god-class.md` | Added ENH-004 |
| `fix-login-bug.md` | `P3-BUG-012-fix-login-bug.md` | Added P3-BUG-012 |

### Cross-Type Duplicate IDs

| ID Number | Conflicting Files | Resolution |
|-----------|-------------------|------------|
| 007 | `P2-BUG-007-...md`, `P2-FEAT-007-...md`, `P2-ENH-007-...md` | Keep BUG-007, reassign FEAT→015, ENH→016 |
| 006 | `P2-BUG-006-...md`, `P2-FEAT-006-...md` | Keep BUG-006, reassign FEAT→017 |

### Duplicate ID Renames

| Current Filename | New Filename | Change |
|------------------|--------------|--------|
| `P2-FEAT-007-user-message.md` | `P2-FEAT-015-user-message.md` | Reassigned 007→015 |
| `P2-ENH-007-high-auto.md` | `P2-ENH-016-high-auto.md` | Reassigned 007→016 |

### Type Mismatch Fixes

| Current Filename | New Filename | Change |
|-----------------|-------------|--------|
| `P3-ENH-NNN-foo.md` (enhancements/) | `P3-BUG-NNN-foo.md` (bugs/) | ENH → BUG (0.82 confidence) |

### Summary
- Files missing IDs: N
- Cross-type duplicate IDs found: M
- Type misclassifications detected: T
- Total files to rename/move: X
- New IDs to assign: BUG: [list], FEAT: [list], ENH: [list]

Proceed with renaming? (y/n)
```

**IMPORTANT**: Wait for user confirmation before proceeding. In `--auto` mode, apply all reclassifications without prompting.

### 6. Rename Files

Use `git mv` to preserve history:

```bash
# Rename within same directory (missing ID and duplicate ID fixes)
git mv "{{config.issues.base_dir}}/[dir]/[old-name].md" \
       "{{config.issues.base_dir}}/[dir]/[new-name].md"

# Cross-directory move for type reclassifications
# (e.g., enhancements/P3-ENH-NNN-foo.md → bugs/P3-BUG-NNN-foo.md)
git mv "{{config.issues.base_dir}}/[source-dir]/[old-name].md" \
       "{{config.issues.base_dir}}/[target-dir]/[new-name].md"
```

**Type reclassification moves**: For each entry in `TYPE_MISMATCHES`, rename the file with the new type prefix AND move it to the corresponding directory:
- BUG → `bugs/`
- FEAT → `features/`
- ENH → `enhancements/`

### 7. Update Internal References (Optional)

Check if any other files reference the old filename and offer to update:

```bash
# Find references to old filename
grep -r "[old-filename]" {{config.issues.base_dir}}/ thoughts/shared/plans/
```

### 7b. Add Missing Document References (if documents.enabled)

**Skip this section if**:
- `documents.enabled` is not `true` in `.ll/ll-config.json`
- OR no documents are configured

**Process:**

For each issue file:

1. **Check if "Related Key Documentation" section exists:**
   ```bash
   grep -q "## Related Key Documentation" "$issue_file"
   ```

2. **If section is missing OR contains only placeholder text:**

   Placeholder text patterns:
   - `_No documents linked`
   - `_No relevant documents identified`

3. **Link relevant documents:**
   - Load documents from `{{config.documents.categories}}`
   - Read each document and extract key concepts
   - Match against issue content
   - Select top 3 matches

4. **Add or update section:**

   If section is missing, append to file before `## Labels` or `---` footer:
   ```bash
   # Find insertion point (before ## Labels or final ---)
   # Insert the Related Key Documentation section
   ```

   If section exists with placeholder, replace the placeholder line:
   ```bash
   # Replace "_No documents linked..." with the table
   ```

5. **Track in report:**
   Add to Step 8 output:
   ```markdown
   ## Document References Added

   | Issue | Documents Linked |
   |-------|------------------|
   | BUG-071 | docs/ARCHITECTURE.md, docs/API.md |
   | ENH-045 | .ll/ll-goals.md |
   ```

### 8. Output Report

```markdown
# Issue Normalization Report

## Summary
- **Files scanned**: X
- **Files missing IDs**: Y
- **Cross-type duplicate IDs found**: Z
- **Directory structure violations**: N
- **Type misclassifications detected/fixed**: T
- **Total files renamed/moved**: W

## Directory Structure

| Check | Status | Action |
|-------|--------|--------|
| No completed/ in bugs/ | ✅ Pass / ❌ Found N files | Moved to completed/ |
| No completed/ in features/ | ✅ Pass / ❌ Found N files | Moved to completed/ |
| No completed/ in enhancements/ | ✅ Pass / ❌ Found N files | Moved to completed/ |
| completed/ is flat | ✅ Pass / ❌ Found N sub-dirs | Flattened |

## Missing ID Fixes

| Original | New Filename | ID Assigned |
|----------|--------------|-------------|
| `P0-split-base-builder-god-class.md` | `P0-ENH-004-split-base-builder-god-class.md` | ENH-004 |

## Duplicate ID Fixes

| Original | New Filename | Change |
|----------|--------------|--------|
| `P2-FEAT-007-user-message.md` | `P2-FEAT-015-user-message.md` | 007→015 |
| `P2-ENH-007-high-auto.md` | `P2-ENH-016-high-auto.md` | 007→016 |

## Type Mismatch Fixes

| Original | New Filename | Inferred Type | Confidence |
|----------|-------------|---------------|-----------|
| `P3-ENH-NNN-foo.md` (enhancements/) | `P3-BUG-NNN-foo.md` (bugs/) | BUG | 0.82 |

## ID Ranges Used
- BUG: 012-014
- FEAT: 015, 017
- ENH: 004-006, 016

## Next Steps
1. Commit the renames: `/ll:commit`
2. Update any external references to these issues
3. Run `/ll:verify-issues` to validate content accuracy
```

---

## Validation Rules

A filename is considered **valid** if it matches:
```regex
^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$
```

A filename **needs normalization** if:
- Missing category prefix (`BUG`, `FEAT`, `ENH`)
- Missing 3+ digit ID number
- Has non-standard prefix format
- **Uses an ID number that exists with a different prefix** (cross-type duplicate)

---

## Directory Structure Rules

The `.issues/` directory must follow this structure:
```
.issues/
├── bugs/           # Active bugs ONLY (no completed/ or deferred/ sub-dir)
├── features/       # Active features ONLY (no completed/ or deferred/ sub-dir)
├── enhancements/   # Active enhancements ONLY (no completed/ or deferred/ sub-dir)
├── completed/      # ALL completed issues (flat, no sub-folders)
└── deferred/       # ALL deferred/parked issues (flat, no sub-folders)
```

**Violations detected and auto-fixed:**
- `bugs/completed/`, `features/completed/`, `enhancements/completed/` directories existing
- Sub-directories within `completed/` (e.g., `completed/bugs/`, `completed/old/`)

---

## Arguments

$ARGUMENTS

- **flags** (optional): Command behavior flags
  - `--auto` - Non-interactive mode: apply all normalization changes without prompting
  - `--check` — Check-only mode for FSM loop evaluators. Scan for violations without fixing, print one line per issue, exit 1 if any found, exit 0 if clean. Implies `--auto`.

## Examples

```bash
# Find and fix all invalid issue filenames
/ll:normalize-issues

# Check-only mode for FSM loop evaluators (exit 0 if clean, exit 1 if violations)
/ll:normalize-issues --check

# Non-interactive mode (apply fixes without prompting)
/ll:normalize-issues --auto

# After normalization, verify and commit
/ll:verify-issues
/ll:commit
```

---

## Integration

Works well with:
- `/ll:scan-codebase` - Run normalize after scanning to fix any non-standard filenames
- `/ll:verify-issues` - Run after normalizing to validate content
- `/ll:prioritize-issues` - Normalizes IDs before prioritization handles priorities

## Edge Cases

### Files in completed/ directory
- Skip files in `completed/` - they're historical records
- If needed, can be run with `--include-completed` flag (future enhancement)

### Custom category prefixes
- Respect `{{config.issues.categories}}` for prefix mappings
- Support custom prefixes defined in config

### Cross-Type Duplicate IDs
- Detect when the same ID number (e.g., 007) is used across different types (BUG-007, FEAT-007, ENH-007)
- Keep the oldest file (by git history) or alphabetically first with the original ID
- Reassign all other duplicates to new globally unique IDs
- When assigning new IDs, always use the next available global number
