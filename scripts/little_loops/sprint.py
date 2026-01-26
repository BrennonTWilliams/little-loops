"""Sprint and sequence management for issue execution."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo


@dataclass
class SprintOptions:
    """Execution options for sprint runs.

    Attributes:
        max_iterations: Maximum Claude iterations per issue
        timeout: Per-issue timeout in seconds
        max_workers: Worker count for parallel execution within waves
    """

    max_iterations: int = 100
    timeout: int = 3600
    max_workers: int = 4

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        return {
            "max_iterations": self.max_iterations,
            "timeout": self.timeout,
            "max_workers": self.max_workers,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "SprintOptions":
        """Create from dictionary (YAML deserialization).

        Args:
            data: Dictionary from YAML file or None for defaults

        Returns:
            SprintOptions instance
        """
        if data is None:
            return cls()
        return cls(
            max_iterations=data.get("max_iterations", 100),
            timeout=data.get("timeout", 3600),
            max_workers=data.get("max_workers", 4),
        )


@dataclass
class Sprint:
    """A sprint is a named group of issues to execute together.

    Sprints allow planning work in batches and executing them as a unit.
    Execution is always dependency-aware with parallel waves.

    Attributes:
        name: Sprint identifier (used as filename)
        description: Human-readable purpose
        issues: List of issue IDs (e.g., BUG-001, FEAT-010)
        created: ISO 8601 timestamp of creation
        options: Execution options (timeout, max_workers, etc.)
    """

    name: str
    description: str
    issues: list[str]
    created: str
    options: SprintOptions | None = None

    def to_dict(self) -> dict[str, str | list[str] | dict]:
        """Convert to dictionary for YAML serialization.

        Returns:
            Dictionary representation suitable for yaml.dump()
        """
        data: dict[str, str | list[str] | dict] = {
            "name": self.name,
            "description": self.description,
            "created": self.created,
            "issues": self.issues,
        }
        if self.options:
            data["options"] = self.options.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Sprint":
        """Create from dictionary (YAML deserialization).

        Args:
            data: Dictionary from YAML file

        Returns:
            Sprint instance
        """
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            issues=data.get("issues", []),
            created=data.get("created", datetime.now(UTC).isoformat()),
            options=SprintOptions.from_dict(data.get("options")),
        )

    def save(self, sprints_dir: Path) -> Path:
        """Save sprint to YAML file.

        Args:
            sprints_dir: Directory containing sprint definitions

        Returns:
            Path to saved file
        """
        sprints_dir.mkdir(parents=True, exist_ok=True)
        sprint_path = sprints_dir / f"{self.name}.yaml"
        with open(sprint_path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)
        return sprint_path

    @classmethod
    def load(cls, sprints_dir: Path, name: str) -> "Sprint | None":
        """Load sprint from YAML file.

        Args:
            sprints_dir: Directory containing sprint definitions
            name: Sprint name (without .yaml extension)

        Returns:
            Sprint instance or None if not found
        """
        sprint_path = sprints_dir / f"{name}.yaml"
        if not sprint_path.exists():
            return None
        with open(sprint_path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)


class SprintManager:
    """Manager for sprint CRUD operations.

    Provides methods to create, load, list, and delete sprint definitions.
    Also validates that issue IDs exist before executing sprints.
    """

    def __init__(self, sprints_dir: Path | None = None, config: "BRConfig | None" = None) -> None:
        """Initialize SprintManager.

        Args:
            sprints_dir: Directory for sprint definitions (overrides config)
            config: Project configuration for settings and issue validation
        """
        self.config = config
        # Derive sprints_dir: explicit arg > config > default
        if sprints_dir is not None:
            self.sprints_dir = sprints_dir
        elif config is not None:
            self.sprints_dir = Path(config.sprints.sprints_dir)
        else:
            self.sprints_dir = Path(".sprints")
        self.sprints_dir.mkdir(parents=True, exist_ok=True)

    def get_default_options(self) -> SprintOptions:
        """Get default SprintOptions from config or hardcoded defaults.

        Returns:
            SprintOptions with values from config if available, else defaults
        """
        if self.config is not None:
            return SprintOptions(
                timeout=self.config.sprints.default_timeout,
                max_workers=self.config.sprints.default_max_workers,
            )
        return SprintOptions()

    def create(
        self,
        name: str,
        issues: list[str],
        description: str = "",
        options: SprintOptions | None = None,
    ) -> Sprint:
        """Create a new sprint.

        Args:
            name: Sprint identifier
            issues: List of issue IDs
            description: Human-readable description
            options: Optional execution options

        Returns:
            Created Sprint instance
        """
        sprint = Sprint(
            name=name,
            description=description,
            issues=[i.strip().upper() for i in issues],
            created=datetime.now(UTC).isoformat(),
            options=options,
        )
        sprint.save(self.sprints_dir)
        return sprint

    def load(self, name: str) -> Sprint | None:
        """Load a sprint by name.

        Args:
            name: Sprint name

        Returns:
            Sprint instance or None if not found
        """
        return Sprint.load(self.sprints_dir, name)

    def list_all(self) -> list[Sprint]:
        """List all sprints.

        Returns:
            List of Sprint instances, sorted by name
        """
        sprints = []
        for path in sorted(self.sprints_dir.glob("*.yaml")):
            sprint = Sprint.load(self.sprints_dir, path.stem)
            if sprint:
                sprints.append(sprint)
        return sprints

    def delete(self, name: str) -> bool:
        """Delete a sprint.

        Args:
            name: Sprint name

        Returns:
            True if deleted, False if not found
        """
        sprint_path = self.sprints_dir / f"{name}.yaml"
        if not sprint_path.exists():
            return False
        sprint_path.unlink()
        return True

    def validate_issues(self, issues: list[str]) -> dict[str, Path]:
        """Validate that issue IDs exist.

        Args:
            issues: List of issue IDs to validate

        Returns:
            Dictionary mapping valid issue IDs to their file paths
        """
        if not self.config:
            # No config provided, skip validation
            return {}

        valid = {}
        for issue_id in issues:
            for category in ["bugs", "features", "enhancements"]:
                issue_dir = self.config.get_issue_dir(category)
                for path in issue_dir.glob(f"*-{issue_id}-*.md"):
                    valid[issue_id] = path
                    break
                if issue_id in valid:
                    break
        return valid

    def load_issue_infos(self, issues: list[str]) -> list["IssueInfo"]:
        """Load IssueInfo objects for the given issue IDs.

        Args:
            issues: List of issue IDs to load

        Returns:
            List of IssueInfo objects (only for issues that exist)
        """
        from little_loops.issue_parser import IssueParser

        if not self.config:
            return []

        parser = IssueParser(self.config)
        result: list[IssueInfo] = []
        for issue_id in issues:
            for category in ["bugs", "features", "enhancements"]:
                issue_dir = self.config.get_issue_dir(category)
                for path in issue_dir.glob(f"*-{issue_id}-*.md"):
                    try:
                        info = parser.parse_file(path)
                        result.append(info)
                        break
                    except Exception:
                        continue
                if any(i.issue_id == issue_id for i in result):
                    break
        return result
