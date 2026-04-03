"""Feature-related configuration dataclasses.

Covers issue tracking, scanning, sprint management, loop management,
and sync configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Required categories that must always exist (cannot be removed by user config)
REQUIRED_CATEGORIES: dict[str, dict[str, str]] = {
    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
}

# Default categories (same as required by default, could include optional defaults)
DEFAULT_CATEGORIES: dict[str, dict[str, str]] = {
    **REQUIRED_CATEGORIES,
}


@dataclass
class CategoryConfig:
    """Configuration for an issue category."""

    prefix: str
    dir: str
    action: str = "fix"

    @classmethod
    def from_dict(cls, key: str, data: dict[str, Any]) -> CategoryConfig:
        """Create CategoryConfig from dictionary."""
        return cls(
            prefix=data.get("prefix", key.upper()[:3]),
            dir=data.get("dir", key),
            action=data.get("action", "fix"),
        )


@dataclass
class DuplicateDetectionConfig:
    """Thresholds for duplicate issue detection."""

    exact_threshold: float = 0.8
    similar_threshold: float = 0.5

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DuplicateDetectionConfig:
        """Create DuplicateDetectionConfig from dictionary."""
        return cls(
            exact_threshold=data.get("exact_threshold", 0.8),
            similar_threshold=data.get("similar_threshold", 0.5),
        )


@dataclass
class IssuesConfig:
    """Issue management configuration."""

    base_dir: str = ".issues"
    categories: dict[str, CategoryConfig] = field(default_factory=dict)
    completed_dir: str = "completed"
    deferred_dir: str = "deferred"
    priorities: list[str] = field(default_factory=lambda: ["P0", "P1", "P2", "P3", "P4", "P5"])
    templates_dir: str | None = None
    capture_template: str = "full"
    duplicate_detection: DuplicateDetectionConfig = field(default_factory=DuplicateDetectionConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssuesConfig:
        """Create IssuesConfig from dictionary.

        Required categories (bugs, features, enhancements) are automatically
        included if not specified in user config.
        """
        # Start with user categories or empty dict
        categories_data = dict(data.get("categories", {}))

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
            deferred_dir=data.get("deferred_dir", "deferred"),
            priorities=data.get("priorities", ["P0", "P1", "P2", "P3", "P4", "P5"]),
            templates_dir=data.get("templates_dir"),
            capture_template=data.get("capture_template", "full"),
            duplicate_detection=DuplicateDetectionConfig.from_dict(
                data.get("duplicate_detection", {})
            ),
        )

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


@dataclass
class ScanConfig:
    """Codebase scanning configuration."""

    focus_dirs: list[str] = field(default_factory=lambda: ["src/", "tests/"])
    exclude_patterns: list[str] = field(
        default_factory=lambda: ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"]
    )
    custom_agents: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScanConfig:
        """Create ScanConfig from dictionary."""
        return cls(
            focus_dirs=data.get("focus_dirs", ["src/", "tests/"]),
            exclude_patterns=data.get(
                "exclude_patterns",
                ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"],
            ),
            custom_agents=data.get("custom_agents", []),
        )


@dataclass
class SprintsConfig:
    """Sprint management configuration."""

    sprints_dir: str = ".sprints"
    default_timeout: int = 3600
    default_max_workers: int = 2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SprintsConfig:
        """Create SprintsConfig from dictionary."""
        return cls(
            sprints_dir=data.get("sprints_dir", ".sprints"),
            default_timeout=data.get("default_timeout", 3600),
            default_max_workers=data.get("default_max_workers", 2),
        )


@dataclass
class LoopsGlyphsConfig:
    """Unicode badge/glyph overrides for FSM box diagram state badges."""

    prompt: str = "\u2726"  # ✦
    slash_command: str = "/\u2501\u25ba"  # /━►
    shell: str = "\u276f_"  # ❯_
    mcp_tool: str = "\u26a1"  # ⚡
    sub_loop: str = "\u21b3\u27f3"  # ↳⟳
    route: str = "\u2443"  # ⑃

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopsGlyphsConfig:
        """Create LoopsGlyphsConfig from dictionary."""
        return cls(
            prompt=data.get("prompt", "\u2726"),
            slash_command=data.get("slash_command", "/\u2501\u25ba"),
            shell=data.get("shell", "\u276f_"),
            mcp_tool=data.get("mcp_tool", "\u26a1"),
            sub_loop=data.get("sub_loop", "\u21b3\u27f3"),
            route=data.get("route", "\u2443"),
        )

    def to_dict(self) -> dict[str, str]:
        """Convert to a glyph-key→string dict for use by _get_state_badge."""
        return {
            "prompt": self.prompt,
            "slash_command": self.slash_command,
            "shell": self.shell,
            "mcp_tool": self.mcp_tool,
            "sub_loop": self.sub_loop,
            "route": self.route,
        }


@dataclass
class LoopsConfig:
    """FSM loop configuration."""

    loops_dir: str = ".loops"
    glyphs: LoopsGlyphsConfig = field(default_factory=LoopsGlyphsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopsConfig:
        """Create LoopsConfig from dictionary."""
        return cls(
            loops_dir=data.get("loops_dir", ".loops"),
            glyphs=LoopsGlyphsConfig.from_dict(data.get("glyphs", {})),
        )


@dataclass
class GitHubSyncConfig:
    """GitHub-specific sync configuration."""

    repo: str | None = None
    label_mapping: dict[str, str] = field(
        default_factory=lambda: {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement"}
    )
    priority_labels: bool = True
    sync_completed: bool = False
    state_file: str = ".ll/ll-sync-state.json"
    pull_template: str = "minimal"
    pull_limit: int = 500

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GitHubSyncConfig:
        """Create GitHubSyncConfig from dictionary."""
        return cls(
            repo=data.get("repo"),
            label_mapping=data.get(
                "label_mapping", {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement"}
            ),
            priority_labels=data.get("priority_labels", True),
            sync_completed=data.get("sync_completed", False),
            state_file=data.get("state_file", ".ll/ll-sync-state.json"),
            pull_template=data.get("pull_template", "minimal"),
            pull_limit=data.get("pull_limit", 500),
        )


@dataclass
class SyncConfig:
    """Issue sync configuration."""

    enabled: bool = False
    provider: str = "github"
    github: GitHubSyncConfig = field(default_factory=GitHubSyncConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SyncConfig:
        """Create SyncConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            provider=data.get("provider", "github"),
            github=GitHubSyncConfig.from_dict(data.get("github", {})),
        )
