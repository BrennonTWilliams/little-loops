# ENH-241: Consolidate Duplicated Frontmatter Parsing - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-241-consolidate-duplicated-frontmatter-parsing.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

There are **5 separate frontmatter parsing implementations** across the Python codebase:

1. **`issue_parser.py:338-376`** - `IssueParser._parse_frontmatter()` - full dict, no type coercion
2. **`sync.py:153-187`** - `_parse_issue_frontmatter()` - full dict, integer coercion via `isdigit()`
3. **`sync.py:190-241`** - `_update_issue_frontmatter()` - contains its own inline parser for existing fields
4. **`issue_history.py:848-874`** - `_parse_discovered_by()` - single-field extraction, same delimiter logic
5. **`issue_history.py:1123-1149`** - `_parse_discovered_date()` - single-field extraction with date coercion

All share identical delimiter detection: `re.search(r"\n---\s*\n", content[3:])` and offset arithmetic `content[4 : 3 + end_match.start()]`.

### Key Discoveries
- `_parse_frontmatter` is an instance method but never uses `self` (`issue_parser.py:338`)
- Both call sites for `_parse_issue_frontmatter` in `sync.py` redundantly wrap results in `int()` (lines 468, 627)
- `issue_history.py` has two single-field variants that duplicate the delimiter logic
- `_update_issue_frontmatter` also contains its own inline key:value parser (lines 220-228)
- `goals_parser.py` uses `yaml.safe_load` - deliberately different, not a candidate for consolidation

## Desired End State

A single shared `parse_frontmatter()` function in a new `frontmatter.py` module that all consumers use. The `issue_history.py` single-field helpers will use the shared parser internally.

### How to Verify
- All existing tests pass unchanged
- `_parse_issue_frontmatter` no longer exists in `sync.py`
- `IssueParser._parse_frontmatter` no longer exists in `issue_parser.py`
- `_parse_discovered_by` and `_parse_discovered_date` in `issue_history.py` use the shared parser
- `_update_issue_frontmatter` in `sync.py` uses the shared parser for reading existing fields

## What We're NOT Doing

- Not changing `goals_parser.py` - it uses `yaml.safe_load` for nested YAML, fundamentally different
- Not changing the shell `parse_frontmatter()` in `hooks/scripts/session-start.sh` - different language
- Not adding yaml dependency - keeping the simple key:value parser
- Not changing public API or behavior of any consumer
- Not modifying test fixtures

## Solution Approach

Create `scripts/little_loops/frontmatter.py` as a new shared utility module (following the `work_verification.py` and `subprocess_utils.py` pattern). Extract the core parsing logic there, with `coerce_types: bool = False` parameter for backward compatibility.

## Implementation Phases

### Phase 1: Create `frontmatter.py` Shared Module

#### Overview
Create the new module with the consolidated parsing function.

#### Changes Required

**File**: `scripts/little_loops/frontmatter.py` [CREATE]
**Changes**: New module with `parse_frontmatter()` function

```python
"""Frontmatter parsing utilities for little-loops.

Provides shared YAML-subset frontmatter parsing used by issue_parser,
sync, and issue_history modules.
"""

from __future__ import annotations

import re
from typing import Any


def parse_frontmatter(
    content: str, *, coerce_types: bool = False
) -> dict[str, Any]:
    """Extract YAML frontmatter from content.

    Looks for content between opening and closing '---' markers.
    Parses simple key: value pairs. Returns empty dict if no
    frontmatter found.

    Args:
        content: File content to parse
        coerce_types: If True, coerce digit strings to int

    Returns:
        Dictionary of frontmatter fields, or empty dict
    """
    if not content or not content.startswith("---"):
        return {}

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return {}

    frontmatter_text = content[4 : 3 + end_match.start()]

    result: dict[str, Any] = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.lower() in ("null", "~", ""):
                result[key] = None
            elif coerce_types and value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value
    return result
```

#### Success Criteria

**Automated Verification**:
- [ ] Module imports: `python -c "from little_loops.frontmatter import parse_frontmatter"`
- [ ] Lint passes: `ruff check scripts/little_loops/frontmatter.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/frontmatter.py`

---

### Phase 2: Replace `IssueParser._parse_frontmatter` in `issue_parser.py`

#### Overview
Replace the instance method with a call to the shared function.

#### Changes Required

**File**: `scripts/little_loops/issue_parser.py`
**Changes**:
1. Add import: `from little_loops.frontmatter import parse_frontmatter`
2. Remove `_parse_frontmatter` method (lines 338-376)
3. Update call site at line 228: `self._parse_frontmatter(content)` → `parse_frontmatter(content)`

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_parser.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_parser.py`

---

### Phase 3: Replace `_parse_issue_frontmatter` in `sync.py`

#### Overview
Replace the module-level function with a call to the shared function.

#### Changes Required

**File**: `scripts/little_loops/sync.py`
**Changes**:
1. Add import: `from little_loops.frontmatter import parse_frontmatter`
2. Remove `_parse_issue_frontmatter` function (lines 153-187)
3. Update call sites (lines 454, 624): `_parse_issue_frontmatter(content)` → `parse_frontmatter(content, coerce_types=True)`
4. Update `_update_issue_frontmatter` (lines 220-228) to use `parse_frontmatter(frontmatter_text_as_content)` - however, since this function needs the raw frontmatter text extracted differently, we'll instead have it call the shared function to parse the whole content, then merge updates. Actually - `_update_issue_frontmatter` needs to reconstruct the body separately, so it's better to just use `parse_frontmatter` for the reading portion and keep the reconstruction logic.

**File**: `scripts/tests/test_sync.py`
**Changes**:
1. Update import: `_parse_issue_frontmatter` → `parse_frontmatter` from `little_loops.frontmatter`
2. Update test calls to use `parse_frontmatter(content, coerce_types=True)`

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sync.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/sync.py`

---

### Phase 4: Simplify `issue_history.py` Single-Field Parsers

#### Overview
Replace duplicated delimiter logic in `_parse_discovered_by` and `_parse_discovered_date` with calls to the shared function.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**:
1. Add import: `from little_loops.frontmatter import parse_frontmatter`
2. Simplify `_parse_discovered_by` (lines 848-874):
   ```python
   def _parse_discovered_by(content: str) -> str | None:
       fm = parse_frontmatter(content)
       value = fm.get("discovered_by")
       return value if isinstance(value, str) else None
   ```
3. Simplify `_parse_discovered_date` (lines 1123-1149):
   ```python
   def _parse_discovered_date(content: str) -> date | None:
       fm = parse_frontmatter(content)
       value = fm.get("discovered_date")
       if not isinstance(value, str):
           return None
       try:
           return date.fromisoformat(value)
       except ValueError:
           return None
   ```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history_parsing.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`

---

### Phase 5: Simplify `_update_issue_frontmatter` in `sync.py`

#### Overview
Replace the inline parser inside `_update_issue_frontmatter` with the shared function.

#### Changes Required

**File**: `scripts/little_loops/sync.py`
**Changes**: In `_update_issue_frontmatter`, replace the inline parsing loop (lines 220-228) with a call to `parse_frontmatter`. Need to reconstruct the content prefix to pass to `parse_frontmatter`, or refactor to extract the frontmatter text and body separately first, then use the shared parser. The simplest approach: since we already have the frontmatter_text extracted, we can wrap it in `---\n{text}\n---\n` and pass to `parse_frontmatter`.

Actually, the cleanest approach: extract the frontmatter text and body as before, then build a temporary string `f"---\n{frontmatter_text}\n---\n"` and pass it to `parse_frontmatter()`.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sync.py::TestFrontmatterUpdating -v`

---

### Phase 6: Add Dedicated Tests for `parse_frontmatter`

#### Overview
Add a test file for the new shared module.

#### Changes Required

**File**: `scripts/tests/test_frontmatter.py` [CREATE]
**Changes**: Port the existing sync frontmatter parsing tests to test the shared function directly, covering both `coerce_types=False` and `coerce_types=True` modes.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_frontmatter.py -v`

---

### Phase 7: Full Verification

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- New `test_frontmatter.py` for the shared function
- Existing `test_sync.py` and `test_issue_parser.py` tests validate no behavioral regression

### Edge Cases
- Empty content, no frontmatter, malformed frontmatter (no closing `---`)
- Null/tilde/empty values → `None`
- `coerce_types=True` with digit strings → `int`
- `coerce_types=False` with digit strings → `str`

## References

- Original issue: `.issues/enhancements/P3-ENH-241-consolidate-duplicated-frontmatter-parsing.md`
- Existing consolidation pattern: `scripts/little_loops/work_verification.py` (commit accdeb2)
- Existing utility pattern: `scripts/little_loops/subprocess_utils.py`
