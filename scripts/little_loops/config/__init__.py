"""Configuration management for little-loops.

Provides the BRConfig class for loading, merging, and accessing project configuration.
Configuration is read from .ll/ll-config.json and merged with sensible defaults.

This package is organized into domain-specific modules:
  core.py       — ProjectConfig, BRConfig (root aggregator)
  cli.py        — CLI color and display configuration
  features.py   — Issue tracking, scanning, sprints, loops, sync
  automation.py — Parallel execution, commands, dependency analysis
"""

from little_loops.config.automation import (
    AutomationConfig,
    CommandsConfig,
    ConfidenceGateConfig,
    DependencyMappingConfig,
    ParallelAutomationConfig,
    RateLimitsConfig,
    ScoringWeightsConfig,
)
from little_loops.config.cli import (
    CliColorsConfig,
    CliColorsEdgeLabelsConfig,
    CliColorsLoggerConfig,
    CliColorsPriorityConfig,
    CliColorsTypeConfig,
    CliConfig,
    RefineStatusConfig,
)
from little_loops.config.core import BRConfig, CLConfig, ProjectConfig
from little_loops.config.features import (
    DEFAULT_CATEGORIES,
    REQUIRED_CATEGORIES,
    CategoryConfig,
    DuplicateDetectionConfig,
    GitHubSyncConfig,
    IssuesConfig,
    LoopsConfig,
    LoopsGlyphsConfig,
    ScanConfig,
    SprintsConfig,
    SyncConfig,
)

__all__ = [
    "BRConfig",
    "CLConfig",
    "CategoryConfig",
    "ProjectConfig",
    "IssuesConfig",
    "AutomationConfig",
    "ParallelAutomationConfig",
    "CommandsConfig",
    "ScanConfig",
    "SprintsConfig",
    "LoopsConfig",
    "LoopsGlyphsConfig",
    "GitHubSyncConfig",
    "ConfidenceGateConfig",
    "RateLimitsConfig",
    "SyncConfig",
    "ScoringWeightsConfig",
    "DependencyMappingConfig",
    "DuplicateDetectionConfig",
    "CliColorsEdgeLabelsConfig",
    "CliColorsLoggerConfig",
    "CliColorsPriorityConfig",
    "CliColorsTypeConfig",
    "CliColorsConfig",
    "CliConfig",
    "RefineStatusConfig",
    "REQUIRED_CATEGORIES",
    "DEFAULT_CATEGORIES",
]
