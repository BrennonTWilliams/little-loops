# FEAT-261: Issue Dependency Mapping — Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-261-issue-dependency-mapping.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

### Existing Dependency Infrastructure (FEAT-030)
The dependency execution infrastructure is mature and well-tested:
- `dependency_graph.py:20-319`: `DependencyGraph` dataclass with `from_issues()`, `get_ready_issues()`, `get_execution_waves()`, `topological_sort()`, `detect_cycles()`
- `issue_parser.py:362-445`: Parses `## Blocked By` / `## Blocks` sections from issue markdown via `_parse_section_items()`
- `issue_parser.py:123-185`: `IssueInfo` dataclass with `blocked_by: list[str]` and `blocks: list[str]` fields
- `issue_parser.py:469-521`: `find_issues()` collects all active issues across categories

### Consumers of Dependency Data
- `issue_manager.py:596-659`: `AutoManager` builds graph, uses `get_ready_issues()` for sequencing
- `cli.py:1760-1789`: `ll-sprint run` builds graph, generates waves for execution
- `cli.py:1459-1583`: `_render_execution_plan()` and `_render_dependency_graph()` for visualization

### Cross-Referencing Patterns Already in Codebase
- `issue_discovery.py:568-695`: `find_existing_issue()` with multi-pass matching (file path, title word overlap, content analysis)
- `issue_discovery.py`: Utility functions `_extract_words()`, `_calculate_word_overlap()`, `_extract_file_paths()`
- `issue_discovery.py:910-963`: `update_existing_issue()` for appending sections to issue files

### Integration Target Commands (Current State)
| Command | File | Current Dep Awareness | Integration Point |
|---------|------|----------------------|-------------------|
| `verify_issues` | `commands/verify_issues.md` | None | Step 2B — add dep validation pass |
| `create_sprint` | `commands/create_sprint.md` | Partial (Step 1.5.3 checks no blockers) | After Step 4 — show graph + warnings |
| `scan_codebase` | `commands/scan_codebase.md` | None | Step 3 — cross-ref during synthesis |
| `tradeoff_review_issues` | `commands/tradeoff_review_issues.md` | None | Phase 2 — add bottleneck scoring dimension |
| `ready_issue` | `commands/ready_issue.md` | None | Step 2 — check blocker completion |

### Skill Pattern
Skills live in `skills/<name>/SKILL.md` with YAML frontmatter (`description` with trigger keywords) + markdown body. Skills are prompt-only (no direct Python invocation) but can reference CLI tools and other tools. Existing examples: `issue-size-review`, `product-analyzer`, `analyze-history`.

## Desired End State

1. A new `/ll:map_dependencies` skill performs cross-issue dependency analysis and proposes relationships
2. A new Python module `dependency_mapper.py` provides the analysis engine (file overlap, validation, report generation)
3. Five existing commands have lightweight dependency integrations
4. All new code is tested

### How to Verify
- `python -m pytest scripts/tests/test_dependency_mapper.py` — new tests pass
- `python -m pytest scripts/tests/` — all existing tests still pass
- `ruff check scripts/` — no lint errors
- `python -m mypy scripts/little_loops/` — no type errors
- `/ll:map_dependencies` produces dependency report with proposed relationships
- Integration touches work in context of their parent commands

## What We're NOT Doing

- Not changing `dependency_graph.py` — it's execution infrastructure, stays unchanged
- Not adding a CLI tool (no `ll-deps` command) — this is a skill + Python module
- Not auto-writing dependencies without user confirmation — always interactive
- Not implementing semantic similarity analysis (NLP/embeddings) — too complex, low ROI; we rely on file overlap and structural analysis instead
- Deferring "component/module dependency" analysis (API interface tracking) — would require call graph analysis, out of scope
- Not adding config schema fields — no configuration needed for this feature

## Problem Analysis

Dependencies between issues are manually authored, which means:
1. Most issues have no dependency data, leading to conflicting parallel execution
2. Sprint creation lacks dependency context
3. New issues from scans are isolated with no cross-references
4. No validation of existing dependency references

## Solution Approach

### Part A: New Python Module (`dependency_mapper.py`)
A focused analysis engine alongside `dependency_graph.py`:
- **File overlap detection**: Extract file paths from issue content, find pairs with overlapping files
- **Dependency validation**: Check that `## Blocked By` refs exist, backlinks are symmetric, no cycles
- **Report generation**: Format proposed dependencies with rationale, render Mermaid diagram
- **Issue file updates**: Write `## Blocked By` / `## Blocks` sections with user confirmation

### Part B: New Skill (`map_dependencies`)
A multi-phase skill that orchestrates the analysis:
1. Discovery — load all active issues
2. Analysis — call dependency_mapper functions
3. Proposal — present findings with rationale
4. User confirmation — multi-select which to apply
5. Execution — write changes to issue files

### Part C: Five Integration Touches
Lightweight additions to existing commands (each 5-20 lines of prompt additions).

## Implementation Phases

### Phase 1: Python Module — `dependency_mapper.py`

#### Overview
Create the core analysis engine that discovers potential dependencies between issues.

#### Changes Required

**File**: `scripts/little_loops/dependency_mapper.py` [NEW]
**Purpose**: Cross-issue dependency analysis — discovery, validation, and report generation

```python
"""Cross-issue dependency discovery and mapping.

Analyzes active issues to discover potential dependencies based on
file overlap, priority/type relationships, and validates existing
dependency references.

Complements dependency_graph.py:
- dependency_graph.py = execution ordering (existing, unchanged)
- dependency_mapper.py = discovery and proposal of new relationships (new)
"""

@dataclass
class DependencyProposal:
    """A proposed dependency relationship between two issues."""
    source_id: str           # Issue that would be blocked
    target_id: str           # Issue that would block (blocker)
    reason: str              # "file_overlap", "priority_ordering", "existing_backlink"
    confidence: float        # 0.0-1.0
    rationale: str           # Human-readable explanation
    overlapping_files: list[str]  # Files in common (for file_overlap reason)

@dataclass
class ValidationResult:
    """Result of validating existing dependency references."""
    broken_refs: list[tuple[str, str]]         # (issue_id, missing_ref_id)
    missing_backlinks: list[tuple[str, str]]    # (issue_id, missing_backlink_from)
    cycles: list[list[str]]                     # From DependencyGraph.detect_cycles()
    stale_completed_refs: list[tuple[str, str]] # (issue_id, completed_ref_id)

@dataclass
class DependencyReport:
    """Complete dependency analysis report."""
    proposals: list[DependencyProposal]
    validation: ValidationResult
    issue_count: int
    existing_dep_count: int

# Core functions:
def extract_file_paths(content: str) -> set[str]
    """Extract file paths from issue content (Location section, code refs, inline paths)."""

def find_file_overlaps(issues: list[IssueInfo], config: BRConfig) -> list[DependencyProposal]
    """Find issues that reference overlapping files and propose dependencies."""

def validate_dependencies(issues: list[IssueInfo], config: BRConfig) -> ValidationResult
    """Validate existing dependency refs: check existence, backlinks, cycles."""

def analyze_dependencies(issues: list[IssueInfo], config: BRConfig) -> DependencyReport
    """Main entry point — run all analysis and return comprehensive report."""

def format_report(report: DependencyReport) -> str
    """Format report as human-readable markdown."""

def format_mermaid(issues: list[IssueInfo], proposals: list[DependencyProposal]) -> str
    """Generate Mermaid dependency graph diagram."""

def apply_proposals(proposals: list[DependencyProposal], config: BRConfig) -> list[str]
    """Write approved dependency proposals to issue files. Returns list of modified file paths."""
```

Key implementation details:

1. **`extract_file_paths(content)`**: Regex-based extraction of paths from:
   - `**File**: \`path/to/file.py\`` (Location section format)
   - Inline backtick paths matching `[a-zA-Z_][a-zA-Z0-9_/.-]+\.(py|ts|js|md|yaml|json|toml)`
   - Strips code fences first (reuse pattern from `issue_parser.py:350-359`)

2. **`find_file_overlaps(issues, config)`**: For each pair of issues:
   - Extract file paths from both issue contents (read files)
   - Compute intersection
   - If overlapping files > 0: propose dependency from lower-priority → higher-priority (or later ID → earlier ID at same priority)
   - Confidence = `len(overlap) / min(len(paths_a), len(paths_b))`
   - Skip pairs that already have a dependency relationship

3. **`validate_dependencies(issues, config)`**:
   - Build `DependencyGraph.from_issues(issues)` to detect cycles
   - For each issue's `blocked_by`: verify referenced ID exists as an active issue or completed issue
   - For each issue's `blocked_by`: verify the target issue has this issue in its `blocks` (backlink check)
   - Track `stale_completed_refs`: where a blocker is completed (dependency is satisfied)

4. **`apply_proposals(proposals, config)`**:
   - For each proposal, read the source issue file
   - If `## Blocked By` section exists, append new entry
   - If not, add `## Blocked By` section before `## Labels` or at end
   - Similarly update `## Blocks` on the target issue
   - Use read-modify-write pattern from `issue_discovery.py:910-963`

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_mapper.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_mapper.py`

---

### Phase 2: Tests for `dependency_mapper.py`

#### Overview
Comprehensive test suite following existing test patterns.

#### Changes Required

**File**: `scripts/tests/test_dependency_mapper.py` [NEW]

Test classes and key tests:

```python
class TestExtractFilePaths:
    """Tests for file path extraction from issue content."""
    def test_extract_from_location_section(self) -> None: ...
    def test_extract_inline_backtick_paths(self) -> None: ...
    def test_ignores_paths_in_code_fences(self) -> None: ...
    def test_empty_content(self) -> None: ...
    def test_deduplicates_paths(self) -> None: ...

class TestFindFileOverlaps:
    """Tests for file overlap detection between issues."""
    def test_no_overlap(self) -> None: ...
    def test_single_file_overlap(self) -> None: ...
    def test_multiple_file_overlap(self) -> None: ...
    def test_skips_existing_dependency(self) -> None: ...
    def test_priority_ordering(self) -> None: ...
    def test_confidence_calculation(self) -> None: ...

class TestValidateDependencies:
    """Tests for dependency reference validation."""
    def test_valid_dependencies(self) -> None: ...
    def test_broken_ref(self) -> None: ...
    def test_missing_backlink(self) -> None: ...
    def test_cycle_detection(self) -> None: ...
    def test_stale_completed_ref(self) -> None: ...

class TestAnalyzeDependencies:
    """Integration tests for full analysis pipeline."""
    def test_empty_issues(self) -> None: ...
    def test_full_analysis_with_overlaps_and_validation(self) -> None: ...

class TestFormatReport:
    """Tests for report formatting."""
    def test_format_with_proposals(self) -> None: ...
    def test_format_with_validation_issues(self) -> None: ...
    def test_format_empty_report(self) -> None: ...

class TestFormatMermaid:
    """Tests for Mermaid diagram generation."""
    def test_simple_graph(self) -> None: ...
    def test_graph_with_proposals(self) -> None: ...

class TestApplyProposals:
    """Tests for writing proposals to issue files."""
    def test_add_blocked_by_to_issue_without_section(self) -> None: ...
    def test_append_to_existing_blocked_by_section(self) -> None: ...
    def test_adds_backlink_blocks_section(self) -> None: ...
```

Use `tmp_path` fixture for file operations, `make_issue()` helper (pattern from `test_dependency_graph.py`).

**File**: `scripts/tests/fixtures/issues/feature-with-file-refs.md` [NEW]
Test fixture for an issue file with file path references in Location section.

**File**: `scripts/tests/fixtures/issues/enhancement-with-file-refs.md` [NEW]
Test fixture for a second issue file referencing overlapping files.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Existing tests still pass: `python -m pytest scripts/tests/ -v`

---

### Phase 3: Skill Definition — `/ll:map_dependencies`

#### Overview
Create the skill that orchestrates the dependency analysis workflow.

#### Changes Required

**File**: `skills/map-dependencies/SKILL.md` [NEW]
**Purpose**: Multi-phase skill for dependency discovery and mapping

```markdown
---
description: |
  Analyze active issues to discover cross-issue dependencies based on file overlap,
  validate existing dependency references, and propose new relationships.

  Trigger keywords: "map dependencies", "dependency mapping", "find dependencies",
  "dependency analysis", "issue dependencies", "cross-issue dependencies",
  "blocked by analysis", "discover dependencies"
---

# Map Dependencies Skill

[5-phase workflow:]

## Phase 1: Discovery
- Load all active issues using Glob + Read
- Parse issue metadata and content
- Optionally filter by --sprint [name] to scope to sprint issues

## Phase 2: Analysis
- Extract file paths from all issue content
- Find file overlaps between issue pairs
- Validate existing dependency references (broken refs, missing backlinks, cycles)
- Identify stale references to completed issues

## Phase 3: Report
- Present dependency report with:
  - Proposed new dependencies with rationale and confidence scores
  - Validation issues (broken refs, missing backlinks, cycles)
  - Mermaid dependency graph diagram
  - Summary statistics

## Phase 4: User Confirmation
- AskUserQuestion with multi-select for which proposals to apply
- Options: Apply all / Select individual / Skip all

## Phase 5: Execution
- Write approved proposals to issue files (## Blocked By / ## Blocks sections)
- Stage modified files with git add
- Show summary of changes made
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists and has valid YAML frontmatter
- [ ] Skill appears in `/ll:help` output

**Manual Verification**:
- [ ] Running `/ll:map_dependencies` produces a dependency report
- [ ] Proposed dependencies include rationale and confidence
- [ ] User can confirm/reject proposals before files are modified

---

### Phase 4: Integration — `verify_issues.md`

#### Overview
Add a dependency validation pass to the verification workflow.

#### Changes Required

**File**: `commands/verify_issues.md`
**Changes**: Add a new step 2.5 between existing Step 2 ("For Each Issue") and Step 3 ("Request User Approval")

Add after the "#### C. Determine Verdict" section (after line ~52):

```markdown
#### E. Validate Dependency References

For each issue, check dependency integrity:

1. **Blocked By references**: For each ID in `## Blocked By`:
   - Verify the referenced issue exists (in active issues or completed)
   - If in completed: note as "satisfied" (not an error, but informational)
   - If missing entirely: flag as BROKEN_REF

2. **Blocks backlinks**: For each ID in `## Blocked By`:
   - Check that the referenced issue has this issue in its `## Blocks` section
   - If missing: flag as MISSING_BACKLINK

3. **Cycle check**: After processing all issues, build a DependencyGraph and check for cycles

Add to the verdict table:
| DEP_ISSUES | Dependency references have problems (broken refs, missing backlinks, cycles) |

Add to the report:
### Dependency Issues
| Issue ID | Problem | Details |
|----------|---------|---------|
| FEAT-042 | BROKEN_REF | References nonexistent BUG-999 |
| BUG-015 | MISSING_BACKLINK | Blocked by FEAT-010, but FEAT-010 has no Blocks entry for BUG-015 |
| FEAT-020 → ENH-030 → FEAT-020 | CYCLE | Circular dependency detected |
```

#### Success Criteria

**Automated Verification**:
- [ ] `commands/verify_issues.md` is syntactically valid markdown
- [ ] Existing tests still pass: `python -m pytest scripts/tests/ -v`

---

### Phase 5: Integration — `ready_issue.md`

#### Overview
Add blocker-completion check to the readiness validation.

#### Changes Required

**File**: `commands/ready_issue.md`
**Changes**: Add dependency check to Step 2 "Validate Issue Content" (after line ~138)

Add a new subsection:

```markdown
#### Dependency Status
- [ ] If `## Blocked By` section exists:
  - Check each referenced issue ID
  - If any blocker is still in an active category (bugs/, features/, enhancements/) and NOT in completed/:
    - Flag as WARNING: "Blocked by [ID] which is still open"
  - If all blockers are in completed/ or don't exist:
    - Mark as PASS
- [ ] If `## Blocked By` section is empty or absent: PASS (no blockers)

**Note**: Open blockers are a WARNING, not a failure. The issue can still be marked READY
but the warning should be prominently displayed so the user is aware of open blockers.

Add to the VALIDATION table output:
| Blockers | PASS/WARN | "All blockers completed" or "Open blockers: FEAT-010, BUG-015" |
```

#### Success Criteria

**Automated Verification**:
- [ ] `commands/ready_issue.md` is syntactically valid markdown
- [ ] Existing tests still pass: `python -m pytest scripts/tests/ -v`

---

### Phase 6: Integration — `create_sprint.md`

#### Overview
Show dependency graph and warn about missing deps after issue selection.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: Add a new Step 4.5 between "Validate Issues Exist" (Step 4) and "Create Sprint Directory" (Step 5)

```markdown
### 4.5 Dependency Analysis for Sprint Issues

After validating that all issues exist, perform dependency analysis on the sprint issue set:

1. **Parse dependency sections** from all sprint issue files:
   - Read `## Blocked By` / `## Blocks` sections from each issue
   - Build a local dependency graph for just the sprint issues

2. **Check for issues blocked by non-sprint issues**:
   - For each sprint issue's `## Blocked By` entries:
     - If the blocker is NOT in the sprint issue set AND NOT completed:
       - Warn: "[ISSUE-ID] is blocked by [BLOCKER-ID] which is not in this sprint"
   - Present warnings to user if any found

3. **Show dependency structure** (if any dependencies exist within the sprint):
   - Display execution waves:
     ```
     Sprint Dependency Structure:
     Wave 1: FEAT-001, BUG-015 (no blockers)
     Wave 2: FEAT-020 (blocked by FEAT-001)
     Wave 3: ENH-030 (blocked by FEAT-020)
     ```
   - Note: This previews how `ll-sprint run` will execute the sprint

4. **Check for cycles** within the sprint issue set:
   - If cycles detected, warn and ask user to resolve before creating sprint

Continue to Step 5 regardless of warnings (unless cycles found).
```

#### Success Criteria

**Automated Verification**:
- [ ] `commands/create_sprint.md` is syntactically valid markdown
- [ ] Existing tests still pass: `python -m pytest scripts/tests/ -v`

---

### Phase 7: Integration — `scan_codebase.md`

#### Overview
Cross-reference new findings during synthesis to suggest dependencies.

#### Changes Required

**File**: `commands/scan_codebase.md`
**Changes**: Add dependency cross-referencing to Step 3 "Synthesize Findings" (after line ~183)

Add a new sub-step after "Assign globally unique sequential numbers":

```markdown
5. **Cross-reference for dependencies**: After assigning IDs to new findings:
   - For each new finding, extract the file path(s) from its Location
   - Compare against file paths in ALL existing active issues
   - If a new finding references files also referenced by an existing issue:
     - If existing issue is higher priority or more foundational: suggest new issue `blocked_by` existing
     - Add a `## Blocked By` section to the new issue with the suggestion
     - Add a comment: `<!-- Suggested by scan_codebase: file overlap with [file.py] -->`
   - This is a suggestion only — the dependency sections are created in the new issue files
   - Users can review and remove suggestions during the confirmation step (Step 4.5)
```

#### Success Criteria

**Automated Verification**:
- [ ] `commands/scan_codebase.md` is syntactically valid markdown
- [ ] Existing tests still pass: `python -m pytest scripts/tests/ -v`

---

### Phase 8: Integration — `tradeoff_review_issues.md`

#### Overview
Factor "blocking bottleneck" into scoring — issues that block many others score higher utility.

#### Changes Required

**File**: `commands/tradeoff_review_issues.md`
**Changes**: Add a 6th scoring dimension in Phase 2 subagent prompt (after line ~74)

Add to the evaluation dimensions:

```markdown
6. **Blocking bottleneck**: How many other issues depend on this one?
   - HIGH: Blocks 3+ other issues (critical bottleneck)
   - MEDIUM: Blocks 1-2 other issues
   - LOW: Blocks no other issues

   To determine this:
   - Read all active issue files and check their `## Blocked By` sections
   - Count how many issues reference this issue ID in their `## Blocked By`
   - Issues that block many others have higher effective utility regardless of their standalone value
```

Update the subagent return format to include `blocking: [LOW/MEDIUM/HIGH]`.

Update the summary tables in Phase 4 to include the Blocking column.

Update the recommendation logic:
```markdown
**Adjusted recommendation**: If an issue scores HIGH on blocking (it blocks 3+ issues),
boost its recommendation by one tier:
- Close/Defer with HIGH blocking → Update first (it unblocks others)
- Update first with HIGH blocking → Implement (it unblocks others)
```

#### Success Criteria

**Automated Verification**:
- [ ] `commands/tradeoff_review_issues.md` is syntactically valid markdown
- [ ] Existing tests still pass: `python -m pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests (Phase 2)
- `test_dependency_mapper.py`: ~25 tests covering all public functions
- File path extraction: Location section, inline paths, code fence exclusion
- File overlap detection: no overlap, single/multi overlap, existing dep skip, confidence calc
- Validation: broken refs, missing backlinks, cycles, stale refs
- Report formatting and Mermaid generation
- Apply proposals: add new section, append to existing, backlink creation

### Integration Tests (Phase 2)
- Full `analyze_dependencies()` pipeline with realistic issue sets
- `apply_proposals()` with actual file I/O via `tmp_path`
- Roundtrip: create issues → analyze → apply → re-analyze shows no new proposals

### Existing Test Regression
- All existing tests in `scripts/tests/` must continue to pass
- No changes to existing modules means low regression risk

## References

- Original issue: `.issues/features/P2-FEAT-261-issue-dependency-mapping.md`
- Existing dependency graph: `scripts/little_loops/dependency_graph.py:20-319`
- Issue parser (dep sections): `scripts/little_loops/issue_parser.py:362-445`
- Issue discovery (cross-ref patterns): `scripts/little_loops/issue_discovery.py:568-695`
- File update pattern: `scripts/little_loops/issue_discovery.py:910-963`
- Skill template: `skills/issue-size-review/SKILL.md`
- Test pattern: `scripts/tests/test_dependency_graph.py`
- FEAT-030 completed issue: `.issues/completed/P2-FEAT-030-issue-dependency-parsing-and-graph.md`
