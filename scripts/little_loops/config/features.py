"""Feature-related configuration dataclasses.

Covers issue tracking, scanning, sprint management, loop management,
and sync configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def feature_enabled(config_data: dict[str, Any], dot_path: str) -> bool:
    """Return whether the boolean flag at *dot_path* is enabled in *config_data*.

    Python port of ``hooks/scripts/lib/common.sh:ll_feature_enabled``. Operates
    on an already-parsed config dict (the bash version uses ``jq`` on the file).
    Mirrors jq's ``// false`` default: missing keys, non-dict intermediates, or
    non-truthy terminal values all yield ``False``.

    Examples:
        >>> feature_enabled({"context_monitor": {"enabled": True}}, "context_monitor.enabled")
        True
        >>> feature_enabled({"context_monitor": {"enabled": False}}, "context_monitor.enabled")
        False
        >>> feature_enabled({}, "sync.enabled")
        False
    """
    value: Any = config_data
    for part in dot_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return bool(value)


# Required categories that must always exist (cannot be removed by user config)
REQUIRED_CATEGORIES: dict[str, dict[str, str]] = {
    "bugs": {"prefix": "BUG", "dir": "bugs", "action": "fix"},
    "features": {"prefix": "FEAT", "dir": "features", "action": "implement"},
    "enhancements": {"prefix": "ENH", "dir": "enhancements", "action": "improve"},
    "epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"},
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


VALID_NEXT_ISSUE_STRATEGIES: frozenset[str] = frozenset({"confidence_first", "priority_first"})
VALID_NEXT_ISSUE_SORT_KEYS: frozenset[str] = frozenset(
    {
        "priority",
        "outcome_confidence",
        "confidence_score",
        "effort",
        "impact",
        "score_complexity",
        "score_test_coverage",
        "score_ambiguity",
        "score_change_surface",
    }
)
VALID_NEXT_ISSUE_SORT_DIRECTIONS: frozenset[str] = frozenset({"asc", "desc"})


@dataclass
class NextIssueSortKey:
    """A single (key, direction) pair for custom next-issue sort orderings."""

    key: str
    direction: str = "asc"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NextIssueSortKey:
        """Create NextIssueSortKey from dictionary, validating key/direction."""
        key = data.get("key")
        if key not in VALID_NEXT_ISSUE_SORT_KEYS:
            raise ValueError(f"Unknown sort key: {key!r}")
        direction = data.get("direction", "asc")
        if direction not in VALID_NEXT_ISSUE_SORT_DIRECTIONS:
            raise ValueError(f"Unknown sort direction: {direction!r}")
        return cls(key=key, direction=direction)


@dataclass
class NextIssueConfig:
    """Selection behavior for ll-issues next-issue / next-issues commands.

    Strategy presets:
    - "confidence_first" (default): sort by (-outcome_confidence, -confidence_score, priority_int)
    - "priority_first": sort by (priority_int, -outcome_confidence, -confidence_score)

    If sort_keys is provided, it overrides strategy.
    """

    strategy: str = "confidence_first"
    sort_keys: list[NextIssueSortKey] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NextIssueConfig:
        """Create NextIssueConfig from dictionary, validating strategy and sort_keys."""
        strategy = data.get("strategy", "confidence_first")
        if strategy not in VALID_NEXT_ISSUE_STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy!r}")
        sort_keys_data = data.get("sort_keys")
        sort_keys: list[NextIssueSortKey] | None
        if sort_keys_data is None:
            sort_keys = None
        else:
            sort_keys = [NextIssueSortKey.from_dict(entry) for entry in sort_keys_data]
        return cls(strategy=strategy, sort_keys=sort_keys)


@dataclass
class IssuesConfig:
    """Issue management configuration."""

    base_dir: str = ".issues"
    categories: dict[str, CategoryConfig] = field(default_factory=dict)
    completed_dir: str = "completed"  # DEPRECATED: use IssueInfo.status instead
    deferred_dir: str = "deferred"  # DEPRECATED: use IssueInfo.status instead
    priorities: list[str] = field(default_factory=lambda: ["P0", "P1", "P2", "P3", "P4", "P5"])
    templates_dir: str | None = None
    capture_template: str = "full"
    duplicate_detection: DuplicateDetectionConfig = field(default_factory=DuplicateDetectionConfig)
    next_issue: NextIssueConfig = field(default_factory=NextIssueConfig)

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
            completed_dir=data.get(
                "completed_dir", "completed"
            ),  # deprecated: kept for backward compat
            deferred_dir=data.get(
                "deferred_dir", "deferred"
            ),  # deprecated: kept for backward compat
            priorities=data.get("priorities", ["P0", "P1", "P2", "P3", "P4", "P5"]),
            templates_dir=data.get("templates_dir"),
            capture_template=data.get("capture_template", "full"),
            duplicate_detection=DuplicateDetectionConfig.from_dict(
                data.get("duplicate_detection", {})
            ),
            next_issue=NextIssueConfig.from_dict(data.get("next_issue", {})),
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
class LearningTestsConfig:
    """Learning test registry configuration."""

    stale_after_days: int = 30

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningTestsConfig:
        """Create LearningTestsConfig from dictionary."""
        return cls(
            stale_after_days=data.get("stale_after_days", 30),
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
    parallel: str = "\u2225"  # ∥

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
            parallel=data.get("parallel", "\u2225"),
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
            "parallel": self.parallel,
        }


@dataclass
class LoopsConfig:
    """FSM loop configuration."""

    loops_dir: str = ".loops"
    queue_wait_timeout_seconds: int = 86400
    glyphs: LoopsGlyphsConfig = field(default_factory=LoopsGlyphsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopsConfig:
        """Create LoopsConfig from dictionary."""
        return cls(
            loops_dir=data.get("loops_dir", ".loops"),
            queue_wait_timeout_seconds=data.get("queue_wait_timeout_seconds", 86400),
            glyphs=LoopsGlyphsConfig.from_dict(data.get("glyphs", {})),
        )


@dataclass
class GitHubSyncConfig:
    """GitHub-specific sync configuration."""

    repo: str | None = None
    label_mapping: dict[str, str] = field(
        default_factory=lambda: {
            "BUG": "bug",
            "FEAT": "enhancement",
            "ENH": "enhancement",
            "EPIC": "epic",
        }
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
                "label_mapping",
                {"BUG": "bug", "FEAT": "enhancement", "ENH": "enhancement", "EPIC": "epic"},
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


@dataclass
class SocketEventsConfig:
    """UnixSocketTransport configuration."""

    path: str = ".ll/events.sock"
    max_clients: int = 32

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SocketEventsConfig:
        """Create SocketEventsConfig from dictionary."""
        return cls(
            path=data.get("path", ".ll/events.sock"),
            max_clients=data.get("max_clients", 32),
        )


@dataclass
class OTelEventsConfig:
    """OTelTransport configuration."""

    endpoint: str = "http://localhost:4317"
    service_name: str = "little-loops"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OTelEventsConfig:
        """Create OTelEventsConfig from dictionary."""
        return cls(
            endpoint=data.get("endpoint", "http://localhost:4317"),
            service_name=data.get("service_name", "little-loops"),
        )


@dataclass
class WebhookEventsConfig:
    """WebhookTransport configuration."""

    url: str | None = None
    batch_ms: int = 1000
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WebhookEventsConfig:
        """Create WebhookEventsConfig from dictionary."""
        return cls(
            url=data.get("url", None),
            batch_ms=data.get("batch_ms", 1000),
            headers=data.get("headers", {}),
        )


@dataclass
class SqliteEventsConfig:
    """SQLiteTransport configuration (unified session store, FEAT-1112)."""

    path: str = ".ll/history.db"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SqliteEventsConfig:
        """Create SqliteEventsConfig from dictionary."""
        return cls(
            path=data.get("path", ".ll/history.db"),
        )


@dataclass
class EventsConfig:
    """Event transport configuration.

    Lists the transports to wire onto the EventBus at runtime. Names are
    resolved against the registry in `little_loops.transport.wire_transports`;
    unknown names are skipped with a warning.
    """

    transports: list[str] = field(default_factory=list)
    socket: SocketEventsConfig = field(default_factory=SocketEventsConfig)
    otel: OTelEventsConfig = field(default_factory=OTelEventsConfig)
    webhook: WebhookEventsConfig = field(default_factory=WebhookEventsConfig)
    sqlite: SqliteEventsConfig = field(default_factory=SqliteEventsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventsConfig:
        """Create EventsConfig from dictionary."""
        return cls(
            transports=data.get("transports", []),
            socket=SocketEventsConfig.from_dict(data.get("socket", {})),
            otel=OTelEventsConfig.from_dict(data.get("otel", {})),
            webhook=WebhookEventsConfig.from_dict(data.get("webhook", {})),
            sqlite=SqliteEventsConfig.from_dict(data.get("sqlite", {})),
        )
