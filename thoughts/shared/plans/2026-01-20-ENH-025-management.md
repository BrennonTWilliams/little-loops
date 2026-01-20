# ENH-025: Universal discovered_by Field for Issue Tracking - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-025-universal-discovered-by-field.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- `issue_parser.py:75-95` - `IssueInfo` dataclass has NO frontmatter fields (only filename-based and markdown section fields)
- `issue_parser.py:263-275` - `_read_content()` reads file but doesn't parse YAML frontmatter
- `commands/scan_codebase.md:188-193` - Missing `discovered_by` field in frontmatter template
- `commands/audit_architecture.md:197` - Already has `discovered_by: audit_architecture`
- `commands/audit_docs.md:199` - Already has `discovered_by: audit_docs`
- `commands/capture_issue.md:345` - Already has `discovered_by: capture_issue`
- `commands/find_dead_code.md:159` - Already has `discovered_by: find_dead_code`
- 34+ issue files already contain `discovered_by` field in frontmatter

### Patterns to Follow
- `blocked_by` and `blocks` fields in `IssueInfo` use `field(default_factory=list)` for optional defaults
- `from_dict()` uses `.get("field", default)` for backwards compatibility
- Tests in `test_issue_parser.py:830-868` show pattern for testing optional field serialization

## Desired End State

After implementation:
1. `IssueInfo` dataclass has `discovered_by: Optional[str] = None` field
2. `IssueParser.parse_file()` extracts `discovered_by` from YAML frontmatter
3. `/ll:scan_codebase` includes `discovered_by: scan_codebase` in created issues
4. Existing issues without `discovered_by` parse as `None` (backwards compatible)

### How to Verify
- Unit tests pass for parsing issues with and without `discovered_by`
- Serialization roundtrip preserves `discovered_by` value
- Existing issue files continue to parse correctly

## What We're NOT Doing

- Not adding other frontmatter fields (`discovered_commit`, `discovered_branch`, `discovered_date`) to parser - separate enhancement
- Not migrating existing issues to add `discovered_by` field
- Not adding filtering by `discovered_by` - future enhancement

## Solution Approach

1. Add `discovered_by` field to `IssueInfo` dataclass with `Optional[str] = None` default
2. Add YAML frontmatter parsing to `IssueParser` (minimal: only extract `discovered_by`)
3. Update `to_dict()` and `from_dict()` methods
4. Update `scan_codebase.md` command template to include `discovered_by`
5. Add unit tests for frontmatter parsing

## Implementation Phases

### Phase 1: Update IssueInfo Dataclass

#### Overview
Add `discovered_by` field to the dataclass with proper default and serialization.

#### Changes Required

**File**: `scripts/little_loops/issue_parser.py`

**Change 1**: Add field to dataclass (after line 95)

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
    """

    path: Path
    issue_type: str
    priority: str
    issue_id: str
    title: str
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    discovered_by: str | None = None
```

**Change 2**: Update `to_dict()` method

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
    }
```

**Change 3**: Update `from_dict()` method

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
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_parser.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_parser.py`

---

### Phase 2: Add YAML Frontmatter Parsing

#### Overview
Add method to extract `discovered_by` from YAML frontmatter in issue files.

#### Changes Required

**File**: `scripts/little_loops/issue_parser.py`

**Change 1**: Add `_parse_frontmatter()` method after `_read_content()`:

```python
def _parse_frontmatter(self, content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from issue content.

    Looks for content between opening and closing '---' markers.
    Returns empty dict if no frontmatter found or on parse error.

    Args:
        content: File content to parse

    Returns:
        Dictionary of frontmatter fields, or empty dict
    """
    if not content or not content.startswith("---"):
        return {}

    # Find closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}

    frontmatter_text = content[4 : 3 + end_match.start()]

    # Simple YAML-like parsing for key: value pairs
    # Avoids adding yaml dependency for this simple use case
    result: dict[str, Any] = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            # Handle null/empty values
            if value.lower() in ("null", "~", ""):
                result[key] = None
            else:
                result[key] = value
    return result
```

**Change 2**: Update `parse_file()` to use frontmatter:

```python
def parse_file(self, issue_path: Path) -> IssueInfo:
    """Parse an issue file to extract metadata.

    Args:
        issue_path: Path to the issue markdown file

    Returns:
        Parsed IssueInfo
    """
    filename = issue_path.name

    # Parse priority from filename prefix (e.g., P1-BUG-123-...)
    priority = self._parse_priority(filename)

    # Parse issue type and ID from filename
    issue_type, issue_id = self._parse_type_and_id(filename, issue_path)

    # Read content once for all content-based parsing
    content = self._read_content(issue_path)

    # Parse frontmatter for discovered_by
    frontmatter = self._parse_frontmatter(content)
    discovered_by = frontmatter.get("discovered_by")

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
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_parser.py`

---

### Phase 3: Update scan_codebase.md Command

#### Overview
Add `discovered_by: scan_codebase` to the issue file template.

#### Changes Required

**File**: `commands/scan_codebase.md`

**Change**: Update frontmatter template (around line 189-193):

```markdown
```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: scan_codebase
---
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/` (if applicable)
- [ ] Command file is valid markdown

---

### Phase 4: Add Unit Tests

#### Overview
Add tests for `discovered_by` field parsing and serialization.

#### Changes Required

**File**: `scripts/tests/test_issue_parser.py`

**Add tests to appropriate test classes:**

```python
# In TestIssueInfo class
def test_discovered_by_default_none(self) -> None:
    """Test discovered_by defaults to None."""
    info = IssueInfo(
        path=Path("test.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-001",
        title="Test",
    )
    assert info.discovered_by is None

def test_discovered_by_value(self) -> None:
    """Test discovered_by can be set."""
    info = IssueInfo(
        path=Path("test.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-001",
        title="Test",
        discovered_by="scan_codebase",
    )
    assert info.discovered_by == "scan_codebase"

def test_discovered_by_in_to_dict(self) -> None:
    """Test discovered_by appears in to_dict."""
    info = IssueInfo(
        path=Path("test.md"),
        issue_type="bugs",
        priority="P0",
        issue_id="BUG-001",
        title="Test",
        discovered_by="audit_architecture",
    )
    data = info.to_dict()
    assert data["discovered_by"] == "audit_architecture"

def test_discovered_by_from_dict(self) -> None:
    """Test discovered_by is restored from dict."""
    data = {
        "path": "/test/path.md",
        "issue_type": "bugs",
        "priority": "P1",
        "issue_id": "BUG-200",
        "title": "Test Issue",
        "discovered_by": "scan_codebase",
    }
    info = IssueInfo.from_dict(data)
    assert info.discovered_by == "scan_codebase"

def test_discovered_by_from_dict_missing(self) -> None:
    """Test from_dict defaults to None for missing discovered_by."""
    data = {
        "path": "/test/path.md",
        "issue_type": "bugs",
        "priority": "P1",
        "issue_id": "BUG-200",
        "title": "Legacy Issue",
    }
    info = IssueInfo.from_dict(data)
    assert info.discovered_by is None


# In TestIssueParser class (or new TestFrontmatterParsing class)
def test_parse_discovered_by_from_frontmatter(
    self, temp_project_dir: Path, sample_config: dict[str, Any]
) -> None:
    """Test parsing discovered_by from YAML frontmatter."""
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    config = BRConfig(temp_project_dir)

    bugs_dir = temp_project_dir / ".issues" / "bugs"
    bugs_dir.mkdir(parents=True)
    issue_file = bugs_dir / "P1-BUG-001-test.md"
    issue_file.write_text("""---
discovered_commit: abc123
discovered_branch: main
discovered_date: 2026-01-20
discovered_by: scan_codebase
---

# BUG-001: Test Issue

## Summary
Test description.
""")

    parser = IssueParser(config)
    info = parser.parse_file(issue_file)

    assert info.discovered_by == "scan_codebase"

def test_parse_no_frontmatter(
    self, temp_project_dir: Path, sample_config: dict[str, Any]
) -> None:
    """Test parsing issue without frontmatter."""
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    config = BRConfig(temp_project_dir)

    bugs_dir = temp_project_dir / ".issues" / "bugs"
    bugs_dir.mkdir(parents=True)
    issue_file = bugs_dir / "P1-BUG-001-test.md"
    issue_file.write_text("""# BUG-001: Test Issue

## Summary
Test description.
""")

    parser = IssueParser(config)
    info = parser.parse_file(issue_file)

    assert info.discovered_by is None

def test_parse_frontmatter_null_discovered_by(
    self, temp_project_dir: Path, sample_config: dict[str, Any]
) -> None:
    """Test parsing frontmatter with null discovered_by."""
    config_path = temp_project_dir / ".claude" / "ll-config.json"
    config_path.write_text(json.dumps(sample_config))
    config = BRConfig(temp_project_dir)

    bugs_dir = temp_project_dir / ".issues" / "bugs"
    bugs_dir.mkdir(parents=True)
    issue_file = bugs_dir / "P1-BUG-001-test.md"
    issue_file.write_text("""---
discovered_commit: abc123
discovered_by: null
---

# BUG-001: Test Issue

## Summary
Test.
""")

    parser = IssueParser(config)
    info = parser.parse_file(issue_file)

    assert info.discovered_by is None
```

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_issue_parser.py`

---

## Testing Strategy

### Unit Tests
- `IssueInfo` dataclass: default value, serialization, deserialization
- `IssueParser`: frontmatter parsing with/without `discovered_by`
- Backwards compatibility: old issues without field still parse

### Integration Tests
- Parse actual issue files from `.issues/` directory
- Verify issues with `discovered_by` field parse correctly

## References

- Original issue: `.issues/enhancements/P3-ENH-025-universal-discovered-by-field.md`
- Similar pattern: `blocked_by`/`blocks` fields in `issue_parser.py:94-95`
- Test pattern: `test_issue_parser.py:830-868`
- Commands with `discovered_by`: `audit_architecture.md:197`, `audit_docs.md:199`, `capture_issue.md:345`
