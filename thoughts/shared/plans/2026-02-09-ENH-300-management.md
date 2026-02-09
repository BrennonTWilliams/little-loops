# ENH-300: Enhance Dependency Mapper with Semantic Conflict Analysis - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-300-enhance-dependency-mapper-semantic-analysis.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: implement

## Current State Analysis

### Key Discoveries
- `find_file_overlaps()` at `dependency_mapper.py:141-222` uses pure file-path set intersection to detect overlap, then orders by `(priority_int, id)` tuple — no semantic analysis
- `DependencyProposal` at `dependency_mapper.py:42-60` has no `conflict_score` field; `confidence` represents file overlap ratio, not semantic conflict
- `extract_file_paths()` at `dependency_mapper.py:107-138` strips code fences and uses 3 regex patterns — well-tested with 8 tests
- `format_report()` at `dependency_mapper.py:306-381` uses `list[str]` accumulator pattern with markdown tables — needs new "Conflict" column and "Parallel Safe" section
- Existing patterns to reuse:
  - `SCOPE_PATTERN` in `file_hints.py:29` already extracts component/module references
  - `VERB_CLASSES` dict-of-sets pattern in `workflow_sequence_analyzer.py:56-63` for modification type classification
  - Weighted multi-signal scoring pattern in `workflow_sequence_analyzer.py:294-338`
  - `_extract_words()` with stopwords in `issue_discovery.py:162-201`

### Patterns to Follow
- Module-level compiled regexes with `_` prefix (e.g., `_BACKTICK_PATH`, `_CODE_FENCE`)
- Functions organized: constants → dataclasses → extraction → analysis → orchestrator → formatters → mutation → private helpers
- Google-style docstrings with Args/Returns sections
- Test classes per public function with `=====` separator headers
- `make_issue()` helper already in test file for creating test fixtures

### Reusable Code
- `file_hints.py:SCOPE_PATTERN` — extend with PascalCase component names and UI region patterns
- `workflow_sequence_analyzer.py:VERB_CLASSES` — create similar dict-of-sets for modification type taxonomy
- `workflow_sequence_analyzer.py:semantic_similarity()` — follow weighted multi-signal pattern for `compute_conflict_score()`
- `issue_discovery.py:_extract_words()` — copy stopword-filtering word extraction pattern

### Potential Concerns
- Semantic extraction is inherently heuristic — false positives/negatives are expected
- The 0.4 conflict threshold from the issue is a reasonable starting default but may need tuning
- Issue content quality varies — some issues have rich section mentions, others are terse

## Desired End State

After implementation:
1. `find_file_overlaps()` computes a semantic conflict score for each file-overlapping pair
2. Pairs with conflict score < 0.4 are NOT proposed as dependencies (parallel-safe)
3. `DependencyProposal` includes a `conflict_score` field
4. Report output shows conflict level (HIGH/MEDIUM/LOW) and a "Parallel Execution Safe" section
5. At same priority, modification type ordering (structural → infrastructure → enhancement) replaces arbitrary ID ordering

### How to Verify
- Existing tests continue passing (no regression)
- New tests cover: parallel-safe detection, same-component conflict, modification type ordering, extraction functions
- `format_report()` output includes conflict column and parallel-safe section

## What We're NOT Doing

- Not modifying the `/ll:map-dependencies` skill workflow (`SKILL.md`) — out of scope per issue
- Not changing `ll-parallel` or `ll-sprint` scheduling logic
- Not implementing AST-level code analysis
- Not tracking cross-file dependencies beyond file overlap
- Not modifying `apply_proposals()` or `_add_to_section()` — they handle writing, not scoring
- Not changing the `DependencyReport` dataclass (parallel-safe pairs are reported via format_report logic)

## Problem Analysis

When multiple issues touch the same file at the same priority level, `find_file_overlaps()` creates dependency proposals for all pairs using ID-based ordering. It cannot distinguish between issues modifying different sections (safe to parallelize) and issues modifying the same component (true conflicts). This produces false-positive dependencies that prevent parallel execution.

## Solution Approach

Add three new extraction functions and one scoring function to `dependency_mapper.py`, then integrate the conflict score into `find_file_overlaps()` to filter low-conflict pairs and improve ordering. Update `format_report()` to display conflict information and identify parallel-safe pairs.

## Code Reuse & Integration

- **Reusable existing code**: Follow `VERB_CLASSES` dict-of-sets pattern from `workflow_sequence_analyzer.py:56`; follow weighted scoring pattern from `workflow_sequence_analyzer.py:294`
- **Patterns to follow**: Module-level compiled regex with `_` prefix, `frozenset` for keyword sets, `list[str]` accumulator for report formatting
- **New code justification**: Semantic target extraction and conflict scoring are domain-specific to dependency mapping — no existing utility covers this. The extraction regexes and keyword sets are specific to issue content analysis.

## Implementation Phases

### Phase 1: Add Semantic Extraction Functions

#### Overview
Add three new private extraction functions and module-level constants to `dependency_mapper.py` for extracting semantic targets, section mentions, and modification types from issue content.

#### Changes Required

**File**: `scripts/little_loops/dependency_mapper.py`
**Changes**: Add module-level constants and three extraction functions after the existing `extract_file_paths()` function (after line 138).

1. **Module-level constants** (after line 39, before the dataclasses):

```python
# Semantic target extraction patterns
_PASCAL_CASE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b")
_FUNCTION_REF = re.compile(r"`(\w+)\(\)`")
_COMPONENT_SCOPE = re.compile(
    r"(?:component|module|class|widget|section)[:\s]+[`\"']?([a-zA-Z0-9_./\-]+)[`\"']?",
    re.IGNORECASE,
)

# UI region / section keywords
_SECTION_KEYWORDS: dict[str, frozenset[str]] = {
    "header": frozenset({"header", "heading", "title bar", "top bar", "nav", "navbar", "toolbar"}),
    "body": frozenset({"body", "content", "main", "droppable", "list", "table", "grid"}),
    "footer": frozenset({"footer", "bottom", "status bar", "action bar"}),
    "sidebar": frozenset({"sidebar", "side panel", "drawer", "menu"}),
    "card": frozenset({"card", "tile", "item", "row", "entry"}),
    "modal": frozenset({"modal", "dialog", "popup", "overlay", "sheet"}),
    "form": frozenset({"form", "input", "field", "editor", "picker"}),
}

# Modification type classification keywords
_MODIFICATION_TYPES: dict[str, frozenset[str]] = {
    "structural": frozenset({
        "extract", "split", "refactor", "restructure", "reorganize",
        "create new component", "break out", "separate", "decompose",
    }),
    "infrastructure": frozenset({
        "enable", "hook", "handler", "event", "listener", "provider",
        "context", "store", "state management", "routing", "middleware",
        "dragging", "drag", "drop", "dnd",
    }),
    "enhancement": frozenset({
        "add button", "add field", "add column", "add stats", "add icon",
        "add toggle", "display", "show", "render", "style", "format",
        "empty state", "placeholder", "tooltip", "badge",
    }),
}
```

2. **Extraction functions** (after `extract_file_paths()`, before `find_file_overlaps()`):

```python
def _extract_semantic_targets(content: str) -> set[str]:
    """Extract component and function references from issue content.

    Identifies PascalCase component names, function references,
    and explicitly mentioned component/module scopes.

    Args:
        content: Issue file content

    Returns:
        Set of normalized semantic target names
    """
    if not content:
        return set()

    stripped = _CODE_FENCE.sub("", content)
    targets: set[str] = set()

    for match in _PASCAL_CASE.finditer(stripped):
        targets.add(match.group(1).lower())

    for match in _FUNCTION_REF.finditer(stripped):
        targets.add(match.group(1).lower())

    for match in _COMPONENT_SCOPE.finditer(stripped):
        targets.add(match.group(1).lower())

    return targets


def _extract_section_mentions(content: str) -> set[str]:
    """Extract UI region/section references from issue content.

    Maps keywords like "header", "body", "sidebar" to canonical
    section names using keyword sets.

    Args:
        content: Issue file content

    Returns:
        Set of canonical section names mentioned
    """
    if not content:
        return set()

    content_lower = content.lower()
    sections: set[str] = set()

    for section_name, keywords in _SECTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in content_lower:
                sections.add(section_name)
                break

    return sections


def _classify_modification_type(content: str) -> str:
    """Classify the modification type of an issue.

    Returns one of: "structural", "infrastructure", "enhancement".
    Falls back to "enhancement" if no clear match.

    Args:
        content: Issue file content

    Returns:
        Modification type classification string
    """
    if not content:
        return "enhancement"

    content_lower = content.lower()

    # Check structural first (highest priority for ordering)
    for mod_type in ("structural", "infrastructure", "enhancement"):
        keywords = _MODIFICATION_TYPES[mod_type]
        for keyword in keywords:
            if keyword in content_lower:
                return mod_type

    return "enhancement"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_mapper.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_mapper.py`

---

### Phase 2: Add Conflict Scoring and Update DependencyProposal

#### Overview
Add `conflict_score` field to `DependencyProposal` and implement `compute_conflict_score()` function that combines semantic target overlap, section overlap, and modification type signals.

#### Changes Required

**File**: `scripts/little_loops/dependency_mapper.py`

1. **Update `DependencyProposal`** — add `conflict_score` field with default:

```python
@dataclass
class DependencyProposal:
    """A proposed dependency relationship between two issues.

    Attributes:
        source_id: Issue that would be blocked
        target_id: Issue that would block (the blocker)
        reason: Category of discovery method
        confidence: Score from 0.0 to 1.0
        rationale: Human-readable explanation
        overlapping_files: Files referenced by both issues
        conflict_score: Semantic conflict score from 0.0 to 1.0
    """

    source_id: str
    target_id: str
    reason: str
    confidence: float
    rationale: str
    overlapping_files: list[str] = field(default_factory=list)
    conflict_score: float = 0.5
```

2. **Add `compute_conflict_score()`** (after `_classify_modification_type()`, before `find_file_overlaps()`):

```python
def compute_conflict_score(
    content_a: str,
    content_b: str,
) -> float:
    """Compute semantic conflict score between two issues.

    Combines three signals:
    - Semantic target overlap (component/function names): weight 0.5
    - Section mention overlap (UI regions): weight 0.3
    - Modification type match: weight 0.2

    Args:
        content_a: First issue's file content
        content_b: Second issue's file content

    Returns:
        Conflict score from 0.0 (parallel-safe) to 1.0 (definite conflict)
    """
    targets_a = _extract_semantic_targets(content_a)
    targets_b = _extract_semantic_targets(content_b)

    sections_a = _extract_section_mentions(content_a)
    sections_b = _extract_section_mentions(content_b)

    type_a = _classify_modification_type(content_a)
    type_b = _classify_modification_type(content_b)

    # Signal 1: Semantic target overlap (0.0 - 1.0)
    if targets_a and targets_b:
        target_intersection = len(targets_a & targets_b)
        target_union = len(targets_a | targets_b)
        target_score = target_intersection / target_union if target_union > 0 else 0.0
    else:
        target_score = 0.5  # Unknown — default to moderate

    # Signal 2: Section overlap (0.0 or 1.0)
    if sections_a and sections_b:
        if sections_a & sections_b:
            section_score = 1.0  # Same sections
        else:
            section_score = 0.0  # Different sections
    else:
        section_score = 0.5  # Unknown

    # Signal 3: Modification type match (0.0 or 1.0)
    type_score = 1.0 if type_a == type_b else 0.0

    # Weighted combination
    return round(target_score * 0.5 + section_score * 0.3 + type_score * 0.2, 2)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_mapper.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_mapper.py`

---

### Phase 3: Update `find_file_overlaps()` with Conflict-Aware Logic

#### Overview
Integrate conflict scoring into the overlap detection loop. Skip low-conflict pairs (< 0.4), use modification type for ordering at same priority, and reduce confidence for arbitrary tiebreakers.

#### Changes Required

**File**: `scripts/little_loops/dependency_mapper.py`
**Changes**: Modify the inner loop of `find_file_overlaps()` (lines 177-218).

The updated logic inside the pairwise loop (after overlap detection and before proposal creation):

```python
            # Compute semantic conflict score
            content_a = issue_contents.get(id_a, "")
            content_b = issue_contents.get(id_b, "")
            conflict = compute_conflict_score(content_a, content_b)

            # Skip low-conflict pairs (different sections of same file)
            if conflict < 0.4:
                parallel_safe.append((id_a, id_b, overlap, conflict))
                continue

            # Determine direction: higher priority (lower number) blocks lower priority
            issue_a = next(iss for iss in issues if iss.issue_id == id_a)
            issue_b = next(iss for iss in issues if iss.issue_id == id_b)

            if issue_a.priority_int != issue_b.priority_int:
                # Different priorities: higher priority blocks lower
                if issue_a.priority_int < issue_b.priority_int:
                    target_id, source_id = id_a, id_b
                else:
                    target_id, source_id = id_b, id_a
            else:
                # Same priority: use modification type ordering
                _type_order = {"structural": 0, "infrastructure": 1, "enhancement": 2}
                type_a = _classify_modification_type(content_a)
                type_b = _classify_modification_type(content_b)
                order_a = _type_order.get(type_a, 2)
                order_b = _type_order.get(type_b, 2)

                if order_a != order_b:
                    if order_a < order_b:
                        target_id, source_id = id_a, id_b
                    else:
                        target_id, source_id = id_b, id_a
                else:
                    # Fall back to ID ordering with reduced confidence
                    if id_a < id_b:
                        target_id, source_id = id_a, id_b
                    else:
                        target_id, source_id = id_b, id_a
                    confidence_modifier = 0.5
```

Also:
- Add `parallel_safe: list[tuple[str, str, set[str], float]] = []` before the loop
- Return both proposals and parallel_safe pairs (via the function return)
- Update the function signature to return a tuple: `tuple[list[DependencyProposal], list[tuple[str, str, set[str], float]]]`

**Wait — this would break the existing API**. Instead, store `parallel_safe` on the report level. Better approach: keep `find_file_overlaps()` returning `list[DependencyProposal]` but also collect parallel-safe pairs. We can store parallel-safe pairs separately in `DependencyReport`.

**Revised approach**: Add a `parallel_safe` field to `DependencyReport` and have `find_file_overlaps()` return a tuple internally, but wrap it in `analyze_dependencies()`.

Actually, the cleanest approach: add a `ParallelSafePair` dataclass and return both from `find_file_overlaps()`.

```python
@dataclass
class ParallelSafePair:
    """A pair of issues that share files but can safely run in parallel.

    Attributes:
        issue_a: First issue ID
        issue_b: Second issue ID
        shared_files: Files referenced by both issues
        conflict_score: Semantic conflict score (< 0.4)
        reason: Why these are parallel-safe
    """

    issue_a: str
    issue_b: str
    shared_files: list[str] = field(default_factory=list)
    conflict_score: float = 0.0
    reason: str = ""
```

Update `find_file_overlaps()` signature:
```python
def find_file_overlaps(
    issues: list[IssueInfo],
    issue_contents: dict[str, str],
) -> tuple[list[DependencyProposal], list[ParallelSafePair]]:
```

Update `DependencyReport`:
```python
@dataclass
class DependencyReport:
    proposals: list[DependencyProposal] = field(default_factory=list)
    parallel_safe: list[ParallelSafePair] = field(default_factory=list)
    validation: ValidationResult = field(default_factory=ValidationResult)
    issue_count: int = 0
    existing_dep_count: int = 0
```

Update `analyze_dependencies()` to unpack the tuple.

#### Success Criteria

**Automated Verification**:
- [ ] All existing tests still pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_mapper.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_mapper.py`

---

### Phase 4: Update Report Formatting

#### Overview
Add "Conflict" column to the proposals table and add a new "Parallel Execution Safe" section to `format_report()`.

#### Changes Required

**File**: `scripts/little_loops/dependency_mapper.py`

1. **Update proposals table** in `format_report()`:

Change header from:
```
| # | Source (blocked) | Target (blocker) | Reason | Confidence | Rationale |
```
To:
```
| # | Source (blocked) | Target (blocker) | Reason | Conflict | Confidence | Rationale |
```

Add conflict level display: `HIGH` (>= 0.7), `MEDIUM` (>= 0.4), `LOW` (< 0.4).

2. **Add parallel-safe section** after proposals section:

```python
    if report.parallel_safe:
        lines.append("## Parallel Execution Safe")
        lines.append("")
        lines.append("| Issue A | Issue B | Shared Files | Conflict Score | Reason |")
        lines.append("|---------|---------|--------------|---------------|--------|")
        for pair in report.parallel_safe:
            files_str = ", ".join(pair.shared_files[:3])
            if len(pair.shared_files) > 3:
                files_str += " and more"
            lines.append(
                f"| {pair.issue_a} | {pair.issue_b} | "
                f"{files_str} | {pair.conflict_score:.0%} | {pair.reason} |"
            )
        lines.append("")
```

3. **Update summary stats** to include parallel-safe count:
```python
    lines.append(f"- **Parallel-safe pairs**: {len(report.parallel_safe)}")
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_mapper.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_mapper.py`

---

### Phase 5: Add Tests

#### Overview
Add comprehensive tests for all new functions and updated behavior.

#### Changes Required

**File**: `scripts/tests/test_dependency_mapper.py`

1. **Update imports** to include new symbols:
```python
from little_loops.dependency_mapper import (
    ...,
    ParallelSafePair,
    compute_conflict_score,
)
```

2. **Add test class for `_extract_semantic_targets`** (test via `compute_conflict_score` since it's private, or import via `dependency_mapper._extract_semantic_targets` for unit tests):

Actually, since the extraction functions are private (`_` prefix), we test them indirectly through `compute_conflict_score()` and `find_file_overlaps()`. Add direct tests for `compute_conflict_score()` since it's public.

3. **New test classes**:

```python
# =============================================================================
# compute_conflict_score tests
# =============================================================================

class TestComputeConflictScore:
    """Tests for semantic conflict scoring."""

    def test_same_component_high_conflict(self) -> None:
        """Issues both modifying same component should have high conflict."""
        content_a = "Add duplicate button to ActivityCard in day-columns.tsx"
        content_b = "Add star toggle to ActivityCard in day-columns.tsx"
        score = compute_conflict_score(content_a, content_b)
        assert score > 0.6

    def test_different_sections_low_conflict(self) -> None:
        """Issues modifying different sections should have low conflict."""
        content_a = "Add stats to day column header in day-columns.tsx"
        content_b = "Add empty state to droppable body in day-columns.tsx"
        score = compute_conflict_score(content_a, content_b)
        assert score < 0.4

    def test_empty_content(self) -> None:
        """Empty content should return moderate default score."""
        score = compute_conflict_score("", "")
        assert 0.3 <= score <= 0.7

    def test_no_semantic_signals_moderate_score(self) -> None:
        """Content with no extractable signals should return moderate score."""
        content_a = "Fix the bug in the config file"
        content_b = "Update the config settings"
        score = compute_conflict_score(content_a, content_b)
        assert 0.2 <= score <= 0.8

    def test_structural_vs_enhancement_different_types(self) -> None:
        """Different modification types should reduce conflict score."""
        content_a = "Extract activity list into separate component"
        content_b = "Add button to display stats in header"
        score = compute_conflict_score(content_a, content_b)
        # Different types contribute 0.0 to the type signal
        assert score < 0.7


# =============================================================================
# find_file_overlaps with semantic analysis tests
# =============================================================================

class TestFindFileOverlapsSemanticAnalysis:
    """Tests for semantic conflict filtering in file overlap detection."""

    def test_parallel_safe_different_sections(self) -> None:
        """Issues touching different sections should be parallel-safe."""
        issues = [
            make_issue("ENH-032", priority="P2", title="Empty state"),
            make_issue("ENH-033", priority="P2", title="Header stats"),
        ]
        contents = {
            "ENH-032": "Add empty state to droppable body in `src/day-columns.tsx`",
            "ENH-033": "Add stats to day column header in `src/day-columns.tsx`",
        }
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(proposals) == 0
        assert len(parallel_safe) == 1
        assert parallel_safe[0].issue_a in ("ENH-032", "ENH-033")

    def test_high_conflict_same_component(self) -> None:
        """Issues modifying same component should create dependency."""
        issues = [
            make_issue("FEAT-030", priority="P2", title="Duplicate button"),
            make_issue("FEAT-031", priority="P2", title="Star toggle"),
        ]
        contents = {
            "FEAT-030": "Add duplicate button to ActivityCard in `src/day-columns.tsx`",
            "FEAT-031": "Add star toggle to ActivityCard in `src/day-columns.tsx`",
        }
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert len(parallel_safe) == 0

    def test_structural_before_enhancement_ordering(self) -> None:
        """Structural changes should block enhancement changes at same priority."""
        issues = [
            make_issue("FEAT-028", priority="P3", title="Extract component"),
            make_issue("FEAT-031", priority="P3", title="Add star toggle"),
        ]
        contents = {
            "FEAT-028": "Extract ActivityCard into `src/activity-card.tsx` from `src/day-columns.tsx`",
            "FEAT-031": "Add star toggle button to ActivityCard in `src/day-columns.tsx`",
        }
        proposals, parallel_safe = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert proposals[0].target_id == "FEAT-028"  # Structural = blocker
        assert proposals[0].source_id == "FEAT-031"  # Enhancement = blocked

    def test_conflict_score_on_proposal(self) -> None:
        """Proposals should include the computed conflict score."""
        issues = [
            make_issue("FEAT-001", priority="P1"),
            make_issue("FEAT-002", priority="P2"),
        ]
        contents = {
            "FEAT-001": "Add button to ActivityCard in `scripts/config.py`",
            "FEAT-002": "Update ActivityCard styling in `scripts/config.py`",
        }
        proposals, _ = find_file_overlaps(issues, contents)
        assert len(proposals) == 1
        assert proposals[0].conflict_score > 0.0


# =============================================================================
# format_report with conflict info tests
# =============================================================================

class TestFormatReportConflictInfo:
    """Tests for conflict information in report formatting."""

    def test_parallel_safe_section(self) -> None:
        """Report should include parallel-safe section."""
        report = DependencyReport(
            parallel_safe=[
                ParallelSafePair(
                    issue_a="ENH-032",
                    issue_b="ENH-033",
                    shared_files=["src/day-columns.tsx"],
                    conflict_score=0.15,
                    reason="Different sections (body vs header)",
                )
            ],
            issue_count=2,
        )
        text = format_report(report)
        assert "Parallel Execution Safe" in text
        assert "ENH-032" in text
        assert "ENH-033" in text

    def test_conflict_column_in_proposals(self) -> None:
        """Proposals table should include conflict level."""
        report = DependencyReport(
            proposals=[
                DependencyProposal(
                    source_id="FEAT-031",
                    target_id="FEAT-028",
                    reason="file_overlap",
                    confidence=0.75,
                    rationale="Both reference day-columns.tsx",
                    overlapping_files=["src/day-columns.tsx"],
                    conflict_score=0.85,
                )
            ],
            issue_count=2,
        )
        text = format_report(report)
        assert "HIGH" in text
        assert "Conflict" in text
```

4. **Update existing tests** that call `find_file_overlaps()` to unpack the tuple return:

All existing `TestFindFileOverlaps` tests need updating from:
```python
proposals = find_file_overlaps(issues, contents)
```
To:
```python
proposals, _ = find_file_overlaps(issues, contents)
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/dependency_mapper.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/dependency_mapper.py`
- [ ] Full test suite: `python -m pytest scripts/tests/ -v`

---

## Testing Strategy

### Unit Tests
- `TestComputeConflictScore`: 5 tests covering same component, different sections, empty content, no signals, different types
- `TestFindFileOverlapsSemanticAnalysis`: 4 tests covering parallel-safe detection, high-conflict detection, ordering, and conflict score propagation
- `TestFormatReportConflictInfo`: 2 tests for report output changes

### Regression Tests
- All 8 existing `TestExtractFilePaths` tests unchanged
- All 9 existing `TestFindFileOverlaps` tests updated to unpack tuple return
- All 8 existing `TestValidateDependencies` tests unchanged
- All 2 existing `TestAnalyzeDependencies` tests updated for new report fields
- All 4 existing `TestFormatReport` tests updated for new table columns
- All 4 existing `TestFormatMermaid` tests unchanged
- All 6 existing `TestApplyProposals` tests unchanged

## References

- Original issue: `.issues/enhancements/P2-ENH-300-enhance-dependency-mapper-semantic-analysis.md`
- Primary file: `scripts/little_loops/dependency_mapper.py`
- Test file: `scripts/tests/test_dependency_mapper.py`
- Related patterns: `scripts/little_loops/workflow_sequence_analyzer.py:56-63` (VERB_CLASSES), `scripts/little_loops/workflow_sequence_analyzer.py:294-338` (weighted scoring)
- Similar implementation: `scripts/little_loops/parallel/file_hints.py:29-32` (SCOPE_PATTERN)
