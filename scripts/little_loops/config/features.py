"""Feature-related configuration dataclasses.

Covers issue tracking, scanning, sprint management, loop management,
and sync configuration.
"""

from __future__ import annotations

import fnmatch
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


def feature_enabled_for(
    config_data: dict[str, Any], dot_path: str, subject: str, default: bool = True
) -> bool:
    """Return whether *subject* matches the glob-pattern list at *dot_path* in *config_data*.

    Operates on a raw config dict (same as ``feature_enabled``). Resolves the value at
    *dot_path*; if absent or the intermediate path doesn't exist, returns *default*.
    The resolved value is normalised to a ``list[str]`` (bare string wrapped in a list,
    ``None`` treated as ``["*"]`` — match all) then tested with ``fnmatch.fnmatch``.

    Examples:
        >>> feature_enabled_for({"analytics": {"capture": {"skills": ["*"]}}},
        ...                     "analytics.capture.skills", "my-skill")
        True
        >>> feature_enabled_for({"analytics": {"capture": {"skills": ["Read"]}}},
        ...                     "analytics.capture.skills", "Write")
        False
        >>> feature_enabled_for({}, "analytics.capture.skills", "any")
        True
    """
    value: Any = config_data
    for part in dot_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]

    # Normalise to list[str]: None → match-all, str → [str], list used as-is
    if value is None:
        patterns: list[str] = ["*"]
    elif isinstance(value, str):
        patterns = [value]
    else:
        patterns = list(value)

    if not patterns:
        return default

    return any(fnmatch.fnmatch(subject, p) for p in patterns)


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
    auto_commit: bool = False
    auto_commit_prefix: str = "chore(issues)"

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
            auto_commit=data.get("auto_commit", False),
            auto_commit_prefix=data.get("auto_commit_prefix", "chore(issues)"),
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
class DesignTokensConfig:
    """Design system token configuration.

    `active` and `profiles_dir` (ENH-1768) select one of several bundled
    profiles. The loader resolves token files from
    `<path>/<profiles_dir or "profiles">/<active>/`, with a fallback to the
    legacy flat layout (`<path>/primitives.json`, ...) for pre-ENH-1768
    projects that haven't been re-initialized.
    """

    enabled: bool = True
    path: str = ".ll/design-tokens"
    primitives_file: str = "primitives.json"
    semantic_file: str = "semantic.json"
    themes_dir: str = "themes"
    active_theme: str = "dark"
    active: str = "default"
    profiles_dir: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DesignTokensConfig:
        """Create DesignTokensConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            path=data.get("path", ".ll/design-tokens"),
            primitives_file=data.get("primitives_file", "primitives.json"),
            semantic_file=data.get("semantic_file", "semantic.json"),
            themes_dir=data.get("themes_dir", "themes"),
            active_theme=data.get("active_theme", "dark"),
            active=data.get("active", "default"),
            profiles_dir=data.get("profiles_dir"),
        )


@dataclass
class ArtifactsConfig:
    """Configuration for `ll-artifact` artifact generators (FEAT-2301).

    `default_output_dir` is the directory where generated human-facing
    artifacts (HTML builders, diagrams, exporters) are written when no
    `--output` override is given. Shared across all `ll-artifact` subcommands.
    """

    default_output_dir: str = "."

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactsConfig:
        """Create ArtifactsConfig from dictionary."""
        return cls(
            default_output_dir=data.get("default_output_dir", "."),
        )


@dataclass
class SprintsConfig:
    """Sprint management configuration."""

    sprints_dir: str = ".sprints"
    default_timeout: int = 3600
    default_max_workers: int = 2
    max_issue_wall_clock_time: int = 2700

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SprintsConfig:
        """Create SprintsConfig from dictionary."""
        return cls(
            sprints_dir=data.get("sprints_dir", ".sprints"),
            default_timeout=data.get("default_timeout", 3600),
            default_max_workers=data.get("default_max_workers", 2),
            max_issue_wall_clock_time=data.get("max_issue_wall_clock_time", 2700),
        )


_CLOSED_UNIT_SIGNALS_DEFAULT: list[str] = [
    r"\bdone\b",
    r"\bcompleted\b",
    r"\bfixed\b",
    r"\bresolved\b",
]
_REDUCIBLE_SIGNALS_DEFAULT: list[str] = [
    r"\bin summary\b",
    r"\bto summarize\b",
    r"\boverall\b",
]
_PROGRESS_SIGNALS_DEFAULT: list[str] = [
    r"\bchanged\b",
    r"\bupdated\b",
    r"\bmodified\b",
    r"\bimplemented\b",
]
_STUCK_SIGNALS_DEFAULT: list[str] = [
    r"\bsame error\b",
    r"\bstill failing\b",
    r"\brepeat\b",
]


@dataclass
class RubricSignalsConfig:
    """Signal lists for each rubric condition in PreCompactRubricConfig (ENH-2341)."""

    closed_unit_signals: list[str] = field(
        default_factory=lambda: list(_CLOSED_UNIT_SIGNALS_DEFAULT)
    )
    reducible_signals: list[str] = field(default_factory=lambda: list(_REDUCIBLE_SIGNALS_DEFAULT))
    progress_signals: list[str] = field(default_factory=lambda: list(_PROGRESS_SIGNALS_DEFAULT))
    stuck_signals: list[str] = field(default_factory=lambda: list(_STUCK_SIGNALS_DEFAULT))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RubricSignalsConfig:
        """Create RubricSignalsConfig from dictionary."""
        return cls(
            closed_unit_signals=data.get("closed_unit_signals", list(_CLOSED_UNIT_SIGNALS_DEFAULT)),
            reducible_signals=data.get("reducible_signals", list(_REDUCIBLE_SIGNALS_DEFAULT)),
            progress_signals=data.get("progress_signals", list(_PROGRESS_SIGNALS_DEFAULT)),
            stuck_signals=data.get("stuck_signals", list(_STUCK_SIGNALS_DEFAULT)),
        )


@dataclass
class PreCompactRubricConfig:
    """Rubric-gated compaction timing configuration (ENH-2341).

    When enabled, the pre_compact hook evaluates four structural conditions over
    the recent transcript before writing state. All conditions must pass; any
    failure returns exit 0 (graceful defer). Disabled by default so existing
    threshold-only behaviour is preserved.
    """

    enabled: bool = False
    hard_ceiling_pct: float = 0.95
    signals: RubricSignalsConfig = field(default_factory=RubricSignalsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreCompactRubricConfig:
        """Create PreCompactRubricConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            hard_ceiling_pct=data.get("hard_ceiling_pct", 0.95),
            signals=RubricSignalsConfig.from_dict(data.get("signals", {})),
        )


@dataclass
class DiscoverabilityConfig:
    """Controls how learning-test gaps are surfaced during implementation."""

    mode: str = "warn"
    skip_packages: list[str] = field(default_factory=lambda: ["std", "typing", "os", "sys"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoverabilityConfig:
        """Create DiscoverabilityConfig from dictionary."""
        return cls(
            mode=data.get("mode", "warn"),
            skip_packages=data.get("skip_packages", ["std", "typing", "os", "sys"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize DiscoverabilityConfig to dictionary."""
        return {
            "mode": self.mode,
            "skip_packages": list(self.skip_packages),
        }


@dataclass
class LearningTestsConfig:
    """Learning test registry configuration."""

    enabled: bool = False
    auto_prove: bool = True
    stale_after_days: int = 30
    discoverability: DiscoverabilityConfig = field(default_factory=DiscoverabilityConfig)
    release_gate: str = "warn"
    scan_dirs: list[str] = field(default_factory=lambda: ["scripts/"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningTestsConfig:
        """Create LearningTestsConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            auto_prove=data.get("auto_prove", True),
            stale_after_days=data.get("stale_after_days", 30),
            discoverability=DiscoverabilityConfig.from_dict(data.get("discoverability", {})),
            release_gate=data.get("release_gate", "warn"),
            scan_dirs=data.get("scan_dirs", ["scripts/"]),
        )


@dataclass
class DecisionsConfig:
    """Decisions and rules log configuration."""

    enabled: bool = False
    log_path: str = ".ll/decisions.yaml"
    auto_generate: list[str] = field(default_factory=list)
    """Issue type prefixes to include during ``ll-issues decisions generate``.

    Empty list (default) generates entries for all completed issue types.
    Non-empty list restricts to the listed prefixes (e.g. ``["FEAT", "ENH"]``
    skips BUG entries).
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionsConfig:
        """Create DecisionsConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            log_path=data.get("log_path", ".ll/decisions.yaml"),
            auto_generate=data.get("auto_generate", []),
        )


@dataclass
class AnalyticsCaptureConfig:
    """Configuration for analytics capture gating (ENH-1840).

    Controls which skills, CLI commands, and event types are captured into the
    unified session store. Used by ENH-1841 write-path gating via
    ``feature_enabled_for()``.
    """

    skills: list[str] = field(default_factory=lambda: ["*"])
    cli_commands: list[str] = field(default_factory=lambda: ["*"])
    corrections: bool = True
    file_events: bool = True
    correction_patterns: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnalyticsCaptureConfig:
        """Create AnalyticsCaptureConfig from dictionary."""
        raw = data.get("correction_patterns", [])
        correction_patterns = (
            [p for p in raw if isinstance(p, str)] if isinstance(raw, list) else []
        )
        return cls(
            skills=data.get("skills", ["*"]),
            cli_commands=data.get("cli_commands", ["*"]),
            corrections=data.get("corrections", True),
            file_events=data.get("file_events", True),
            correction_patterns=correction_patterns,
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


_VALID_SHOW_DIAGRAMS: frozenset[str] = frozenset(
    {
        "layered",
        "neighborhood",
        "inline",  # topologies
        "detailed",
        "summary",
        "clean",
        "local",  # presets
        "slim",
        "oneline",  # presets (continued)
        "default",  # bare --show-diagrams sentinel
    }
)


@dataclass
class LoopRunDefaults:
    """Persistent CLI defaults for ``ll-loop run``."""

    clear: bool = False
    show_diagrams: str | None = None
    mode: str | None = None
    include: str = ""
    delay: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopRunDefaults:
        """Create LoopRunDefaults from dictionary, validating show_diagrams and delay."""
        show_diagrams = data.get("show_diagrams", None)
        if show_diagrams is not None and show_diagrams not in _VALID_SHOW_DIAGRAMS:
            raise ValueError(
                f"loops.run_defaults.show_diagrams: {show_diagrams!r} is not valid. "
                f"Valid values: {sorted(_VALID_SHOW_DIAGRAMS)}"
            )
        delay = data.get("delay", None)
        if delay is not None:
            if not isinstance(delay, (int, float)) or isinstance(delay, bool):
                raise ValueError(
                    f"loops.run_defaults.delay: {delay!r} is not valid. "
                    f"Expected a non-negative number of seconds."
                )
            if delay < 0:
                raise ValueError(
                    f"loops.run_defaults.delay: {delay!r} is not valid. "
                    f"Must be a non-negative number of seconds."
                )
        return cls(
            clear=data.get("clear", False),
            show_diagrams=show_diagrams,
            mode=data.get("mode", None),
            include=data.get("include", ""),
            delay=delay,
        )


@dataclass
class LoopsConfig:
    """FSM loop configuration."""

    loops_dir: str = ".loops"
    queue_wait_timeout_seconds: int = 86400
    glyphs: LoopsGlyphsConfig = field(default_factory=LoopsGlyphsConfig)
    run_defaults: LoopRunDefaults = field(default_factory=LoopRunDefaults)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoopsConfig:
        """Create LoopsConfig from dictionary."""
        return cls(
            loops_dir=data.get("loops_dir", ".loops"),
            queue_wait_timeout_seconds=data.get("queue_wait_timeout_seconds", 86400),
            glyphs=LoopsGlyphsConfig.from_dict(data.get("glyphs", {})),
            run_defaults=LoopRunDefaults.from_dict(data.get("run_defaults", {})),
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


@dataclass
class SessionDigestConfig:
    """Session digest injection configuration (ENH-1907)."""

    enabled: bool = True
    days: int = 7
    char_cap: int = 1200
    sections: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionDigestConfig:
        """Create SessionDigestConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            days=data.get("days", 7),
            char_cap=data.get("char_cap", 1200),
            sections=data.get("sections", []),
        )


@dataclass
class EvolutionConfig:
    """Feedback evolution configuration (ENH-1911)."""

    feedback_min_recurrence: int = 2
    bypass_min_count: int = 2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvolutionConfig:
        """Create EvolutionConfig from dictionary."""
        return cls(
            feedback_min_recurrence=data.get("feedback_min_recurrence", 2),
            bypass_min_count=data.get("bypass_min_count", 2),
        )


@dataclass
class GoNoGoConfig:
    """Go/no-go history configuration (ENH-1914)."""

    correction_penalty: float = -0.2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoNoGoConfig:
        """Create GoNoGoConfig from dictionary."""
        return cls(
            correction_penalty=data.get("correction_penalty", -0.2),
        )


@dataclass
class CaptureIssueConfig:
    """Capture-issue history configuration (ENH-1914)."""

    dup_overlap_threshold: float = 0.7

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaptureIssueConfig:
        """Create CaptureIssueConfig from dictionary."""
        return cls(
            dup_overlap_threshold=data.get("dup_overlap_threshold", 0.7),
        )


@dataclass
class CompactionConfig:
    """LCM-style compaction configuration for summary_nodes (FEAT-1712).

    Controls whether backfill() generates LLM summaries over message_events blocks
    via three-level LCM Algorithm 3 escalation (normal → aggressive bullet-point →
    deterministic truncation). Disabled by default to avoid background LLM calls
    without user opt-in.

    Cross-session condensation (ENH-1954): when ``cross_session_enabled`` is True
    (default), the compaction pass recurses over existing condensed nodes level by
    level, grouping by token budget and summarising each group until exactly one
    project-root summary node remains (``session_id IS NULL``, ``level = max``).
    """

    enabled: bool = False
    budget_tokens: int = 4096
    model: str | None = None
    timeout: int = 60
    cross_session_enabled: bool = True
    max_level: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompactionConfig:
        """Create CompactionConfig from dictionary. Lenient: ignores unknown keys."""
        return cls(
            enabled=data.get("enabled", False),
            budget_tokens=data.get("budget_tokens", 4096),
            model=data.get("model", None),
            timeout=data.get("timeout", 60),
            cross_session_enabled=data.get("cross_session_enabled", True),
            max_level=data.get("max_level", None),
        )


@dataclass
class RetentionConfig:
    """Retention policy for history.db raw event tables (ENH-1906).

    Pruning is dual-gated: both ``min_project_age_days`` and ``min_db_size_mb``
    must be exceeded before any rows are deleted. Default thresholds are generous
    so fresh or small projects are never affected.

    Only high-volume tables are pruned (tool_events, cli_events, file_events,
    message_events). High-value tables (issue_events, user_corrections) are
    never pruned.
    """

    min_project_age_days: int = 365
    min_db_size_mb: int = 800
    raw_event_max_age_days: int | None = 90

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetentionConfig:
        """Create RetentionConfig from dictionary. Lenient: ignores unknown keys."""
        return cls(
            min_project_age_days=data.get("min_project_age_days", 365),
            min_db_size_mb=data.get("min_db_size_mb", 800),
            raw_event_max_age_days=data.get("raw_event_max_age_days", 90),
        )


@dataclass
class HistoryConfig:
    """History read/consume configuration (ENH-1913).

    Single, consistent foundation for .ll/history.db read/consume configurability.
    Owns the complete history.* namespace; consumers wire runtime + CLI only.
    """

    velocity_window: int = 10
    effort_fields: list[str] = field(default_factory=lambda: ["session_count", "cycle_time_days"])
    max_age_days: int | None = None
    planning_skills: list[str] = field(
        default_factory=lambda: ["create-sprint", "scope-epic", "manage-issue", "review-epic"]
    )
    session_digest: SessionDigestConfig = field(default_factory=SessionDigestConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    go_no_go: GoNoGoConfig = field(default_factory=GoNoGoConfig)
    capture_issue: CaptureIssueConfig = field(default_factory=CaptureIssueConfig)
    compaction: CompactionConfig = field(default_factory=CompactionConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryConfig:
        """Create HistoryConfig from dictionary. Lenient: ignores unknown keys, never raises."""
        return cls(
            velocity_window=data.get("velocity_window", 10),
            effort_fields=data.get("effort_fields", ["session_count", "cycle_time_days"]),
            max_age_days=data.get("max_age_days", None),
            planning_skills=data.get(
                "planning_skills",
                ["create-sprint", "scope-epic", "manage-issue", "review-epic"],
            ),
            session_digest=SessionDigestConfig.from_dict(data.get("session_digest", {})),
            evolution=EvolutionConfig.from_dict(data.get("evolution", {})),
            go_no_go=GoNoGoConfig.from_dict(data.get("go_no_go", {})),
            capture_issue=CaptureIssueConfig.from_dict(data.get("capture_issue", {})),
            compaction=CompactionConfig.from_dict(data.get("compaction", {})),
        )
