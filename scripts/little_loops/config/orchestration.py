"""Orchestration configuration dataclass.

Covers host CLI selection and related orchestration settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OrchestrationConfig:
    """Orchestration settings, primarily host CLI selection.

    ``host_cli`` mirrors the ``LL_HOST_CLI`` environment variable and is used
    by :func:`~little_loops.host_runner.apply_host_cli_from_config` to export
    the config value into the environment before :func:`~little_loops.host_runner.resolve_host`
    runs. The env var takes precedence if already set.
    """

    host_cli: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationConfig:
        """Create OrchestrationConfig from dictionary."""
        return cls(
            host_cli=data.get("host_cli"),
        )
