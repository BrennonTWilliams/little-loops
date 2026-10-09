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
from dataclasses import dataclass, field
from types import MappingProxyType

#: Output contract version (positive integer, independent of the history DB schema).
#: 2 (FEAT-3769): ``resolve-blocker``/``run-loop`` verbs, the ``loop`` ``action_spec``
#: variant, the ``run-loop`` action key, loop axes and the alternate ``blocker`` summary.
#: 3 (FEAT-3711): required envelope ``recording`` ``{status, reason}``, required-nullable
#: per-recommendation ``rec_id`` and microsecond (``.ffffffZ``) envelope ``as_of``.
#: 4 (FEAT-3713): ``run-sprint``/``capture-issues`` verbs, the ``sprint``/``scan`` ``action_spec``
#: variants, the ``run-sprint``/``scan-codebase`` action keys and the ``ready_share``/
#: ``since_last_run`` axes.
SCHEMA_VERSION = 4

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
ACTION_VARIANTS: tuple[str, ...] = ("slash", "loop", "sprint", "scan")
#: Discriminator names reserved for follow-on slices; none remain after FEAT-3713.
RESERVED_VARIANTS: tuple[str, ...] = ()

#: Candidate domains: ``issue`` verbs target ``issue:ID`` keys, ``loop`` verbs ``loop:NAME``,
#: ``sprint`` verbs ``sprint:NAME`` and ``scan`` verbs ``scan:SCOPE_HASH``.
DOMAIN_ISSUE = "issue"
DOMAIN_LOOP = "loop"
DOMAIN_SPRINT = "sprint"
DOMAIN_SCAN = "scan"

#: Default per-type cap applied by round-robin selection.
DEFAULT_VERB_CAP = 2
#: Default per-issue refinement cap (``/ll:refine-issue`` runs) used by ``refine-issue``.
DEFAULT_REFINE_CAP = 5
#: Default scoped-commit threshold of the ``capture-issues`` activity gate (FEAT-3713).
DEFAULT_ACTIVITY_THRESHOLD = 20
#: Default lookback (days) of the ``capture-issues`` activity gate (FEAT-3713).
DEFAULT_ACTIVITY_LOOKBACK_DAYS = 30


@dataclass(frozen=True)
class VerbSpec:
    """Static description of one registered verb."""

    name: str
    axes: tuple[str, ...]
    default_weights: Mapping[str, float]
    default_cap: int
    minimum_evidence: str
    default_refine_cap: int | None = None
    domain: str = DOMAIN_ISSUE
    #: Wording for the fallback order of cold-start candidates in ``selection_reason``.
    cold_start_order: str = "priority then target"
    #: Extra per-verb integer settings (``name -> default``) beyond ``cap``/``refine_cap``.
    extra_settings: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def evidence_only(self) -> bool:
        """True for a verb with no scored axes: eligibility alone ranks its candidates."""
        return not self.axes


@dataclass(frozen=True)
class ArenaSettings:
    """Validated, resolved ``next.verbs`` settings.

    ``weights`` maps each registered verb (canonical order) to its axis weights
    in canonical axis order; ``caps`` holds the per-verb selection cap.
    """

    weights: Mapping[str, Mapping[str, float]]
    caps: Mapping[str, int]
    refine_cap: int
    #: ``capture-issues`` activity gate (FEAT-3713): minimum scoped commits and lookback days.
    activity_threshold: int = DEFAULT_ACTIVITY_THRESHOLD
    activity_lookback_days: int = DEFAULT_ACTIVITY_LOOKBACK_DAYS


_MIN_EVIDENCE = "valid priority plus at least one resolved positive-weight non-priority axis"
_LOOP_MIN_EVIDENCE = "at least one resolved positive-weight history axis"
_SPRINT_MIN_EVIDENCE = "at least one resolved positive-weight axis after the eligibility gates"
_SCAN_MIN_EVIDENCE = "evidence-only: the scoped-activity gate must pass (no scored axes)"

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
    VerbSpec(
        name="resolve-blocker",
        axes=("priority", "leverage", "effort", "staleness", "momentum"),
        default_weights=MappingProxyType(
            {
                "priority": 0.25,
                "leverage": 0.50,
                "effort": 0.15,
                "staleness": 0.05,
                "momentum": 0.05,
            }
        ),
        default_cap=DEFAULT_VERB_CAP,
        minimum_evidence=_MIN_EVIDENCE,
    ),
    VerbSpec(
        name="run-loop",
        axes=("frequency", "recency", "success"),
        default_weights=MappingProxyType({"frequency": 0.50, "recency": 0.30, "success": 0.20}),
        default_cap=DEFAULT_VERB_CAP,
        minimum_evidence=_LOOP_MIN_EVIDENCE,
        domain=DOMAIN_LOOP,
        cold_start_order="target",
    ),
    VerbSpec(
        name="run-sprint",
        axes=("ready_share", "priority", "since_last_run"),
        default_weights=MappingProxyType(
            {"ready_share": 0.50, "priority": 0.30, "since_last_run": 0.20}
        ),
        default_cap=DEFAULT_VERB_CAP,
        minimum_evidence=_SPRINT_MIN_EVIDENCE,
        domain=DOMAIN_SPRINT,
        cold_start_order="target",
    ),
    VerbSpec(
        name="capture-issues",
        axes=(),
        default_weights=MappingProxyType({}),
        default_cap=DEFAULT_VERB_CAP,
        minimum_evidence=_SCAN_MIN_EVIDENCE,
        domain=DOMAIN_SCAN,
        cold_start_order="target",
        extra_settings=MappingProxyType(
            {
                "activity_threshold": DEFAULT_ACTIVITY_THRESHOLD,
                "activity_lookback_days": DEFAULT_ACTIVITY_LOOKBACK_DAYS,
            }
        ),
    ),
)

#: Landed verbs in canonical order. A later slice appends here in canonical position.
REGISTRY: Mapping[str, VerbSpec] = MappingProxyType(
    {name: spec for name in CANONICAL_VERB_ORDER for spec in _SPECS if spec.name == name}
)


def registered_verbs() -> tuple[str, ...]:
    """Return registered verb names in canonical order."""
    return tuple(REGISTRY)


def verbs_in_domain(domain: str) -> tuple[str, ...]:
    """Registered verb names of one candidate *domain*, in canonical order."""
    return tuple(name for name, spec in REGISTRY.items() if spec.domain == domain)


def loop_verbs() -> tuple[str, ...]:
    """Registered verbs whose candidates are loop definitions (``loop:NAME`` targets)."""
    return verbs_in_domain(DOMAIN_LOOP)


def sprint_verbs() -> tuple[str, ...]:
    """Registered verbs whose candidates are sprint definitions (``sprint:NAME`` targets)."""
    return verbs_in_domain(DOMAIN_SPRINT)


def scan_verbs() -> tuple[str, ...]:
    """Registered verbs whose candidate is the configured scan scope (``scan:SCOPE_HASH``)."""
    return verbs_in_domain(DOMAIN_SCAN)


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
