---
discovered_commit: a558610
discovered_branch: main
discovered_date: 2026-01-12T00:00:00Z
---

# FEAT-033: Generalize Issue Type System Configuration

## Summary

Refactor the issue type system to be fully config-driven, removing hardcoded type matching and centralizing default category definitions. This enables users to add custom issue types (like DOC, CHORE, TECH-DEBT) without code changes.

## Motivation

The current implementation has issue types partially configurable but with critical hardcoded dependencies:

1. **Hardcoded type matching** in `issue_discovery.py:339-343`:
   ```python
   issue_type_match = (
       (finding_type == "BUG" and "/bugs/" in str(issue_path))
       or (finding_type == "ENH" and "/enhancements/" in str(issue_path))
       or (finding_type == "FEAT" and "/features/" in str(issue_path))
       or is_completed
   )
   ```

2. **Scattered defaults** in `config.py` and template files

3. **No required type validation** - users could accidentally remove core types

Adding new types like DOC (see FEAT-032) currently requires modifying multiple source files. A generalized system would make this a simple config change.

## Proposed Implementation

### 1. Define Required vs Optional Categories

**File**: `scripts/little_loops/config.py`

Add constants for required categories that must always exist:

```python
REQUIRED_CATEGORIES = {
    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
}

DEFAULT_CATEGORIES = {
    **REQUIRED_CATEGORIES,
    # Optional defaults can be added here
}
```

### 2. Add Config Validation

**File**: `scripts/little_loops/config.py`

In `IssuesConfig.from_dict()`, validate that required categories exist:

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> IssuesConfig:
    categories_data = data.get("categories", DEFAULT_CATEGORIES)

    # Ensure required categories exist
    for key, defaults in REQUIRED_CATEGORIES.items():
        if key not in categories_data:
            categories_data[key] = defaults

    categories = {
        key: CategoryConfig.from_dict(key, value)
        for key, value in categories_data.items()
    }
    return cls(...)
```

### 3. Refactor Type Matching to Use Config

**File**: `scripts/little_loops/issue_discovery.py`

Replace hardcoded matching with config-driven approach:

```python
def _matches_issue_type(
    finding_type: str,
    issue_path: Path,
    config: LLConfig,
    is_completed: bool
) -> bool:
    """Check if finding type matches issue path using configured categories."""
    if is_completed:
        return True

    path_str = str(issue_path)
    for category in config.issues.categories.values():
        if finding_type == category.prefix and f"/{category.dir}/" in path_str:
            return True
    return False
```

### 4. Update Config Schema

**File**: `config-schema.json`

Document required vs optional categories in schema description:

```json
"categories": {
  "type": "object",
  "description": "Issue category definitions. Required categories (bugs, features, enhancements) are automatically included if not specified. Additional categories can be added.",
  ...
}
```

### 5. Add Helper Methods

**File**: `scripts/little_loops/config.py`

Add methods to `IssuesConfig` for common operations:

```python
def get_category_by_prefix(self, prefix: str) -> CategoryConfig | None:
    """Get category config by prefix (e.g., 'BUG', 'FEAT')."""
    for category in self.categories.values():
        if category.prefix == prefix:
            return category
    return None

def get_category_by_dir(self, dir_name: str) -> CategoryConfig | None:
    """Get category config by directory name."""
    for category in self.categories.values():
        if category.dir == dir_name:
            return category
    return None

def get_all_prefixes(self) -> list[str]:
    """Get all configured issue type prefixes."""
    return [cat.prefix for cat in self.categories.values()]
```

## Location

- **Modified**: `scripts/little_loops/config.py` - Add REQUIRED_CATEGORIES, validation, helpers
- **Modified**: `scripts/little_loops/issue_discovery.py` - Config-driven type matching
- **Modified**: `config-schema.json` - Document required vs optional
- **Modified**: `README.md` - Document custom category configuration

## Current Behavior

- Three hardcoded issue types: BUG, FEAT, ENH
- Type matching in `issue_discovery.py` uses hardcoded conditions
- Users cannot add custom types without code changes
- No validation that required types exist

## Expected Behavior

- Core types (BUG, FEAT, ENH) always exist and cannot be removed
- Type matching dynamically uses configured categories
- Users can add custom types via config:
  ```json
  {
    "issues": {
      "categories": {
        "documentation": {"prefix": "DOC", "dir": "documentation", "action": "document"},
        "chores": {"prefix": "CHORE", "dir": "chores", "action": "complete"}
      }
    }
  }
  ```
- Config validation ensures required types present

## Acceptance Criteria

- [ ] REQUIRED_CATEGORIES constant defined in config.py
- [ ] Config validation ensures required categories exist
- [ ] issue_discovery.py uses config-driven type matching
- [ ] Helper methods added to IssuesConfig
- [ ] config-schema.json documents required vs optional
- [ ] README.md documents custom category configuration
- [ ] Existing tests pass
- [ ] New tests for custom category handling
- [ ] Integration test: custom DOC type works without code changes

## Impact

- **Severity**: Medium - Architectural improvement
- **Effort**: Medium - Multiple files, requires careful refactoring
- **Risk**: Low - Maintains backwards compatibility

## Dependencies

None

## Blocked By

None

## Blocks

None - FEAT-032 can proceed independently but will benefit from this

## Related

- FEAT-032: Add DOC Issue Type (independent but related)

## Labels

`feature`, `configuration`, `architecture`, `issue-management`

---

## Status

**Open** | Created: 2026-01-12 | Priority: P2
