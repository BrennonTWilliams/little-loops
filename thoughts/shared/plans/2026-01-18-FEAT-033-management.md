# FEAT-033: Generalize Issue Type System Configuration - Implementation Plan

## Issue Reference
- **File**: .issues/features/P2-FEAT-033-generalize-issue-type-system.md
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The configuration system has a partially config-driven category system with critical hardcoded dependencies:

### Key Discoveries

1. **Default categories inline in from_dict** (`config.py:87-93`):
   ```python
   categories_data = data.get(
       "categories",
       {
           "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
           "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
           "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
       },
   )
   ```
   - Defaults defined inline, not as a reusable constant
   - User categories completely **replace** defaults (no merge)

2. **Hardcoded type matching** (`issue_discovery.py:339-343`):
   ```python
   issue_type_match = (
       (finding_type == "BUG" and "/bugs/" in str(issue_path))
       or (finding_type == "ENH" and "/enhancements/" in str(issue_path))
       or (finding_type == "FEAT" and "/features/" in str(issue_path))
       or is_completed
   )
   ```
   - Bypasses config entirely
   - Custom categories would never match

3. **Config-driven pattern exists** (`issue_discovery.py:431-445`):
   ```python
   def _get_category_from_issue_path(issue_path: Path, config: BRConfig) -> str:
       filename = issue_path.name.upper()
       for category_name, category_config in config.issues.categories.items():
           if category_config.prefix in filename:
               return category_name
       return "bugs"
   ```
   - This function already uses config dynamically
   - Shows the pattern to follow for type matching

4. **IssueParser uses config-driven prefix mapping** (`issue_parser.py:147-151`):
   ```python
   def _build_prefix_map(self) -> None:
       self._prefix_to_category: dict[str, str] = {}
       for category_name, category in self.config.issues.categories.items():
           self._prefix_to_category[category.prefix] = category_name
   ```

5. **Helper methods on BRConfig** (`config.py:305-348`):
   - `get_issue_dir()`, `get_issue_prefix()`, `get_category_action()` exist
   - No helper methods on `IssuesConfig` dataclass itself

## Desired End State

1. **REQUIRED_CATEGORIES constant** defines the three core categories that cannot be removed
2. **Config validation** ensures required categories exist after user config is applied
3. **Config-driven type matching** in `find_existing_issue()` uses configured categories
4. **Helper methods on IssuesConfig** provide convenient category lookup
5. **Documentation** explains required vs optional categories

### How to Verify
- Tests pass with default config (required categories present)
- Tests pass with custom categories added (merged with required)
- Tests verify required categories cannot be removed
- Type matching works for custom categories (e.g., DOC type)
- Existing tests continue to pass

## What We're NOT Doing

- Not adding new issue types (that's FEAT-032)
- Not changing the config schema structure
- Not modifying how categories are stored in config file
- Not adding migration for existing configs (backwards compatible)
- Not changing command files - they use `{{config.issues.categories}}` already

## Problem Analysis

The issue exists because:
1. Default categories defined inline without reusable constant
2. No validation that user config preserves required types
3. Hardcoded string matching in `find_existing_issue()` bypasses config

## Solution Approach

1. Extract default categories to `DEFAULT_CATEGORIES` constant
2. Define `REQUIRED_CATEGORIES` subset that must always exist
3. Modify `IssuesConfig.from_dict()` to merge required categories
4. Add helper methods to `IssuesConfig` for category lookup
5. Replace hardcoded type matching with config-driven lookup
6. Add tests for validation and new functionality

## Implementation Phases

### Phase 1: Add REQUIRED_CATEGORIES and DEFAULT_CATEGORIES Constants

#### Overview
Extract hardcoded defaults to module-level constants, enabling reuse and validation.

#### Changes Required

**File**: `scripts/little_loops/config.py`
**Changes**: Add constants after imports, before dataclasses

```python
# Required categories that must always exist (cannot be removed by user config)
REQUIRED_CATEGORIES: dict[str, dict[str, str]] = {
    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
}

# Default categories (same as required by default, but could include optional defaults)
DEFAULT_CATEGORIES: dict[str, dict[str, str]] = {
    **REQUIRED_CATEGORIES,
}
```

Add to `__all__`:
```python
__all__ = [
    "BRConfig",
    "CLConfig",
    "CategoryConfig",
    "ProjectConfig",
    "IssuesConfig",
    "AutomationConfig",
    "ParallelAutomationConfig",
    "CommandsConfig",
    "ScanConfig",
    "REQUIRED_CATEGORIES",
    "DEFAULT_CATEGORIES",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_config.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/config.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/config.py`

---

### Phase 2: Modify IssuesConfig.from_dict() to Ensure Required Categories

#### Overview
Change the `from_dict()` method to merge user categories with required categories, ensuring core types always exist.

#### Changes Required

**File**: `scripts/little_loops/config.py`
**Changes**: Modify `IssuesConfig.from_dict()` method

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> IssuesConfig:
    """Create IssuesConfig from dictionary.

    Required categories (bugs, features, enhancements) are automatically
    included if not specified in user config.
    """
    # Start with user categories or empty dict
    categories_data = data.get("categories", {})

    # Ensure required categories exist (merge with defaults)
    for key, defaults in REQUIRED_CATEGORIES.items():
        if key not in categories_data:
            categories_data[key] = defaults

    categories = {
        key: CategoryConfig.from_dict(key, value) for key, value in categories_data.items()
    }
    return cls(
        base_dir=data.get("base_dir", ".issues"),
        categories=categories,
        completed_dir=data.get("completed_dir", "completed"),
        priorities=data.get("priorities", ["P0", "P1", "P2", "P3", "P4", "P5"]),
        templates_dir=data.get("templates_dir"),
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_config.py -v`
- [ ] Test for empty config still has 3 categories
- [ ] Test for custom-only config also has required categories

---

### Phase 3: Add Helper Methods to IssuesConfig

#### Overview
Add utility methods to `IssuesConfig` dataclass for convenient category lookups by prefix or directory.

#### Changes Required

**File**: `scripts/little_loops/config.py`
**Changes**: Add methods to `IssuesConfig` dataclass

```python
@dataclass
class IssuesConfig:
    """Issue management configuration."""

    base_dir: str = ".issues"
    categories: dict[str, CategoryConfig] = field(default_factory=dict)
    completed_dir: str = "completed"
    priorities: list[str] = field(default_factory=lambda: ["P0", "P1", "P2", "P3", "P4", "P5"])
    templates_dir: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssuesConfig:
        # ... existing implementation ...

    def get_category_by_prefix(self, prefix: str) -> CategoryConfig | None:
        """Get category config by prefix (e.g., 'BUG', 'FEAT').

        Args:
            prefix: Issue type prefix to look up

        Returns:
            CategoryConfig if found, None otherwise
        """
        for category in self.categories.values():
            if category.prefix == prefix:
                return category
        return None

    def get_category_by_dir(self, dir_name: str) -> CategoryConfig | None:
        """Get category config by directory name.

        Args:
            dir_name: Directory name to look up

        Returns:
            CategoryConfig if found, None otherwise
        """
        for category in self.categories.values():
            if category.dir == dir_name:
                return category
        return None

    def get_all_prefixes(self) -> list[str]:
        """Get all configured issue type prefixes.

        Returns:
            List of prefixes (e.g., ['BUG', 'FEAT', 'ENH'])
        """
        return [cat.prefix for cat in self.categories.values()]

    def get_all_dirs(self) -> list[str]:
        """Get all configured issue directory names.

        Returns:
            List of directory names (e.g., ['bugs', 'features', 'enhancements'])
        """
        return [cat.dir for cat in self.categories.values()]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_config.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/config.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/config.py`

---

### Phase 4: Refactor Type Matching in issue_discovery.py

#### Overview
Replace hardcoded type-to-directory matching with config-driven lookup using the new helper methods.

#### Changes Required

**File**: `scripts/little_loops/issue_discovery.py`
**Changes**: Modify the type matching logic around lines 339-343

Add helper function near other helper functions (after `_get_category_from_issue_path`):

```python
def _matches_issue_type(
    finding_type: str,
    issue_path: Path,
    config: BRConfig,
    is_completed: bool,
) -> bool:
    """Check if finding type matches issue path using configured categories.

    Args:
        finding_type: The type of finding (e.g., 'BUG', 'ENH', 'FEAT')
        issue_path: Path to the issue file
        config: Configuration with category definitions
        is_completed: Whether the issue is in the completed directory

    Returns:
        True if the finding type matches the issue path's category
    """
    if is_completed:
        return True

    path_str = str(issue_path)
    for category in config.issues.categories.values():
        if finding_type == category.prefix and f"/{category.dir}/" in path_str:
            return True
    return False
```

Then modify `find_existing_issue()` to use it:

```python
# Around line 338-344, replace:
issue_type_match = (
    (finding_type == "BUG" and "/bugs/" in str(issue_path))
    or (finding_type == "ENH" and "/enhancements/" in str(issue_path))
    or (finding_type == "FEAT" and "/features/" in str(issue_path))
    or is_completed
)

# With:
issue_type_match = _matches_issue_type(
    finding_type, issue_path, config, is_completed
)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_discovery.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_discovery.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_discovery.py`

---

### Phase 5: Add Tests for New Functionality

#### Overview
Add comprehensive tests for the new constants, validation, and helper methods.

#### Changes Required

**File**: `scripts/tests/test_config.py`
**Changes**: Add new test methods

```python
class TestCategoryConstants:
    """Tests for REQUIRED_CATEGORIES and DEFAULT_CATEGORIES constants."""

    def test_required_categories_contains_core_types(self) -> None:
        """Test that REQUIRED_CATEGORIES has bugs, features, enhancements."""
        from little_loops.config import REQUIRED_CATEGORIES

        assert "bugs" in REQUIRED_CATEGORIES
        assert "features" in REQUIRED_CATEGORIES
        assert "enhancements" in REQUIRED_CATEGORIES
        assert REQUIRED_CATEGORIES["bugs"]["prefix"] == "BUG"
        assert REQUIRED_CATEGORIES["features"]["prefix"] == "FEAT"
        assert REQUIRED_CATEGORIES["enhancements"]["prefix"] == "ENH"

    def test_default_categories_includes_required(self) -> None:
        """Test that DEFAULT_CATEGORIES includes all required categories."""
        from little_loops.config import DEFAULT_CATEGORIES, REQUIRED_CATEGORIES

        for key in REQUIRED_CATEGORIES:
            assert key in DEFAULT_CATEGORIES


class TestIssuesConfigValidation:
    """Tests for required category validation."""

    def test_required_categories_always_present_empty_config(self) -> None:
        """Test that required categories exist with empty config."""
        config = IssuesConfig.from_dict({})

        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories

    def test_required_categories_merged_with_custom(self) -> None:
        """Test that custom categories are merged with required."""
        data = {
            "categories": {
                "documentation": {"prefix": "DOC", "dir": "docs", "action": "document"},
            }
        }
        config = IssuesConfig.from_dict(data)

        # Custom category present
        assert "documentation" in config.categories
        assert config.categories["documentation"].prefix == "DOC"

        # Required categories also present
        assert "bugs" in config.categories
        assert "features" in config.categories
        assert "enhancements" in config.categories

    def test_user_can_override_required_category_settings(self) -> None:
        """Test that user can customize required category settings."""
        data = {
            "categories": {
                "bugs": {"prefix": "BUG", "dir": "bug-reports", "action": "resolve"},
            }
        }
        config = IssuesConfig.from_dict(data)

        # User's customization applied
        assert config.categories["bugs"].dir == "bug-reports"
        assert config.categories["bugs"].action == "resolve"

        # Other required categories still present
        assert "features" in config.categories
        assert "enhancements" in config.categories


class TestIssuesConfigHelperMethods:
    """Tests for IssuesConfig helper methods."""

    def test_get_category_by_prefix_found(self) -> None:
        """Test get_category_by_prefix returns category when found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_prefix("BUG")

        assert result is not None
        assert result.prefix == "BUG"
        assert result.dir == "bugs"

    def test_get_category_by_prefix_not_found(self) -> None:
        """Test get_category_by_prefix returns None when not found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_prefix("UNKNOWN")

        assert result is None

    def test_get_category_by_dir_found(self) -> None:
        """Test get_category_by_dir returns category when found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_dir("features")

        assert result is not None
        assert result.prefix == "FEAT"
        assert result.dir == "features"

    def test_get_category_by_dir_not_found(self) -> None:
        """Test get_category_by_dir returns None when not found."""
        config = IssuesConfig.from_dict({})

        result = config.get_category_by_dir("unknown")

        assert result is None

    def test_get_all_prefixes(self) -> None:
        """Test get_all_prefixes returns all configured prefixes."""
        config = IssuesConfig.from_dict({})

        prefixes = config.get_all_prefixes()

        assert "BUG" in prefixes
        assert "FEAT" in prefixes
        assert "ENH" in prefixes

    def test_get_all_dirs(self) -> None:
        """Test get_all_dirs returns all configured directories."""
        config = IssuesConfig.from_dict({})

        dirs = config.get_all_dirs()

        assert "bugs" in dirs
        assert "features" in dirs
        assert "enhancements" in dirs
```

**File**: `scripts/tests/test_issue_discovery.py`
**Changes**: Add test for config-driven type matching

```python
class TestMatchesIssueType:
    """Tests for _matches_issue_type helper function."""

    def test_matches_standard_types(self, temp_project_dir: Path) -> None:
        """Test matching standard BUG/FEAT/ENH types."""
        from little_loops.issue_discovery import _matches_issue_type

        config = BRConfig(temp_project_dir)

        # BUG matches bugs dir
        bug_path = temp_project_dir / ".issues/bugs/P1-BUG-001-test.md"
        assert _matches_issue_type("BUG", bug_path, config, False) is True
        assert _matches_issue_type("FEAT", bug_path, config, False) is False

        # FEAT matches features dir
        feat_path = temp_project_dir / ".issues/features/P2-FEAT-001-test.md"
        assert _matches_issue_type("FEAT", feat_path, config, False) is True
        assert _matches_issue_type("BUG", feat_path, config, False) is False

    def test_completed_always_matches(self, temp_project_dir: Path) -> None:
        """Test that completed issues match any type."""
        from little_loops.issue_discovery import _matches_issue_type

        config = BRConfig(temp_project_dir)
        completed_path = temp_project_dir / ".issues/completed/P1-BUG-001-test.md"

        # Any type matches completed
        assert _matches_issue_type("BUG", completed_path, config, True) is True
        assert _matches_issue_type("FEAT", completed_path, config, True) is True
        assert _matches_issue_type("CUSTOM", completed_path, config, True) is True

    def test_custom_type_with_custom_config(self, temp_project_dir: Path) -> None:
        """Test matching custom DOC type with configured category."""
        import json
        from little_loops.issue_discovery import _matches_issue_type

        # Create config with custom DOC category
        config_data = {
            "issues": {
                "categories": {
                    "documentation": {"prefix": "DOC", "dir": "documentation", "action": "document"},
                }
            }
        }
        config_path = temp_project_dir / ".claude" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config_data))

        config = BRConfig(temp_project_dir)
        doc_path = temp_project_dir / ".issues/documentation/P2-DOC-001-readme.md"

        # DOC matches documentation dir
        assert _matches_issue_type("DOC", doc_path, config, False) is True
        assert _matches_issue_type("BUG", doc_path, config, False) is False
```

#### Success Criteria

**Automated Verification**:
- [ ] All new tests pass: `python -m pytest scripts/tests/test_config.py scripts/tests/test_issue_discovery.py -v`
- [ ] Full test suite passes: `python -m pytest scripts/tests/ -v`

---

### Phase 6: Update Documentation

#### Overview
Update config-schema.json description and README to document required vs optional categories.

#### Changes Required

**File**: `config-schema.json`
**Changes**: Update categories description (around line 67-69)

```json
"categories": {
  "type": "object",
  "description": "Issue category definitions. Required categories (bugs, features, enhancements) are automatically included if not specified. Custom categories can be added alongside the required ones.",
  ...
}
```

**File**: `README.md`
**Changes**: Add section explaining custom categories (if not already documented)

Find the configuration section and ensure it documents:
```markdown
### Custom Issue Categories

The three core categories (`bugs`, `features`, `enhancements`) are always available.
You can add custom categories alongside them:

```json
{
  "issues": {
    "categories": {
      "documentation": {"prefix": "DOC", "dir": "documentation", "action": "document"},
      "tech-debt": {"prefix": "DEBT", "dir": "tech-debt", "action": "address"}
    }
  }
}
```

Custom categories will be merged with the required categories - you cannot remove
the core `bugs`, `features`, or `enhancements` categories.
```

#### Success Criteria

**Automated Verification**:
- [ ] JSON schema is valid: `python -c "import json; json.load(open('config-schema.json'))"`
- [ ] Lint passes on all modified files

**Manual Verification**:
- [ ] Schema description accurately describes behavior
- [ ] README section is clear and provides a useful example

---

## Testing Strategy

### Unit Tests
- REQUIRED_CATEGORIES constant contains expected keys
- DEFAULT_CATEGORIES includes all required categories
- IssuesConfig.from_dict() merges required categories
- Helper methods (get_category_by_prefix, etc.) work correctly
- _matches_issue_type uses config for matching

### Integration Tests
- BRConfig loads with custom categories merged
- Issue discovery works with custom DOC type
- Existing tests for default categories continue to pass

## References

- Original issue: `.issues/features/P2-FEAT-033-generalize-issue-type-system.md`
- Config-driven pattern: `scripts/little_loops/issue_discovery.py:431-445`
- Existing helpers: `scripts/little_loops/config.py:305-348`
- Test patterns: `scripts/tests/test_config.py:111-122`
