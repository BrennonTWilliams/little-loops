"""Orchestration configuration dataclass.

Covers host CLI selection and related orchestration settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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


def _validate_model_hints(raw: Any) -> dict[str, dict[str, str | Literal[False]]]:
    """Validate ``orchestration.model_hints``; raise ``ValueError`` naming the bad path."""
    from little_loops.host_runner import MODEL_HINTS, hint_backend_keys

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("orchestration.model_hints must be a mapping")
    backends = hint_backend_keys()
    result: dict[str, dict[str, str | Literal[False]]] = {}
    for backend, mapping in raw.items():
        path = f"orchestration.model_hints.{backend}"
        if backend not in backends:
            raise ValueError(f"{path}: unknown backend key; expected one of {sorted(backends)}")
        if not isinstance(mapping, dict):
            raise ValueError(f"{path}: must be a mapping of hint -> model")
        entry: dict[str, str | Literal[False]] = {}
        for hint, value in mapping.items():
            if hint not in MODEL_HINTS:
                raise ValueError(
                    f"{path}.{hint}: unknown hint; expected one of {list(MODEL_HINTS)}"
                )
            if value is False or (isinstance(value, str) and value.strip()):
                entry[hint] = value
            else:
                raise ValueError(f"{path}.{hint}: must be a non-empty string or false")
        result[backend] = entry
    return result


@dataclass
class OrchestrationConfig:
    """Orchestration settings, primarily host CLI selection.

    ``host_cli`` mirrors the ``LL_HOST_CLI`` environment variable and is read
    directly by :func:`~little_loops.host_runner.resolve_host` (ambient-env path
    only; nothing is exported to ``os.environ``). Precedence: ``LL_HOST_CLI`` >
    ``LL_HOOK_HOST`` > this key > binary probe.

    ``request_path`` (FEAT-2673, EPIC-2456 F1) selects between the existing
    CLI shell-subprocess path (``"cli"``, default — unchanged behavior), the
    opt-in Anthropic SDK path (``"sdk"``) that calls
    :func:`~little_loops.host_runner.build_anthropic_request`, and the
    opt-in Message Batches API path (``"batch"``, FEAT-2710, EPIC-2456)
    that submits via :func:`~little_loops.host_runner.build_batch_request`
    for a flat 50% discount on both input and output tokens. The 0.1x-read
    / 1.25x-write cache discount only exists when the request body carries a
    ``cache_control`` parameter, which is unreachable over the CLI shell
    path, so ``"sdk"``/``"batch"`` must be explicitly opted into. ``"batch"``
    trades latency for cost — results arrive asynchronously via polling —
    so it is only suitable for latency-insensitive states/loops.

    A configured ``"sdk"``/``"batch"`` value automatically downgrades to
    ``"cli"`` at dispatch time (ENH-2737) if the ``anthropic`` package is not
    importable or ``ANTHROPIC_API_KEY`` is unset, so a run never hard-fails
    on a host that only has the CLI available.
    """

    host_cli: str | None = None
    request_path: str = "cli"
    composer: ComposerConfig = field(default_factory=ComposerConfig)
    cluster: ClusterConfig = field(default_factory=ClusterConfig)
    disable_background_tasks: bool = False
    # ENH-3527: backend key -> hint -> model literal; ``False`` disables a
    # built-in mapping. Validated in ``from_dict`` (config-schema.json is not
    # enforced at runtime).
    model_hints: dict[str, dict[str, str | Literal[False]]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationConfig:
        """Create OrchestrationConfig from dictionary."""
        return cls(
            model_hints=_validate_model_hints(data.get("model_hints", {})),
            host_cli=data.get("host_cli"),
            request_path=data.get("request_path", "cli"),
            composer=ComposerConfig.from_dict(data.get("composer", {})),
            cluster=ClusterConfig.from_dict(data.get("cluster", {})),
            disable_background_tasks=data.get("disable_background_tasks", False),
        )


@dataclass
class AdvisorConfig:
    """Advisor (FEAT-3037) configuration: host, model, capability floor, and consult timeout.

    ``host`` is a registry key and validates against the same enum as
    ``orchestration.host_cli`` (``claude-code | codex | opencode | pi | gemini |
    omp | kimi-code``), enforced structurally by ``config-schema.json`` — this
    dataclass performs no enum validation itself, mirroring
    :class:`OrchestrationConfig`'s division of labor.

    Read by ``little_loops.advisor.consult()`` / ``ll-advise`` (FEAT-3120).
    """

    enabled: bool = False
    host: str | None = None
    model: str = "opus"
    min_tier: str | None = None
    timeout_seconds: int = 300
    triggers: list[str] = field(default_factory=list)
    max_consults_per_task: int = 3
    store_verdict_body: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdvisorConfig:
        """Create AdvisorConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            host=data.get("host"),
            model=data.get("model", "opus"),
            min_tier=data.get("min_tier"),
            timeout_seconds=data.get("timeout_seconds", 300),
            triggers=list(data.get("triggers", [])),
            max_consults_per_task=data.get("max_consults_per_task", 3),
            store_verdict_body=data.get("store_verdict_body", False),
        )
