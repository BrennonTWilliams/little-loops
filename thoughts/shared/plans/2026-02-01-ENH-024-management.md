# ENH-024: Product Impact Fields in Issue Templates - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-024-product-impact-fields-in-issue-templates.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

Based on comprehensive research completed in Phase 1.5:

### Key Discoveries
- `IssueInfo` dataclass exists at `scripts/little_loops/issue_parser.py:76-135` with `discovered_by` field already implemented (line 98)
- `_parse_frontmatter()` method exists (lines 287-325) that handles YAML frontmatter parsing with null value support
- `scan_product.md` already creates issues with product fields (`goal_alignment`, `persona_impact`, `business_value`) in frontmatter (lines 220-222)
- No `ProductImpact` dataclass or `product_impact` field currently exists in `IssueInfo`
- Commands `manage_issue.md` and `prioritize_issues.md` do not currently handle product impact fields

### Patterns to Follow
- **Optional field pattern**: Use `str | None = None` for optional string fields (like `discovered_by` at line 98)
- **Nested dataclass pattern**: `RegressionEvidence` in `issue_discovery.py:46-86` shows how to nest optional dataclasses
- **Serialization pattern**: Use `.get(key)` for optional fields in `from_dict()` and include all fields in `to_dict()`
- **Test pattern**: Tests for `discovered_by` (lines 148-207) show how to test optional fields with fixtures

### What Already Works
- `discovered_by` field parsing and serialization is fully implemented
- Frontmatter parsing handles null values ("null", "~", "") correctly
- Fixture files exist for various frontmatter scenarios

## Desired End State

1. **ProductImpact dataclass** added to `issue_parser.py` with fields: `goal_alignment`, `persona_impact`, `business_value`, `user_benefit`
2. **IssueInfo.product_impact** field added (optional, defaults to None)
3. **Parsing logic** extracts product fields from frontmatter when present
4. **Serialization** (`to_dict`/`from_dict`) handles ProductImpact correctly
5. **Tests** cover all scenarios: present, absent, null values
6. **Commands** display product impact when available

### How to Verify
- Run tests: `python -m pytest scripts/tests/test_issue_parser.py -v`
- Run lint: `ruff check scripts/`
- Run types: `python -m mypy scripts/little_loops/`
- Test with real issue file that has product impact fields

## What We're NOT Doing

- **Not modifying** `scan_product.md` - it already creates product fields (verified in issue)
- **Not adding** product impact filtering to `find_issues()` - deferred to future enhancement
- **Not modifying** other issue-creating commands - only `scan_product` uses product fields
- **Not creating** a separate product issue type - using existing types with optional fields
- **Not adding** CLI filtering by product impact - issue mentions this as future enhancement

## Problem Analysis

The issue describes adding optional product impact fields to issue templates. The blocker issues are all complete:

- FEAT-020 (Product Analysis Opt-In Configuration) - Completed
- FEAT-021 (Goals/Vision Ingestion Mechanism) - Completed 2026-01-29
- FEAT-022 (Product Analyzer Skill) - Completed
- ENH-025 (Universal discovered_by Field) - Completed 2026-01-20

The `scan_product.md` command already writes product fields to issue files. The gap is that Python code doesn't read or use these fields.

## Solution Approach

Following the existing pattern for `discovered_by` field (already implemented):

1. Create `ProductImpact` dataclass with all optional fields
2. Add `product_impact: ProductImpact | None = None` to `IssueInfo`
3. Add `_parse_product_impact()` method to extract fields from frontmatter
4. Update `parse_file()` to call the new parsing method
5. Update serialization methods to include product_impact
6. Add comprehensive tests following existing patterns
7. Update commands to display product impact when present

## Implementation Phases

### Phase 1: Add ProductImpact Dataclass and Field

#### Overview
Create the ProductImpact dataclass and add it to IssueInfo as an optional field.

#### Changes Required

**File**: `scripts/little_loops/issue_parser.py`
**Location**: After line 75 (before IssueInfo class)
**Changes**: Add ProductImpact dataclass

```python
@dataclass
class ProductImpact:
    """Product impact assessment for an issue.

    Attributes:
        goal_alignment: ID of the strategic priority this supports
        persona_impact: ID of the persona affected
        business_value: Business value assessment (high|medium|low)
        user_benefit: Description of how this helps the target user
    """

    goal_alignment: str | None = None
    persona_impact: str | None = None
    business_value: str | None = None  # high|medium|low
    user_benefit: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "goal_alignment": self.goal_alignment,
            "persona_impact": self.persona_impact,
            "business_value": self.business_value,
            "user_benefit": self.user_benefit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ProductImpact | None:
        """Create ProductImpact from dictionary.

        Args:
            data: Dictionary with product impact fields, or None

        Returns:
            ProductImpact instance or None if data is None/empty
        """
        if not data:
            return None
        return cls(
            goal_alignment=data.get("goal_alignment"),
            persona_impact=data.get("persona_impact"),
            business_value=data.get("business_value"),
            user_benefit=data.get("user_benefit"),
        )
```

**File**: `scripts/little_loops/issue_parser.py`
**Location**: After line 98 (in IssueInfo class)
**Changes**: Add product_impact field

```python
@dataclass
class IssueInfo:
    """Parsed information from an issue file.

    Attributes:
        path: Path to the issue file
        issue_type: Type of issue (e.g., "bugs", "features")
        priority: Priority level (e.g., "P0", "P1")
        issue_id: Issue identifier (e.g., "BUG-123")
        title: Issue title from markdown header
        blocked_by: List of issue IDs that block this issue
        blocks: List of issue IDs that this issue blocks
        discovered_by: Source command/workflow that created this issue
        product_impact: Product impact assessment (optional)
    """

    path: Path
    issue_type: str
    priority: str
    issue_id: str
    title: str
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    discovered_by: str | None = None
    product_impact: ProductImpact | None = None  # NEW
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 2: Add Product Impact Parsing Logic

#### Overview
Add method to parse product impact fields from frontmatter and integrate it into parse_file().

#### Changes Required

**File**: `scripts/little_loops/issue_parser.py`
**Location**: After line 432 (after _parse_blocks method)
**Changes**: Add _parse_product_impact method

```python
def _parse_product_impact(self, frontmatter: dict[str, Any]) -> ProductImpact | None:
    """Extract product impact from frontmatter.

    Args:
        frontmatter: Dictionary of frontmatter fields

    Returns:
        ProductImpact instance if any product fields are present, None otherwise
    """
    # Check if any product fields are present
    product_fields = ("goal_alignment", "persona_impact", "business_value", "user_benefit")
    if not any(frontmatter.get(key) for key in product_fields):
        return None

    return ProductImpact(
        goal_alignment=frontmatter.get("goal_alignment"),
        persona_impact=frontmatter.get("persona_impact"),
        business_value=frontmatter.get("business_value"),
        user_benefit=frontmatter.get("user_benefit"),
    )
```

**File**: `scripts/little_loops/issue_parser.py`
**Location**: Lines 187-196 (in parse_file method)
**Changes**: Add product_impact parsing

```python
# Parse frontmatter for discovered_by and product impact
frontmatter = self._parse_frontmatter(content)
discovered_by = frontmatter.get("discovered_by")
product_impact = self._parse_product_impact(frontmatter)  # NEW

# Parse title and dependencies from file content
title = self._parse_title_from_content(content, issue_path)
blocked_by = self._parse_blocked_by(content)
blocks = self._parse_blocks(content)

return IssueInfo(
    path=issue_path,
    issue_type=issue_type,
    priority=priority,
    issue_id=issue_id,
    title=title,
    blocked_by=blocked_by,
    blocks=blocks,
    discovered_by=discovered_by,
    product_impact=product_impact,  # NEW
)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Update Serialization Methods

#### Overview
Update to_dict() and from_dict() to handle ProductImpact field.

#### Changes Required

**File**: `scripts/little_loops/issue_parser.py`
**Location**: Lines 109-120 (to_dict method)
**Changes**: Include product_impact in serialization

```python
def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for JSON serialization."""
    return {
        "path": str(self.path),
        "issue_type": self.issue_type,
        "priority": self.priority,
        "issue_id": self.issue_id,
        "title": self.title,
        "blocked_by": self.blocked_by,
        "blocks": self.blocks,
        "discovered_by": self.discovered_by,
        "product_impact": (
            self.product_impact.to_dict() if self.product_impact else None
        ),
    }
```

**File**: `scripts/little_loops/issue_parser.py`
**Location**: Lines 122-134 (from_dict method)
**Changes**: Handle product_impact in deserialization

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> IssueInfo:
    """Create IssueInfo from dictionary."""
    return cls(
        path=Path(data["path"]),
        issue_type=data["issue_type"],
        priority=data["priority"],
        issue_id=data["issue_id"],
        title=data["title"],
        blocked_by=data.get("blocked_by", []),
        blocks=data.get("blocks", []),
        discovered_by=data.get("discovered_by"),
        product_impact=ProductImpact.from_dict(data.get("product_impact")),
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 4: Create Test Fixtures

#### Overview
Create fixture files with product impact fields for testing.

#### Changes Required

**File**: `scripts/tests/fixtures/issues/bug-with-product-impact.md`
**New file**:

```markdown
---
discovered_commit: abc123
discovered_branch: main
discovered_date: 2026-02-01
discovered_by: scan_product
goal_alignment: automation
persona_impact: developer
business_value: high
user_benefit: Faster issue processing
---

# BUG-001: Test Issue with Product Impact

## Summary
Test description with product impact.
```

**File**: `scripts/tests/fixtures/issues/bug-no-product-impact.md`
**New file**:

```markdown
---
discovered_commit: abc123
discovered_by: scan_codebase
---

# BUG-002: Test Issue without Product Impact

## Summary
Test description without product impact.
```

**File**: `scripts/tests/fixtures/issues/bug-null-product-fields.md`
**New file**:

```markdown
---
discovered_by: scan_product
goal_alignment: null
persona_impact: null
business_value: null
user_benefit: null
---

# BUG-003: Test Issue with Null Product Fields

## Summary
Test description with null product values.
```

#### Success Criteria

**Automated Verification**:
- [ ] Fixture files exist in `scripts/tests/fixtures/issues/`

---

### Phase 5: Add Tests for Product Impact

#### Overview
Add comprehensive tests following the pattern of discovered_by tests.

#### Changes Required

**File**: `scripts/tests/test_issue_parser.py`
**Location**: After line 207 (after discovered_by tests)
**Changes**: Add product impact tests

```python
def test_product_impact_default_none(self) -> None:
    """Test product_impact defaults to None."""
    info = IssueInfo(
        path=Path("test.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-001",
        title="Test",
    )
    assert info.product_impact is None

def test_product_impact_with_values(self) -> None:
    """Test product_impact can be set with values."""
    impact = ProductImpact(
        goal_alignment="automation",
        persona_impact="developer",
        business_value="high",
        user_benefit="Faster processing",
    )
    info = IssueInfo(
        path=Path("test.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-001",
        title="Test",
        product_impact=impact,
    )
    assert info.product_impact is not None
    assert info.product_impact.goal_alignment == "automation"
    assert info.product_impact.persona_impact == "developer"
    assert info.product_impact.business_value == "high"
    assert info.product_impact.user_benefit == "Faster processing"

def test_product_impact_in_to_dict(self) -> None:
    """Test product_impact appears in to_dict."""
    impact = ProductImpact(
        goal_alignment="ux",
        persona_impact="end_user",
        business_value="medium",
    )
    info = IssueInfo(
        path=Path("test.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-001",
        title="Test",
        product_impact=impact,
    )
    data = info.to_dict()
    assert data["product_impact"] is not None
    assert data["product_impact"]["goal_alignment"] == "ux"

def test_product_impact_from_dict(self) -> None:
    """Test product_impact is restored from dict."""
    data = {
        "path": "/test/path.md",
        "issue_type": "bugs",
        "priority": "P1",
        "issue_id": "BUG-200",
        "title": "Test Issue",
        "discovered_by": "scan_product",
        "product_impact": {
            "goal_alignment": "performance",
            "persona_impact": "admin",
            "business_value": "high",
            "user_benefit": "Faster reports",
        },
    }
    info = IssueInfo.from_dict(data)
    assert info.product_impact is not None
    assert info.product_impact.goal_alignment == "performance"

def test_product_impact_from_dict_missing(self) -> None:
    """Test from_dict defaults to None for missing product_impact."""
    data = {
        "path": "/test/path.md",
        "issue_type": "bugs",
        "priority": "P1",
        "issue_id": "BUG-200",
        "title": "Legacy Issue",
    }
    info = IssueInfo.from_dict(data)
    assert info.product_impact is None

def test_parse_product_impact_from_frontmatter(
    self,
    temp_project_dir: Path,
    sample_config: dict[str, Any],
    fixtures_dir: Path,
) -> None:
    """Test parsing product_impact from YAML frontmatter."""
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    config = BRConfig(temp_project_dir)

    bugs_dir = temp_project_dir / ".issues" / "bugs"
    bugs_dir.mkdir(parents=True)
    issue_file = bugs_dir / "P1-BUG-001-test.md"
    issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-with-product-impact.md"))

    parser = IssueParser(config)
    info = parser.parse_file(issue_file)

    assert info.product_impact is not None
    assert info.product_impact.goal_alignment == "automation"
    assert info.product_impact.persona_impact == "developer"
    assert info.product_impact.business_value == "high"
    assert info.product_impact.user_benefit == "Faster issue processing"

def test_parse_no_product_impact(
    self,
    temp_project_dir: Path,
    sample_config: dict[str, Any],
    fixtures_dir: Path,
) -> None:
    """Test parsing issue without product impact."""
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    config = BRConfig(temp_project_dir)

    bugs_dir = temp_project_dir / ".issues" / "bugs"
    bugs_dir.mkdir(parents=True)
    issue_file = bugs_dir / "P1-BUG-002-test.md"
    issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-no-product-impact.md"))

    parser = IssueParser(config)
    info = parser.parse_file(issue_file)

    assert info.product_impact is None

def test_parse_product_impact_null_values(
    self,
    temp_project_dir: Path,
    sample_config: dict[str, Any],
    fixtures_dir: Path,
) -> None:
    """Test parsing frontmatter with null product fields."""
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    config = BRConfig(temp_project_dir)

    bugs_dir = temp_project_dir / ".issues" / "bugs"
    bugs_dir.mkdir(parents=True)
    issue_file = bugs_dir / "P1-BUG-003-test.md"
    issue_file.write_text(load_fixture(fixtures_dir, "issues", "bug-null-product-fields.md"))

    parser = IssueParser(config)
    info = parser.parse_file(issue_file)

    # When all fields are null, product_impact should be None
    assert info.product_impact is None
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v -k product_impact`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 6: Update Commands to Display Product Impact

#### Overview
Update manage_issue.md and prioritize_issues.md to handle product impact fields.

#### Changes Required

**File**: `commands/manage_issue.md`
**Location**: Lines 536-572 (Final Report section)
**Changes**: Add product impact to report template

```markdown
## Final Report

Output in this format for machine parsing:

```
================================================================================
ISSUE MANAGED: {ISSUE_ID} - {action}
================================================================================

## METADATA
- Type: {issue_type}
- Priority: {priority}
- Title: {title}
- Action: {action}
{if product_impact exists:}
## PRODUCT IMPACT
- Goal Alignment: {goal_alignment}
- Persona Impact: {persona_impact}
- Business Value: {business_value}
- User Benefit: {user_benefit}
{endif}
```

Add instruction to check for and display product impact in issue review.
```

**File**: `commands/prioritize_issues.md`
**Location**: Lines 46-62 (Analyze Each Issue section)
**Changes**: Add product field consideration

```markdown
2. **Assess priority** based on:
   - **User impact**: How many users affected?
   - **Business impact**: Revenue, reputation, compliance?
   - **Product fields** (if present):
     - `business_value`: high/medium/low from frontmatter
     - `goal_alignment`: Strategic priority connection
     - `persona_impact`: Which users are affected
   - **Technical debt**: Blocking other work?
   - **Effort**: Quick win vs. major undertaking?
```

#### Success Criteria

**Manual Verification**:
- [ ] Review manage_issue.md shows product impact display instruction
- [ ] Review prioritize_issues.md shows business_value consideration

---

## Testing Strategy

### Unit Tests
- ProductImpact dataclass: creation, serialization, null handling
- IssueInfo with product_impact: defaults, values, to_dict, from_dict
- Frontmatter parsing: with fields, without fields, null values
- Roundtrip serialization for all field combinations

### Integration Tests
- Parse real issue files with product impact
- Verify product impact survives roundtrip
- Test with fixture files covering all scenarios

### Property-Based Tests
- Add to `test_issue_parser_properties.py` for ProductImpact
- Test roundtrip with random product field combinations
- Use hypothesis strategies for optional fields

## References

- Original issue: `.issues/enhancements/P2-ENH-024-product-impact-fields-in-issue-templates.md`
- Core parser: `scripts/little_loops/issue_parser.py:76-433`
- Existing pattern: `discovered_by` field at line 98
- Similar pattern: `RegressionEvidence` in `issue_discovery.py:46-86`
- Test fixtures: `scripts/tests/fixtures/issues/`
- Product analyzer skill: `skills/product-analyzer/SKILL.md`
- Completed dependencies:
  - `.issues/completed/P2-FEAT-020-product-analysis-opt-in-configuration.md`
  - `.issues/completed/P2-FEAT-021-goals-vision-ingestion-mechanism.md`
  - `.issues/completed/P1-FEAT-022-product-analyzer-skill.md`
  - `.issues/completed/P3-ENH-025-universal-discovered-by-field.md`
