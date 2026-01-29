"""Tests for goals_parser module."""

import tempfile
from collections.abc import Generator
from pathlib import Path

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

    def test_from_file_minimal(
        self, temp_dir: Path, minimal_goals_content: str
    ) -> None:
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
        goals_file.write_text(
            """---
persona:
  id: [unclosed bracket
---
"""
        )

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
        goals_file.write_text(
            """---
---

# Content
"""
        )

        goals = ProductGoals.from_file(goals_file)

        assert goals is None

    def test_from_file_no_closing_delimiter(self, temp_dir: Path) -> None:
        """Test handling file with unclosed frontmatter."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text(
            """---
version: "1.0"
persona:
  id: user
"""
        )

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

    def test_is_valid_true(
        self, temp_dir: Path, valid_goals_content: str
    ) -> None:
        """Test is_valid returns True for complete goals."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text(valid_goals_content)
        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.is_valid() is True

    def test_is_valid_no_persona(self, temp_dir: Path) -> None:
        """Test is_valid returns False without persona."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text(
            """---
version: "1.0"
priorities:
  - id: p1
    name: "Goal"
---
"""
        )
        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.is_valid() is False

    def test_is_valid_no_priorities(self, temp_dir: Path) -> None:
        """Test is_valid returns False without priorities."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text(
            """---
version: "1.0"
persona:
  id: user
  name: "User"
  role: "Role"
---
"""
        )
        goals = ProductGoals.from_file(goals_file)

        assert goals is not None
        assert goals.is_valid() is False

    def test_version_defaults(self, temp_dir: Path) -> None:
        """Test version defaults to 1.0 if not specified."""
        goals_file = temp_dir / "ll-goals.md"
        goals_file.write_text(
            """---
persona:
  id: user
  name: "User"
  role: "Role"
priorities:
  - id: p1
    name: "Goal"
---
"""
        )
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

    def test_validate_empty_priority_name(self) -> None:
        """Test validation warns about empty priority names."""
        goals = ProductGoals(
            version="1.0",
            persona=Persona(id="user", name="User", role="Custom role"),
            priorities=[Priority(id="p1", name="")],
            raw_content="",
        )

        warnings = validate_goals(goals)

        assert any("placeholder or empty name" in w for w in warnings)


@pytest.mark.integration
class TestIntegration:
    """Integration tests using actual template file."""

    def test_parse_template_file(self) -> None:
        """Test parsing the actual goals template file."""
        # Find the template relative to this test file
        test_dir = Path(__file__).parent
        template_path = test_dir.parent.parent / "templates" / "ll-goals-template.md"

        if not template_path.exists():
            pytest.skip("Template file not found")

        goals = ProductGoals.from_file(template_path)

        assert goals is not None
        assert goals.version == "1.0"
        assert goals.persona is not None
        assert goals.persona.id == "developer"
        assert len(goals.priorities) == 2

    def test_template_file_has_warnings(self) -> None:
        """Test that template file generates appropriate warnings."""
        test_dir = Path(__file__).parent
        template_path = test_dir.parent.parent / "templates" / "ll-goals-template.md"

        if not template_path.exists():
            pytest.skip("Template file not found")

        goals = ProductGoals.from_file(template_path)
        assert goals is not None

        warnings = validate_goals(goals)

        # Template should have warnings about placeholders
        assert len(warnings) > 0
        # Should warn about template persona
        assert any("template description" in w for w in warnings)
        # Should warn about placeholder priority names
        assert any("placeholder or empty name" in w for w in warnings)
