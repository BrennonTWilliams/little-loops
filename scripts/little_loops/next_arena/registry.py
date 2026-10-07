"""Verb registry for the ``ll-next`` action arena (FEAT-3561).

One registry owns the canonical verb order, each landed verb's scoring axes,
default weights and caps, and the action-variant discriminator names. Config
keys, CLI choices and output-schema enums derive from it. Follow-on slices
(FEAT-3769, FEAT-3713) register their verbs in place; the canonical order is
fixed up front so a later registration never reorders existing verbs.

This module is deliberately dependency-free (stdlib only) so that
``little_loops.config`` may import it lazily without an import cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

#: Output contract version (positive integer, independent of the history DB schema).
SCHEMA_VERSION = 1

#: Fixed canonical verb order; only landed verbs are registered (see ``REGISTRY``).
CANONICAL_VERB_ORDER: tuple[str, ...] = (
    "implement-issue",
    "refine-issue",
    "resolve-blocker",
    "run-loop",
    "run-sprint",
    "capture-issues",
)

#: Registered ``action_spec`` ``variant`` discriminators.
ACTION_VARIANTS: tuple[str, ...] = ("slash",)
#: Discriminator names reserved for follow-on slices; not accepted by this slice.
RESERVED_VARIANTS: tuple[str, ...] = ("loop", "sprint", "scan")

#: Default per-type cap applied by round-robin selection.
DEFAULT_VERB_CAP = 2
#: Default per-issue refinement cap (``/ll:refine-issue`` runs) used by ``refine-issue``.
DEFAULT_REFINE_CAP = 5


@dataclass(frozen=True)
class VerbSpec:
    """Static description of one registered verb."""

    name: str
    axes: tuple[str, ...]
    default_weights: Mapping[str, float]
    default_cap: int
    minimum_evidence: str
    default_refine_cap: int | None = None


@dataclass(frozen=True)
class ArenaSettings:
    """Validated, resolved ``next.verbs`` settings.

    ``weights`` maps each registered verb (canonical order) to its axis weights
    in canonical axis order; ``caps`` holds the per-verb selection cap.
    """

    weights: Mapping[str, Mapping[str, float]]
    caps: Mapping[str, int]
    refine_cap: int


_MIN_EVIDENCE = "valid priority plus at least one resolved positive-weight non-priority axis"

_SPECS: tuple[VerbSpec, ...] = (
    VerbSpec(
        name="implement-issue",
        axes=("priority", "outcome", "leverage", "effort", "momentum"),
        default_weights=MappingProxyType(
            {"priority": 0.30, "outcome": 0.30, "leverage": 0.20, "effort": 0.10, "momentum": 0.10}
        ),
        default_cap=DEFAULT_VERB_CAP,
        minimum_evidence=_MIN_EVIDENCE,
    ),
    VerbSpec(
        name="refine-issue",
        axes=("priority", "readiness_gap", "leverage", "staleness", "momentum"),
        default_weights=MappingProxyType(
            {
                "priority": 0.30,
                "readiness_gap": 0.30,
                "leverage": 0.15,
                "staleness": 0.15,
                "momentum": 0.10,
            }
        ),
        default_cap=DEFAULT_VERB_CAP,
        minimum_evidence=_MIN_EVIDENCE,
        default_refine_cap=DEFAULT_REFINE_CAP,
    ),
)

#: Landed verbs in canonical order. A later slice appends here in canonical position.
REGISTRY: Mapping[str, VerbSpec] = MappingProxyType(
    {name: spec for name in CANONICAL_VERB_ORDER for spec in _SPECS if spec.name == name}
)


def registered_verbs() -> tuple[str, ...]:
    """Return registered verb names in canonical order."""
    return tuple(REGISTRY)


def get_verb(name: str) -> VerbSpec:
    """Return the registered :class:`VerbSpec` for *name*.

    Raises:
        KeyError: *name* is not a registered verb (including canonical-but-unlanded verbs).
    """
    try:
        return REGISTRY[name]
    except KeyError:
        known = ", ".join(registered_verbs())
        raise KeyError(f"unknown or unregistered verb {name!r} (registered: {known})") from None
