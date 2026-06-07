"""Orchestration configuration dataclass.

Covers host CLI selection and related orchestration settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComposerAdaptiveConfig:
    """Tuning knobs for the adaptive loop-composer-adaptive built-in loop."""

    enabled: bool = False
    max_replans: int = 2
    reassess_min_confidence: float = 0.6

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComposerAdaptiveConfig:
        """Create ComposerAdaptiveConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            max_replans=data.get("max_replans", 2),
            reassess_min_confidence=data.get("reassess_min_confidence", 0.6),
        )


@dataclass
class ClusterConfig:
    """Settings for the goal-cluster multi-goal orchestration loop."""

    max_batch_size: int = 5
    enable_dedup: bool = True
    propagate_context: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClusterConfig:
        """Create ClusterConfig from dictionary."""
        return cls(
            max_batch_size=data.get("max_batch_size", 5),
            enable_dedup=data.get("enable_dedup", True),
            propagate_context=data.get("propagate_context", True),
        )


@dataclass
class ComposerConfig:
    """Settings for the loop-composer built-in orchestration loop."""

    adaptive: ComposerAdaptiveConfig = field(default_factory=ComposerAdaptiveConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComposerConfig:
        """Create ComposerConfig from dictionary."""
        return cls(
            adaptive=ComposerAdaptiveConfig.from_dict(data.get("adaptive", {})),
        )


@dataclass
class OrchestrationConfig:
    """Orchestration settings, primarily host CLI selection.

    ``host_cli`` mirrors the ``LL_HOST_CLI`` environment variable and is used
    by :func:`~little_loops.host_runner.apply_host_cli_from_config` to export
    the config value into the environment before :func:`~little_loops.host_runner.resolve_host`
    runs. The env var takes precedence if already set.
    """

    host_cli: str | None = None
    composer: ComposerConfig = field(default_factory=ComposerConfig)
    cluster: ClusterConfig = field(default_factory=ClusterConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationConfig:
        """Create OrchestrationConfig from dictionary."""
        return cls(
            host_cli=data.get("host_cli"),
            composer=ComposerConfig.from_dict(data.get("composer", {})),
            cluster=ClusterConfig.from_dict(data.get("cluster", {})),
        )
