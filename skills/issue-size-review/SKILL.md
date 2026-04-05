---
description: |
  Use when the user wants to evaluate issue size/complexity, decompose large issues, check if issues are too big for a single session, or audit backlog sizes for sprint planning.

  Trigger keywords: "issue size review", "decompose issues", "split large issues", "issue complexity", "break down issues", "audit issue sizes", "large issue check"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Bash(ll-issues:*, git:*)
---

# Issue Size Review Skill

This skill evaluates active issues for complexity and proposes decomposition for those unlikely to be completed in a single session.

## When to Activate

Proactively offer or invoke this skill when the user:

- Mentions an issue seems too large or complex
- Is doing sprint planning and wants manageable chunks
- Asks to audit or review issue sizes
- Mentions context running out during issue work
- Says "this issue is too big" or similar

## How to Use

Invoke this skill to review all active issues:

```
/ll:issue-size-review
```

## Arguments

$ARGUMENTS

Parse arguments for flags:

```bash
ISSUE_ID=""
AUTO_MODE=false
CHECK_MODE=false
SPRINT_NAME=""

# Auto-enable in automation contexts
if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]]; then AUTO_MODE=true; fi

# Explicit flags
if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$ARGUMENTS" == *"--check"* ]]; then CHECK_MODE=true; AUTO_MODE=true; fi
if [[ "$ARGUMENTS" =~ --sprint[[:space:]]+([^[:space:]]+) ]]; then SPRINT_NAME="${BASH_REMATCH[1]}"; fi

# Extract issue ID (non-flag argument)
for token in $ARGUMENTS; do
    case "$token" in
        --*) ;; # skip flags
        *) ISSUE_ID="$token" ;;
    esac
done

# --sprint implies --auto
if [[ -n "$SPRINT_NAME" ]]; then AUTO_MODE=true; fi
```

- **issue_id** (optional): Specific issue ID to review (e.g., `ENH-179`)
- **flags** (optional):
  - `--auto` - Non-interactive mode: auto-decompose only Very Large issues (score ≥ 8) where decomposition is unambiguous. Skip Large issues (5-7) as ambiguous. Emit one status line per issue: `[ID] [action]: [summary]`
  - `--check` — Check-only mode for FSM loop evaluators. Run size scoring without decomposition, print `[ID] size: score N (oversized)` per issue scoring >= 5, exit 1 if any oversized, exit 0 if all pass. Implies `--auto`.
  - `--sprint <name>` — Scope the audit to only the issues listed in the named sprint definition (`.sprints/<name>.yaml`). Implies `--auto`. A summary header `Sprint: <name> (N issues)` is shown in the output.

## Workflow

The skill follows a 5-phase workflow:

### Phase 1: Discovery

**Sprint Mode** (`--sprint <name>`): When `SPRINT_NAME` is set, load issues from the sprint definition instead of scanning all active directories:

```bash
SPRINT_FILE=".sprints/${SPRINT_NAME}.yaml"
if [ ! -f "$SPRINT_FILE" ]; then
    echo "Error: Sprint '$SPRINT_NAME' not found at $SPRINT_FILE"
    exit 1
fi

# Read the sprint YAML with the Read tool; parse the issues: list (flat list of bare IDs)
# Resolve each ID to a file path using find:
declare -a ISSUE_FILES
for id in <sprint-issue-ids>; do
    FILE=""
    for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
        if [ -d "$dir" ]; then
            FILE=$(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | grep -E "[-_]${id}[-_.]" | head -1)
            if [ -n "$FILE" ]; then break; fi
        fi
    done
    if [ -n "$FILE" ]; then ISSUE_FILES+=("$FILE")
    else echo "Warning: Sprint issue $id not found in active issues (skipping)"; fi
done

echo "Sprint: $SPRINT_NAME (${#ISSUE_FILES[@]} issues)"
```

**Default (full backlog)**: Scan all active issues:

1. Use Glob to find all `.md` files in:
   - `{{config.issues.base_dir}}/bugs/`
   - `{{config.issues.base_dir}}/features/`
   - `{{config.issues.base_dir}}/enhancements/`
2. Read each issue file to extract content
3. Parse issue metadata (ID, type, priority, title)

### Phase 2: Size Assessment

Apply scoring heuristics to each issue:

| Criterion | Points | How to Detect |
|-----------|--------|---------------|
| File count | +2 | Count file paths (patterns like `src/`, `.py`, `.ts`, `.md`) mentioned in issue |
| Section complexity | +2 | "Proposed Solution" or "Implementation" sections >300 words |
| Multiple concerns | +3 | Multiple `##` subsections in solution, or phrases like "additionally", "also need to" |
| Dependency mentions | +2 | References to other issues (BUG-/FEAT-/ENH-) or "depends on", "blocked by" |
| Word count | +2 | >800 words total in issue file |

**Maximum score: 11 points**

Issues scoring **≥5 points** are candidates for decomposition.

### Phase 3: Decomposition Proposal

For each candidate issue:

1. Identify distinct sub-tasks or concerns by analyzing:
   - Separate sections in "Proposed Solution"
   - Different files/components mentioned
   - Distinct acceptance criteria
   - Logical boundaries between concerns

2. Propose 2-N focused child issues where each:
   - Has a clear, single responsibility
   - Can be implemented independently
   - Has testable completion criteria
   - Inherits appropriate priority and type

3. Draft child issue structure:
   ```markdown
   # [TYPE]-[NNN]: [Specific Title]

   ## Summary
   [Focused description from parent issue]

   ## Parent Issue
   Decomposed from [PARENT-ID]: [Parent Title]

   [Relevant sections from parent...]
   ```

### Phase 4: User Approval

#### Auto Mode Behavior

**When `AUTO_MODE` is true**: Skip the AskUserQuestion prompts below. Auto-approve decomposition only for Very Large issues (score ≥ 8) where the decomposition is unambiguous (distinct sub-tasks with clear boundaries). Skip Large issues (score 5-7) as ambiguous — flag them in the output but do not decompose. Emit one status line per issue: `[ID] decomposed: N child issues` or `[ID] skipped: score X (ambiguous)`.

#### Check Mode Behavior (--check)

**When `CHECK_MODE` is true**: Run size scoring only (no decomposition). For each issue scoring >= 5 (Large or Very Large), print `[ID] size: score N (oversized)`. After all issues scored, if any were oversized: print `N issues oversized`, then `exit 1`. If all pass: print `All issues pass size check`, then `exit 0`. This integrates with FSM `evaluate: type: exit_code` routing.

#### Interactive Mode (default)

For each decomposition proposal, use AskUserQuestion:

```yaml
questions:
  - question: "Decompose [ISSUE-ID] '[Title]' (score: X/11) into N smaller issues?"
    header: "[ISSUE-ID]"
    multiSelect: false
    options:
      - label: "Yes, decompose"
        description: "Create N child issues: [brief titles]"
      - label: "No, keep as-is"
        description: "Leave this issue intact"
```

Present proposals one at a time or batch (user preference).

### Phase 5: Execution

For each approved decomposition:

1. **Get next issue numbers**:
   ```bash
   ll-issues next-id
   ```
   Next numbers are the printed value, +1, +2, etc. for multiple issues.

2. **Create child issue files**:
   - Determine target directory based on type (bugs/, features/, enhancements/)
   - Generate filename: `P[priority]-[TYPE]-[NNN]-[slug].md`
   - Write issue content with parent reference in frontmatter
   - For each child issue file created, append a session log entry:

```markdown
## Session Log
- `/ll:issue-size-review` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), find the most recently modified `.jsonl` file (excluding `agent-*`). If `## Session Log` already exists, append below the header. If not, add before `---` / `## Status` footer.

3. **Update and move parent issue**:
   Add resolution section to parent:
   ```markdown
   ---

   ## Resolution

   - **Status**: Decomposed
   - **Completed**: YYYY-MM-DD
   - **Reason**: Issue too large for single session

   ### Decomposed Into
   - [TYPE]-[NNN]: [Child title 1]
   - [TYPE]-[NNN]: [Child title 2]
   - [TYPE]-[NNN]: [Child title 3]
   ```

   Move to completed:
   ```bash
   git mv "{{config.issues.base_dir}}/[category]/[parent-file].md" \
          "{{config.issues.base_dir}}/completed/"
   ```

   Before moving the parent, append a session log entry to the parent issue file:

```markdown
## Session Log
- `/ll:issue-size-review` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), find the most recently modified `.jsonl` file (excluding `agent-*`). If `## Session Log` already exists, append below the header. If not, add before `---` / `## Status` footer.

4. **Stage all changes**:
   ```bash
   git add {{config.issues.base_dir}}/
   ```

## Output Format

```
================================================================================
ISSUE SIZE REVIEW                          [Sprint: <name> (N issues) | Full backlog]
================================================================================

## SUMMARY
- Issues scanned: N
- Large issues found: M (scoring ≥5)
- Decomposition candidates: K

## ASSESSMENT

### Small Issues (0-2 points)
- [ID]: [Title] (score: X)

### Medium Issues (3-4 points)
- [ID]: [Title] (score: X)

### Large Issues (5-7 points) - CANDIDATES
- [ID]: [Title] (score: X)
  Breakdown: files(+2), complexity(+2), concerns(+3)

### Very Large Issues (8+ points) - STRONG CANDIDATES
- [ID]: [Title] (score: X)
  Breakdown: [scoring details]

## PROPOSALS

### [ISSUE-ID]: [Title]
**Score**: X/11
**Breakdown**: [which criteria scored]

**Proposed decomposition into N issues:**

1. **[TYPE]-[NNN]: [Child title 1]**
   - Scope: [What this child covers]
   - Files: [Which files this affects]

2. **[TYPE]-[NNN]: [Child title 2]**
   - Scope: [What this child covers]
   - Files: [Which files this affects]

**Rationale**: [Why this split makes sense]

[AskUserQuestion prompt]

---

## RESULTS

### Decomposed
- [PARENT-ID] → [CHILD-1], [CHILD-2], [CHILD-3]

### Declined
- [ID]: User chose to keep as-is

### Created Issues
- [TYPE]-[NNN]: [Title] (from [PARENT-ID])
- [TYPE]-[NNN]: [Title] (from [PARENT-ID])

### Moved to Completed
- [PARENT-ID]: [Title]

================================================================================
```

## Examples

| User Says | Action |
|-----------|--------|
| "This issue is too big" | Run issue size review on that specific issue |
| "Audit issue sizes" | Run full issue size review |
| "Break down large issues" | Run issue size review |
| "Sprint planning - need smaller tasks" | Run issue size review |
| "Review issue complexity" | Run issue size review |
| "Can we split ENH-179?" | Run issue size review targeting ENH-179 |
| "Review sizes non-interactively" | `/ll:issue-size-review --auto` |
| "Check if issues are sized for sprint" | `/ll:issue-size-review --check` |
| "Check sizes for a specific sprint" | `/ll:issue-size-review --sprint my-sprint` |

## Size Thresholds

| Score | Assessment | Recommendation |
|-------|------------|----------------|
| 0-2 | Small | No action needed - good size for single session |
| 3-4 | Medium | Borderline - may benefit from split if multiple concerns |
| 5-7 | Large | Recommend decomposition |
| 8+ | Very Large | Strongly recommend decomposition |

## Configuration

Uses project configuration from `.ll/ll-config.json`:

- `issues.base_dir` - Base directory for issues (default: `.issues`)
- `issues.categories` - Bug/feature/enhancement directory config
- `issues.completed_dir` - Where to move decomposed parents (default: `completed`)

## Best Practices

### Good Decomposition

- Each child issue has **one clear goal**
- Children are **independently implementable** (no blocking dependencies between them)
- Children have **similar size** (avoid 1 large + 2 tiny)
- Children **preserve context** from parent (link back, include relevant details)

### Avoid

- Creating too many tiny issues (cognitive overhead)
- Splitting tightly-coupled concerns that should stay together
- Losing context when decomposing (always reference parent)
- Creating circular dependencies between children

## Integration

After running issue size review:

- Review created child issues with `cat [path]`
- Validate with `/ll:ready-issue [ID]`
- Commit changes with `/ll:commit`
- Process with `/ll:manage-issue` or `/ll:create-sprint`
