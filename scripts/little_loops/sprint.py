"""Sprint and sequence management for issue execution."""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

logger = logging.getLogger(__name__)

_EPIC_ID_RE = re.compile(r"^EPIC-\d+$", re.IGNORECASE)
_ACTIVE_STATUSES: set[str] = {"open", "in_progress", "blocked"}

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
    max_workers: int = 2

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
            max_workers=data.get("max_workers", 2),
        )


@dataclass
class SprintState:
    """Persistent state for sprint execution.

    Enables resume capability after interruption by tracking:
    - Sprint name being executed
    - Current wave number
    - Completed issues
    - Failed issues with reasons
    - Timing information

    Attributes:
        sprint_name: Name of the sprint being executed
        current_wave: Wave number currently being processed (1-indexed)
        completed_issues: List of completed issue IDs
        failed_issues: Mapping of issue ID to failure reason
        timing: Per-issue timing breakdown
        started_at: ISO 8601 timestamp when sprint started
        last_checkpoint: ISO 8601 timestamp of last state save
    """

    sprint_name: str = ""
    current_wave: int = 0
    completed_issues: list[str] = field(default_factory=list)
    failed_issues: dict[str, str] = field(default_factory=dict)
    skipped_blocked_issues: dict[str, str] = field(default_factory=dict)
    timing: dict[str, dict[str, float]] = field(default_factory=dict)
    started_at: str = ""
    last_checkpoint: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for JSON serialization."""
        return {
            "sprint_name": self.sprint_name,
            "current_wave": self.current_wave,
            "completed_issues": self.completed_issues,
            "failed_issues": self.failed_issues,
            "skipped_blocked_issues": self.skipped_blocked_issues,
            "timing": self.timing,
            "started_at": self.started_at,
            "last_checkpoint": self.last_checkpoint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SprintState":
        """Create state from dictionary (JSON deserialization)."""
        return cls(
            sprint_name=data.get("sprint_name", ""),
            current_wave=data.get("current_wave", 0),
            completed_issues=data.get("completed_issues", []),
            failed_issues=data.get("failed_issues", {}),
            skipped_blocked_issues=data.get("skipped_blocked_issues", {}),
            timing=data.get("timing", {}),
            started_at=data.get("started_at", ""),
            last_checkpoint=data.get("last_checkpoint", ""),
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

    def load_or_resolve(self, arg: str) -> "Sprint | None":
        """Load a sprint by name or resolve an EPIC ID to an ephemeral Sprint.

        If `arg` matches ^EPIC-\\d+$ (case-insensitive), resolves the EPIC's
        active children via union of forward (relates_to:) and backward (parent:)
        lookups, filtered to active statuses and ordered by dependency graph.
        Otherwise falls through to the file-based load() path.

        Args:
            arg: Sprint name (file-based) or EPIC ID matching ^EPIC-\\d+$

        Returns:
            Sprint instance, or None if not found / EPIC not found
        """
        if not _EPIC_ID_RE.match(arg):
            return self.load(arg)

        epic_id = arg.upper()

        if not self.config:
            return self.load(arg)

        epic_path = self._find_issue_path(epic_id)
        if epic_path is None:
            return None

        from little_loops.issue_parser import IssueParser, find_issues

        parser = IssueParser(self.config)
        try:
            epic_info = parser.parse_file(epic_path)
        except Exception as e:
            logger.warning("Failed to parse EPIC file %s: %s", epic_path, e)
            return None

        # Forward lookup: relates_to on the EPIC file
        forward_ids: set[str] = set(epic_info.relates_to)

        # Backward lookup (ENH-2615): walk each active issue's parent: chain
        # transitively so grandchildren (e.g. follow-ups decomposed from a child
        # mid-run) resolve into the set — the same semantics
        # compute_epic_progress / _maybe_complete_epic use for the EPIC
        # completion gate, so run construction and closure agree on membership.
        # The parent map spans ALL statuses so a done intermediate (a decomposed
        # parent closed in place) still links its open children to the EPIC;
        # membership itself stays active-only.
        from little_loops.issue_progress import (
            _ALL_STATUSES,
            _issue_descends_to,
            build_parent_map,
        )

        all_active = find_issues(self.config, status_filter=_ACTIVE_STATUSES)
        parent_map = build_parent_map(find_issues(self.config, status_filter=set(_ALL_STATUSES)))
        backward_ids = {
            info.issue_id
            for info in all_active
            if _issue_descends_to(info.issue_id, epic_id, parent_map)
        }

        # Union + dedup; intersect with active set so forward refs to done issues are dropped
        active_ids_set = {info.issue_id for info in all_active}
        child_ids = (forward_ids | backward_ids) & active_ids_set
        child_infos = [info for info in all_active if info.issue_id in child_ids]

        sprint_name = f"epic-{epic_id.split('-', 1)[1]}"

        if not child_infos:
            logger.info("EPIC %s has no active children", epic_id)
            return Sprint(
                name=sprint_name,
                description=f"Resolved from {epic_id}",
                issues=[],
                created=datetime.now(UTC).isoformat(),
            )

        from little_loops.dependency_graph import DependencyGraph

        dep_graph = DependencyGraph.from_issues(child_infos, all_known_ids=active_ids_set)
        try:
            waves = dep_graph.get_execution_waves()
            ordered_ids = [issue.issue_id for wave in waves for issue in wave]
        except ValueError:
            ordered_ids = [
                info.issue_id
                for info in sorted(child_infos, key=lambda i: (i.priority or "P5", i.issue_id))
            ]

        return Sprint(
            name=sprint_name,
            description=f"Resolved from {epic_id}: {epic_info.title}",
            issues=ordered_ids,
            created=datetime.now(UTC).isoformat(),
        )

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

    def _find_issue_path(self, issue_id: str) -> Path | None:
        """Find the filesystem path for an issue ID.

        Searches all configured issue categories for a file matching the issue ID.

        Args:
            issue_id: Issue ID to locate (e.g. "BUG-001")

        Returns:
            Path to the issue file, or None if not found
        """
        if not self.config:
            return None
        for category in self.config.issue_categories:
            issue_dir = self.config.get_issue_dir(category)
            for path in issue_dir.glob(f"*-{issue_id}-*.md"):
                return path
        return None

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
            path = self._find_issue_path(issue_id)
            if path is not None:
                valid[issue_id] = path
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
            path = self._find_issue_path(issue_id)
            if path is not None:
                try:
                    info = parser.parse_file(path)
                    result.append(info)
                except Exception as e:
                    logger.warning("Failed to parse issue file %s: %s", path, e)
        return result
