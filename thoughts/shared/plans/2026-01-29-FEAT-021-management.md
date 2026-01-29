# FEAT-021: Goals/Vision Ingestion Mechanism - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-021-goals-vision-ingestion-mechanism.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

Based on research findings:

### Key Discoveries
- Template file `templates/ll-goals-template.md` already exists (created in FEAT-020)
- Config schema `config-schema.json:500-526` has `product` section with `enabled`, `goals_file`, `analyze_user_impact`, `analyze_business_value` but does NOT have `goals_discovery` settings
- `/ll:init` command at `commands/init.md:351-387` creates goals file when product enabled, but has no auto-discovery from documentation
- Pattern for YAML frontmatter parsing exists at `scripts/little_loops/issue_parser.py:287-325`
- Dataclass pattern with `from_dict`/`to_dict` established at `scripts/little_loops/issue_parser.py:76-134`
- Validation pattern established at `scripts/little_loops/fsm/validation.py:29-70`
- Test fixtures pattern at `scripts/tests/conftest.py:14-71`

### Current Behavior
- No `goals_parser.py` module exists
- No mechanism for parsing product goals from `ll-goals.md`
- No auto-discovery of goals from existing documentation (README.md, etc.)
- The `/ll:init` command simply copies the template without extracting content from existing docs

### Patterns to Follow
- Use YAML frontmatter parsing similar to `issue_parser.py:287-325`
- Use `yaml.safe_load()` for full YAML parsing (as in `fsm/validation.py:294-345`)
- Use dataclass pattern with `from_file()` class method (similar to `from_dict` pattern)
- Return structured validation errors as `list[str]` (simpler than ValidationError for this use case)

## Desired End State

After implementation:
1. `scripts/little_loops/goals_parser.py` exists with:
   - `Persona` dataclass
   - `Priority` dataclass
   - `ProductGoals` dataclass with `from_file()` class method
   - `validate_goals()` function returning list of warnings

2. Unit tests cover all acceptance criteria

3. Config schema includes `goals_discovery` settings

4. `/ll:init` auto-discovers goals from documentation when product analysis enabled

### How to Verify
- All unit tests pass: `python -m pytest scripts/tests/test_goals_parser.py -v`
- Lint passes: `ruff check scripts/little_loops/goals_parser.py`
- Types pass: `python -m mypy scripts/little_loops/goals_parser.py`
- Parser correctly parses the existing template file

## What We're NOT Doing

- Not implementing the Product Analyzer Agent (FEAT-022) - that's a downstream feature
- Not implementing Product Scanning Integration (FEAT-023) - that's a downstream feature
- Not implementing Product Impact Fields in Issue Templates (ENH-024) - that's a downstream feature
- Not adding CLI tools for goals management - keeping scope minimal
- Not implementing the full LLM-based extraction from documentation - that requires the AI agent during init; we'll provide the structure for it

## Problem Analysis

The goals parser is a foundational piece that enables product-focused analysis. It needs to:
1. Parse structured YAML frontmatter (persona, priorities)
2. Provide the full markdown content for LLM context
3. Validate that minimum required content is present
4. Return None gracefully when file doesn't exist or is malformed

## Solution Approach

Create a minimal, focused parser module following established patterns:
1. Use `yaml` library for reliable YAML parsing (it's already used elsewhere in the codebase)
2. Create dataclasses for type safety
3. Provide class methods for file-based construction
4. Separate parsing from validation for flexibility

## Implementation Phases

### Phase 1: Create goals_parser.py Module

#### Overview
Create the core parser module with dataclasses and parsing logic.

#### Changes Required

**File**: `scripts/little_loops/goals_parser.py`
**Changes**: Create new module

```python
"""Parser for ll-goals.md product goals document.

Provides structured access to product goals including persona and priorities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Persona:
    """Primary user persona.

    Attributes:
        id: Unique identifier for the persona
        name: Display name
        role: Description of the persona's role
    """

    id: str
    name: str
    role: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Persona:
        """Create Persona from dictionary."""
        return cls(
            id=data.get("id", "user"),
            name=data.get("name", "User"),
            role=data.get("role", ""),
        )


@dataclass
class Priority:
    """Strategic priority.

    Attributes:
        id: Unique identifier for the priority
        name: Description of the priority
    """

    id: str
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> Priority:
        """Create Priority from dictionary."""
        return cls(
            id=data.get("id", f"priority-{index}"),
            name=data.get("name", ""),
        )


@dataclass
class ProductGoals:
    """Parsed product goals from ll-goals.md.

    Attributes:
        version: Schema version of the goals file
        persona: Primary user persona (may be None)
        priorities: List of strategic priorities
        raw_content: Full markdown content for LLM context
    """

    version: str
    persona: Persona | None
    priorities: list[Priority] = field(default_factory=list)
    raw_content: str = ""

    @classmethod
    def from_file(cls, path: Path) -> ProductGoals | None:
        """Parse goals from ll-goals.md file.

        Args:
            path: Path to the goals file

        Returns:
            ProductGoals instance or None if file doesn't exist or is invalid
        """
        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        return cls.from_content(content)

    @classmethod
    def from_content(cls, content: str) -> ProductGoals | None:
        """Parse goals from string content.

        Args:
            content: Raw file content

        Returns:
            ProductGoals instance or None if content is invalid
        """
        if not content or not content.startswith("---"):
            return None

        # Find closing frontmatter delimiter
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_text = parts[1].strip()
        if not frontmatter_text:
            return None

        try:
            frontmatter = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError:
            return None

        if not isinstance(frontmatter, dict):
            return None

        # Parse persona
        persona = None
        persona_data = frontmatter.get("persona")
        if persona_data and isinstance(persona_data, dict):
            persona = Persona.from_dict(persona_data)

        # Parse priorities
        priorities: list[Priority] = []
        priorities_data = frontmatter.get("priorities", [])
        if isinstance(priorities_data, list):
            for i, p in enumerate(priorities_data, 1):
                if isinstance(p, dict):
                    priorities.append(Priority.from_dict(p, i))

        return cls(
            version=str(frontmatter.get("version", "1.0")),
            persona=persona,
            priorities=priorities,
            raw_content=content,
        )

    def is_valid(self) -> bool:
        """Check if goals have minimum required content.

        Returns:
            True if persona and at least one priority are defined
        """
        return self.persona is not None and len(self.priorities) > 0


def validate_goals(goals: ProductGoals) -> list[str]:
    """Validate product goals and return warnings.

    Args:
        goals: ProductGoals instance to validate

    Returns:
        List of validation warning messages (empty if valid)
    """
    warnings: list[str] = []

    if not goals.persona:
        warnings.append("No persona defined - product analysis may be less effective")

    if not goals.priorities:
        warnings.append("No priorities defined - cannot assess goal alignment")
    elif len(goals.priorities) > 5:
        warnings.append(
            "More than 5 priorities defined - consider focusing on top priorities"
        )

    if "[NEEDS REVIEW]" in goals.raw_content:
        warnings.append("File contains [NEEDS REVIEW] placeholders - please update")

    # Check for empty priority names
    for i, priority in enumerate(goals.priorities, 1):
        if not priority.name or priority.name == "Primary goal description":
            warnings.append(f"Priority {i} has placeholder or empty name")
        if not priority.name or priority.name == "Secondary goal description":
            # Only warn once per unique placeholder
            if f"Priority {i} has placeholder or empty name" not in warnings:
                warnings.append(f"Priority {i} has placeholder or empty name")

    # Check for template persona
    if goals.persona and goals.persona.role == "Software developer using this project":
        warnings.append("Persona has template description - please customize")

    return warnings
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `ls scripts/little_loops/goals_parser.py`
- [ ] Lint passes: `ruff check scripts/little_loops/goals_parser.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/goals_parser.py`
- [ ] Module imports: `python -c "from little_loops.goals_parser import ProductGoals, validate_goals"`

**Manual Verification**:
- [ ] Code follows established patterns from issue_parser.py

---

### Phase 2: Add Unit Tests

#### Overview
Create comprehensive unit tests for the goals parser module.

#### Changes Required

**File**: `scripts/tests/test_goals_parser.py`
**Changes**: Create new test module

```python
"""Tests for goals_parser module."""

from pathlib import Path
from typing import Generator
import tempfile

import pytest

from little_loops.goals_parser import (
    Persona,
    Priority,
    ProductGoals,
    validate_goals,
)


class TestPersona:
    """Tests for Persona dataclass."""

    def test_from_dict_full(self) -> None:
        """Test creating Persona with all fields."""
        data = {"id": "developer", "name": "Developer", "role": "Software engineer"}
        persona = Persona.from_dict(data)

        assert persona.id == "developer"
        assert persona.name == "Developer"
        assert persona.role == "Software engineer"

    def test_from_dict_defaults(self) -> None:
        """Test creating Persona with missing fields uses defaults."""
        persona = Persona.from_dict({})

        assert persona.id == "user"
        assert persona.name == "User"
        assert persona.role == ""


class TestPriority:
    """Tests for Priority dataclass."""

    def test_from_dict_full(self) -> None:
        """Test creating Priority with all fields."""
        data = {"id": "perf", "name": "Improve performance"}
        priority = Priority.from_dict(data)

        assert priority.id == "perf"
        assert priority.name == "Improve performance"

    def test_from_dict_defaults(self) -> None:
        """Test creating Priority with missing fields uses defaults."""
        priority = Priority.from_dict({}, index=3)

        assert priority.id == "priority-3"
        assert priority.name == ""


class TestProductGoals:
    """Tests for ProductGoals dataclass."""

    @pytest.fixture
    def valid_goals_content(self) -> str:
        """Valid goals file content."""
        return '''---
version: "1.0"
persona:
  id: developer
  name: "Developer"
  role: "Software engineer building apps"
priorities:
  - id: priority-1
    name: "Improve developer experience"
  - id: priority-2
    name: "Reduce build times"
---

# Product Vision

## About This Project

A tool to help developers work faster.
'''

    @pytest.fixture
    def minimal_goals_content(self) -> str:
        """Minimal valid goals file content."""
        return '''---
version: "1.0"
persona:
  id: user
  name: "User"
  role: "Generic user"
priorities:
  - id: p1
    name: "Main goal"
---

# Vision
'''

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_from_file_valid(self, temp_dir: Path, valid_goals_content: str) -> None:
        """Test parsing valid ll-goals.md file."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text(valid_goals_content)

        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.version == "1.0"
        assert goals.persona is not None
        assert goals.persona.id == "developer"
        assert goals.persona.name == "Developer"
        assert goals.persona.role == "Software engineer building apps"
        assert len(goals.priorities) == 2
        assert goals.priorities[0].name == "Improve developer experience"
        assert goals.priorities[1].name == "Reduce build times"
        assert "# Product Vision" in goals.raw_content

    def test_from_file_minimal(self, temp_dir: Path, minimal_goals_content: str) -> None:
        """Test parsing minimal ll-goals.md with only required fields."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text(minimal_goals_content)

        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.version == "1.0"
        assert goals.persona is not None
        assert len(goals.priorities) == 1

    def test_from_file_missing(self, temp_dir: Path) -> None:
        """Test handling missing file gracefully."""
        goals_file = temp_dir / "nonexistent.md"

        goals = ProductGoals.from_file(goals_file)

        assert goals is None

    def test_from_file_malformed_yaml(self, temp_dir: Path) -> None:
        """Test handling malformed YAML frontmatter."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text("""---
persona:
  id: [unclosed bracket
---
""")

        goals = ProductGoals.from_file(goals_file)

        assert goals is None

    def test_from_file_missing_frontmatter(self, temp_dir: Path) -> None:
        """Test handling file without frontmatter."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text("# Just a heading\n\nNo frontmatter here.")

        goals = ProductGoals.from_file(goals_file)

        assert goals is None

    def test_from_file_empty_frontmatter(self, temp_dir: Path) -> None:
        """Test handling file with empty frontmatter."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text("""---
---

# Content
""")

        goals = ProductGoals.from_file(goals_file)

        assert goals is None

    def test_from_file_no_closing_delimiter(self, temp_dir: Path) -> None:
        """Test handling file with unclosed frontmatter."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text("""---
version: "1.0"
persona:
  id: user
""")

        goals = ProductGoals.from_file(goals_file)

        assert goals is None

    def test_from_content_direct(self, valid_goals_content: str) -> None:
        """Test parsing from string content directly."""
        goals = ProductGoals.from_content(valid_goals_content)

        assert goals is not None
        assert goals.persona is not None
        assert len(goals.priorities) == 2

    def test_from_content_empty(self) -> None:
        """Test parsing empty content."""
        goals = ProductGoals.from_content("")

        assert goals is None

    def test_is_valid_true(self, temp_dir: Path, valid_goals_content: str) -> None:
        """Test is_valid returns True for complete goals."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text(valid_goals_content)
        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.is_valid() is True

    def test_is_valid_no_persona(self, temp_dir: Path) -> None:
        """Test is_valid returns False without persona."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text("""---
version: "1.0"
priorities:
  - id: p1
    name: "Goal"
---
""")
        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.is_valid() is False

    def test_is_valid_no_priorities(self, temp_dir: Path) -> None:
        """Test is_valid returns False without priorities."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text("""---
version: "1.0"
persona:
  id: user
  name: "User"
  role: "Role"
---
""")
        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.is_valid() is False

    def test_version_defaults(self, temp_dir: Path) -> None:
        """Test version defaults to 1.0 if not specified."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text("""---
persona:
  id: user
  name: "User"
  role: "Role"
priorities:
  - id: p1
    name: "Goal"
---
""")
        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.version == "1.0"


class TestValidateGoals:
    """Tests for validate_goals function."""

    def test_validate_valid_goals(self) -> None:
        """Test validation returns no warnings for valid goals."""
        goals = ProductGoals(
            version="1.0",
            persona=Persona(id="dev", name="Developer", role="Engineer"),
            priorities=[Priority(id="p1", name="Improve DX")],
            raw_content="# Content",
        )

        warnings = validate_goals(goals)

        assert len(warnings) == 0

    def test_validate_no_persona(self) -> None:
        """Test validation warns about missing persona."""
        goals = ProductGoals(
            version="1.0",
            persona=None,
            priorities=[Priority(id="p1", name="Goal")],
            raw_content="",
        )

        warnings = validate_goals(goals)

        assert any("No persona defined" in w for w in warnings)

    def test_validate_no_priorities(self) -> None:
        """Test validation warns about missing priorities."""
        goals = ProductGoals(
            version="1.0",
            persona=Persona(id="user", name="User", role="Role"),
            priorities=[],
            raw_content="",
        )

        warnings = validate_goals(goals)

        assert any("No priorities defined" in w for w in warnings)

    def test_validate_too_many_priorities(self) -> None:
        """Test validation warns about too many priorities."""
        goals = ProductGoals(
            version="1.0",
            persona=Persona(id="user", name="User", role="Role"),
            priorities=[Priority(id=f"p{i}", name=f"Goal {i}") for i in range(6)],
            raw_content="",
        )

        warnings = validate_goals(goals)

        assert any("More than 5 priorities" in w for w in warnings)

    def test_validate_needs_review_placeholder(self) -> None:
        """Test validation warns about [NEEDS REVIEW] placeholders."""
        goals = ProductGoals(
            version="1.0",
            persona=Persona(id="user", name="User", role="Role"),
            priorities=[Priority(id="p1", name="Goal")],
            raw_content="# Vision\n\n[NEEDS REVIEW] section here",
        )

        warnings = validate_goals(goals)

        assert any("[NEEDS REVIEW]" in w for w in warnings)

    def test_validate_template_persona(self) -> None:
        """Test validation warns about template persona description."""
        goals = ProductGoals(
            version="1.0",
            persona=Persona(
                id="developer",
                name="Developer",
                role="Software developer using this project",
            ),
            priorities=[Priority(id="p1", name="Goal")],
            raw_content="",
        )

        warnings = validate_goals(goals)

        assert any("template description" in w for w in warnings)

    def test_validate_placeholder_priority_name(self) -> None:
        """Test validation warns about placeholder priority names."""
        goals = ProductGoals(
            version="1.0",
            persona=Persona(id="user", name="User", role="Custom role"),
            priorities=[Priority(id="p1", name="Primary goal description")],
            raw_content="",
        )

        warnings = validate_goals(goals)

        assert any("placeholder or empty name" in w for w in warnings)
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `ls scripts/tests/test_goals_parser.py`
- [ ] Tests pass: `python -m pytest scripts/tests/test_goals_parser.py -v`
- [ ] All acceptance criteria tests included

**Manual Verification**:
- [ ] Tests cover all acceptance criteria from the issue

---

### Phase 3: Update Config Schema

#### Overview
Add `goals_discovery` settings to the config schema.

#### Changes Required

**File**: `config-schema.json`
**Changes**: Add `goals_discovery` nested object inside `product` section

Add after `analyze_business_value` (around line 523):

```json
        "goals_discovery": {
          "type": "object",
          "description": "Settings for auto-discovering product goals from documentation",
          "properties": {
            "max_files": {
              "type": "integer",
              "description": "Maximum markdown files to analyze for goal discovery",
              "default": 5,
              "minimum": 1,
              "maximum": 20
            },
            "required_files": {
              "type": "array",
              "description": "Files that must exist for discovery (warning if missing)",
              "items": {"type": "string"},
              "default": ["README.md"]
            }
          },
          "additionalProperties": false
        }
```

#### Success Criteria

**Automated Verification**:
- [ ] Schema is valid JSON: `python -c "import json; json.load(open('config-schema.json'))"`
- [ ] Schema validates: `python -c "import jsonschema; jsonschema.Draft7Validator.check_schema(json.load(open('config-schema.json')))"`

**Manual Verification**:
- [ ] New settings appear in correct location within `product` section

---

### Phase 4: Integrate Goals Discovery into /ll:init

#### Overview
Update the init command to support auto-discovery of goals from documentation.

#### Changes Required

**File**: `commands/init.md`
**Changes**: Update Step 5d (Product Analysis) to include auto-discovery flow

Replace the "If 'Yes, enable' selected" section (around lines 367-378) with enhanced logic:

The updated section should:

1. When product analysis is enabled in interactive mode:
   - Scan for documentation files (README.md, docs/*.md, etc.)
   - Present option to auto-discover or start from template
   - If auto-discover selected, analyze docs and generate populated goals file
   - If template selected, copy template as before

2. When product analysis is enabled in non-interactive mode (--yes):
   - Attempt auto-discovery from README.md
   - Generate goals file with extracted content
   - Warn about any [NEEDS REVIEW] sections

This is primarily a documentation/instruction update since init.md is a command definition that guides Claude's behavior, not executable code.

#### Success Criteria

**Automated Verification**:
- [ ] File parses correctly (no syntax errors)
- [ ] Lint passes on any code examples

**Manual Verification**:
- [ ] Auto-discovery flow is clearly documented
- [ ] Both interactive and non-interactive flows are covered
- [ ] Fallback to template is handled

---

## Testing Strategy

### Unit Tests
- Test Persona creation from dict with full and partial data
- Test Priority creation from dict with full and partial data
- Test ProductGoals parsing from valid file
- Test ProductGoals parsing from minimal file
- Test ProductGoals returns None for missing file
- Test ProductGoals returns None for malformed YAML
- Test ProductGoals returns None for missing frontmatter
- Test is_valid() returns correct boolean
- Test validate_goals() returns appropriate warnings

### Integration Tests
- Test parsing the actual template file: `templates/ll-goals-template.md`
- Test that warnings are generated for template file (has placeholders)

## References

- Original issue: `.issues/features/P2-FEAT-021-goals-vision-ingestion-mechanism.md`
- Existing parser pattern: `scripts/little_loops/issue_parser.py:287-325`
- Dataclass pattern: `scripts/little_loops/issue_parser.py:76-134`
- Validation pattern: `scripts/little_loops/fsm/validation.py:29-70`
- Goals template: `templates/ll-goals-template.md`
- Config schema: `config-schema.json:500-526`
- Init command: `commands/init.md:351-387`
