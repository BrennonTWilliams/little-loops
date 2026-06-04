---
name: scope-epic
description: Use when asked to decompose a theme or goal into an EPIC with 3–8 child issues. Creates the EPIC file, pre-wired child stubs, and stages everything for git.
args: "<theme> [--from-doc <path>] [--priority P2]"
argument-hint: "<theme>"
model: sonnet
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
  - Bash(ll-issues:*, git:*)
  - Bash(ll-history-context:*)
arguments:
  - name: theme
    description: Natural-language theme or goal description to decompose into an EPIC + children
    required: true
  - name: flags
    description: Optional flags (--from-doc <path> to load theme from a file, --priority P2 to override default EPIC priority)
    required: false
metadata:
  short-description: Decompose a theme into an EPIC with 3–8 pre-wired child issue stubs.
---

# Scope EPIC

You are tasked with decomposing a high-level theme or goal into an EPIC issue file and 3–8 pre-wired child issue stubs. This is the upstream creation step that `/ll:capture-issue --parent` assumes already happened.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **EPIC dir**: `{{config.issues.base_dir}}/epics/`
- **Min children**: `{{config.epics.scope.min_children}}` (default: 3)
- **Max children**: `{{config.epics.scope.max_children}}` (default: 8)
- **Status enum**: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`

## Arguments

$ARGUMENTS

- **theme** (required): Natural-language description of the theme or goal
- **flags** (optional):
  - `--from-doc <path>` — Read the theme from a markdown file instead of the argument string
  - `--priority <P0-P5>` — Override the default EPIC priority (default: P2)

## Process

### Phase 1: Parse Arguments and Extract Theme

**Parse flags:**

```bash
THEME="${theme:-}"
FROM_DOC=""
PRIORITY="P2"

if [[ "$ARGUMENTS" =~ --from-doc[[:space:]]+([^[:space:]]+) ]]; then
  FROM_DOC="${BASH_REMATCH[1]}"
fi

if [[ "$ARGUMENTS" =~ --priority[[:space:]]+(P[0-5]) ]]; then
  PRIORITY="${BASH_REMATCH[1]}"
fi
```

**Extract theme text:**

If `--from-doc` was given:
1. Verify the file exists at `FROM_DOC`. If not found, abort with:
   ```
   ❌ File not found: [FROM_DOC]. Check the path and try again.
   ```
2. Read the file content. Extract the theme from the top-level heading (`# ...`) and first paragraph of description text.
3. If no usable text is found, abort:
   ```
   ❌ Could not extract a theme from [FROM_DOC]. Provide a heading and description paragraph, or pass the theme directly: /ll:scope-epic "your theme"
   ```

Otherwise, use `THEME` directly.

---

### Phase 2: Decompose Theme into EPIC + Children

Decompose the theme into one EPIC summary and 3–8 child issue proposals. Each child must be independently shippable — each child should produce its own PR with tests; no artifact-type splits, no wiring-from-implementation splits.

**Read config thresholds:**

```
MIN_CHILDREN = {{config.epics.scope.min_children}}  (default 3)
MAX_CHILDREN = {{config.epics.scope.max_children}}  (default 8)
```

To calibrate child-issue size estimates, fetch recent velocity:

```bash
EFFORT=$(ll-history-context PARENT_ISSUE_ID --effort 2>/dev/null || true)
```

If `$EFFORT` is non-empty, use session count and cycle time from historical data
to calibrate child issue size and complexity estimates.

**LLM Decomposition — produce a structured JSON array:**

Analyze the theme and generate a JSON array of child proposals. Each entry must have:

```json
[
  {
    "type": "FEAT",
    "priority": "P2",
    "summary": "One-sentence description of the child issue",
    "title": "Concise title (5-10 words)"
  }
]
```

**Decomposition guidelines:**
- Each child must be **independently shippable** — it must produce its own PR with tests. No artifact-type splits (e.g., "the models" / "the tests" / "the docs" for the same feature). No wiring-from-implementation splits (e.g., "the implementation" / "the wiring").
- **Type selection**: Use `FEAT` for new capabilities, `ENH` for improvements to existing code, `BUG` for defects the theme implies fixing.
- **Priority**: Default to one level below the EPIC priority (if EPIC is P2, children default to P3). Raise to match EPIC priority for critical-path items.
- **Count**: Aim for 4–6 children. Fewer than `MIN_CHILDREN` is a sign the theme may be a single issue; more than `MAX_CHILDREN` suggests sub-EPIC decomposition.

**Count warnings (emit before presenting the proposal):**

```
IF child_count < MIN_CHILDREN:
  ⚠ This theme produced only [child_count] child proposal(s) — below the minimum of [MIN_CHILDREN].
    This might be a single-issue task. Consider using /ll:capture-issue instead.
    Proceeding with the available proposals.

IF child_count > MAX_CHILDREN:
  ⚠ This theme produced [child_count] child proposals — above the maximum of [MAX_CHILDREN].
    Consider decomposing into sub-EPICs. Proceeding with the full list for review.
```

---

### Phase 3: Interactive Review

#### Step 1: Present the proposal

Display a markdown table summarizing the EPIC and all proposed children:

```markdown
## Proposed EPIC Decomposition

**EPIC**: [EPIC title] (Priority: [PRIORITY])

| # | Type | Priority | Summary |
|---|------|----------|---------|
| 1 | FEAT | P3       | [summary] |
| 2 | ENH  | P3       | [summary] |
| 3 | FEAT | P3       | [summary] |
```

Follow the table with per-child detail sections:

```markdown
### Child 1: [Title]
- **Type**: FEAT
- **Priority**: P3
- **Summary**: [summary]

### Child 2: [Title]
- **Type**: ENH
- **Priority**: P3
- **Summary**: [summary]
```

#### Step 2: AskUserQuestion — select which children to keep

Use `AskUserQuestion` with `multiSelect: true` to let the user select which children to proceed with:

```yaml
questions:
  - question: "Which child issues should be created? Deselect any you want to drop."
    header: "Select children"
    multiSelect: true
    options:
      - label: "1. FEAT P3: [title]"
        description: "[summary]"
      - label: "2. ENH P3: [title]"
        description: "[summary]"
```

If the user deselects all children, report and stop:

```
No children selected. Cancelling — nothing was written.
```

#### Step 3: AskUserQuestion — confirm, edit, or cancel

After children are selected, present a summary of what will be created and ask for confirmation:

```yaml
questions:
  - question: "Create EPIC [EPIC title] with [N] children? Files will be written to {{config.issues.base_dir}}/epics/ and {{config.issues.base_dir}}/(features|enhancements|bugs)/."
    header: "Confirm"
    options:
      - label: "Create all files"
        description: "Write the EPIC and [N] child issue stubs, then stage for git"
      - label: "Edit before creating"
        description: "I want to modify the EPIC summary or child details before writing files"
      - label: "Cancel"
        description: "Write nothing — stop now"
```

**If "Cancel"**: Stop. No files written.

**If "Edit before creating"**: Ask the user what changes they want (free-text), apply them, then re-present the confirm/cancel question.

**If "Create all files"**: Proceed to Phase 4.

---

### Phase 4: ID Allocation and File Writes

Write the EPIC first, then each child in order. Call `ll-issues next-id` **immediately before each Write** — do NOT batch-allocate IDs upfront.

**EPIC directory**: `{{config.issues.base_dir}}/epics/`
**Child directories**: `{{config.issues.base_dir}}/features/` for FEAT, `{{config.issues.base_dir}}/enhancements/` for ENH, `{{config.issues.base_dir}}/bugs/` for BUG

#### Step 1: Write the EPIC file

1. **Get next ID:**
   ```bash
   ll-issues next-id
   ```
   Store as `EPIC_NNN` (e.g., `071` → `EPIC-071`).

2. **Generate filename**: `P[PRIORITY]-EPIC-[NNN]-[slugified-epic-title].md`
   Slugify: lowercase, replace spaces/special chars with hyphens.

3. **Build EPIC content** using the full template:
   - Read `templates/epic-sections.json` to get section definitions.
   - Use `variant="full"` with `scripts/little_loops/issue_template.py:assemble_issue_markdown()`.
   - Frontmatter must include: `id: EPIC-NNN`, `type: EPIC`, `priority: [PRIORITY]`, `status: open`, `captured_at` (ISO 8601 UTC via `date -u +"%Y-%m-%dT%H:%M:%SZ"`), `discovered_date` (date-only), `discovered_by: scope-epic`, `relates_to: []`.
   - `## Summary`: the EPIC summary from decomposition.
   - `## Children`: placeholder section (will be populated in Phase 5).

   The EPIC template includes: Summary, Motivation, Goal, Scope, Children, Success Metrics, Integration Map, Impact, Labels, Status.

4. **Write the file:**
   ```bash
   Write to {{config.issues.base_dir}}/epics/[filename]
   ```

5. **Append session log entry** to the EPIC file:
   ```markdown
   ## Session Log
   - `/ll:scope-epic` - [ISO timestamp] - `[path to current session JSONL]`
   ```
   Find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project, find the most recently modified `.jsonl` file (excluding `agent-*`).

> **Duplicate-ID recovery**: If the PostToolUse hook reports the file was deleted (duplicate integer ID), call `ll-issues next-id` again, generate a new filename, and retry.

#### Step 2: Write each child file

For each selected child in order:

1. **Get next ID:**
   ```bash
   ll-issues next-id
   ```
   Store as `CHILD_NNN` → e.g., `072` with type `FEAT` → `FEAT-072`.

2. **Generate filename**: `P[priority]-[TYPE]-[NNN]-[slugified-title].md`

3. **Build child content** using the minimal template:
   - Read `templates/{type}-sections.json` for the child's type.
   - Use `variant="minimal"` with `assemble_issue_markdown()`.
   - Frontmatter must include: `id: TYPE-NNN`, `type: [TYPE]`, `priority: [priority]`, `status: open`, `captured_at` (ISO 8601 UTC), `discovered_date` (date-only), `discovered_by: scope-epic`, `parent: EPIC-NNN`.
   - `## Summary`: the child's one-sentence summary.

4. **Write the file** to the appropriate type directory.

5. **Append session log entry** to the child file (same pattern as EPIC).

6. **Store child info** for Phase 5 wiring: `{id, title, type, priority, summary}`.

> **Duplicate-ID recovery**: Same as above — re-allocate and retry.

---

### Phase 5: Wire EPIC ↔ Children

For each child that was successfully written:

#### 5a: Add child ID to EPIC `relates_to:` frontmatter

Read the EPIC file's frontmatter. The `relates_to:` field may be:
- **Absent** — insert `relates_to: [CHILD_ID]` after the last frontmatter field (before closing `---`)
- **Empty list** `relates_to: []` — replace with `relates_to: [CHILD_ID]`
- **Populated list** `relates_to: [FEAT-100, FEAT-101]` — append `, CHILD_ID` inside the closing `]`

Use `Edit` to apply each change in-place. Do not rewrite the whole file.

Example transformation:
```
# Before
relates_to: [FEAT-100, FEAT-101]

# After
relates_to: [FEAT-100, FEAT-101, FEAT-102]
```

On the first child when the EPIC's `relates_to` is empty (`[]`): replace the empty list with the first ID. On subsequent children: append to the existing list.

#### 5b: Append child to EPIC `## Children` section

If the EPIC body already contains a `## Children` section (created from the template in Phase 4), append a new bullet:

```markdown
- **CHILD_ID** — [one-sentence child title]
```

Use `Edit` to append the bullet line after the last existing bullet in that section.

If no `## Children` section exists (should not happen with the full EPIC template, but handle defensively), insert one before `## Status`:

```markdown
## Children

- **CHILD_ID** — [one-sentence child title]
```

#### 5c: Verify `parent:` on each child

Each child was written with `parent: EPIC-NNN` in its frontmatter during Phase 4. If any child is missing this field (e.g., due to a template issue), add it via `Edit`: insert `parent: EPIC-NNN` before the closing `---` of the child's frontmatter block.

---

### Phase 6: Git Stage

Stage the EPIC file and all child files:

```bash
git add "{{config.issues.base_dir}}/epics/[epic_filename]"
git add "{{config.issues.base_dir}}/[category]/[child_filename]"
# ... repeat for each child
```

---

### Phase 7: Output Report

```
================================================================================
EPIC CREATED: EPIC-NNN — [EPIC title]
================================================================================

## Files Created

| File | Type | Priority |
|------|------|----------|
| .issues/epics/P2-EPIC-NNN-slug.md | EPIC | P2 |
| .issues/features/P3-FEAT-NNN-slug.md | FEAT | P3 |
| .issues/enhancements/P3-ENH-NNN-slug.md | ENH | P3 |
| ... | ... | ... |

## Next Steps

1. **Refine children**: `/ll:refine-issue FEAT-NNN` on any child whose scope needs deepening
2. **Review EPIC health**: `/ll:review-epic EPIC-NNN` to validate decomposition coverage
3. **Create a sprint**: `/ll:create-sprint EPIC-NNN` to group children for execution
4. **Or implement immediately**: `/ll:manage-issue feature implement FEAT-NNN`

================================================================================
```

---

## Examples

```bash
# Decompose a theme into an EPIC
/ll:scope-epic "Automatic docs sweep — detect drift, propose updates, verify links"

# Load theme from a goals document
/ll:scope-epic --from-doc thoughts/goals/docs-automation.md

# Override EPIC priority
/ll:scope-epic "Add dark mode support across the dashboard" --priority P1
```

---

## Integration

After scoping an EPIC:
1. **Refine**: `/ll:refine-issue [CHILD_ID]` to fill knowledge gaps in child stubs
2. **Review**: `/ll:review-epic EPIC-NNN` to audit decomposition coverage
3. **Sprint**: `/ll:create-sprint EPIC-NNN` to group children for execution
4. **Implement**: `/ll:manage-issue [type] implement [CHILD_ID]` on individual children
5. **Commit**: `/ll:commit` to save any refinements
