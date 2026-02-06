# ENH-260: Fix align_issues Workflow and Argument Handling - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-260-fix-align-issues-workflow-and-argument-handling.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: fix

## Current State Analysis

### Key Discoveries
- `commands/capture_issue.md:368` and `:420` both contain incorrect placeholder text referencing `/ll:align_issues` for document discovery
- `commands/align_issues.md:4-6` defines `category` as `required: true` — no way to run without an argument
- `commands/align_issues.md:67-77` parses arguments with no default/fallback for missing category
- `commands/normalize_issues.md:249-298` (Section 7b) already handles document linking/discovery — this is the correct tool to reference
- `commands/capture_issue.md:439-496` (Phase 4b) also does document linking at capture time

### Patterns
- Arguments are defined in YAML frontmatter with `required: true/false`
- Argument parsing uses bash-style variable expansion: `${category}`, `${flags:-}`
- The command already checks for `--all` as a special category value (line 82)

## Desired End State

1. `capture_issue.md` placeholder text references `/ll:normalize_issues` instead of `/ll:align_issues`
2. `align_issues.md` supports three argument modes:
   - **No argument**: Check each active issue against its own linked Key Documents
   - **Document path** (contains `.md` or `/`): Check all active issues against that specific document
   - **Category / `--all`**: Existing behavior unchanged

### How to Verify
- Read modified files and confirm placeholder text is correct
- Read align_issues.md and confirm argument is optional with three modes documented
- Lint passes

## What We're NOT Doing

- Not modifying Python code — these are markdown command files only
- Not changing normalize_issues.md — it already works correctly
- Not fixing existing issue files that contain the old placeholder text (those will be corrected when `/ll:normalize_issues` runs)
- Not adding new test files — these are prompt-based commands, not executable code

## Implementation Phases

### Phase 1: Fix capture_issue.md Placeholder Text

#### Overview
Change two occurrences of incorrect guidance from referencing `/ll:align_issues` to `/ll:normalize_issues`.

#### Changes Required

**File**: `commands/capture_issue.md`

**Line 368** (minimal template):
```
OLD: _No documents linked. Run `/ll:align_issues` to discover relevant docs._
NEW: _No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._
```

**Line 420** (full template):
```
OLD: _No documents linked. Run `/ll:align_issues` to discover relevant docs._
NEW: _No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._
```

#### Success Criteria
- [ ] Both occurrences updated
- [ ] No other references to align_issues for document discovery remain in capture_issue.md

### Phase 2: Update align_issues.md Argument Handling

#### Overview
Make the `category` argument optional and add support for three argument modes: no-arg (linked docs), document path, and category (existing).

#### Changes Required

**File**: `commands/align_issues.md`

**2a. Frontmatter (lines 3-6)**: Change `category` from required to optional, update description:
```yaml
  - name: category
    description: "Document category, document path (.md), or omit to check linked docs. Use --all for all categories."
    required: false
```

**2b. Arguments documentation (lines 55-59)**: Add the new modes:
```markdown
- **category** (optional): What to align against
  - *(omitted)* - Check each issue against its own linked Key Documents
  - `path/to/doc.md` - Check all issues against a specific document file
  - `architecture` - Check alignment with architecture/design documents
  - `product` - Check alignment with product/goals documents
  - `--all` - Check all configured categories
  - Any custom category name defined in config
```

**2c. Parse Arguments section (lines 67-77)**: Add mode detection logic:
```bash
CATEGORY="${category:-}"
FLAGS="${flags:-}"
VERBOSE=false
DRY_RUN=false

if [[ "$FLAGS" == *"--verbose"* ]]; then VERBOSE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi

# Determine mode
if [[ -z "$CATEGORY" ]]; then
  MODE="linked-docs"
elif [[ "$CATEGORY" == *.md || "$CATEGORY" == */* ]]; then
  MODE="specific-doc"
elif [[ "$CATEGORY" == "--all" ]]; then
  MODE="all-categories"
else
  MODE="category"
fi
```

**2d. Load Document Categories section (lines 79-100)**: Add mode-specific behavior:

Replace lines 79-100 with logic that handles three modes:

- **MODE=linked-docs**: Skip category loading; documents will be resolved per-issue from their "Related Key Documentation" section
- **MODE=specific-doc**: Verify the specified document file exists and read it; do not look up categories
- **MODE=category / all-categories**: Existing behavior unchanged

**2e. Per-issue analysis (lines 126-196)**: Add linked-docs mode behavior:

For MODE=linked-docs:
- Read each issue's "Related Key Documentation" section
- If the issue has no linked documents, report: `Skipped: No linked documents — run /ll:normalize_issues first`
- For each linked document, perform the existing alignment check (step 5D)
- Skip the relevance check (step 5B) and missing doc check (step 5C) since we're only checking what's already linked

For MODE=specific-doc:
- Use the single specified document for all alignment checks
- Skip relevance check and missing doc check
- Run alignment check against the specified document for every active issue

**2f. Examples section (lines 328-348)**: Add new usage examples:
```bash
# Check each issue against its own linked documents (default)
/ll:align_issues

# Check all issues against a specific document
/ll:align_issues docs/ARCHITECTURE.md

# Existing: Check by category with auto-fix
/ll:align_issues architecture

# Existing: Check all categories
/ll:align_issues --all
```

#### Success Criteria
- [ ] `category` argument is `required: false` in frontmatter
- [ ] Three modes documented in Arguments section
- [ ] Mode detection logic present in Parse Arguments
- [ ] Load Document Categories handles all three modes
- [ ] Per-issue analysis handles linked-docs and specific-doc modes
- [ ] Examples show all usage modes
- [ ] Existing category and --all behavior unchanged

### Phase 3: Verify

- [ ] Read both files and confirm changes are correct
- [ ] Run lint: `ruff check scripts/`
- [ ] Run tests: `python -m pytest scripts/tests/`

## References

- Issue: `.issues/enhancements/P3-ENH-260-fix-align-issues-workflow-and-argument-handling.md`
- capture_issue placeholder: `commands/capture_issue.md:368,420`
- align_issues frontmatter: `commands/align_issues.md:3-6`
- align_issues argument parsing: `commands/align_issues.md:67-77`
- normalize_issues Section 7b: `commands/normalize_issues.md:249-298`
