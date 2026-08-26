"""``ll-artifact templatize`` Phase A: deterministic templating (FEAT-3314).

Given an artifact plus a hand-written region map (``--regions <map.json>``),
splice the regions into Jinja2 expressions/blocks, emit a ``manifest.yaml``
+ ``data.json``, and verify byte-exact round trip via a
build-in-temp-then-promote flow. No LLM call is on this path — Phase B
(FEAT-3315) adds ``discover_regions`` on top of this.

This module must never import ``host_runner`` or ``anthropic`` (mirrors the
constraint on ``artifact_templates.py`` — Phase A has no LLM call).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from little_loops.artifact_templates import (
    ArtifactTemplate,
    DataValidationError,
    ManifestError,
    load_manifest,
    render_template,
    validate_top_level_data,
)
from little_loops.logger import Logger

if TYPE_CHECKING:
    from little_loops.design_tokens import DesignTokens

_DELIMITER_TOKENS = (b"[[=", b"[[%", b"[[#")
_RAW_START = b"[[% raw %]]"
_RAW_END = b"[[% endraw %]]"
_RESERVED_CONTEXT_KEY = "ll"


class RegionMapError(ValueError):
    """Raised when a ``--regions`` map fails to parse or validate (fail-closed)."""


class SpliceError(ValueError):
    """Raised when ``apply_regions`` cannot safely splice the given regions."""


@dataclass
class Region:
    start: int
    end: int
    expr: str
    group: str | None = None
    anchor_before: str | None = None
    anchor_after: str | None = None


@dataclass
class RegionGroup:
    id: str
    binding: str
    array_path: str
    start: int
    end: int
    iterations: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    data_schema: dict[str, Any]
    data: dict[str, Any]
    regions: list[Region]
    groups: list[RegionGroup]


# --------------------------------------------------------------------------
# load_regions
# --------------------------------------------------------------------------

_REGION_REQUIRED = {"start", "end", "expr"}
_REGION_OPTIONAL = {"group", "anchor_before", "anchor_after"}
_REGION_ALLOWED = _REGION_REQUIRED | _REGION_OPTIONAL

_GROUP_REQUIRED = {"id", "binding", "array_path", "start", "end", "iterations"}

_MAP_ALLOWED_KEYS = {"regions", "groups"}


def _require_int(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RegionMapError(f"{where}: expected an integer offset, got {value!r}")
    return value


def _parse_region(raw: dict[str, Any], index: int) -> Region:
    if not isinstance(raw, dict):
        raise RegionMapError(f"regions[{index}]: expected an object")
    unknown = set(raw.keys()) - _REGION_ALLOWED
    if unknown:
        raise RegionMapError(f"regions[{index}]: unknown key(s) {sorted(unknown)}")
    missing = _REGION_REQUIRED - set(raw.keys())
    if missing:
        raise RegionMapError(f"regions[{index}]: missing required field(s) {sorted(missing)}")
    if not isinstance(raw["expr"], str) or not raw["expr"]:
        raise RegionMapError(f"regions[{index}].expr: expected a non-empty string")
    return Region(
        start=_require_int(raw["start"], f"regions[{index}].start"),
        end=_require_int(raw["end"], f"regions[{index}].end"),
        expr=raw["expr"],
        group=raw.get("group"),
        anchor_before=raw.get("anchor_before"),
        anchor_after=raw.get("anchor_after"),
    )


def _parse_group(raw: dict[str, Any], index: int) -> RegionGroup:
    if not isinstance(raw, dict):
        raise RegionMapError(f"groups[{index}]: expected an object")
    unknown = set(raw.keys()) - _GROUP_REQUIRED
    if unknown:
        raise RegionMapError(f"groups[{index}]: unknown key(s) {sorted(unknown)}")
    missing = _GROUP_REQUIRED - set(raw.keys())
    if missing:
        raise RegionMapError(f"groups[{index}]: missing required field(s) {sorted(missing)}")
    iterations_raw = raw["iterations"]
    if not isinstance(iterations_raw, list) or not iterations_raw:
        raise RegionMapError(f"groups[{index}].iterations: expected a non-empty list")
    iterations: list[tuple[int, int]] = []
    for i, pair in enumerate(iterations_raw):
        if not isinstance(pair, list) or len(pair) != 2:
            raise RegionMapError(f"groups[{index}].iterations[{i}]: expected a [start, end] pair")
        iterations.append(
            (
                _require_int(pair[0], f"groups[{index}].iterations[{i}][0]"),
                _require_int(pair[1], f"groups[{index}].iterations[{i}][1]"),
            )
        )
    return RegionGroup(
        id=str(raw["id"]),
        binding=str(raw["binding"]),
        array_path=str(raw["array_path"]),
        start=_require_int(raw["start"], f"groups[{index}].start"),
        end=_require_int(raw["end"], f"groups[{index}].end"),
        iterations=iterations,
    )


def _parse_region_map(raw: dict[str, Any], where: str) -> DiscoveryResult:
    """Fail-closed parse of an in-memory region-map dict.

    Rejects unknown keys, missing required fields, and non-integer offsets.
    Returns ``data={}`` / ``data_schema={}`` — both are derived, never
    supplied (§ Proposed Solution 1); a map carrying either key is rejected.

    Extracted from ``load_regions()`` (FEAT-3315 Proposed Solution 4) so
    ``discover_regions``'s resolved-offset payload can be validated through
    the same fail-closed checks as a hand-written ``--regions`` map, without
    a round trip through the filesystem.
    """
    if not isinstance(raw, dict):
        raise RegionMapError(f"{where}: expected a top-level object")

    unknown = set(raw.keys()) - _MAP_ALLOWED_KEYS
    if unknown:
        raise RegionMapError(
            f"{where}: unknown top-level key(s) {sorted(unknown)} — only 'regions' and "
            "'groups' are accepted; 'data'/'data_schema' are derived outputs, not inputs"
        )

    regions_raw = raw.get("regions", [])
    groups_raw = raw.get("groups", [])
    if not isinstance(regions_raw, list):
        raise RegionMapError(f"{where}: 'regions' must be a list")
    if not isinstance(groups_raw, list):
        raise RegionMapError(f"{where}: 'groups' must be a list")

    regions = [_parse_region(r, i) for i, r in enumerate(regions_raw)]
    groups = [_parse_group(g, i) for i, g in enumerate(groups_raw)]

    group_ids = {g.id for g in groups}
    for i, r in enumerate(regions):
        if r.group is not None and r.group not in group_ids:
            raise RegionMapError(f"regions[{i}].group: unknown group id {r.group!r}")

    return DiscoveryResult(data_schema={}, data={}, regions=regions, groups=groups)


def load_regions(path: Path) -> DiscoveryResult:
    """Fail-closed parse of the ``--regions`` map file.

    Thin file-reading wrapper over :func:`_parse_region_map` (FEAT-3315).
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegionMapError(f"{path}: could not read/parse region map: {exc}") from exc

    return _parse_region_map(raw, where=str(path))


# --------------------------------------------------------------------------
# extract_data / derive_schema
# --------------------------------------------------------------------------


def _set_nested(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _region_iteration_index(region: Region, group: RegionGroup) -> int:
    for idx, (it_start, it_end) in enumerate(group.iterations):
        if it_start <= region.start and region.end <= it_end:
            return idx
    raise SpliceError(
        f"region at [{region.start}, {region.end}) (group {group.id!r}) does not fall "
        "within any declared iteration span"
    )


def extract_data(artifact: bytes, result: DiscoveryResult) -> dict[str, Any]:
    """Fill ``data`` from the artifact bytes at each region span.

    Raises SpliceError on a duplicate top-level ``expr`` whose two spans'
    bytes differ, naming both offsets.
    """
    data: dict[str, Any] = {}
    seen_top_level: dict[str, tuple[int, int, str]] = {}

    groups_by_id = {g.id: g for g in result.groups}

    for region in result.regions:
        if region.group is None:
            try:
                value = artifact[region.start : region.end].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SpliceError(
                    f"region {region.expr!r} at [{region.start}, {region.end}) is not valid "
                    f"UTF-8 (span lands mid-multibyte-sequence): {exc}"
                ) from exc
            if region.expr in seen_top_level:
                prev_start, prev_end, prev_value = seen_top_level[region.expr]
                if prev_value != value:
                    raise SpliceError(
                        f"duplicate expr {region.expr!r} at [{prev_start}, {prev_end}) and "
                        f"[{region.start}, {region.end}) extract different bytes"
                    )
                continue
            seen_top_level[region.expr] = (region.start, region.end, value)
            _set_nested(data, region.expr, value)

    for group in result.groups:
        per_iteration: list[dict[str, str]] = [{} for _ in group.iterations]
        for region in result.regions:
            if region.group != group.id:
                continue
            idx = _region_iteration_index(region, group)
            try:
                value = artifact[region.start : region.end].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise SpliceError(
                    f"region {region.expr!r} at [{region.start}, {region.end}) (group "
                    f"{group.id!r}) is not valid UTF-8 (span lands mid-multibyte-sequence): {exc}"
                ) from exc
            per_iteration[idx][region.expr] = value
        _set_nested(data, group.array_path, per_iteration)
        groups_by_id.pop(group.id, None)

    return data


def derive_schema(result: DiscoveryResult) -> dict[str, Any]:
    """Build ``data_schema`` from the region expression paths."""

    def ensure_object(node: dict[str, Any]) -> dict[str, Any]:
        node.setdefault("type", "object")
        node.setdefault("properties", {})
        return node["properties"]  # type: ignore[no-any-return]

    schema: dict[str, Any] = {"type": "object", "properties": {}}

    for region in result.regions:
        if region.group is not None:
            continue
        parts = region.expr.split(".")
        props = schema["properties"]
        for part in parts[:-1]:
            sub = props.setdefault(part, {"type": "object", "properties": {}})
            props = ensure_object(sub)
        props[parts[-1]] = {"type": "string"}

    for group in result.groups:
        field_names: list[str] = []
        seen: set[str] = set()
        for region in result.regions:
            if region.group == group.id and region.expr not in seen:
                seen.add(region.expr)
                field_names.append(region.expr)

        item_schema: dict[str, Any] = {
            "type": "object",
            "properties": {name: {"type": "string"} for name in field_names},
        }

        parts = group.array_path.split(".")
        props = schema["properties"]
        for part in parts[:-1]:
            sub = props.setdefault(part, {"type": "object", "properties": {}})
            props = ensure_object(sub)
        props[parts[-1]] = {"type": "array", "items": item_schema}

    return schema


# --------------------------------------------------------------------------
# escape_literal_delimiters
# --------------------------------------------------------------------------


def escape_literal_delimiters(text: bytes) -> bytes:
    """Wrap any pre-existing ``[[=``/``[[%``/``[[#`` in ``[[% raw %]]``/``endraw``.

    Raises SpliceError if a literal ``[[% endraw %]]`` is present — it
    terminates the wrapper from inside and Jinja2 offers no escape for it.
    """
    if b"[[% endraw %]]" in text:
        offset = text.index(b"[[% endraw %]]")
        raise SpliceError(
            f"literal '[[% endraw %]]' at byte offset {offset} cannot be escaped "
            "(it would terminate its own raw wrapper) — Phase A hard-errors rather than "
            "emit a template that cannot parse"
        )

    if not any(token in text for token in _DELIMITER_TOKENS):
        return text

    out = bytearray()
    i = 0
    n = len(text)
    while i < n:
        matched = None
        for token in _DELIMITER_TOKENS:
            if text.startswith(token, i):
                matched = token
                break
        if matched is None:
            out.append(text[i])
            i += 1
            continue
        # Find the closing delimiter for this token to wrap the whole construct.
        closers = {b"[[=": b"=]]", b"[[%": b"%]]", b"[[#": b"#]]"}
        closer = closers[matched]
        end = text.find(closer, i + len(matched))
        if end == -1:
            # No closer found; escape just the opening token itself.
            out += _RAW_START + matched + _RAW_END
            i += len(matched)
            continue
        end += len(closer)
        out += _RAW_START + text[i:end] + _RAW_END
        i = end
    return bytes(out)


# --------------------------------------------------------------------------
# apply_regions
# --------------------------------------------------------------------------


def _preceding_line_prefix(artifact: bytes, pos: int) -> bytes:
    nl = artifact.rfind(b"\n", 0, pos)
    return artifact[nl + 1 : pos]


def _is_whitespace_only(b: bytes) -> bool:
    return b == b"" or b.strip(b" \t") == b""


def _splice_group(
    artifact: bytes, group: RegionGroup, result: DiscoveryResult
) -> tuple[bytes, int]:
    """Return (replacement_bytes, extra_bytes_consumed_past group.end)."""
    if not group.iterations:
        raise SpliceError(f"group {group.id!r}: no iterations declared")

    iter0_start, iter0_end = group.iterations[0]

    def iteration_regions(it_start: int, it_end: int) -> list[Region]:
        return sorted(
            (
                r
                for r in result.regions
                if r.group == group.id and it_start <= r.start and r.end <= it_end
            ),
            key=lambda r: r.start,
        )

    def literal_segments(it_start: int, it_end: int, regions: list[Region]) -> list[bytes]:
        segments = []
        cursor = it_start
        for r in regions:
            segments.append(artifact[cursor : r.start])
            cursor = r.end
        segments.append(artifact[cursor:it_end])
        return segments

    iter0_regions = iteration_regions(iter0_start, iter0_end)
    iter0_segments = literal_segments(iter0_start, iter0_end, iter0_regions)

    for it_start, it_end in group.iterations[1:]:
        it_regions = iteration_regions(it_start, it_end)
        it_segments = literal_segments(it_start, it_end, it_regions)
        if len(it_segments) != len(iter0_segments):
            raise SpliceError(
                f"group {group.id!r}: iteration [{it_start}, {it_end}) has a different "
                f"region count than iteration 1"
            )
        cursor = it_start
        for seg_idx, (expected, actual) in enumerate(zip(iter0_segments, it_segments, strict=True)):
            if expected != actual:
                # locate first differing byte offset within this segment
                offset = cursor
                for a, b in zip(expected, actual, strict=False):
                    if a != b:
                        break
                    offset += 1
                raise SpliceError(
                    f"group {group.id!r}: iteration [{it_start}, {it_end}) literal text "
                    f"differs from iteration 1 starting at byte offset {offset}"
                )
            if seg_idx < len(it_regions):
                cursor = it_regions[seg_idx].end

    # Build iteration-1 body with field regions rewritten to [[= binding.field =]]
    body = bytearray()
    cursor = iter0_start
    for r in iter0_regions:
        body += escape_literal_delimiters(artifact[cursor : r.start])
        body += f"[[= {group.binding}.{r.expr} =]]".encode()
        cursor = r.end
    body += escape_literal_delimiters(artifact[cursor:iter0_end])

    for_tag = f"[[% for {group.binding} in {group.array_path} %]]".encode()
    endfor_tag = b"[[% endfor %]]"

    prefix = _preceding_line_prefix(artifact, group.start)
    suffix_is_newline = group.end < len(artifact) and artifact[group.end : group.end + 1] == b"\n"
    prefix_is_ws = _is_whitespace_only(prefix)

    if prefix_is_ws and suffix_is_newline:
        content_after_indent = artifact[group.start : iter0_end].lstrip(b" \t")
        indent_width = (iter0_end - group.start) - len(content_after_indent)
        indent = artifact[group.start : group.start + indent_width]
        replacement = indent + for_tag + b"\n" + bytes(body) + b"\n" + indent + endfor_tag + b"\n"
        return bytes(replacement), 1  # consume the trailing newline too
    if not prefix_is_ws and not suffix_is_newline:
        replacement = for_tag + bytes(body) + endfor_tag
        return bytes(replacement), 0
    raise SpliceError(
        f"group {group.id!r} at [{group.start}, {group.end}) has a mixed block-tag "
        "boundary (whitespace-only prefix without a following newline, or "
        "newline-followed without a whitespace-only prefix) — every emitted block tag "
        "must be either fully own-line or fully mid-line"
    )


def apply_regions(artifact: bytes, result: DiscoveryResult) -> bytes:
    """Pure, LLM-free splice over sorted, non-overlapping spans.

    Overlapping or out-of-bounds spans are a hard error, not a best-effort
    merge.
    """
    spans: list[tuple[int, int, str, Any]] = []
    for r in result.regions:
        if r.group is None:
            spans.append((r.start, r.end, "region", r))
    for g in result.groups:
        spans.append((g.start, g.end, "group", g))

    spans.sort(key=lambda s: s[0])

    out = bytearray()
    cursor = 0
    prev_end = -1
    n = len(artifact)
    for start, end, kind, obj in spans:
        if start < 0 or end > n or end < start:
            raise SpliceError(f"span [{start}, {end}) is out of bounds for artifact of length {n}")
        if start < prev_end:
            raise SpliceError(
                f"span [{start}, {end}) overlaps a preceding span ending at {prev_end}"
            )
        out += escape_literal_delimiters(artifact[cursor:start])
        if kind == "region":
            out += f"[[= {obj.expr} =]]".encode()
            cursor = end
        else:
            replacement, extra = _splice_group(artifact, obj, result)
            out += replacement
            cursor = end + extra
        prev_end = cursor

    out += escape_literal_delimiters(artifact[cursor:])
    return bytes(out)


# --------------------------------------------------------------------------
# build_manifest
# --------------------------------------------------------------------------


def build_manifest(
    name: str, output: str, schema: dict[str, Any], source: Path, extraction: dict[str, Any]
) -> dict[str, Any]:
    """Build the ``manifest.yaml`` payload for a templatized artifact."""
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if isinstance(properties, dict) and _RESERVED_CONTEXT_KEY in properties:
        raise SpliceError(
            f"region binds reserved top-level name '{_RESERVED_CONTEXT_KEY}', which is "
            "reserved for the render context"
        )
    return {
        "name": name,
        "version": 1,
        "renderer": "jinja2",
        "output": output,
        "data_schema": schema,
        "source": str(source),
        "extraction": extraction,
    }


# --------------------------------------------------------------------------
# verify_round_trip
# --------------------------------------------------------------------------


def _render_tmp_dir(tmp_dir: Path, data: dict[str, Any], config: object) -> str:
    """Shared ``load_manifest`` -> ``ArtifactTemplate`` -> ``render_template`` prologue.

    Factored out (ENH-3319) so :func:`verify_lift_renders` reuses the exact
    sequence :func:`verify_round_trip` already performs, minus the
    ``difflib`` comparison.
    """
    manifest = load_manifest(tmp_dir)
    template = ArtifactTemplate(root=tmp_dir, manifest=manifest)
    return render_template(template, data, config)


def verify_round_trip(
    template_dir: Path, data: dict[str, Any], original: bytes, config: object
) -> str | None:
    """Render *template_dir* against *data* and diff against *original* bytes.

    Returns a unified diff string on mismatch, or ``None`` on an exact match.
    """
    import difflib

    rendered = _render_tmp_dir(template_dir, data, config)
    rendered_bytes = rendered.encode("utf-8")
    if rendered_bytes == original:
        return None
    diff = difflib.unified_diff(
        original.decode("utf-8", errors="replace").splitlines(keepends=True),
        rendered.splitlines(keepends=True),
        fromfile="original",
        tofile="rendered",
    )
    return "".join(diff)


# --------------------------------------------------------------------------
# promote
# --------------------------------------------------------------------------


def _sweep_stale_siblings(out_dir: Path) -> None:
    parent = out_dir.parent
    if not parent.is_dir():
        return
    prefix_tmp = f"{out_dir.name}.tmp-"
    prefix_bak = f"{out_dir.name}.bak-"
    for entry in parent.iterdir():
        if entry.name.startswith(prefix_tmp) or entry.name.startswith(prefix_bak):
            shutil.rmtree(entry, ignore_errors=True)


def promote(tmp_dir: Path, out_dir: Path, force: bool) -> None:
    """Promote *tmp_dir* into *out_dir* via a sibling-temp-dir, backup/restore flow.

    Not a bare ``os.replace`` — that raises on an existing non-empty
    directory (ENOTEMPTY) and across filesystems (EXDEV).
    """
    if out_dir.exists() and not force:
        raise SpliceError(f"{out_dir} already exists (use --force to overwrite)")

    backup_dir = out_dir.parent / f"{out_dir.name}.bak-{os.getpid()}"
    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    existed = out_dir.exists()
    if existed:
        os.replace(out_dir, backup_dir)
    try:
        os.replace(tmp_dir, out_dir)
    except OSError:
        if existed:
            os.replace(backup_dir, out_dir)
        raise
    if existed:
        shutil.rmtree(backup_dir, ignore_errors=True)


# --------------------------------------------------------------------------
# report_token_literals (FEAT-3316) — baked design-token color literals
# --------------------------------------------------------------------------


class UnliftedToken(TypedDict):
    literal: str
    candidate_names: list[str]
    occurrences: int


# Colors only (§ Matching rule) — every other tokens.resolved namespace
# (space, radius, font, bare numbers) is out of scope for v1.
_HEX_LITERAL_RE = re.compile(r"#[0-9a-fA-F]+")
_FUNCTIONAL_COLOR_RE = re.compile(r"\b(?:rgba?|hsla?)\s*\([^)]*\)", re.IGNORECASE)
_TOKEN_SCAN_RE = re.compile(
    f"{_HEX_LITERAL_RE.pattern}|{_FUNCTIONAL_COLOR_RE.pattern}", re.IGNORECASE
)


def _normalize_hex(value: str) -> str | None:
    lowered = value.strip().lower()
    if not lowered.startswith("#"):
        return None
    digits = lowered[1:]
    if not digits or any(c not in "0123456789abcdef" for c in digits):
        return None
    if len(digits) in (3, 4):
        digits = "".join(c * 2 for c in digits)
    elif len(digits) not in (6, 8):
        return None
    return "#" + digits


def _normalize_color_value(value: str) -> str | None:
    """Normalize *value* for color-literal comparison, or None if not a color.

    Hex forms are lowercased with `#abc`/`#abcd` shorthand expanded to
    `#aabbcc`/`#aabbccdd`. Functional forms (`rgb()`/`rgba()`/`hsl()`/
    `hsla()`) are compared case-insensitively with whitespace runs collapsed
    — no component parsing or cross-notation equivalence (§ Matching rule).
    """
    stripped = value.strip()
    if stripped.startswith("#"):
        return _normalize_hex(stripped)
    lowered = stripped.lower()
    if re.match(r"^(?:rgba?|hsla?)\s*\(", lowered):
        return re.sub(r"\s+", " ", lowered)
    return None


class TokenLiteralMatch(TypedDict):
    """A single regex-match occurrence of a baked design-token color literal.

    Sibling of :class:`UnliftedToken` that exposes ``.start()``/``.end()``
    per-occurrence spans (ENH-3319), which :func:`report_token_literals`
    discards into aggregate counts. ``literal`` is the *normalized* form
    (§ Matching rule), not the original on-disk bytes — callers that need
    to restore the exact original text must re-slice the source text at
    ``[start, end)``.
    """

    start: int
    end: int
    literal: str
    candidate_names: list[str]


def find_token_literals(template_text: str, tokens: DesignTokens) -> list[TokenLiteralMatch]:
    """Span-returning primitive over baked design-token color literals (ENH-3319).

    Every regex match is included regardless of CSS-value position — the
    CSS-context guard (Decision Rules § CSS-context guard) only decides
    *lift* eligibility (:func:`lift_token_literals`), not whether a match is
    reported. This keeps :func:`report_token_literals`'s aggregation, and
    therefore ``TestReportTokenLiterals``, unaffected by this issue.
    """
    value_to_names: dict[str, list[str]] = {}
    for name, value in tokens.resolved.items():
        normalized = _normalize_color_value(str(value))
        if normalized is None:
            continue
        value_to_names.setdefault(normalized, []).append(name)

    if not value_to_names:
        return []

    matches: list[TokenLiteralMatch] = []
    for match in _TOKEN_SCAN_RE.finditer(template_text):
        normalized = _normalize_color_value(match.group(0))
        if normalized is None or normalized not in value_to_names:
            continue
        matches.append(
            TokenLiteralMatch(
                start=match.start(),
                end=match.end(),
                literal=normalized,
                candidate_names=sorted(value_to_names[normalized]),
            )
        )
    return matches


def _aggregate_matches(matches: list[TokenLiteralMatch]) -> list[UnliftedToken]:
    """Aggregate per-occurrence matches into the today's-shape ``UnliftedToken`` list."""
    counts: dict[str, int] = {}
    candidate_names: dict[str, list[str]] = {}
    for m in matches:
        literal = m["literal"]
        counts[literal] = counts.get(literal, 0) + 1
        candidate_names[literal] = m["candidate_names"]
    return [
        UnliftedToken(
            literal=literal,
            candidate_names=sorted(candidate_names[literal]),
            occurrences=count,
        )
        for literal, count in sorted(counts.items())
    ]


def report_token_literals(template_text: str, tokens: DesignTokens) -> list[UnliftedToken]:
    """Report baked design-token color literals in *template_text* (FEAT-3316).

    Report-only — this does not rewrite anything. *template_text* must be
    the spliced template body (never the original artifact), since extracted
    data regions are not part of the template (§ Scan input). The value ->
    token-name inversion of ``tokens.resolved`` is not injective, so a
    matched literal maps to every candidate name (§ Matching rule).

    Reimplemented (ENH-3319) as a thin aggregation over the span-returning
    :func:`find_token_literals` — signature and return shape unchanged.
    """
    return _aggregate_matches(find_token_literals(template_text, tokens))


# --------------------------------------------------------------------------
# --lift-tokens (ENH-3319) — rewrite matched literals to var(--...) refs
# --------------------------------------------------------------------------

# § CSS-context guard: rewrites fire only in CSS-value position — inside a
# <style>...</style> element or a style="..." attribute value — and only
# when the nearest preceding delimiter is ':' and the nearest following
# delimiter is ';' or '}' (scope-then-nearest-delimiter rule).
_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_STYLE_ATTR_RE = re.compile(r"""style\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
_BACKWARD_DELIMS = frozenset(":;{}")
_FORWARD_DELIMS = frozenset(";{}")


def _css_value_scopes(text: str) -> list[tuple[int, int]]:
    scopes: list[tuple[int, int]] = []
    for m in _STYLE_BLOCK_RE.finditer(text):
        scopes.append((m.start(1), m.end(1)))
    for m in _STYLE_ATTR_RE.finditer(text):
        scopes.append((m.start(2), m.end(2)))
    return scopes


def _is_css_value_position(text: str, start: int, end: int) -> bool:
    """Decision Rules § CSS-context guard: scope test, then nearest-delimiter test.

    A match outside CSS-value position (a fragment attribute, a CSS
    selector, script-string text, or a presentation attribute like inline
    SVG ``fill``) is never eligible for rewriting — only for reporting.
    """
    scope: tuple[int, int] | None = None
    for scope_start, scope_end in _css_value_scopes(text):
        if scope_start <= start and end <= scope_end:
            scope = (scope_start, scope_end)
            break
    if scope is None:
        return False
    scope_start, scope_end = scope

    backward_char: str | None = None
    for i in range(start - 1, scope_start - 1, -1):
        if text[i] in _BACKWARD_DELIMS:
            backward_char = text[i]
            break
    if backward_char != ":":
        return False

    forward_char = ";"  # reaching the scope boundary (closing quote / block end) terminates
    for j in range(end, scope_end):
        if text[j] in _FORWARD_DELIMS:
            forward_char = text[j]
            break
    return forward_char in (";", "}")


def _raw_layered_flat(tokens: DesignTokens) -> dict[str, Any]:
    """Mirror the loader's raw-layer merge order (``design_tokens.py:376-381``).

    Reads the same raw nested layers the loader flattens *before* alias
    resolution — semantic, typography, spacing, theme, in that order — so
    the alias-preference filter can ask "was this name's pre-resolution
    value an alias reference?" without re-deriving that from
    ``tokens.resolved``, which has already erased it. Primitives are absent
    from every raw layer (injected into ``resolved`` separately) and are
    therefore correctly treated as non-alias by a plain ``.get()`` miss.
    """
    from little_loops.design_tokens import _flatten

    if tokens.source == "design_md":
        # DESIGN.md has no separate typography.json/spacing.json files;
        # tokens.semantic is the only raw layer (design_tokens.py:504-512).
        return _flatten(tokens.semantic)

    from little_loops.design_tokens import _load_json

    root = tokens.source_path
    typography = _load_json(root / "typography.json")
    spacing = _load_json(root / "spacing.json")
    return {
        **_flatten(tokens.semantic),
        **_flatten(typography),
        **_flatten(spacing),
        **_flatten(tokens.theme),
    }


def _is_alias_reference(raw_value: Any) -> bool:
    return isinstance(raw_value, str) and raw_value.startswith("{") and raw_value.endswith("}")


def _alias_preferred_candidate_map(tokens: DesignTokens) -> dict[str, str]:
    """Build normalized-literal-value -> single winning token name (Decision Rules
    § Ambiguous literal-to-token mapping).

    Only literal values with exactly one alias-preferred candidate survive;
    everything else (zero aliases, or two-or-more) is absent from the map
    and therefore never lifted. ``_``-prefixed names are excluded entirely,
    mirroring ``render_as_css_vars_themed``'s metadata skip
    (``design_tokens.py:701-702``).
    """
    raw_flat = _raw_layered_flat(tokens)

    value_to_names: dict[str, list[str]] = {}
    for name, value in tokens.resolved.items():
        if name.startswith("_"):
            continue
        normalized = _normalize_color_value(str(value))
        if normalized is None:
            continue
        value_to_names.setdefault(normalized, []).append(name)

    candidate_map: dict[str, str] = {}
    for literal, names in value_to_names.items():
        aliased = [n for n in names if _is_alias_reference(raw_flat.get(n))]
        if len(aliased) == 1:
            candidate_map[literal] = aliased[0]
    return candidate_map


def lift_token_literals(
    spliced: bytes, tokens: DesignTokens
) -> tuple[bytes, list[TokenLiteralMatch], list[TokenLiteralMatch], list[tuple[int, int]]]:
    """Rewrite eligible color literals to ``var(--name)`` references (ENH-3319).

    A separate pass over the already-spliced body (Decision Rules
    § Splice placement) — never composed into ``apply_regions``'s span
    list. Collected ``(start, end, replacement)`` spans are applied in
    **reverse order**, per ``issues/anchor_sweep.py:59``.

    Returns ``(lifted_body, lifted, unlifted, lift_spans)``: the lifted
    body bytes, the per-occurrence matches that were rewritten (each
    ``candidate_names`` is the single winning token name), the
    per-occurrence matches that were not, and ``lift_spans`` — the
    position of each rewritten ``var(--x)`` reference *in the returned
    body's coordinate space*, index-aligned with ``lifted``, for
    :func:`verify_lift_reversible` to consume.
    """
    text = spliced.decode("utf-8")
    matches = find_token_literals(text, tokens)
    alias_map = _alias_preferred_candidate_map(tokens)

    lifted: list[TokenLiteralMatch] = []
    unlifted: list[TokenLiteralMatch] = []
    write_spans: list[tuple[int, int, str]] = []

    for m in matches:
        var_name = alias_map.get(m["literal"])
        if var_name is not None and _is_css_value_position(text, m["start"], m["end"]):
            replacement = f"var(--{var_name.replace('.', '-')})"
            write_spans.append((m["start"], m["end"], replacement))
            lifted.append(
                TokenLiteralMatch(
                    start=m["start"], end=m["end"], literal=m["literal"], candidate_names=[var_name]
                )
            )
        else:
            unlifted.append(m)

    ordered_spans = sorted(write_spans, key=lambda s: s[0])

    new_text = text
    for start, end, replacement in reversed(ordered_spans):
        new_text = new_text[:start] + replacement + new_text[end:]

    # lift_spans is computed independently via forward cumulative-delta
    # accumulation so it reflects the *final* text regardless of which
    # order the string was actually built in above.
    lift_spans: list[tuple[int, int]] = []
    delta = 0
    for start, end, replacement in ordered_spans:
        new_start = start + delta
        new_end = new_start + len(replacement)
        lift_spans.append((new_start, new_end))
        delta += len(replacement) - (end - start)

    return new_text.encode("utf-8"), lifted, unlifted, lift_spans


# --------------------------------------------------------------------------
# Stamp injection (ENH-3319) — [[= ll.theme_css =]], data-theme, manifest.theme
# --------------------------------------------------------------------------

_HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_STYLE_OPEN_RE = re.compile(r"<style\b[^>]*>", re.IGNORECASE)
_HTML_OPEN_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE)
_DATA_THEME_ATTR_RE = re.compile(r"""data-theme\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


def _themed_css_vars(config: object) -> str:
    """Thin, patchable wrapper over ``artifact_template_kit.themed_css_vars``."""
    from little_loops.artifact_template_kit import themed_css_vars

    return themed_css_vars(config)


def _check_lift_preconditions(
    body_text: str,
    dt_cfg: Any,
    tokens: DesignTokens,
    emitted_var_names: set[str],
    config: object,
) -> str | None:
    """Decision Rules § Hard preconditions — all five must hold, or no lift at all.

    Returns a human-readable description of the first failed precondition,
    or ``None`` if all five hold.
    """
    head_match = _HEAD_OPEN_RE.search(body_text)
    style_match = _STYLE_OPEN_RE.search(body_text)
    if head_match is None and style_match is None:
        return "precondition 1: no <head> or <style> element to place the theme stamp point"

    if _HTML_OPEN_RE.search(body_text) is None:
        return "precondition 2: no root <html> element to carry the data-theme attribute"

    active_theme = dt_cfg.active_theme
    existing = _DATA_THEME_ATTR_RE.search(body_text)
    if existing is not None and existing.group(1) != active_theme:
        return (
            f'precondition 3: body already carries data-theme="{existing.group(1)}", which '
            f'disagrees with the active theme "{active_theme}"'
        )

    if tokens.source != "design_md" and active_theme not in ("light", "dark"):
        return (
            f"precondition 4: active_theme {active_theme!r} is neither 'light' nor 'dark' "
            "(and source is not design_md)"
        )

    try:
        css_text = _themed_css_vars(config)
    except Exception as exc:  # noqa: BLE001 — a raising themed_css_vars is a failed precondition
        return f"precondition 5: themed_css_vars(config) raised: {exc}"

    declared = set(re.findall(r"--([A-Za-z0-9-]+)\s*:", css_text))
    missing = {name for name in emitted_var_names if name not in declared}
    if missing:
        return f"precondition 5: themed_css_vars(config) does not declare: {', '.join(sorted(missing))}"

    return None


def _inject_theme_stamp(
    body_text: str, active_theme: str, lift_spans: list[tuple[int, int]] | None = None
) -> tuple[str, list[tuple[int, int]], list[tuple[int, int]]]:
    """Inject the ``[[= ll.theme_css =]]`` stamp point and ``data-theme`` attribute.

    Preconditions must already hold. The stamp goes immediately after the
    ``<head>`` open tag, ahead of every author ``<style>`` (Decision Rules
    § Stamp insertion position); when no ``<head>`` exists but a ``<style>``
    does, ``[[= ll.theme_css =]]`` is prepended at the top of that existing
    block instead, which preserves the same "author declarations win"
    ordering by construction.

    Both insertion points sit earlier in the document than any literal this
    issue rewrites (inside ``<head>``/an existing ``<style>``, ahead of the
    body), so inserting them shifts every already-recorded ``lift_spans``
    entry forward by however much text lands before it — this function
    re-bases *lift_spans* accordingly rather than leaving that to the
    caller, since a caller computing it independently is exactly the kind
    of drift ``verify_lift_reversible`` exists to catch. Returns
    ``(new_text, stamp_spans, rebased_lift_spans)``, all in the *returned*
    text's coordinate space.
    """
    insertions: list[tuple[int, str]] = []

    head_match = _HEAD_OPEN_RE.search(body_text)
    if head_match is not None:
        insertions.append((head_match.end(), "<style>[[= ll.theme_css =]]</style>"))
    else:
        style_match = _STYLE_OPEN_RE.search(body_text)
        assert style_match is not None  # precondition 1 already checked
        insertions.append((style_match.end(), "[[= ll.theme_css =]]"))

    html_match = _HTML_OPEN_RE.search(body_text)
    assert html_match is not None  # precondition 2 already checked
    existing_attr = _DATA_THEME_ATTR_RE.search(body_text[html_match.start() : html_match.end()])
    if existing_attr is None:
        insertions.append((html_match.end() - 1, f' data-theme="{active_theme}"'))

    insertions.sort(key=lambda ins: ins[0])

    parts: list[str] = []
    cursor = 0
    stamp_spans: list[tuple[int, int]] = []
    for pos, ins_text in insertions:
        parts.append(body_text[cursor:pos])
        start_final = sum(len(p) for p in parts)
        parts.append(ins_text)
        stamp_spans.append((start_final, start_final + len(ins_text)))
        cursor = pos
    parts.append(body_text[cursor:])
    new_text = "".join(parts)

    def _shift(pos: int) -> int:
        return pos + sum(len(ins_text) for ins_pos, ins_text in insertions if ins_pos <= pos)

    rebased_lift_spans = [(_shift(s), _shift(e)) for s, e in (lift_spans or [])]

    return new_text, stamp_spans, rebased_lift_spans


def verify_lift_reversible(
    lifted: bytes,
    pre_lift: bytes,
    lift_matches: list[TokenLiteralMatch],
    lift_spans: list[tuple[int, int]],
    stamp_spans: list[tuple[int, int]],
) -> str | None:
    """Undo the recorded lift + stamp spans; assert byte equality against *pre_lift*.

    Span-tracked, never a whole-body textual ``var()`` -> literal
    substitution (Decision Rules § Reversibility) — restores the exact
    original bytes at each recorded span (read from *pre_lift* itself, not
    the normalized ``literal`` field) and removes the injected stamp
    spans. Returns a unified diff on mismatch, or ``None`` on success.
    """
    pre_lift_text = pre_lift.decode("utf-8")
    lifted_text = lifted.decode("utf-8")

    undo_spans: list[tuple[int, int, str]] = []
    for match, (start, end) in zip(lift_matches, lift_spans, strict=True):
        original = pre_lift_text[match["start"] : match["end"]]
        undo_spans.append((start, end, original))
    for start, end in stamp_spans:
        undo_spans.append((start, end, ""))

    undo_spans.sort(key=lambda s: s[0])
    prev_end = -1
    for start, end, _ in undo_spans:
        if start < prev_end:
            return f"overlapping undo spans at byte offset {start}"
        prev_end = end

    new_text = lifted_text
    for start, end, replacement in reversed(undo_spans):
        new_text = new_text[:start] + replacement + new_text[end:]

    result_bytes = new_text.encode("utf-8")
    if result_bytes == pre_lift:
        return None

    import difflib

    diff = difflib.unified_diff(
        pre_lift_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="pre_lift",
        tofile="un-lifted",
    )
    return "".join(diff)


def verify_lift_renders(
    tmp_dir: Path, data: dict[str, Any], emitted_var_names: set[str], config: object
) -> str | None:
    """Re-render *tmp_dir* from disk; assert a ``--x:`` declaration for every emitted
    ``var(--x)`` reference (Decision Rules § Post-lift render verification).

    Deliberately does **not** assert the absence of ``[[=``/``[[%`` in the
    rendered output — ``escape_literal_delimiters`` (``templatize.py:327-339``)
    makes a source artifact's own delimiters render back as literal ``[[=``
    text by design, so such a check would false-reject a valid lift.
    """
    rendered = _render_tmp_dir(tmp_dir, data, config)
    missing = [name for name in emitted_var_names if f"--{name}:" not in rendered]
    if missing:
        return (
            "lifted body's rendered output is missing a declaration for: "
            f"{', '.join(sorted(missing))}"
        )
    return None


@dataclass
class _LiftOutcome:
    stamped_bytes: bytes | None
    lifted: list[TokenLiteralMatch]
    unlifted: list[TokenLiteralMatch]
    skip_reason: str | None
    lift_spans: list[tuple[int, int]]
    stamp_spans: list[tuple[int, int]]
    tokens_available: bool


def _attempt_lift(spliced: bytes, config: object) -> _LiftOutcome:
    """Orchestrate the full ``--lift-tokens`` pipeline (steps 4-6), pure and
    side-effect-free: nothing is written to disk here.

    ``stamped_bytes`` is ``None`` unless every hard precondition holds *and*
    at least one literal was lift-eligible — the caller must then treat this
    exactly like the flag-off path (nothing rewritten), reporting
    ``unlifted`` (with ``skip_reason`` if a precondition actually failed).
    """
    from little_loops.config.core import BRConfig
    from little_loops.design_tokens import load_design_tokens

    assert isinstance(config, BRConfig)
    dt_cfg = config.design_tokens
    active_theme = dt_cfg.active_theme

    tokens = load_design_tokens(config, theme=active_theme)  # type: ignore[arg-type]
    if tokens is None:
        return _LiftOutcome(None, [], [], None, [], [], tokens_available=False)

    lifted_bytes, lifted, unlifted, lift_spans = lift_token_literals(spliced, tokens)

    if not lifted:
        return _LiftOutcome(None, [], unlifted, None, [], [], tokens_available=True)

    body_text = spliced.decode("utf-8")
    emitted_var_names = {m["candidate_names"][0].replace(".", "-") for m in lifted}
    skip_reason = _check_lift_preconditions(body_text, dt_cfg, tokens, emitted_var_names, config)
    if skip_reason is not None:
        return _LiftOutcome(None, [], lifted + unlifted, skip_reason, [], [], tokens_available=True)

    stamped_text, stamp_spans, rebased_lift_spans = _inject_theme_stamp(
        lifted_bytes.decode("utf-8"), active_theme, lift_spans
    )
    stamped_bytes = stamped_text.encode("utf-8")

    return _LiftOutcome(
        stamped_bytes,
        lifted,
        unlifted,
        None,
        rebased_lift_spans,
        stamp_spans,
        tokens_available=True,
    )


def _write_unlifted_tokens_report(
    tmp_dir: Path,
    unlifted: list[UnliftedToken],
    lifted: list[dict[str, Any]] | None = None,
    lift_skipped_reason: str | None = None,
) -> Path:
    """Write ``unlifted-tokens.json`` into *tmp_dir*, pre-promote (FEAT-3316/ENH-3319)."""
    payload = {
        "_comment": (
            "Design-token color literals in the spliced template body that match the "
            "resolved token map. With --lift-tokens, a matched literal in CSS-value "
            "position is rewritten to a var(--...) reference (see 'lifted') and the "
            "manifest sets theme: design-tokens; entries in 'unlifted' were left as "
            "literals (ambiguous candidate, outside CSS-value position, or a hard "
            "precondition failed — see 'lift_skipped_reason'). Without --lift-tokens "
            "(the default), this report is report-only: nothing is rewritten and the "
            "manifest does not set theme: design-tokens. Colors only "
            "(#rgb/#rgba/#rrggbb/#rrggbbaa and rgb()/rgba()/hsl()/hsla() functional "
            "forms) — other token namespaces (space, radius, font, bare numbers) are "
            "out of scope for v1. Regenerate by re-running `ll-artifact templatize`."
        ),
        "lifted": lifted or [],
        "unlifted": unlifted,
        "lift_skipped_reason": lift_skipped_reason,
    }
    path = tmp_dir / "unlifted-tokens.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def _aggregate_lifted(matches: list[TokenLiteralMatch]) -> list[dict[str, Any]]:
    """Aggregate per-occurrence lifted matches into the report's ``lifted`` list.

    Not a pinned shape (§ Types only pins ``UnliftedToken``'s three keys) —
    each entry records the literal, the winning token name, the mangled
    ``var()`` reference emitted, and an occurrence count.
    """
    counts: dict[str, int] = {}
    name_for: dict[str, str] = {}
    for m in matches:
        literal = m["literal"]
        counts[literal] = counts.get(literal, 0) + 1
        name_for[literal] = m["candidate_names"][0]
    return [
        {
            "literal": literal,
            "name": name_for[literal],
            "var": f"var(--{name_for[literal].replace('.', '-')})",
            "occurrences": count,
        }
        for literal, count in sorted(counts.items())
    ]


def _report_unlifted_tokens(
    tmp_dir: Path,
    spliced: bytes,
    config: object,
    logger: Logger,
    *,
    lifted: list[TokenLiteralMatch] | None = None,
    unlifted: list[TokenLiteralMatch] | None = None,
    lift_skipped_reason: str | None = None,
) -> None:
    """Run the token report step, fully contained (FEAT-3316/ENH-3319).

    No exception raised anywhere in this step may change cmd_templatize's
    exit code, block promote, or suppress the success line — a failure here
    surfaces only as a warning line.

    With ``lifted``/``unlifted`` both ``None`` (the flag-off default), this
    rescans *spliced* exactly as today. Under ``--lift-tokens``, the lift
    already computed the authoritative split, so the caller passes it in
    directly rather than letting this rescan the (possibly already-lifted)
    body, which would always yield an empty ``lifted`` list.
    """
    try:
        if lifted is None and unlifted is None:
            from little_loops.design_tokens import load_design_tokens

            tokens = load_design_tokens(config)  # type: ignore[arg-type]
            if tokens is None:
                return
            template_text = spliced.decode("utf-8", errors="replace")
            unlifted_report = report_token_literals(template_text, tokens)
            lifted_report: list[dict[str, Any]] = []
        else:
            unlifted_report = _aggregate_matches(unlifted or [])
            lifted_report = _aggregate_lifted(lifted or [])

        _write_unlifted_tokens_report(tmp_dir, unlifted_report, lifted_report, lift_skipped_reason)
        if unlifted_report:
            names = sorted({name for entry in unlifted_report for name in entry["candidate_names"]})
            logger.warning(
                f"{len(unlifted_report)} unlifted design-token color literal(s) baked into "
                f"template body: {', '.join(names)}"
            )
    except Exception as exc:  # noqa: BLE001 — report step must never affect exit code
        logger.warning(f"token report failed (non-blocking): {exc}")


# --------------------------------------------------------------------------
# cmd_templatize
# --------------------------------------------------------------------------


def _derive_body_suffix(artifact_path: Path) -> str:
    suffix = artifact_path.suffix
    if not suffix or suffix == ".":
        raise SpliceError(
            f"{artifact_path}: extensionless artifacts are unsupported (would derive an "
            "empty template.*.j2 suffix) — rename the artifact or pass -o with an "
            "explicit extension"
        )
    return suffix.lstrip(".")


def _resolve_output_dir(args: argparse.Namespace, config: object, artifact_path: Path) -> Path:
    from little_loops.config.core import BRConfig

    assert isinstance(config, BRConfig)
    if args.output:
        out = Path(args.output)
        if out.suffix != ".llat":
            out = out.with_name(out.name + ".llat")
    else:
        templates_dir = config.project_root / config.artifacts.templates_dir
        out = templates_dir / f"{artifact_path.stem}.llat"
    if not out.is_absolute():
        out = config.project_root / out
    return out


def cmd_templatize(args: argparse.Namespace, logger: Logger) -> int:
    """Templating: artifact + (--regions map | LLM discovery) -> a .llat/ template.

    With ``--regions``, runs the deterministic Phase A (FEAT-3314) path — no
    host call, no size-ceiling check, no ``source`` read. Without it, calls
    ``discover_regions`` (FEAT-3315 Phase B) to identify the regions by LLM.

    Returns 0 on success, 1 on malformed input / IO failure / discovery
    failure, 2 on round-trip rejection.
    """
    from little_loops.config.core import BRConfig

    try:
        config = BRConfig(Path.cwd())
        artifact_path = Path(args.artifact)
        source_path = Path(args.source)

        if not artifact_path.is_file():
            logger.error(f"artifact not found: {artifact_path}")
            return 1

        artifact_bytes = artifact_path.read_bytes()
        if b"\r" in artifact_bytes:
            logger.error(
                f"{artifact_path}: CRLF/CR line endings are unsupported — render_template "
                "reads the template body via read_text(), which applies universal-newline "
                "translation and would silently corrupt the round trip"
            )
            return 1

        try:
            body_suffix = _derive_body_suffix(artifact_path)
        except SpliceError as exc:
            logger.error(str(exc))
            return 1

        out_dir = _resolve_output_dir(args, config, artifact_path)
        _sweep_stale_siblings(out_dir)

        if out_dir.exists() and not args.force:
            logger.error(f"{out_dir} already exists (use --force to overwrite)")
            return 1

        rejected_dir = out_dir.with_name(out_dir.name + ".rejected")
        if rejected_dir.exists():
            shutil.rmtree(rejected_dir)

        discovery_raw: dict[str, Any] | None = None
        discovery_resolved: dict[str, Any] | None = None

        if args.regions:
            regions_path = Path(args.regions)
            if not regions_path.is_file():
                logger.error(f"regions map not found: {regions_path}")
                return 1
            try:
                result = load_regions(regions_path)
            except RegionMapError as exc:
                logger.error(str(exc))
                return 1
            extraction = {"method": "regions", "regions_map": str(regions_path)}
        else:
            if not source_path.is_file():
                logger.error(f"source not found: {source_path}")
                return 1
            try:
                source_text = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.error(f"{source_path}: could not read source document: {exc}")
                return 1

            combined_size = len(artifact_bytes) + len(source_text.encode("utf-8"))
            max_input_bytes = config.artifacts.templatize_max_input_bytes
            if combined_size > max_input_bytes:
                logger.error(
                    f"combined artifact+source size ({combined_size} bytes) exceeds "
                    f"artifacts.templatize_max_input_bytes ({max_input_bytes}) — no discovery "
                    "call issued"
                )
                return 1

            from little_loops.cli.artifact.discover import discover_regions

            try:
                response = discover_regions(artifact_bytes, source_text, config)
            except RegionMapError as exc:
                discovery_raw = getattr(exc, "raw", None)
                discovery_resolved = getattr(exc, "resolved", None)
                logger.error(str(exc))
                _write_rejected_discovery(rejected_dir, discovery_raw, discovery_resolved)
                return 1

            result = response.result
            discovery_raw = response.raw
            discovery_resolved = response.resolved
            extraction = {
                "method": "llm_discovery",
                "host": response.host,
                "model": response.model,
            }

        try:
            data = extract_data(artifact_bytes, result)
            schema = derive_schema(result)
            spliced = apply_regions(artifact_bytes, result)
            name = out_dir.stem
            from little_loops.cli.artifact.lockfile import relativize_path

            normalized_source = Path(relativize_path(source_path, config.project_root))
            manifest = build_manifest(
                name=name,
                output=artifact_path.name,
                schema=schema,
                source=normalized_source,
                extraction=extraction,
            )
        except (SpliceError, RegionMapError) as exc:
            logger.error(str(exc))
            _write_rejected_discovery(rejected_dir, discovery_raw, discovery_resolved)
            return 1

        out_dir.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"{out_dir.name}.tmp-", dir=out_dir.parent))
        try:
            (tmp_dir / f"template.{body_suffix}.j2").write_bytes(spliced)
            (tmp_dir / "data.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (tmp_dir / "manifest.yaml").write_text(_dump_manifest_yaml(manifest), encoding="utf-8")

            try:
                validate_top_level_data(data, manifest["data_schema"])
            except DataValidationError as exc:
                logger.error(str(exc))
                _write_rejected_discovery(rejected_dir, discovery_raw, discovery_resolved)
                return 1

            diff = verify_round_trip(tmp_dir, data, artifact_bytes, config)
            if diff is not None:
                rejected_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(tmp_dir, rejected_dir)
                (rejected_dir / "roundtrip.diff").write_text(diff, encoding="utf-8")
                _write_rejected_discovery(rejected_dir, discovery_raw, discovery_resolved)
                logger.error(
                    f"round-trip verification failed — candidate + diff written to {rejected_dir}"
                )
                return 2

            if getattr(args, "lift_tokens", False):
                outcome = _attempt_lift(spliced, config)
                if not outcome.tokens_available:
                    # Mirrors the flag-off "tokens is None" degradation:
                    # nothing to lift or report, no file written, exit 0.
                    pass
                elif outcome.stamped_bytes is not None:
                    reversibility_diff = verify_lift_reversible(
                        outcome.stamped_bytes,
                        spliced,
                        outcome.lifted,
                        outcome.lift_spans,
                        outcome.stamp_spans,
                    )
                    if reversibility_diff is not None:
                        rejected_dir.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(tmp_dir, rejected_dir)
                        (rejected_dir / "lift-reversibility.diff").write_text(
                            reversibility_diff, encoding="utf-8"
                        )
                        _write_rejected_discovery(rejected_dir, discovery_raw, discovery_resolved)
                        logger.error(
                            "lift reversibility verification failed — candidate + diff "
                            f"written to {rejected_dir}"
                        )
                        return 2

                    # Re-serialize tmp_dir before promote() — both the template
                    # body and manifest.yaml were already written pre-lift
                    # (§ Implementation Steps step 6's explicit warning).
                    (tmp_dir / f"template.{body_suffix}.j2").write_bytes(outcome.stamped_bytes)
                    manifest["theme"] = "design-tokens"
                    (tmp_dir / "manifest.yaml").write_text(
                        _dump_manifest_yaml(manifest), encoding="utf-8"
                    )

                    emitted_var_names = {
                        m["candidate_names"][0].replace(".", "-") for m in outcome.lifted
                    }
                    render_err = verify_lift_renders(tmp_dir, data, emitted_var_names, config)
                    if render_err is not None:
                        rejected_dir.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(tmp_dir, rejected_dir)
                        (rejected_dir / "lift-render-check.txt").write_text(
                            render_err, encoding="utf-8"
                        )
                        _write_rejected_discovery(rejected_dir, discovery_raw, discovery_resolved)
                        logger.error(
                            "post-lift render verification failed — candidate written to "
                            f"{rejected_dir}: {render_err}"
                        )
                        return 2

                    _report_unlifted_tokens(
                        tmp_dir,
                        spliced,
                        config,
                        logger,
                        lifted=outcome.lifted,
                        unlifted=outcome.unlifted,
                    )
                else:
                    _report_unlifted_tokens(
                        tmp_dir,
                        spliced,
                        config,
                        logger,
                        lifted=[],
                        unlifted=outcome.unlifted,
                        lift_skipped_reason=outcome.skip_reason,
                    )
            else:
                _report_unlifted_tokens(tmp_dir, spliced, config, logger)

            promote(tmp_dir, out_dir, force=bool(args.force))
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

        logger.success(f"Wrote {out_dir}")
        return 0
    except (ManifestError, SpliceError, RegionMapError) as exc:
        logger.error(str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001 — surface any failure as exit 1
        logger.error(str(exc))
        return 1


def _write_rejected_discovery(
    rejected_dir: Path, raw: dict[str, Any] | None, resolved: dict[str, Any] | None
) -> None:
    """Preserve the discovery response on a post-call failure (FEAT-3315 Proposed Solution 7).

    No-op on the ``--regions`` (non-discovery) path, where *raw* is always
    ``None``. ``rejected_dir`` may or may not already exist — the round-trip
    branch creates it via ``shutil.copytree`` before calling this; every
    other branch never reaches that copytree, so this creates it directly.
    """
    if raw is None:
        return
    rejected_dir.mkdir(parents=True, exist_ok=True)
    (rejected_dir / "discovery.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if resolved is not None:
        (rejected_dir / "regions.json").write_text(
            json.dumps(resolved, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def _dump_manifest_yaml(manifest: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)


def add_templatize_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``templatize`` subcommand parser."""
    templatize = subparsers.add_parser(
        "templatize",
        help=(
            "Save a generated artifact as a reusable .llat/ template — deterministic with "
            "--regions, or LLM-discovered region map without it"
        ),
    )
    templatize.add_argument(
        "artifact", type=str, help="Path to the generated artifact to templatize"
    )
    templatize.add_argument(
        "source",
        type=str,
        help=(
            "Path to the source document. With --regions, recorded into manifest.source but "
            "not read (every data.json value is captured from an artifact span). Without "
            "--regions, read and sent to the LLM discovery call."
        ),
    )
    templatize.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help=(
            "Output <name>.llat directory (default: "
            "config.artifacts.templates_dir/<artifact-stem>.llat)"
        ),
    )
    templatize.add_argument(
        "--regions",
        type=str,
        default=None,
        help=(
            "Path to a hand-written region map. When omitted, an LLM discovery call identifies "
            "the regions instead (subject to artifacts.templatize_max_input_bytes)."
        ),
    )
    templatize.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing template at the resolved -o path",
    )
    templatize.add_argument(
        "--lift-tokens",
        action="store_true",
        help=(
            "Rewrite baked-in color literals matching a resolved design token, in "
            "CSS-value position, to var(--dotted-name) references, and inject the "
            "[[= ll.theme_css =]] stamp point plus data-theme attribute so they resolve "
            "(default: off — report-only, byte-exact round trip). See "
            "docs/reference/CLI.md for the accepted limitations."
        ),
    )
