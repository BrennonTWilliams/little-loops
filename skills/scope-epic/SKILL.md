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
trigger_fixtures:
  should_fire:
    - "decompose this theme into an epic with child issues and pre-wired stubs"
    - "scope a new epic from this goal with child issue stubs"
  should_not_fire:
    - "review epic health and audit stalled children"
    - "capture this bug as a new issue"
---

# Scope EPIC

You are tasked with decomposing a high-level theme or goal into an EPIC issue file and 3–8 pre-wired child issue stubs. This is the upstream creation step that `/ll:capture-issue --parent` assumes already happened.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **EPIC dir**: `{{config.issues.base_dir}}/epics/`
- **Min children**: `3` (default: 3)
- **Max children**: `8` (default: 8)
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
MIN_CHILDREN = 3  (default 3)
MAX_CHILDREN = 8  (default 8)
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

### Phase 4: Create EPIC + Children

`ll-issues create` / `ll-issues scaffold-epic` (FEAT-2947) atomically handle ID allocation,
slugification, type-directory selection, template assembly, `parent:` frontmatter, and the
EPIC's `## Children` bullet — no prose ID/slug/filename templating is done by this skill
anymore.

#### Step 1: No learning tests (`LT_PROPOSALS` is empty) — one atomic call

Compose the full children array from Phase 2's selections and scaffold everything — EPIC plus
every implementation child — in a single, all-or-nothing call:

```bash
ll-issues scaffold-epic --title "[EPIC title]" --priority [PRIORITY] --stage --json \
  --children '[
    {"type": "FEAT", "title": "[child 1 title]", "priority": "P2", "summary": "[child 1 one-sentence summary]"},
    {"type": "ENH",  "title": "[child 2 title]", "priority": "P3", "summary": "[child 2 one-sentence summary]"}
  ]'
```

Parse the JSON result: `{"epic": {"id", "path"}, "children": [{"id", "path"}, ...]}` (children
in the same order given). `--stage` runs the equivalent of `git add` on the EPIC and every child
file in one call — no separate staging step. If any child write fails mid-call, `scaffold-epic`
unlinks every file it created in this call and re-raises — nothing partial is left behind.

Skip to Step 3 (Session Log) once this call succeeds.

#### Step 2: Learning tests needed (`LT_PROPOSALS` is non-empty) — sequential creates

Learning test sub-issue IDs must exist before implementation children can `depends_on` them, so
this path cannot use one atomic `scaffold-epic` call — create the EPIC, then each learning test
sub-issue, then each implementation child, each via `ll-issues create --parent EPIC_ID --stage`.

1. **Create the EPIC alone:**
   ```bash
   ll-issues create --type EPIC --title "[EPIC title]" --priority [PRIORITY] \
     --variant full --stage --json
   ```
   Store `EPIC_ID`/`EPIC_PATH` from the JSON `{"id", "path"}` result.

2. **For each proposal in `LT_PROPOSALS` (in order)**, create a learning test sub-issue wired to
   the EPIC — `--parent` writes `parent: EPIC_ID` and appends the EPIC's `## Children` bullet in
   the same call:
   ```bash
   ll-issues create --type ENH \
     --title "Explore and prove [package] API behavior" \
     --priority [EPIC_PRIORITY] --parent EPIC_ID --labels learning-tests \
     --body-file - --stage --json <<'EOF'
   Explore and prove `[package]` API behavior before implementing dependent epic children.

   Run `/ll:explore-api "[package]"` to build a proven record of this API surface.
   EOF
   ```
   `create`'s frontmatter surface doesn't cover `learning_tests_required` — use `Edit` to add
   `learning_tests_required: ["[package]"]` to the new file's frontmatter, then re-stage:
   `git add "[lt_path]"`. Store `LT_IDS[package] = ENH_ID` for step 3.

3. **For each selected implementation child (in order):**
   ```bash
   ll-issues create --type [TYPE] --title "[child title]" --priority [priority] \
     --parent EPIC_ID --body-file - --stage --json <<'EOF'
   [child one-sentence summary]
   EOF
   ```
   When `LT_IDS` is non-empty, use `Edit` to add `learning_tests_required: [<pkg1>, <pkg2>, ...]`
   (all packages in `UNPROVEN_PACKAGES`) and `depends_on: [ENH-NNN, ...]` (all learning test IDs
   from `LT_IDS`) to the child's frontmatter, then re-stage: `git add "[child_path]"`.

#### Step 3: Append session log entries

For the EPIC and every created child (learning test sub-issues and implementation children
alike):

```bash
ll-issues append-log <path-to-file> /ll:scope-epic
```

If `ll-issues` is not available, fall back to manually appending with **exactly** this format
(backticks required):
```
- `/ll:scope-epic` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

#### Step 4: Re-stage after the session-log append

`--stage` staged each file as it was created, but the Step 3 append-log edits land afterwards.
Re-stage every created path so the staged content matches the final file:

```bash
git add "{{config.issues.base_dir}}/epics/[epic_filename]"
git add "{{config.issues.base_dir}}/enhancements/[lt_filename]"  # repeat for each learning test sub-issue
git add "{{config.issues.base_dir}}/[category]/[child_filename]"  # repeat for each implementation child
```

---

### Phase 5: Post-write Consistency Check

`create`/`scaffold-epic` already guarantee `parent:` frontmatter and the EPIC's `## Children`
bullet for every child (Phase 4) — no manual wiring step is needed. This phase only re-verifies
after any Step 2 learning-test-path `Edit` (`learning_tests_required`/`depends_on` additions),
since those touch frontmatter outside the atomic create call:

For each child written via the learning-test path, confirm `parent:` and the child ID's presence
in the EPIC's `## Children` section are both still intact after the `Edit`. If either check
fails, emit a non-blocking warning (do not halt):

```
⚠ Post-write consistency check failed for CHILD_ID: parent: missing or child absent from ## Children
```

This inline validation substitutes for `ll-issues epic-consistency` until FEAT-2332 ships.

> **Note (ENH-162)**: child membership lives in `parent:` frontmatter, not in `relates_to:`. Never populate `relates_to:` with child IDs — containment is expressed via `parent:` only. `relates_to:` is reserved for peer/see-also cross-references between EPICs and sibling issues.

---

### Phase 6: Output Report

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
