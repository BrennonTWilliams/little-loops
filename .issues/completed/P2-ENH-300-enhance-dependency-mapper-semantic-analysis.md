---
discovered_date: 2026-02-09
discovered_by: user_feedback
---

# ENH-300: Enhance Dependency Mapper with Semantic Conflict Analysis

## Summary

Upgrade `/ll:map_dependencies` to detect semantic conflicts within shared files, enabling it to distinguish between safe parallel modifications (different sections) and true conflicts (same component/function) that require sequential execution.

## Context

Current `dependency_mapper.py:find_file_overlaps()` uses simple file overlap + priority-based ordering. When multiple issues at the same priority touch the same file, it falls back to arbitrary ID-based ordering and assumes they conflict.

**Real-world failure case**: Sprint with 5 Wave 2 issues touching `day-columns.tsx`:
- ENH-032 (empty state) and ENH-033 (header stats) touch **different sections** → should be **parallel** ✅
- FEAT-028 (drag), FEAT-030 (duplicate), FEAT-031 (star) all modify **activity card rendering** → should be **sequential** ❌

Current algorithm missed this distinction, allowed all 5 to run in Wave 2, causing merge conflicts.

## Current Pain Point

`find_file_overlaps()` in `dependency_mapper.py` treats all file overlaps at the same priority as conflicts, falling back to arbitrary ID-based ordering. This produces false-positive dependencies that prevent parallel execution of non-conflicting issues. In real sprints (e.g., 5 issues touching `day-columns.tsx`), issues modifying completely different sections are forced into sequential execution, significantly reducing throughput and increasing sprint duration.

## Scope Boundaries

- **In scope**: Semantic conflict scoring for `find_file_overlaps()`, enhanced reporting with conflict/parallel-safe sections, new extraction/scoring functions in `dependency_mapper.py`
- **Out of scope**: Changes to the `/ll:map-dependencies` skill workflow itself, modifications to `ll-parallel` or `ll-sprint` scheduling logic, AST-level code analysis, cross-file dependency tracking beyond file overlap

## Root Cause

**Lines 187-190 in `dependency_mapper.py`:**
```python
if (issue_a.priority_int, id_a) <= (issue_b.priority_int, id_b):
    target_id, source_id = id_a, id_b
```

Uses ID as tiebreaker at same priority, doesn't analyze semantic conflict.

## Proposed Solution

### Phase 1: Extract Semantic Context from Issues

When analyzing file overlaps, parse issue descriptions to identify:

1. **Component/Function targets** - extract what's being modified:
   - Regex patterns: `"modify X"`, `"add Y to Z"`, `"refactor the ABC"`
   - Section identifiers: `"in the header"`, `"activity card rendering"`, `"droppable body"`
   - Common patterns: Component names (PascalCase), function names, UI regions

2. **Modification type** - classify the change:
   - Structural: `"extract"`, `"split"`, `"create new component"`
   - Enhancement: `"add button"`, `"add field"`, `"add stats"`
   - Infrastructure: `"enable dragging"`, `"add event handler"`

### Phase 2: Semantic Conflict Scoring

For each pair of issues with file overlap, compute a **conflict score**:

```python
def compute_conflict_score(
    issue_a: IssueInfo,
    issue_b: IssueInfo,
    shared_files: set[str],
    issue_contents: dict[str, str],
) -> float:
    """
    Returns 0.0-1.0:
    - 1.0 = Definite conflict (same component, same modification type)
    - 0.5 = Possible conflict (same file, unclear if same section)
    - 0.0 = Likely safe (different sections/components in same file)
    """
    # Extract semantic targets from issue descriptions
    targets_a = extract_semantic_targets(issue_contents[issue_a.issue_id])
    targets_b = extract_semantic_targets(issue_contents[issue_b.issue_id])

    # Check for overlapping component/function references
    if targets_a & targets_b:
        return 1.0  # Same component → definite conflict

    # Check for section/region mentions
    sections_a = extract_section_mentions(issue_contents[issue_a.issue_id])
    sections_b = extract_section_mentions(issue_contents[issue_b.issue_id])

    if sections_a and sections_b and sections_a.isdisjoint(sections_b):
        return 0.0  # Different sections → likely safe

    # Default: file overlap but unclear semantic relationship
    return 0.5
```

### Phase 3: Enhanced Dependency Logic

Update `find_file_overlaps()`:

```python
# After computing file overlap
conflict_score = compute_conflict_score(issue_a, issue_b, overlap, issue_contents)

# Only propose dependency if conflict score > threshold (e.g., 0.4)
if conflict_score < 0.4:
    # Log: "Issues can likely be parallelized (different sections)"
    continue

# For conflicts at same priority, use additional heuristics:
if issue_a.priority_int == issue_b.priority_int:
    # Prefer infrastructure/structural changes before enhancements
    type_order = {"structural": 0, "infrastructure": 1, "enhancement": 2}
    type_a = classify_modification_type(issue_contents[id_a])
    type_b = classify_modification_type(issue_contents[id_b])

    if type_order[type_a] < type_order[type_b]:
        target_id, source_id = id_a, id_b
    elif type_order[type_a] > type_order[type_b]:
        target_id, source_id = id_b, id_a
    else:
        # Fall back to ID ordering, but flag as LOW CONFIDENCE
        confidence *= 0.5  # Reduce confidence score
```

### Phase 4: Enhanced Reporting

Update report output to show semantic reasoning:

```markdown
## Proposed Dependencies

| # | Source | Target | Reason | Conflict | Confidence | Rationale |
|---|--------|--------|--------|----------|------------|-----------|
| 1 | FEAT-031 | FEAT-028 | file_overlap | HIGH (same component: activity card) | 90% | Both modify activity card rendering in day-columns.tsx |
| 2 | FEAT-030 | FEAT-031 | file_overlap | HIGH (same component: activity card) | 90% | Both modify activity card rendering in day-columns.tsx |

## Parallel Execution Safe

| Issue A | Issue B | Shared Files | Reason |
|---------|---------|--------------|--------|
| ENH-032 | ENH-033 | day-columns.tsx | Different sections (empty state vs header) |
```

## Implementation Plan

### Step 1: Add Semantic Extraction Functions
- `extract_semantic_targets()` - find component/function references
- `extract_section_mentions()` - find UI region identifiers
- `classify_modification_type()` - structural/infrastructure/enhancement

**Location**: `scripts/little_loops/dependency_mapper.py`

### Step 2: Add Conflict Scoring
- `compute_conflict_score()` - 0.0-1.0 semantic conflict metric
- Add `conflict_score` field to `DependencyProposal` dataclass

### Step 3: Update `find_file_overlaps()`
- Replace simple priority comparison with conflict-aware logic
- Skip low-conflict pairs (< 0.4 threshold)
- Use modification type ordering at same priority
- Reduce confidence for arbitrary ID-based tiebreakers

### Step 4: Enhance Report Formatting
- Add "Conflict" column showing HIGH/MEDIUM/LOW
- Add "Parallel Execution Safe" section listing non-conflicting pairs
- Include semantic reasoning in rationale text

### Step 5: Add Tests
- Test fixture issues with different section mentions
- Test cases for parallel-safe detection
- Test conflict score edge cases
- Integration test with real sprint scenario

## Current Behavior

1. All file overlaps at same priority use ID-based ordering
2. No distinction between conflicting and non-conflicting modifications
3. Reports don't explain semantic reasoning
4. No way to identify parallel-safe pairs

## Expected Behavior

1. Semantic analysis detects when issues touch different sections of same file
2. Conflict scoring determines if dependency is actually needed
3. Low-conflict pairs are NOT proposed as dependencies (safe for parallel execution)
4. High-conflict pairs get sequential dependencies with semantic rationale
5. Reports include conflict level and explain reasoning
6. Parallel-safe pairs are explicitly identified

## Impact

- **Priority**: P2 (addresses critical sprint planning gap)
- **Effort**: Medium (3-4 new functions + updates to existing logic)
- **Risk**: Low (additive, doesn't change existing API)
- **Benefit**: Prevents false-positive dependencies, enables more parallelization

## Test Cases

```python
def test_different_sections_parallel_safe():
    """Issues modifying header vs body of same file should not block each other."""
    issue_a = "Add stats to day column header in day-columns.tsx"
    issue_b = "Add empty state to droppable body in day-columns.tsx"

    conflict = compute_conflict_score(issue_a, issue_b, {"day-columns.tsx"}, ...)
    assert conflict < 0.4  # Should be parallel-safe

def test_same_component_conflict():
    """Issues both modifying activity card rendering should block each other."""
    issue_a = "Add duplicate button to activity card in day-columns.tsx"
    issue_b = "Add star toggle to activity card in day-columns.tsx"

    conflict = compute_conflict_score(issue_a, issue_b, {"day-columns.tsx"}, ...)
    assert conflict > 0.8  # High conflict

def test_infrastructure_before_features():
    """Structural changes should block features that use them."""
    issue_a = "Extract activity-list.tsx component (P3)"
    issue_b = "Make activity cards draggable in activity-list.tsx (P3)"

    target, source = determine_dependency_direction(issue_a, issue_b)
    assert target == issue_a  # Extract blocks drag feature
```

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| implementation | scripts/little_loops/dependency_mapper.py:141-222 | `find_file_overlaps()` function to enhance |
| skill | skills/map-dependencies/SKILL.md | Skill workflow (no changes needed) |

## Labels

`enhancement`, `dependency-mapping`, `sprint-planning`, `semantic-analysis`

## Status

**Completed** | Created: 2026-02-09 | Completed: 2026-02-09 | Priority: P2

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-09
- **Status**: Completed

### Changes Made
- `scripts/little_loops/dependency_mapper.py`: Added semantic extraction functions (`_extract_semantic_targets`, `_extract_section_mentions`, `_classify_modification_type`), `compute_conflict_score()` function, `ParallelSafePair` dataclass, `conflict_score` field on `DependencyProposal`, updated `find_file_overlaps()` with conflict-aware logic and parallel-safe detection, updated `format_report()` with conflict column and parallel-safe section
- `scripts/tests/test_dependency_mapper.py`: Added `TestComputeConflictScore` (7 tests), `TestFindFileOverlapsSemanticAnalysis` (5 tests), `TestFormatReportConflictInfo` (4 tests), updated all existing tests for new return type

### Verification Results
- Tests: PASS (58/58 in module, 2639/2639 full suite)
- Lint: PASS
- Types: PASS
- Integration: PASS
