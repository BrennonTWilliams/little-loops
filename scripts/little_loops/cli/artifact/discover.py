"""``ll-artifact templatize`` Phase B: LLM region discovery (FEAT-3315).

The only module on this call path that imports ``host_runner``/``anthropic``
— ``templatize.py`` is forbidden from doing so (module docstring, and
mirrors ``artifact_templates.py``'s no-LLM-import constraint). This module
is the boundary where ``BlockingJsonError`` is translated to
``RegionMapError`` so ``cmd_templatize``'s existing
``except (ManifestError, SpliceError, RegionMapError)`` arm covers the new
failure mode without a host-aware change.

The LLM never emits byte offsets — it quotes each span's literal text, and
``_resolve_offsets()`` locates it with ``bytes.index``. See FEAT-3315
§ Decision Rationale → *Offset resolution* for why: the Phase A round-trip
gate is self-consistent by construction and cannot detect a
uniformly-wrong-but-orderly offset map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from little_loops.cli.artifact.templatize import (
    DiscoveryResult,
    RegionMapError,
    _parse_region_map,
)
from little_loops.fsm.schema import DEFAULT_LLM_MODEL
from little_loops.host_runner import BlockingJsonError, resolve_host, run_blocking_json

# Sent to the host at build time (``build_blocking_json(json_schema=...)``),
# following advisor.consult()'s Option A shape exactly (advisor.py:269-280).
# Enforcement is host-dependent — Codex materializes this into
# ``--output-schema``, Claude Code silently drops it — so the caller-side
# ``_DISCOVERY_KEYS.issubset(...)`` check below is required regardless of
# host (host_runner.py:442-465, :736-770).
_DISCOVERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "expr": {"type": "string"},
                    "group": {"type": ["string", "null"]},
                    "anchor_before": {"type": ["string", "null"]},
                    "anchor_after": {"type": ["string", "null"]},
                },
                "required": ["text", "expr"],
            },
        },
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "binding": {"type": "string"},
                    "array_path": {"type": "string"},
                    "iterations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "anchor_before": {"type": ["string", "null"]},
                                "anchor_after": {"type": ["string", "null"]},
                            },
                            "required": ["text"],
                        },
                    },
                },
                "required": ["id", "binding", "array_path", "iterations"],
            },
        },
    },
    "required": ["regions", "groups"],
}

_DISCOVERY_KEYS = frozenset({"regions", "groups"})

_PROMPT_TEMPLATE = """\
You are converting a generated HTML/text artifact into a reusable Jinja2 \
template by identifying which spans of the artifact were derived from the \
source document below, versus spans that are fixed presentation.

Respond with a single JSON object matching this shape (no other text):

{{
  "regions": [
    {{"text": "<exact literal substring of the artifact>", "expr": "dotted.path", \
"group": null, "anchor_before": null, "anchor_after": null}}
  ],
  "groups": [
    {{"id": "group_id", "binding": "item", "array_path": "dotted.path", \
"iterations": [{{"text": "<exact literal substring of iteration 1>"}}, ...]}}
  ]
}}

Rules — read carefully, these are verified mechanically after your response:

1. Never invent, paraphrase, or offset any text. Every "text" value must be \
an EXACT, byte-for-byte literal substring copied from the artifact below — \
copy it character-for-character as it appears in the byte stream, including \
whitespace and HTML entities. Do not emit numeric offsets; only quoted text.
2. A top-level region (repeats once) goes in "regions" with "group": null. \
A field that repeats once per row/item of a list goes in "groups" — declare \
one group per repeating structure, with one "iterations[].text" entry per \
repetition (the whole literal text of that one repetition), and then list \
each of that repetition's individual field spans as additional entries in \
the top-level "regions" array with "group" set to the group's "id".
3. Field-region entries for a given group MUST be listed in the top-level \
"regions" array in iteration-major order: all of iteration 1's field spans \
first (in the same order for every iteration), then iteration 2's, and so \
on — the same number of field spans per iteration.
4. Within a single group, the non-region literal text between fields must \
be byte-identical across every iteration you declare — only quote \
repetitions that genuinely share one template, not merely look similar.
5. If a quoted "text" value could match more than one place in the \
artifact, set "anchor_before" and/or "anchor_after" to a short literal \
string immediately preceding/following the intended occurrence, to \
disambiguate it. Leave them null when the text is unambiguous.
6. Do not include "data" or "data_schema" — those are derived separately \
and are not part of this response.

--- ARTIFACT ({artifact_len} bytes) ---
{artifact_text}
--- SOURCE DOCUMENT ---
{source_text}
"""


@dataclass(frozen=True)
class DiscoveryResponse:
    """Everything ``cmd_templatize`` needs from a discovery call.

    ``result`` is the validated, offset-resolved payload consumed downstream
    exactly like a hand-written ``--regions`` map. ``raw``/``resolved`` are
    carried so every post-call failure branch can preserve
    ``discovery.json``/``regions.json`` (FEAT-3315 Proposed Solution 7)
    without re-deriving them or re-paying for the call.
    """

    result: DiscoveryResult
    raw: dict[str, Any]
    resolved: dict[str, Any]
    host: str
    model: str


def _find_candidates(haystack: bytes, needle: bytes, start: int, end: int) -> list[int]:
    """All (possibly overlapping) start offsets of *needle* in haystack[start:end]."""
    positions: list[int] = []
    i = start
    while True:
        idx = haystack.find(needle, i, end)
        if idx == -1:
            break
        positions.append(idx)
        i = idx + 1
    return positions


def _resolve_span(
    artifact: bytes,
    text: Any,
    anchor_before: Any,
    anchor_after: Any,
    *,
    where: str,
    search_start: int,
    search_end: int,
) -> tuple[int, int]:
    """Locate *text* within artifact[search_start:search_end], never a best-effort guess.

    Never a nearest-match fallback (FEAT-3315 Proposed Solution 2): a
    not-found, ambiguous, or anchor-failing match is a loud ``RegionMapError``
    naming *where* and the quoted text.
    """
    if not isinstance(text, str) or not text:
        raise RegionMapError(f"{where}: expected a non-empty quoted 'text' string")
    needle = text.encode("utf-8")

    candidates = _find_candidates(artifact, needle, search_start, search_end)
    if not candidates:
        raise RegionMapError(f"{where}: quoted text {text!r} not found in artifact")

    def anchors_ok(start: int, end: int) -> bool:
        if anchor_before is not None:
            if not isinstance(anchor_before, str):
                return False
            if not artifact[:start].endswith(anchor_before.encode("utf-8")):
                return False
        if anchor_after is not None:
            if not isinstance(anchor_after, str):
                return False
            if not artifact[end:].startswith(anchor_after.encode("utf-8")):
                return False
        return True

    matches = [(c, c + len(needle)) for c in candidates if anchors_ok(c, c + len(needle))]

    if not matches:
        if anchor_before is None and anchor_after is None:
            raise RegionMapError(
                f"{where}: quoted text {text!r} is ambiguous ({len(candidates)} occurrence(s) "
                "in range) and no anchor_before/anchor_after was supplied to disambiguate it"
            )
        raise RegionMapError(
            f"{where}: quoted text {text!r} found but anchor_before/anchor_after did not match "
            "at any candidate position"
        )
    if len(matches) > 1:
        raise RegionMapError(
            f"{where}: quoted text {text!r} is ambiguous ({len(matches)} anchor-matching "
            "occurrence(s))"
        )
    return matches[0]


def _resolve_offsets(artifact: bytes, raw: dict[str, Any]) -> dict[str, Any]:
    """Convert the LLM's quote-based response into Phase A's ``{regions, groups}`` byte-offset map.

    Resolution order (FEAT-3315 Proposed Solution 2):

    1. All groups' iteration spans, group by group in payload order,
       iteration by iteration, via one monotonically advancing cursor
       (``bytes.index(text, cursor)``) — this is what disambiguates
       repeated literal text and guarantees the sorted, non-overlapping
       ordering ``apply_regions`` requires.
    2. All top-level (``group: null``) regions, continuing that same
       cursor, in the order given in ``regions``.
    3. Each group's field-region entries (``regions[].group == <id>``),
       resolved via a search *bounded to their own iteration's byte range*
       rather than the global cursor. Field entries for a group must be
       listed in the flat ``regions`` array in iteration-major order (all
       of iteration 1's fields, then iteration 2's, ...) with an equal
       count per iteration — the prompt states this rule. This is what
       guarantees the result satisfies ``_region_iteration_index`` by
       construction: a field region can only resolve inside the iteration
       range it was searched against.

    Group spans are derived, not supplied: ``group.start``/``group.end`` are
    the first/last iteration's resolved start/end.
    """
    if not isinstance(raw, dict):
        raise RegionMapError("discovery response: expected a top-level object")
    unknown = set(raw.keys()) - _DISCOVERY_KEYS
    if unknown:
        raise RegionMapError(f"discovery response: unknown top-level key(s) {sorted(unknown)}")
    missing = _DISCOVERY_KEYS - set(raw.keys())
    if missing:
        raise RegionMapError(f"discovery response: missing required key(s) {sorted(missing)}")

    regions_raw = raw["regions"]
    groups_raw = raw["groups"]
    if not isinstance(regions_raw, list):
        raise RegionMapError("discovery response: 'regions' must be a list")
    if not isinstance(groups_raw, list):
        raise RegionMapError("discovery response: 'groups' must be a list")

    cursor = 0
    resolved_groups: list[dict[str, Any]] = []
    group_iterations: dict[str, list[tuple[int, int]]] = {}

    for gi, g in enumerate(groups_raw):
        if not isinstance(g, dict):
            raise RegionMapError(f"groups[{gi}]: expected an object")
        gid = g.get("id")
        binding = g.get("binding")
        array_path = g.get("array_path")
        if not isinstance(gid, str) or not gid:
            raise RegionMapError(f"groups[{gi}].id: expected a non-empty string")
        if not isinstance(binding, str) or not binding:
            raise RegionMapError(f"groups[{gi}].binding: expected a non-empty string")
        if not isinstance(array_path, str) or not array_path:
            raise RegionMapError(f"groups[{gi}].array_path: expected a non-empty string")
        if gid in group_iterations:
            raise RegionMapError(f"groups[{gi}].id: duplicate group id {gid!r}")

        iterations_raw = g.get("iterations")
        if not isinstance(iterations_raw, list) or not iterations_raw:
            raise RegionMapError(f"groups[{gi}].iterations: expected a non-empty list")

        iteration_spans: list[tuple[int, int]] = []
        for ii, it in enumerate(iterations_raw):
            if not isinstance(it, dict):
                raise RegionMapError(f"groups[{gi}].iterations[{ii}]: expected an object")
            start, end = _resolve_span(
                artifact,
                it.get("text"),
                it.get("anchor_before"),
                it.get("anchor_after"),
                where=f"groups[{gi}].iterations[{ii}] (group {gid!r})",
                search_start=cursor,
                search_end=len(artifact),
            )
            iteration_spans.append((start, end))
            cursor = end

        group_iterations[gid] = iteration_spans
        resolved_groups.append(
            {
                "id": gid,
                "binding": binding,
                "array_path": array_path,
                "start": iteration_spans[0][0],
                "end": iteration_spans[-1][1],
                "iterations": [[s, e] for s, e in iteration_spans],
            }
        )

    resolved_regions: list[dict[str, Any]] = []
    field_entries_by_group: dict[str, list[dict[str, Any]]] = {}

    for ri, r in enumerate(regions_raw):
        if not isinstance(r, dict):
            raise RegionMapError(f"regions[{ri}]: expected an object")
        group = r.get("group")
        if group is not None:
            if not isinstance(group, str) or not group:
                raise RegionMapError(f"regions[{ri}].group: expected a non-empty string or null")
            field_entries_by_group.setdefault(group, []).append(r)
            continue

        expr = r.get("expr")
        if not isinstance(expr, str) or not expr:
            raise RegionMapError(f"regions[{ri}].expr: expected a non-empty string")
        start, end = _resolve_span(
            artifact,
            r.get("text"),
            r.get("anchor_before"),
            r.get("anchor_after"),
            where=f"regions[{ri}] (expr={expr!r})",
            search_start=cursor,
            search_end=len(artifact),
        )
        cursor = end
        resolved_regions.append(
            {
                "start": start,
                "end": end,
                "expr": expr,
                "group": None,
                "anchor_before": r.get("anchor_before"),
                "anchor_after": r.get("anchor_after"),
            }
        )

    for gid, entries in field_entries_by_group.items():
        if gid not in group_iterations:
            raise RegionMapError(f"regions: group {gid!r} referenced but not declared in 'groups'")
        iteration_spans = group_iterations[gid]
        n_iterations = len(iteration_spans)
        if len(entries) % n_iterations != 0:
            raise RegionMapError(
                f"group {gid!r}: {len(entries)} field region(s) is not evenly divisible by "
                f"{n_iterations} declared iteration(s) — field regions must be listed in "
                "iteration-major order with an equal count per iteration"
            )
        per_iteration = len(entries) // n_iterations

        for it_idx, (it_start, it_end) in enumerate(iteration_spans):
            chunk = entries[it_idx * per_iteration : (it_idx + 1) * per_iteration]
            for entry in chunk:
                expr = entry.get("expr")
                if not isinstance(expr, str) or not expr:
                    raise RegionMapError(f"group {gid!r} field region: expected non-empty 'expr'")
                start, end = _resolve_span(
                    artifact,
                    entry.get("text"),
                    entry.get("anchor_before"),
                    entry.get("anchor_after"),
                    where=f"group {gid!r} field (expr={expr!r}, iteration {it_idx})",
                    search_start=it_start,
                    search_end=it_end,
                )
                resolved_regions.append(
                    {
                        "start": start,
                        "end": end,
                        "expr": expr,
                        "group": gid,
                        "anchor_before": entry.get("anchor_before"),
                        "anchor_after": entry.get("anchor_after"),
                    }
                )

    resolved_regions.sort(key=lambda r: r["start"])
    return {"regions": resolved_regions, "groups": resolved_groups}


def discover_regions(artifact_bytes: bytes, source_text: str, config: object) -> DiscoveryResponse:
    """LLM stage: identify source-derived spans by quoted literal text (FEAT-3315).

    The only function on this call path that touches ``host_runner``. Takes
    **bytes**, not ``str`` — ``_resolve_offsets`` needs the same byte stream
    ``extract_data``/``apply_regions`` will slice.

    Raises:
        RegionMapError: on any host or response failure — including a
            translated ``BlockingJsonError`` (timeout, missing binary,
            non-zero exit, unparseable output) and a malformed/missing-key
            response (Option A fail-closed contract, mirroring
            ``advisor.consult()``'s ``issubset`` key-check). Once a raw
            response was received, the raised ``RegionMapError`` carries it
            as a ``.raw`` attribute (and ``.resolved`` once resolution
            succeeds) so ``cmd_templatize`` can preserve
            ``discovery.json``/``regions.json`` on every downstream failure
            without re-deriving them (FEAT-3315 Proposed Solution 7) — no
            failure past a successful call requires re-paying for it.
    """
    del config  # not yet needed — host/model resolution is ambient (resolve_host())

    runner = resolve_host()
    model = DEFAULT_LLM_MODEL
    prompt = _PROMPT_TEMPLATE.format(
        artifact_len=len(artifact_bytes),
        artifact_text=artifact_bytes.decode("utf-8", errors="replace"),
        source_text=source_text,
    )
    invocation = runner.build_blocking_json(
        prompt=prompt, model=model, json_schema=_DISCOVERY_SCHEMA
    )

    try:
        raw = run_blocking_json(invocation, timeout=180)
    except BlockingJsonError as exc:
        raise RegionMapError(f"discovery call failed: {exc}") from exc

    if raw is None or not _DISCOVERY_KEYS.issubset(raw.keys()):
        got_keys = sorted((raw or {}).keys())
        exc = RegionMapError(
            f"discovery response missing expected keys ({sorted(_DISCOVERY_KEYS)}): got {got_keys}"
        )
        exc.raw = raw  # type: ignore[attr-defined]
        raise exc
    unknown = set(raw.keys()) - _DISCOVERY_KEYS
    if unknown:
        exc = RegionMapError(f"discovery response: unknown top-level key(s) {sorted(unknown)}")
        exc.raw = raw  # type: ignore[attr-defined]
        raise exc

    try:
        resolved = _resolve_offsets(artifact_bytes, raw)
    except RegionMapError as exc:
        exc.raw = raw  # type: ignore[attr-defined]
        raise
    try:
        result = _parse_region_map(resolved, where="discovery response")
    except RegionMapError as exc:
        exc.raw = raw  # type: ignore[attr-defined]
        exc.resolved = resolved  # type: ignore[attr-defined]
        raise

    return DiscoveryResponse(
        result=result,
        raw=raw,
        resolved=resolved,
        host=runner.name,
        model=model,
    )
