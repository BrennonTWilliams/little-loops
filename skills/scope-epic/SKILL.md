---
name: scope-epic
description: Use when asked to decompose a theme or goal into an EPIC with 3–8 child issues. Creates the EPIC file, pre-wired child stubs, and stages everything for git.
args: "<theme> [--from-doc <path>] [--priority P2] [--auto]"
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
  - Bash(ll-learning-tests:*)
arguments:
  - name: theme
    description: Natural-language theme or goal description to decompose into an EPIC + children
    required: true
  - name: flags
    description: Optional flags (--from-doc <path> to load theme from a file, --priority P2 to override default EPIC priority, --auto to skip the interactive review and create all proposed children non-interactively)
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
  - `--auto` — Non-interactive mode for automation callers (e.g. the `rn-build` loop). Skips Phase 3's `AskUserQuestion` checkpoints and creates **all** proposed children without prompting. Count warnings are still emitted, but never block.

## Process

### Phase 1: Parse Arguments and Extract Theme

**Parse flags:**

```bash
THEME="${theme:-}"
FROM_DOC=""
PRIORITY="P2"
AUTO=false

if [[ "$ARGUMENTS" =~ --from-doc[[:space:]]+([^[:space:]]+) ]]; then
  FROM_DOC="${BASH_REMATCH[1]}"
fi

if [[ "$ARGUMENTS" =~ --priority[[:space:]]+(P[0-5]) ]]; then
  PRIORITY="${BASH_REMATCH[1]}"
fi

if [[ "$ARGUMENTS" =~ (^|[[:space:]])--auto($|[[:space:]]) ]]; then
  AUTO=true
fi
```

When `--auto` is set, you are running on behalf of an automation caller with no
human at the keyboard. Carry `AUTO` through to Phase 3 and follow its
non-interactive branch instead of calling `AskUserQuestion`.

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
EFFORT=$(ll-history-context --for-skill scope-epic --effort PARENT_ISSUE_ID 2>/dev/null || true)
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

### Phase 2.5: Learning Test Detection

**Skip this phase entirely if**: `config.learning_tests.enabled` is `false` (the default). When disabled, set `LT_PROPOSALS = []` and proceed to Phase 3 with no learning test proposals.

When `learning_tests.enabled` is `true`:

#### Step 1: Extract external packages from the epic description

Analyze the THEME text (and `FROM_DOC` content when used) and identify all external packages, SDKs, or third-party APIs the epic depends on. Apply the same inclusion/exclusion rules as `extract_learning_targets()`:

- **Include**: third-party Python packages (anthropic, requests, boto3, stripe), external APIs and services (Stripe webhooks, GitHub API), cloud SDKs, non-obvious stdlib components (asyncio, multiprocessing)
- **Exclude**: internal project code, Python builtins (str, dict, list), contract-stable stdlib (os, sys, pathlib, json, re, datetime)

Store the result as `DETECTED_PACKAGES` (list of canonical short names). If the epic has no external dependencies, set `DETECTED_PACKAGES = []` and proceed to Phase 3.

#### Step 2: Check each package against the learning test registry

For each package name in `DETECTED_PACKAGES`:

```bash
ll-learning-tests check "<package>" --stale-aware
```

- **Exit 0** → package is proven and current → add to `PROVEN_PACKAGES` list, skip
- **Exit 1** → package is unproven, stale, or refuted → add to `UNPROVEN_PACKAGES` list

#### Step 3: Build learning test sub-issue proposals

For each package in `UNPROVEN_PACKAGES`, create a proposal with: type `ENH`, priority matching the EPIC, title `Explore and prove <package> API behavior`, summary `Run /ll:explore-api "<package>" to build a proven record of this API surface before implementing the dependent epic children.`, and flags `is_learning_test: true`, `package: <package>`.

Store all proposals as `LT_PROPOSALS`. If `LT_PROPOSALS` is empty, proceed to Phase 3 unchanged.

---

### Phase 3: Interactive Review

> **Non-interactive (`--auto`) shortcut:** If `AUTO` is `true`, **skip Steps 2 and 3
> entirely** — do not call `AskUserQuestion`. Print the Step 1 proposal table for the
> log, keep **all** proposed children, and proceed directly to Phase 4. The count
> warnings from Phase 2 are still printed but never block. This is the path the
> `rn-build` loop's `scope_project` state depends on; calling `AskUserQuestion` here
> would halt the automated pipeline permanently.

#### Step 1: Present the proposal

Display a markdown table summarizing the EPIC and all proposed children. When `LT_PROPOSALS` is non-empty, insert a **Prerequisites** section above the implementation children to surface learning test sub-issues prominently:

```markdown
## Proposed EPIC Decomposition

**EPIC**: [EPIC title] (Priority: [PRIORITY])

### Prerequisites (Learning Tests)

| # | Type | Priority | Summary |
|---|------|----------|---------|
| LT1 | ENH | P[N] | Explore and prove <package> API behavior |

These sub-issues must be completed before the implementation children that depend on the same packages.

### Implementation Children

| # | Type | Priority | Summary |
|---|------|----------|---------|
| 1 | FEAT | P3       | [summary] |
| 2 | ENH  | P3       | [summary] |
| 3 | FEAT | P3       | [summary] |
```

When `LT_PROPOSALS` is empty, display only the implementation table (no prerequisites section).

Follow the table with per-child detail sections in the same format as before: learning test proposals first (labeled `[Prerequisite]` with `Role: Prerequisite — must complete before dependent implementation children` and `Implementation: /ll:explore-api "<package>"`), then implementation children.

#### Step 2: AskUserQuestion — select which children to keep

**Skip this step if `AUTO` is `true`** (keep all children; go to Phase 4).

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

**Skip this step if `AUTO` is `true`** (proceed directly to Phase 4 — files are created without confirmation).

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
   - Run `ll-issues sections epic` to get section definitions.
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

#### Step 2a: Write learning test sub-issues (when LT_PROPOSALS is non-empty)

**Skip if `LT_PROPOSALS` is empty.**

For each proposal in `LT_PROPOSALS` (in order), write a learning test sub-issue **before** writing implementation children, so their IDs are known for `depends_on` wiring:

1. **Get next ID:**
   ```bash
   ll-issues next-id
   ```
   Store as `LT_NNN` → e.g., `073` → `ENH-073`.

2. **Generate filename**: `P[EPIC_PRIORITY]-ENH-[NNN]-explore-and-prove-[slugified-package]-api-behavior.md`

3. **Build content** using the minimal ENH template:
   - Frontmatter must include: `id: ENH-NNN`, `type: ENH`, `priority: [EPIC_PRIORITY]`, `status: open`, `captured_at` (ISO 8601 UTC), `discovered_date` (date-only), `discovered_by: scope-epic`, `parent: EPIC-NNN`, `learning_tests_required: ["<package>"]` (the single package this issue proves), `labels: learning-tests`.
   - `## Summary`: `Explore and prove \`<package>\` API behavior before implementing dependent epic children.`
   - `## Implementation`: `Run \`/ll:explore-api "<package>"\` to build a proven record of this API surface.`

4. **Write the file** to `{{config.issues.base_dir}}/enhancements/`.

5. **Append session log entry** to the file (same pattern as EPIC).

6. **Store mapping**: `LT_IDS[package] = ENH-NNN` for use in implementation child wiring below.

> **Duplicate-ID recovery**: Re-allocate and retry on ID collision.

#### Step 2b: Write each implementation child file

For each selected **implementation** child in order (the children from Phase 2, not learning test proposals):

1. **Get next ID:**
   ```bash
   ll-issues next-id
   ```
   Store as `CHILD_NNN` → e.g., `072` with type `FEAT` → `FEAT-072`.

2. **Generate filename**: `P[priority]-[TYPE]-[NNN]-[slugified-title].md`

3. **Build child content** using the minimal template:
   - Run `ll-issues sections {type}` for the child's type.
   - Use `variant="minimal"` with `assemble_issue_markdown()`.
   - Frontmatter must include: `id: TYPE-NNN`, `type: [TYPE]`, `priority: [priority]`, `status: open`, `captured_at` (ISO 8601 UTC), `discovered_date` (date-only), `discovered_by: scope-epic`, `parent: EPIC-NNN`.
   - When `LT_IDS` is non-empty, also include:
     - `learning_tests_required: [<pkg1>, <pkg2>, ...]` — all packages in `UNPROVEN_PACKAGES`
     - `depends_on: [ENH-NNN, ...]` — all learning test sub-issue IDs from `LT_IDS`
   - `## Summary`: the child's one-sentence summary.

4. **Write the file** to the appropriate type directory.

5. **Append session log entry** to the child file (same pattern as EPIC).

6. **Store child info** for Phase 5 wiring: `{id, title, type, priority, summary}`.

> **Duplicate-ID recovery**: Same as above — re-allocate and retry.

---

### Phase 5: Wire EPIC ↔ Children

Include learning test sub-issues (from Step 2a) alongside implementation children in all wiring below. Learning test sub-issues are full children of the EPIC and appear in the `relates_to` list and `## Children` section just like implementation children.

For each child (learning test sub-issues first, then implementation children) that was successfully written:

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

Stage the EPIC file, all learning test sub-issue files, and all implementation child files:

```bash
git add "{{config.issues.base_dir}}/epics/[epic_filename]"
git add "{{config.issues.base_dir}}/enhancements/[lt_filename]"  # repeat for each learning test sub-issue
git add "{{config.issues.base_dir}}/[category]/[child_filename]"  # repeat for each implementation child
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
