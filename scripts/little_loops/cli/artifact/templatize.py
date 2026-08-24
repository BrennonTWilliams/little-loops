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
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from little_loops.artifact_templates import (
    ArtifactTemplate,
    DataValidationError,
    ManifestError,
    load_manifest,
    render_template,
    validate_top_level_data,
)
from little_loops.logger import Logger

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


def verify_round_trip(
    template_dir: Path, data: dict[str, Any], original: bytes, config: object
) -> str | None:
    """Render *template_dir* against *data* and diff against *original* bytes.

    Returns a unified diff string on mismatch, or ``None`` on an exact match.
    """
    import difflib

    manifest = load_manifest(template_dir)
    template = ArtifactTemplate(root=template_dir, manifest=manifest)
    rendered = render_template(template, data, config)
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
            manifest = build_manifest(
                name=name,
                output=artifact_path.name,
                schema=schema,
                source=source_path,
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
