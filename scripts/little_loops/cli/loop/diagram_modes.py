"""DiagramFacets: orthogonal diagram display axes + named presets for ll-loop.

Replaces the old ``--show-diagrams=main|full|mini`` single-enum with:

  --show-diagrams=<topology-or-preset>
    topology: layered | neighborhood | inline | window
    preset:   detailed | summary | clean | local | oneline

  --diagram-edge-labels=on|off   (default on)
  --diagram-state-detail=title|full  (default full)
  --diagram-scope=main|full          (default full)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace

TOPOLOGY_VALUES: frozenset[str] = frozenset({"layered", "neighborhood", "inline", "window"})
PRESET_VALUES: frozenset[str] = frozenset(
    {"detailed", "summary", "clean", "local", "oneline", "slim"}
)

_LEGACY_HINTS: dict[str, str] = {
    "main": (
        "main was renamed: use --show-diagrams=summary "
        "(path scope is now controlled by --diagram-scope=main)."
    ),
    "full": (
        "full was renamed: use --show-diagrams=detailed "
        "(full graph is now controlled by --diagram-scope=full)."
    ),
    "mini": (
        "mini was renamed: use --show-diagrams=clean "
        "(or set --diagram-edge-labels=off --diagram-state-detail=title "
        "for the underlying primitives)."
    ),
}


@dataclass(frozen=True)
class DiagramFacets:
    """Resolved, orthogonal diagram display settings.

    ``source`` drives fallback gating in ``_choose_pinned_layout``:
    - ``"topology"`` — user passed an explicit topology; no auto-degradation.
    - ``"preset"``   — a named preset was used; fall back through smaller topologies.
    - ``"default"``  — bare ``--show-diagrams`` flag; same fallback as preset.
    """

    topology: str  # layered | neighborhood | inline | window
    edge_labels: bool  # True = render edge labels
    state_detail: str  # title | full
    scope: str  # main | full  (silently ignored for inline topology)
    source: str  # default | preset | topology


PRESET_EXPANSIONS: dict[str, DiagramFacets] = {
    "detailed": DiagramFacets("layered", True, "full", "full", "preset"),
    "summary": DiagramFacets("layered", True, "full", "main", "preset"),
    "clean": DiagramFacets("layered", False, "title", "main", "preset"),
    "local": DiagramFacets("neighborhood", True, "title", "main", "preset"),
    "slim": DiagramFacets("neighborhood", False, "title", "main", "preset"),
    "oneline": DiagramFacets("inline", True, "title", "full", "preset"),
}

# Maps topology name to the detail string used by _build_pinned_pane
TOPOLOGY_TO_DETAIL: dict[str, str] = {
    "layered": "full",
    "neighborhood": "neighborhood",
    "inline": "single",
    # "window" crops the real layered render to ±K layers around the active
    # state (ENH-2410); K is sized to the viewport by _build_pinned_pane.
    "window": "window",
}


def _parse_show_diagrams(value: str) -> str:
    """argparse ``type=`` validator for ``--show-diagrams``.

    Accepts topology values and preset names; rejects legacy mode strings
    with a migration hint. The ``const=True`` sentinel (bare flag) bypasses
    this function entirely — argparse does not call ``type=`` on ``const``.
    """
    if value in TOPOLOGY_VALUES | PRESET_VALUES:
        return value
    if value in _LEGACY_HINTS:
        raise argparse.ArgumentTypeError(_LEGACY_HINTS[value])
    raise argparse.ArgumentTypeError(
        f"unknown --show-diagrams value {value!r}; "
        f"choose from topologies {sorted(TOPOLOGY_VALUES)} "
        f"or presets {sorted(PRESET_VALUES)}"
    )


def resolve_facets(args: argparse.Namespace) -> DiagramFacets | None:
    """Resolve argparse Namespace into a ``DiagramFacets``, or ``None`` if the flag was absent.

    Modifier flags (``diagram_edge_labels``, ``diagram_state_detail``,
    ``diagram_scope``) override the preset expansion only when explicitly set
    (non-None), so preset defaults are preserved when modifiers are absent.
    """
    raw = getattr(args, "show_diagrams", None)
    if raw is None:
        return None

    if raw is True:  # bare --show-diagrams (const=True sentinel)
        base = replace(PRESET_EXPANSIONS["summary"], source="default")
    elif raw in PRESET_EXPANSIONS:
        base = PRESET_EXPANSIONS[raw]
    elif raw in TOPOLOGY_VALUES:
        base = DiagramFacets(raw, True, "full", "full", "topology")
    else:
        raise ValueError(f"unreachable: argparse should have rejected {raw!r}")

    # Apply modifier overrides — only when the user explicitly set them (not None).
    edge_labels_raw = getattr(args, "diagram_edge_labels", None)
    edge_labels = (edge_labels_raw != "off") if edge_labels_raw is not None else base.edge_labels

    state_detail_raw = getattr(args, "diagram_state_detail", None)
    state_detail = state_detail_raw if state_detail_raw is not None else base.state_detail

    scope_raw = getattr(args, "diagram_scope", None)
    scope = scope_raw if scope_raw is not None else base.scope

    return replace(base, edge_labels=edge_labels, state_detail=state_detail, scope=scope)
