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
        """Create Persona from dictionary.

        Args:
            data: Dictionary with persona fields

        Returns:
            Persona instance
        """
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
        """Create Priority from dictionary.

        Args:
            data: Dictionary with priority fields
            index: Index for generating default ID

        Returns:
            Priority instance
        """
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
        warnings.append("More than 5 priorities defined - consider focusing on top priorities")

    if "[NEEDS REVIEW]" in goals.raw_content:
        warnings.append("File contains [NEEDS REVIEW] placeholders - please update")

    # Check for template placeholder priority names
    template_placeholders = {"Primary goal description", "Secondary goal description"}
    for i, priority in enumerate(goals.priorities, 1):
        if not priority.name or priority.name in template_placeholders:
            warnings.append(f"Priority {i} has placeholder or empty name")

    # Check for template persona
    if goals.persona and goals.persona.role == "Software developer using this project":
        warnings.append("Persona has template description - please customize")

    return warnings
