"""CLI presentation configuration dataclasses.

Covers ANSI color overrides for log levels, priority labels, type labels,
and general CLI display options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CliColorsLoggerConfig:
    """ANSI color overrides for Logger log-level output."""

    info: str = "36"
    success: str = "32"
    warning: str = "33"
    error: str = "38;5;208"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CliColorsLoggerConfig:
        """Create CliColorsLoggerConfig from dictionary."""
        return cls(
            info=data.get("info", "36"),
            success=data.get("success", "32"),
            warning=data.get("warning", "33"),
            error=data.get("error", "38;5;208"),
        )


@dataclass
class CliColorsPriorityConfig:
    """ANSI color overrides for issue priority labels (P0–P5)."""

    P0: str = "38;5;208;1"
    P1: str = "38;5;208"
    P2: str = "33"
    P3: str = "0"
    P4: str = "2"
    P5: str = "2"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CliColorsPriorityConfig:
        """Create CliColorsPriorityConfig from dictionary."""
        return cls(
            P0=data.get("P0", "38;5;208;1"),
            P1=data.get("P1", "38;5;208"),
            P2=data.get("P2", "33"),
            P3=data.get("P3", "0"),
            P4=data.get("P4", "2"),
            P5=data.get("P5", "2"),
        )


@dataclass
class CliColorsTypeConfig:
    """ANSI color overrides for issue type labels (BUG, FEAT, ENH)."""

    BUG: str = "38;5;208"
    FEAT: str = "32"
    ENH: str = "34"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CliColorsTypeConfig:
        """Create CliColorsTypeConfig from dictionary."""
        return cls(
            BUG=data.get("BUG", "38;5;208"),
            FEAT=data.get("FEAT", "32"),
            ENH=data.get("ENH", "34"),
        )


@dataclass
class CliColorsConfig:
    """ANSI color overrides for logger levels, priority labels, and type labels."""

    logger: CliColorsLoggerConfig = field(default_factory=CliColorsLoggerConfig)
    priority: CliColorsPriorityConfig = field(default_factory=CliColorsPriorityConfig)
    type: CliColorsTypeConfig = field(default_factory=CliColorsTypeConfig)
    fsm_active_state: str = "32"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CliColorsConfig:
        """Create CliColorsConfig from dictionary."""
        return cls(
            logger=CliColorsLoggerConfig.from_dict(data.get("logger", {})),
            priority=CliColorsPriorityConfig.from_dict(data.get("priority", {})),
            type=CliColorsTypeConfig.from_dict(data.get("type", {})),
            fsm_active_state=data.get("fsm_active_state", "32"),
        )


@dataclass
class RefineStatusConfig:
    """refine-status display configuration."""

    columns: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RefineStatusConfig:
        """Create RefineStatusConfig from dictionary."""
        return cls(columns=data.get("columns", []))


@dataclass
class CliConfig:
    """CLI output configuration."""

    color: bool = True
    colors: CliColorsConfig = field(default_factory=CliColorsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CliConfig:
        """Create CliConfig from dictionary."""
        return cls(
            color=data.get("color", True),
            colors=CliColorsConfig.from_dict(data.get("colors", {})),
        )
