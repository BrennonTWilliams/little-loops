---
description: Refine issue files with codebase-driven research to fill knowledge gaps needed for implementation
argument-hint: "[issue-id]"
allowed-tools:
  - Read
  - Glob
  - Edit(.issues/**)
  - Task
  - Bash(git:*, ll-issues:*)
  - Bash(ll-history-context:*)
arguments:
  - name: issue_id
    description: Issue ID to refine (e.g., BUG-071, FEAT-225, ENH-042)
    required: true
  - name: flags
    description: "Optional flags: --auto (non-interactive), --dry-run (preview)"
    required: false
---

# Refine Issue

Enrich issue files with codebase-driven research findings. Unlike `/ll:format-issue` (which aligns structure) or `/ll:ready-issue` (which validates accuracy), this command **researches the codebase** to identify and fill knowledge gaps needed for successful implementation.

The core workflow: read the issue, research the codebase, identify what an implementer needs to know that isn't in the issue, then fill those gaps with actual findings (file paths, function signatures, behavioral analysis).

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Source dir**: `{{config.project.src_dir}}`
- **Status enum**: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled` — see `.claude/CLAUDE.md` § Issue File Format for full enum and forbidden synonyms.

## Arguments

$ARGUMENTS

- **issue_id** (required): Issue ID to refine (e.g., BUG-071, FEAT-225, ENH-042)

- **flags** (optional): Command behavior flags
  - `--auto` - Non-interactive mode: fill gaps with research findings without prompting
  - `--dry-run` - Preview what research would produce without modifying the issue file
  - `--gap-analysis` - Additive-only mode: inventory existing coverage, detect stale references and missing sections, apply only additive changes — never removes content (default for new runs)
  - `--full-rewrite` - Full-rewrite mode (legacy behavior): rewrites sections with research findings; use when you want a complete enrichment pass

## Process

### 0. Parse Flags

```bash
ISSUE_ID="${issue_id:-}"
FLAGS="${flags:-}"
AUTO_MODE=false
DRY_RUN=false
GAP_ANALYSIS=false
FULL_REWRITE=false

# Auto-enable auto mode in automation contexts
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${LL_NON_INTERACTIVE:-}" ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
if [[ "$FLAGS" == *"--gap-analysis"* ]]; then GAP_ANALYSIS=true; fi
if [[ "$FLAGS" == *"--full-rewrite"* ]]; then FULL_REWRITE=true; fi

if [[ -z "$ISSUE_ID" ]]; then
    echo "Error: issue_id is required"
    echo "Usage: /ll:refine-issue [ISSUE_ID] [--auto] [--dry-run]"
    exit 1
fi
```

### 1. Locate Issue File

```bash
# Support both issue ID and explicit file path
if [[ "$ISSUE_ID" == *"/"* ]] || [[ "$ISSUE_ID" == *.md ]]; then
    if [ -f "$ISSUE_ID" ]; then
        FILE="$ISSUE_ID"
    else
        echo "WARNING: File not found at path: $ISSUE_ID"
        echo "Falling back to ID search..."
    fi
fi

# Search for issue file by ID
if [ -z "$FILE" ]; then
    FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)
fi

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found"
    exit 1
fi
```

### 2. Analyze Issue Content

1. Read the issue file completely
2. Parse frontmatter (discovered_date, discovered_by, etc.)
3. Identify issue type from filename or ID prefix (BUG/FEAT/ENH/EPIC)
4. Extract existing sections and their content
5. **Extract key concepts** for research:
   - File paths mentioned or implied
   - Function/class/module names
   - Error messages or behavioral descriptions
   - Feature/component names
   - Configuration keys or CLI flags

### 2.5 — Query Historical Context

Run:

```bash
HIST=$(ll-history-context {{issue_id}} 2>/dev/null || true)
```

If `$HIST` is non-empty, include the output as a `## Historical Context` section in the prompt context for Step 5a gap-filling. Cap: already enforced by the CLI (5 rows max). If DB is missing or no matches, proceed without the section.

### 3. Research Codebase

Spawn parallel sub-agents to gather comprehensive context about the issue's subject matter.

**IMPORTANT**: Spawn all 3 agents in a SINGLE message with multiple Task tool calls.

#### Agent 1: codebase-locator

```
Use Task tool with subagent_type="ll:codebase-locator"

Prompt: Find all files related to this issue:

Issue: [ISSUE-ID] - [issue title]
Key concepts: [extracted concepts from Step 2]

Search for:
- Files mentioned or implied in the issue description
- Related components and dependencies
- Test files that cover affected code
- Configuration files that may be relevant
- Documentation that describes affected features

Return file paths grouped by category:
- Implementation files
- Test files
- Configuration
- Documentation
```

#### Agent 2: codebase-analyzer

```
Use Task tool with subagent_type="ll:codebase-analyzer"

Prompt: Analyze the current behavior related to this issue:

Issue: [ISSUE-ID] - [issue title]
Summary: [issue summary]

Analyze:
- Current behavior of the code described in the issue
- Data flow and integration points
- How the affected component connects to the rest of the system
- Any existing error handling or edge cases

Return analysis with specific file path and anchor references (e.g., function names, class names).
```

#### Agent 3: codebase-pattern-finder

```
Use Task tool with subagent_type="ll:codebase-pattern-finder"

Prompt: Find similar patterns and reusable code for this issue:

Issue: [ISSUE-ID] - [issue title]
Type: [BUG|FEAT|ENH|EPIC]

Search for:
- Similar fixes/features already in the codebase
- Established conventions for this type of change
- Test patterns to model after
- Existing utility functions and shared modules that could be reused
- Similar logic elsewhere that suggests consolidation

Return examples with file path and anchor references (e.g., function names, class names).
```

#### Wait for ALL agents to complete before proceeding.

### 4. Identify Knowledge Gaps

Using the research findings from Step 3, identify what information is **missing from the issue** that an implementer would need. This is **knowledge gap analysis**, not structural gap analysis.

A section can be "present" per the template but still lack the codebase-specific context an implementer needs.

#### Gap Categories by Issue Type

**For BUGs:**
| Knowledge Gap | What's Missing | Research Source |
|---------------|---------------|----------------|
| Root cause location | Which file and function/class contains the bug | codebase-analyzer |
| Affected code paths | What other code calls/depends on the buggy code | codebase-locator |
| Reproduction context | What conditions trigger the bug based on code analysis | codebase-analyzer |
| Test coverage | Which tests exist for affected code, what's untested | codebase-locator |
| Related fixes | Similar bugs fixed before — patterns to follow | codebase-pattern-finder |

**For FEATs:**
| Knowledge Gap | What's Missing | Research Source |
|---------------|---------------|----------------|
| Integration surface | Where the new feature connects to existing code | codebase-locator + analyzer |
| Existing patterns | How similar features are implemented in this codebase | codebase-pattern-finder |
| API conventions | How existing public interfaces are structured | codebase-pattern-finder |
| Test patterns | How similar features are tested | codebase-pattern-finder |
| Reusable code | Existing utilities/modules to leverage | codebase-pattern-finder |

**For ENHs:**
| Knowledge Gap | What's Missing | Research Source |
|---------------|---------------|----------------|
| Current implementation | How the code being enhanced currently works | codebase-analyzer |
| Refactoring surface | What needs to change and what can stay | codebase-analyzer |
| Consistency considerations | How nearby/similar code is structured | codebase-pattern-finder |
| Callers/dependents | What code uses the component being enhanced | codebase-locator |
| Existing abstractions | Shared code that already partially solves this | codebase-pattern-finder |

#### Gap Detection

For each knowledge gap category relevant to the issue type:
1. Check if the issue already contains this information (with specific file path and anchor references, not vague descriptions)
2. Check if the research findings provide this information
3. If the issue lacks it but research found it: mark as **FILLABLE**
4. If neither the issue nor research provides it: mark as **UNKNOWN** (requires interactive clarification)

### 5a. Fill Gaps with Research Findings (Auto Mode)

**Skip this section if**: `AUTO_MODE` is false (interactive mode uses Step 5b instead)

**Scope boundary**: Only use `Edit` to modify files under `.issues/`. If research reveals a missing implementation (code, tests, config), document it in the issue — write it as a gap finding under `## Codebase Research Findings`. Do NOT implement code, even when the gap is small and the implementation is obvious. The `Edit` tool is restricted to `.issues/**` by the command's allowed-tools; attempting to edit code files will fail.

For each **FILLABLE** gap, update the issue with research findings.

#### Enrichment Rules

**Integration Map** — populate with real findings:
```markdown
## Integration Map

### Files to Modify
- `path/to/file.py` — [what needs to change, from analyzer findings]
- `path/to/other.py` — [related change needed, from locator findings]

### Dependent Files (Callers/Importers)
- `path/to/caller.py:42` — calls `affected_function()` [from locator]
- `path/to/importer.py:5` — imports `affected_module` [from locator]

### Similar Patterns
- `path/to/similar.py:100` — similar implementation to follow [from pattern-finder]

### Tests
- `tests/test_affected.py` — existing test coverage [from locator]
- [Suggest new test file if none exists]

### Documentation
- `docs/relevant.md` — may need updates [from locator]

### Configuration
- [Config files if relevant, from locator]
```

**Root Cause** (BUG) — populate with analyzer findings:
```markdown
## Root Cause

- **File**: `path/to/buggy_file.py`
- **Anchor**: `in function problematic_func()`
- **Cause**: [Behavioral analysis from codebase-analyzer — what the code does wrong and why]
```

**Proposed Solution** — enrich with pattern-finder findings:
- If a Proposed Solution section exists but is vague, add a subsection with concrete implementation guidance based on similar patterns found
- If no Proposed Solution exists, add one based on how similar changes were made elsewhere

**Option-Count Detection (Auto Mode only)** — after writing to Proposed Solution:

Count distinct implementation options deposited. Detect by any of these patterns in the deposited content:
- Numbered approaches: top-level items `1. ...`, `2. ...` each describing a distinct approach
- Headed options: `### Option A`, `### Option B`, `### Option C` (etc.)
- Bold options: `**Option A**`, `**Option B**`, `**Option 1**`, `**Option 2**` (etc.)

Then update `decision_needed` in the issue's YAML frontmatter using the Edit tool (inline `---` block replacement, following `skills/confidence-check/SKILL.md` in section "Phase 4: Update Frontmatter"):
- If option count >= 2: set `decision_needed: true`
- If option count < 2: set `decision_needed: false` (or remove if absent — prevents stale `true` from a prior pass)

**Idempotency**: skip the write if `decision_needed` already has the same value (follow `skills/format-issue/SKILL.md` in section "2.5a. Testable Inference (doc-only detection)").
**Dry-run guard**: skip the frontmatter write in `--dry-run` mode; report what would have been set in the DRY RUN PREVIEW block.

**Implementation Steps** — make concrete with real file references:
```markdown
## Implementation Steps

1. [Phase based on actual code structure — e.g., "Modify `parser.py:parse_args()` to handle new flag"]
2. [Phase with real references — e.g., "Add test cases following pattern in `test_parser.py:TestFlagParsing`"]
3. [Verification — e.g., "Run `python -m pytest scripts/tests/test_parser.py -v`"]
```

#### Preservation Rule

**Do NOT overwrite non-empty sections** with >2 lines of meaningful text (not "TBD" or placeholders).

When a section already has meaningful content:
- **Append** research findings as a subsection or additional bullets, clearly marked
- **Do NOT replace** existing human-written or previously-refined content
- Use a marker to distinguish researched content:

```markdown
### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- [Finding 1 with file path and anchor reference]
- [Finding 2 with file path and anchor reference]
```

### 5b. Interactive Refinement (Skip in Auto Mode)

**Skip this entire section if `AUTO_MODE` is true.**

Present research findings and ask targeted questions informed by what was found in the codebase.

#### Research Summary

First, display a summary of what was discovered:

```
Research Findings for [ISSUE-ID]:
- Found [N] related files
- Identified [key integration points]
- Found [similar patterns at file in function/class anchor]
- [Key discovery from analysis]
```

#### Research-Informed Questions

Use AskUserQuestion with **maximum 4 questions per round**, prioritized by implementation importance.

Questions must reference specific codebase findings:

```yaml
questions:
  - question: "I found that `function_name()` at `file.py:42` handles this case. Is this the right place to make changes?"
    header: "Location"
    multiSelect: false
    options:
      - label: "Yes, modify there"
        description: "Change function_name() in file.py"
      - label: "No, different location"
        description: "I'll specify the correct location"

  - question: "There are 3 callers of `affected_function()`: caller_a.py:10, caller_b.py:25, caller_c.py:50. Should all be updated?"
    header: "Scope"
    multiSelect: true
    options:
      - label: "caller_a.py"
        description: "Updates the primary usage path"
      - label: "caller_b.py"
        description: "Updates the secondary usage path"
      - label: "caller_c.py"
        description: "Updates the test helper"

  - question: "Similar implementation exists at `pattern_file.py:100`. Should this follow the same pattern?"
    header: "Pattern"
    multiSelect: false
    options:
      - label: "Yes, follow existing pattern"
        description: "Consistent with codebase conventions"
      - label: "No, different approach"
        description: "I'll explain the preferred approach"
```

For **UNKNOWN** gaps (research didn't find enough), ask open-ended questions:

```yaml
  - question: "[Specific question about what couldn't be determined from code alone]"
    header: "Context"
    multiSelect: false
    options:
      - label: "[Option based on best guess from research]"
        description: "[What research suggests]"
      - label: "[Alternative interpretation]"
        description: "[Different approach]"
```

After gathering answers, update the issue file with both research findings and user-provided context.

### 5c. Gap-Analysis Mode (Skip Unless `--gap-analysis`)

**Skip this entire section if `GAP_ANALYSIS` is false.**

Gap-analysis mode performs additive-only enrichment — it never removes existing content. The core contract: "Gap-analysis never removes existing content — it only adds or enhances."

#### 1. Parse Existing Issue into Section Map

Extract all H2 sections from the issue file and catalog their content:
- Sections present: list of H2 headings found
- Sections with meaningful content (>2 lines, not placeholder text like "TBD" or "N/A")
- Sections that are empty or contain only boilerplate

Use the H2 extraction pattern from `scripts/little_loops/issue_history/doc_synthesis.py:_extract_section()`:
```python
# re.search(r"^##\s+heading", content, re.MULTILINE) then slice to next ##
```

#### 2. Check Each Section Against Codebase Reality

For each section type, verify against current codebase state:

**Integration Map checks:**
- Referenced files: do they exist on disk? Missing = high-priority gap.
- Stale anchor references: use `scripts/little_loops/issues/anchor_sweep.py:_sweep_file()` → `skipped_refs` to detect `file:N`-style anchors that no longer resolve.
- Missing callers: are there known callers of modified code not listed?

**Proposed Solution / Implementation Steps:**
- Anchor references still valid? (`_sweep_file()` → `skipped_refs`)
- Do Implementation Steps reference all files in the Integration Map?

**Acceptance Criteria:**
- Are there code paths identified during research that have no corresponding criterion?

#### 3. Score Gaps by Impact

Adopt the `"critical"/"high"/"medium"/"low"` priority model from `scripts/little_loops/issue_history/models.py:TestGap`:

| Gap Type | Priority |
|----------|----------|
| Referenced file doesn't exist on disk | high |
| Stale anchor reference (function/class gone) | medium |
| Implementation Step references file not in Integration Map | medium |
| Missing edge case in Acceptance Criteria | low |
| Required section empty or placeholder-only | medium |

#### 4. Present Gap Report

Display a prioritized gap table:

```
## Gap Analysis Report — [ISSUE-ID]

| Section | Gap | Priority | Suggestion |
|---------|-----|----------|------------|
| Integration Map | `path/to/file.py` does not exist | high | Remove or update path |
| Proposed Solution | `old_function()` not found | medium | Update anchor reference |
| Acceptance Criteria | Edge case X not covered | low | Add criterion for X |
```

If no gaps found, output:
```
✓ No gaps detected. Issue coverage is current.
```

If `AUTO_MODE` is true, proceed directly to application without prompting. Otherwise, present the gap report and confirm before applying.

#### 5. Apply Additive Changes Only

For each approved gap, use the Edit tool with append-only changes:

1. **Append** missing information to the relevant section using the `### Codebase Research Findings` subsection marker (same as Step 5a)
2. **Stale anchor repair**: when `_sweep_file()` returns a stale reference, append a warning note under the section containing it:
   ```
   > ⚠ Anchor `old_function:N` no longer resolves — verify against current codebase.
   ```
3. **Do NOT** replace any existing text block with more than 2 meaningful lines
4. **Do NOT** remove any existing content under any circumstance

**Gap-analysis and max_refine_count**: Gap-analysis runs (`--gap-analysis`) do NOT count against `max_refine_count` — they are additive-only, non-destructive, and designed for repeated iterative use. Only full-rewrite passes (`--full-rewrite` or the default non-flag mode) consume the refinement budget.

#### 6. Gap-Analysis Output

```
================================================================================
GAP ANALYSIS COMPLETE: [ISSUE-ID]
================================================================================

| Gap | Priority | Applied |
|-----|----------|---------|
| [gap 1] | [priority] | ✓ Appended to [Section] |
| [gap 2] | [priority] | ✓ Stale-anchor note added |

Sections preserved verbatim: [N]
Content added: [N] additions
Content removed: 0 (gap-analysis never removes)

Run /ll:ready-issue [ISSUE-ID] to validate.
================================================================================
```

### 6. Update Issue File

**Skip file modifications if `DRY_RUN` is true.**

1. Use Edit tool to add/update sections with research findings and user input
2. Preserve existing frontmatter
3. Preserve existing non-empty sections (append, don't replace)
4. Add new sections in appropriate locations following v2.0 template ordering
5. Ensure all added file paths and references are from actual research (no placeholders in auto mode)

### 7. Append Session Log

After updating the issue, use the Bash tool to append a session log entry:

```bash
ll-issues append-log <path-to-issue-file> /ll:refine-issue
```

If `ll-issues` is not available, fall back to manually appending with **exactly** this format (backticks required):

```
- `/ll:refine-issue` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

### 8. Output Report

```
================================================================================
ISSUE REFINED: [ISSUE-ID]
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH|EPIC]
- Title: [title]
- Mode: [Interactive | Auto] [--dry-run]

## RESEARCH SUMMARY
- Files discovered: [N]
- Integration points identified: [N]
- Similar patterns found: [N]
- Key finding: [most important discovery]

## KNOWLEDGE GAPS IDENTIFIED
| Gap | Status | Source |
|-----|--------|--------|
| [Gap 1] | FILLED — [brief description of finding] | [agent] |
| [Gap 2] | FILLED — [brief description of finding] | [agent] |
| [Gap 3] | UNKNOWN — [asked user / left for implementer] | — |

## SECTIONS ENRICHED
- **Integration Map**: Populated with [N] file paths and [N] callers
- **Root Cause**: Added file path and anchor reference and behavioral analysis [BUG only]
- **Implementation Steps**: Made concrete with [N] specific file references
- **[Other section]**: [What was added]

## SECTIONS PRESERVED
- **[Section]**: Existing content preserved (non-empty)
- **[Section]**: Existing content preserved

## DRY RUN PREVIEW [--dry-run only]
[Show exact enrichments that would be applied without applying them]
- Would add to Integration Map: [N] file paths
- Would update Root Cause with: [file path and anchor reference]
- Would enrich Implementation Steps with: [N] concrete references

## FILE STATUS
- [Modified | Not modified (--dry-run)]
- decision_needed: [true | false | not set | skipped (--dry-run)] [Auto mode only]

## NEXT STEPS
- If `decision_needed: true` was set (2+ options deposited): run `/ll:decide-issue [ID]` to select the best option before wiring
- Run `/ll:wire-issue [ID]` to add integration wiring (callers, entry points, test hooks)
- Run `/ll:ready-issue [ID]` to validate the enriched issue
- Run `/ll:manage-issue` to implement
- If `/ll:ready-issue` continues to score NOT_READY after 2+ refinement passes, run `/ll:issue-size-review [ID]` — a persistent readiness gap often means the issue is too large or poorly scoped, not just under-researched

================================================================================
```

---

## Examples

```bash
# Interactive refinement with codebase research
/ll:refine-issue FEAT-225

# Auto-refine with codebase research (non-interactive)
/ll:refine-issue BUG-042 --auto

# Dry-run to preview what research would produce
/ll:refine-issue ENH-015 --auto --dry-run

# Gap-analysis mode: additive-only, never removes content
/ll:refine-issue ENH-100 --gap-analysis

# Full-rewrite mode (legacy behavior, now explicit)
/ll:refine-issue ENH-100 --full-rewrite --auto
```

---

## Integration

### Pipeline Position

```
/ll:capture-issue → /ll:format-issue → /ll:refine-issue → /ll:decide-issue → /ll:wire-issue → /ll:ready-issue → /ll:manage-issue
```

- **Before**: `/ll:format-issue` — ensures structural template compliance
- **After**: `/ll:verify-issues` or `/ll:ready-issue` — validates accuracy and completeness

### Typical Workflows

**Interactive workflow** (developer preparing an issue):
```
/ll:capture-issue "description" → /ll:format-issue [ID] → /ll:refine-issue [ID] → /ll:ready-issue [ID]
```

**Automated workflow** (pipeline):
```
/ll:capture-issue → /ll:format-issue [ID] --auto → /ll:refine-issue [ID] --auto → /ll:ready-issue [ID]
```

### Key Differences from Related Commands

| Aspect | format-issue | refine-issue | ready-issue |
|--------|-------------|-------------|-------------|
| **Purpose** | Template alignment | Codebase research & enrichment | Validation & gatekeeping |
| **Gap type** | Structural (missing sections) | Knowledge (missing implementation context) | Accuracy (claims vs reality) |
| **Research** | None (text inference) | Always (core function) | Optional (--deep flag) |
| **Output** | Boilerplate/inferred text | Concrete file paths, signatures, analysis | Verdict + corrections |
