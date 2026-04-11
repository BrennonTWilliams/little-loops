---
description: |
  Use when the user asks to audit issues for conflicts, detect conflicting requirements or objectives across open issues, find incompatible architecture decisions, or says "check my backlog for conflicts." Supports auto-apply and dry-run modes.

  Trigger keywords: "audit issue conflicts", "detect conflicts", "conflicting issues", "backlog conflicts", "incompatible issues", "conflict audit", "check for conflicts"
argument-hint: "[--auto] [--dry-run]"
model: sonnet
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - AskUserQuestion
  - Bash(git:*)
  - Bash(ll-issues:*)
arguments:
  - name: flags
    description: "Optional flags: --auto (apply all recommendations without prompting), --dry-run (report only, no changes)"
    required: false
---

# Audit Issue Conflicts

You are tasked with scanning all open issues for semantic conflicts, synthesizing a ranked conflict report, and optionally applying recommended resolutions — either interactively (default), automatically (`--auto`), or as a report only (`--dry-run`).

## Configuration

This skill uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Completed dir**: `{{config.issues.completed_dir}}`

---

## Phase 0: Parse Flags

```
AUTO_MODE = false
DRY_RUN = false

# Auto-enable in automation contexts
if ARGUMENTS contains "--dangerously-skip-permissions": AUTO_MODE = true

# Explicit flags
if ARGUMENTS contains "--auto": AUTO_MODE = true
if ARGUMENTS contains "--dry-run": DRY_RUN = true
```

Log the active mode:
- `--auto` → "Running in auto-apply mode: all recommendations will be applied without prompting."
- `--dry-run` → "Running in dry-run mode: conflict report will be output, no files will be modified."
- neither → "Running in interactive mode: each recommendation will require approval."

---

## Phase 1: Load Issues

Collect all active issue files:

```bash
declare -a ISSUE_FILES
for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
    if [ -d "$dir" ]; then
        while IFS= read -r file; do
            ISSUE_FILES+=("$file")
        done < <(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | sort)
    fi
done

if [[ ${#ISSUE_FILES[@]} -eq 0 ]]; then
    echo "No active issues found"
    exit 0
fi

echo "Found ${#ISSUE_FILES[@]} active issues to evaluate"
```

For each file, parse from the filename:
- **ID** (e.g., `FEAT-1028`, `BUG-042`)
- **Type** (`BUG`, `FEAT`, `ENH`)
- **Priority** (`P0`–`P5`)

Then read the file to extract:
- **Title** (from `# heading`)
- **Summary** section
- **Integration Map** / **Implementation Steps** / **Objectives** sections (first 300 chars each)

---

## Phase 2: Conflict Detection

Batch issues **3–5 per Task call**. Spawn all batch Task calls in a **single message** (parallel).

For each batch, use this prompt template:

```
Analyze the following issues for semantic conflicts.

You are looking for four conflict types:

1. **Requirement conflicts** — Issue A requires X, Issue B requires not-X (contradictory requirements)
2. **Objective conflicts** — Two issues solve the same problem but with different approaches (duplicated goal)
3. **Architecture conflicts** — Incompatible technical approaches (e.g., sync vs async, different data models, conflicting API shapes)
4. **Scope overlap** — Issues that partially duplicate each other's scope (overlapping but not identical)

For EACH pair of issues in this batch, determine if a conflict exists.

Issues to analyze (read each full file before reasoning):

[For each issue in the batch:]
- **File**: [path]
- **ID**: [ISSUE-ID]
- **Type**: [BUG/FEAT/ENH]
- **Priority**: [P0-P5]
- **Title**: [title]
- **Summary excerpt**: [first 300 chars of summary]

Return a structured list of conflicts found. For each conflict:

- conflict_type: requirement | objective | architecture | scope
- severity: high | medium | low
  - high: directly contradictory, will cause implementation failures if both proceed
  - medium: significant overlap or incompatibility requiring coordination
  - low: minor duplication or loose coupling concern
- issues: [LIST of affected ISSUE-IDs, e.g. ["FEAT-100", "FEAT-200"]]
- description: [1-2 sentence explanation of the specific conflict]
- recommendation: merge | deprecate | split | add_dependency | update_scope
  - merge: consolidate both into one issue (one closes, scope absorbed)
  - deprecate: one issue is superseded, should be closed
  - split: issues should be explicitly scoped to avoid overlap
  - add_dependency: issues can coexist but need blocked_by ordering
  - update_scope: scope notes should be added to clarify boundaries
- proposed_change: [specific action, e.g., "Close FEAT-200, add its auth-caching scope to FEAT-100"]

If no conflicts exist among this batch, return: []
```

Wait for **all batch agents** to complete before proceeding.

Handle agent failures: if a batch agent fails, retry once. If retry fails, log a warning for those issues and continue.

---

## Phase 3: Synthesize Report

Aggregate all batch findings:

1. **Deduplicate**: merge any identical conflict pairs reported by overlapping batches
2. **Group by severity**: high → medium → low
3. **Within each severity group**: sort by issue priority (P0 first)

If no conflicts were found across all batches:

```
================================================================================
AUDIT ISSUE CONFLICTS
================================================================================

No conflicts detected among [N] active issues.

All issues appear to have compatible requirements, objectives, architecture
decisions, and scope boundaries.
================================================================================
```

Output this message and stop (exit 0).

Otherwise, display the conflict report:

```
================================================================================
AUDIT ISSUE CONFLICTS
================================================================================

Issues scanned: [N]
Conflicts found: [C] ([H] high / [M] medium / [L] low)

## HIGH SEVERITY

| # | Type | Issues | Description | Recommendation |
|---|------|--------|-------------|----------------|
| 1 | [type] | [ID-A] vs [ID-B] | [description] | [recommendation] |

## MEDIUM SEVERITY

| # | Type | Issues | Description | Recommendation |
|---|------|--------|-------------|----------------|
| 2 | [type] | [ID-A] vs [ID-B] | [description] | [recommendation] |

## LOW SEVERITY

| # | Type | Issues | Description | Recommendation |
|---|------|--------|-------------|----------------|
| 3 | [type] | [ID-A] vs [ID-B] | [description] | [recommendation] |

================================================================================
```

---

## Phase 4: Apply Recommendations

### Dry-Run Mode (`--dry-run`)

Output the report (Phase 3) and stop. Do not modify any issue files.

```
Dry-run mode: no changes applied.
```

### Auto Mode (`--auto`)

Apply **all** recommendations without prompting. For each conflict, execute the appropriate action (see Phase 4b below).

### Interactive Mode (default)

For each conflict, present an `AskUserQuestion` prompt with options shaped by recommendation type.

**merge / deprecate** conflicts:

```yaml
questions:
  - question: "[SEVERITY] conflict: [ISSUE-A] vs [ISSUE-B] — [description]. Apply recommendation?"
    header: "[ISSUE-A] vs [ISSUE-B]"
    multiSelect: false
    options:
      - label: "Yes, apply — [proposed_change summary]"
        description: "[specific action, e.g., merge scope into ISSUE-A, close ISSUE-B]"
      - label: "No, keep both as-is"
        description: "Leave both issues unchanged"
      - label: "Add dependency instead"
        description: "Add blocked_by frontmatter to link them without closing either"
```

**add_dependency** conflicts:

```yaml
questions:
  - question: "Add blocked_by link: [ISSUE-A] should depend on [ISSUE-B]?"
    header: "[ISSUE-A]"
    multiSelect: false
    options:
      - label: "Yes, add blocked_by frontmatter"
        description: "Appends blocked_by: [ISSUE-B] to [ISSUE-A] frontmatter"
      - label: "No, skip"
        description: "Leave both issues unchanged"
```

**split / update_scope** conflicts:

```yaml
questions:
  - question: "Scope overlap: [ISSUE-A] vs [ISSUE-B] — [description]. Add scope note?"
    header: "[ISSUE-A] vs [ISSUE-B]"
    multiSelect: false
    options:
      - label: "Yes, append scope clarification note"
        description: "Adds a ## Scope Boundary note to each issue clarifying their split"
      - label: "No, keep as-is"
        description: "Leave both issues unchanged"
```

---

## Phase 4b: Execute Approved Changes

For each approved recommendation:

### merge / deprecate

1. Identify the issue to be **kept** and the one to be **closed/superseded**
2. If merging scope: append a `## Scope Addition` note to the kept issue file:

```markdown

---

## Scope Addition

**Source**: Merged from [CLOSED-ID] during `/ll:audit-issue-conflicts` conflict resolution.

[Relevant scope absorbed from CLOSED-ID]
```

3. Add a resolution section to the closed issue file:

```markdown

---

## Resolution

- **Status**: Closed - Superseded
- **Completed**: YYYY-MM-DD
- **Reason**: Superseded by [KEPT-ID] via conflict resolution audit
- **Proposed change**: [proposed_change from conflict record]
```

4. Move the closed issue:

```bash
git mv "{{config.issues.base_dir}}/[category]/[file].md" \
       "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/"
```

5. Append session log to closed issue (after moving):

```bash
ll-issues append-log "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/[file].md" /ll:audit-issue-conflicts
```

6. Append session log to kept issue:

```bash
ll-issues append-log "[kept-issue-path]" /ll:audit-issue-conflicts
```

### add_dependency

Append `blocked_by: [ISSUE-B]` to the frontmatter of the dependent issue file using Edit. Then append session log:

```bash
ll-issues append-log "[issue-path]" /ll:audit-issue-conflicts
```

### split / update_scope

Append a scope boundary note to each affected issue file:

```markdown

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): [Specific scope clarification. E.g., "This issue covers X only. Related issue [OTHER-ID] covers Y."]
```

Then append session log to each modified file:

```bash
ll-issues append-log "[issue-path]" /ll:audit-issue-conflicts
```

---

## Phase 5: Cleanup

After all approved changes are applied, stage everything in one shot:

```bash
git add {{config.issues.base_dir}}/
```

---

## Phase 6: Final Report

```
================================================================================
AUDIT ISSUE CONFLICTS — COMPLETE
================================================================================

## SUMMARY
- Issues scanned: [N]
- Conflicts found: [C]
- Recommendations applied: [A]
- Skipped (user declined or no-op): [S]
- Could not evaluate: [W]

## APPLIED CHANGES
- [ISSUE-A] vs [ISSUE-B]: [action taken, e.g., "FEAT-200 closed, scope merged into FEAT-100"]
- [ISSUE-A]: [action taken, e.g., "blocked_by: FEAT-300 added to frontmatter"]

## UNCHANGED
- [ISSUE-A] vs [ISSUE-B]: user declined recommendation
- [ISSUE-A] vs [ISSUE-B]: no action needed (low severity, skipped in auto mode)

## SKIPPED (evaluation errors)
- [file]: Could not evaluate (subagent failure)

## GIT STATUS
All changes staged in {{config.issues.base_dir}}/

================================================================================
```

---

## Examples

```bash
# Interactive mode: review each conflict and approve/reject
/ll:audit-issue-conflicts

# Auto-apply all recommendations without prompting
/ll:audit-issue-conflicts --auto

# Report only, no changes
/ll:audit-issue-conflicts --dry-run
```

## Related Commands

- `/ll:tradeoff-review-issues` — Evaluates utility vs complexity (is it worth doing?)
- `/ll:align-issues` — Validates issues against project goals
- `/ll:map-dependencies` — Traces blocked_by relationships
- `/ll:refine-issue` — Fills knowledge gaps in a single issue
