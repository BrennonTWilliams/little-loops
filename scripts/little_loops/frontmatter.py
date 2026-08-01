"""Frontmatter read/write utilities for little-loops.

Provides shared YAML-subset frontmatter parsing, stripping, and updating
used by issue_parser, sync, and issue_history modules.
"""

from __future__ import annotations

import logging
import re
import textwrap
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import yaml

logger = logging.getLogger(__name__)

STATUS_SYNONYMS: dict[str, str] = {
    "complete": "done",
    "completed": "done",
    "finished": "done",
    "closed": "done",
    "in-progress": "in_progress",
    "in progress": "in_progress",
    "wip": "in_progress",
    "pending": "open",
}


@dataclass(frozen=True)
class DeprecatedFrontmatterEntry:
    """A retired frontmatter key/value paired with a mandatory prose reason (ENH-2876).

    ``reason`` must be non-empty prose naming what replaced the retired
    key/value and why — a bare ``deprecated: true``-style flag with no
    explanation is exactly the gap this map closes. Enforced at construction
    time so a deprecation entry added without a reason fails immediately
    rather than silently defaulting to an empty string.
    """

    reason: str

    def __post_init__(self) -> None:
        if not self.reason or not self.reason.strip():
            raise ValueError("DeprecatedFrontmatterEntry requires a non-empty prose reason")


# Deprecated frontmatter *keys* — presence of the key itself is the signal.
# The already-retired cases come first (ENH-2876 AC3): superseded_by (ENH-2829,
# purely derived and never hand-authored) and the pre-existing renamed-key
# aliases (ENH-1434/BUG-... rename passes).
DEPRECATED_FRONTMATTER_KEYS: dict[str, DeprecatedFrontmatterEntry] = {
    "superseded_by": DeprecatedFrontmatterEntry(
        reason=(
            "Always derived from 'supersedes' on the replacement issue via "
            "issue_parser.superseded_by(); never hand-author this key — it is "
            "silently ignored on read (ENH-2829)."
        )
    ),
    "parent_issue": DeprecatedFrontmatterEntry(reason="Renamed to 'parent' (ENH-1434)."),
    "target_branch": DeprecatedFrontmatterEntry(reason="Renamed to 'base_branch'."),
    "related": DeprecatedFrontmatterEntry(reason="Renamed to 'relates_to' (ENH-1434)."),
}

# Deprecated frontmatter *status values* — the coerced STATUS_SYNONYMS cases
# (ENH-2876 AC3), each paired with the canonical replacement it is silently
# rewritten to today.
DEPRECATED_STATUS_VALUES: dict[str, DeprecatedFrontmatterEntry] = {
    synonym: DeprecatedFrontmatterEntry(
        reason=f"Coerced to canonical status '{canonical}' on read — write '{canonical}' directly."
    )
    for synonym, canonical in STATUS_SYNONYMS.items()
}


@dataclass(frozen=True)
class FrontmatterBlock:
    """One parsed ``---``-delimited frontmatter block located within a file (BUG-2955).

    ``span`` covers the whole block including both fence lines; ``body_span``
    covers only the YAML text between them (the slice ``update_frontmatter``
    splices into). ``is_canonical`` is true when ``data`` carries an ``id``
    key — the block that owns an issue's identity, as opposed to a
    scoring-path-prepended block that carries only ``score_*`` keys.
    """

    span: tuple[int, int]
    body_span: tuple[int, int]
    data: dict[str, Any]
    is_canonical: bool


_FENCE_MARKER_RE = re.compile(r"(?m)^---[ \t]*$")
_HEADER_BOUNDARY_RE = re.compile(r"(?m)^##[ \t]")


def _mask_fenced_code(text: str) -> str:
    """Blank out fenced code regions (``` `` `` / ``~~~``) to same-length
    whitespace, so a ``---`` inside a fenced block can't be mistaken for a
    frontmatter fence by :func:`_iter_frontmatter_blocks`. Preserves length
    and line structure so offsets computed on the result still index
    correctly into the original text.
    """
    lines = text.split("\n")
    out: list[str] = []
    fence_marker: str | None = None
    for line in lines:
        stripped = line.strip()
        if fence_marker is None and (stripped.startswith("```") or stripped.startswith("~~~")):
            fence_marker = stripped[:3]
            out.append(" " * len(line))
            continue
        if fence_marker is not None:
            if stripped.startswith(fence_marker):
                fence_marker = None
            out.append(" " * len(line))
            continue
        out.append(line)
    return "\n".join(out)


def _normalize_loaded_mapping(loaded: dict[Any, Any], *, coerce_types: bool) -> dict[str, Any]:
    """Apply the historical scalar-normalization contract to a loaded YAML mapping.

    Stringifies keys, strips trailing newlines from block scalars, normalizes
    empty/``null``/``~`` values to ``None``, and (when ``coerce_types``) coerces
    bare digit strings to ``int``. Does not canonicalize ``status`` synonyms —
    callers that need that apply :data:`STATUS_SYNONYMS` themselves (BUG-2955
    moved that step to :func:`_merge_blocks`, which runs it once on the
    merged result rather than once per block).
    """
    result: dict[str, Any] = {}
    for raw_key, value in loaded.items():
        key = str(raw_key)
        if isinstance(value, str):
            value = value.rstrip("\n")
            if value.lower() in ("null", "~", ""):
                result[key] = None
            elif coerce_types and value.isdigit():
                result[key] = int(value)
            else:
                result[key] = value
        else:
            result[key] = value
    return result


def _parse_block_data(text: str, *, coerce_types: bool) -> dict[str, Any]:
    """Parse one block's raw YAML text, falling back to the permissive line scan."""
    try:
        loaded = yaml.load(text, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        loaded = None
    if not isinstance(loaded, dict):
        return _parse_frontmatter_lines(text, coerce_types=coerce_types)
    return _normalize_loaded_mapping(loaded, coerce_types=coerce_types)


def _iter_frontmatter_blocks(content: str, *, coerce_types: bool = False) -> list[FrontmatterBlock]:
    """Scan *content* for one or more ``---``-delimited frontmatter blocks (BUG-2955).

    Scans only the header region — content up to the first ``^## `` heading —
    and skips fenced code regions, so a ` ```yaml ` block or a body horizontal
    rule is never mistaken for a second frontmatter block. The first candidate
    block is always accepted, including via the permissive line-based fallback
    for malformed YAML (matching the historical single-block contract). Any
    later candidate block is accepted only when its body parses as a YAML
    mapping — this is what keeps the scanner from false-positiving on prose
    ``---`` horizontal rules, which measured at 912 files under a naive
    ``^---$`` scan (see BUG-2955 Impact).

    Returns:
        Blocks in document order. Empty list if *content* has no frontmatter
        at all, or an unterminated opening fence.
    """
    if not content or not content.startswith("---"):
        return []

    boundary_match = _HEADER_BOUNDARY_RE.search(content)
    header_end = boundary_match.start() if boundary_match else len(content)
    header = content[:header_end]
    masked = _mask_fenced_code(header)
    markers = list(_FENCE_MARKER_RE.finditer(masked))

    blocks: list[FrontmatterBlock] = []
    i = 0
    is_first = True
    while i + 1 < len(markers):
        open_marker = markers[i]
        close_marker = markers[i + 1]
        i += 2

        body_start = open_marker.end() + 1
        body_end = close_marker.start() - 1
        if body_end < body_start:
            body_end = body_start
        body_text = content[body_start:body_end]

        if is_first:
            data = _parse_block_data(body_text, coerce_types=coerce_types)
            is_first = False
        else:
            try:
                loaded = yaml.load(body_text, Loader=yaml.BaseLoader)
            except yaml.YAMLError:
                continue
            if not isinstance(loaded, dict):
                continue
            data = _normalize_loaded_mapping(loaded, coerce_types=coerce_types)

        blocks.append(
            FrontmatterBlock(
                span=(open_marker.start(), close_marker.end()),
                body_span=(body_start, body_end),
                data=data,
                is_canonical="id" in data,
            )
        )
    return blocks


def _canonical_frontmatter_block(blocks: list[FrontmatterBlock]) -> FrontmatterBlock | None:
    """Return the first block carrying an ``id`` key, or ``None`` if none does."""
    for block in blocks:
        if block.is_canonical:
            return block
    return None


def _merge_blocks(blocks: list[FrontmatterBlock]) -> dict[str, Any]:
    """Merge blocks in document order into one dict, then canonicalize ``status``.

    Later blocks' keys overwrite earlier ones on conflict — a document-order
    fallback, not a load-bearing precedence rule (see BUG-2955 Decision
    Rationale: a static "canonical wins" rule would resurrect stale data on
    the legacy double-block files). In practice this only matters for files
    that still carry the malformed multi-block shape; the migration that
    accompanies this fix folds all known instances into a single block.
    """
    merged: dict[str, Any] = {}
    for block in blocks:
        merged.update(block.data)
    if "status" in merged and isinstance(merged["status"], str):
        merged["status"] = STATUS_SYNONYMS.get(merged["status"], merged["status"])
    return merged


def has_multiple_frontmatter_blocks(content: str) -> bool:
    """True when *content* carries more than one YAML frontmatter block (BUG-2955)."""
    return len(_iter_frontmatter_blocks(content)) > 1


def parse_frontmatter(content: str, *, coerce_types: bool = False) -> dict[str, Any]:
    """Extract YAML frontmatter from content.

    Looks for content between opening and closing '---' markers and parses it
    with ``yaml.load`` (``BaseLoader``), so any valid YAML frontmatter is
    supported — including PyYAML's own serialized output (block sequences whose
    long items wrap across physical lines, block scalars, flow lists, and
    unicode escapes). ``BaseLoader`` resolves every scalar to a *string*, which
    preserves this function's historical ``coerce_types=False`` contract (values
    stay strings rather than being coerced to int/bool/datetime by ``safe_load``).

    Empty values (``key:``, ``null``, ``~``) normalize to ``None``. Post-loading,
    ``status`` synonyms are canonicalized (see :data:`STATUS_SYNONYMS`) and, when
    ``coerce_types`` is True, bare digit scalars are coerced to ``int``.

    If the frontmatter is not valid YAML, falls back to a permissive line-based
    scan (top-level ``key: value`` pairs and single-line ``- item`` sequences),
    which emits a ``logging.WARNING`` for orphaned list items.

    When *content* carries more than one frontmatter block (BUG-2955 — e.g. an
    outer ``score_*`` block prepended by the confidence-check scoring path,
    followed by the canonical ``id:``-bearing block), all blocks are merged in
    document order via :func:`_merge_blocks` so neither block's keys are lost.
    For the overwhelming single-block majority this is byte-identical to the
    historical single-block-only behavior.

    Returns empty dict if no frontmatter found.

    Args:
        content: File content to parse
        coerce_types: If True, coerce digit strings to int

    Returns:
        Dictionary of frontmatter fields, or empty dict
    """
    blocks = _iter_frontmatter_blocks(content, coerce_types=coerce_types)
    return _merge_blocks(blocks)


def _parse_frontmatter_lines(frontmatter_text: str, *, coerce_types: bool) -> dict[str, Any]:
    """Line-based fallback parser for frontmatter that is not valid YAML.

    Handles top-level ``key: value`` pairs, single-line block sequences
    (``key:`` followed by ``- item`` lines), block scalars (``|``/``>``), and
    inline flow arrays (``[a, b, c]``). Orphaned ``- item`` lines emit a
    ``logging.WARNING``. This mirrors the historical hand-rolled behavior and
    exists so genuinely malformed frontmatter degrades the same way it always
    has, rather than silently returning ``{}``.
    """
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    lines = frontmatter_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            if current_list_key is not None:
                result[current_list_key].append(line[2:].strip())
            else:
                logger.warning("Unsupported YAML list syntax in frontmatter: %r", line)
            continue
        # Non-list line: finalize any in-progress empty list, then reset
        if current_list_key is not None and result[current_list_key] == []:
            result[current_list_key] = None
        current_list_key = None
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith("|") or value.startswith(">"):
                # Block scalar: collect indented continuation lines
                block_type = value[0]
                block_lines: list[str] = []
                while i < len(lines):
                    next_line = lines[i]
                    if next_line and (next_line[0] == " " or next_line[0] == "\t"):
                        block_lines.append(next_line)
                        i += 1
                    else:
                        break
                if block_lines:
                    dedented = textwrap.dedent("\n".join(block_lines))
                    if block_type == ">":
                        dedented = re.sub(r"\s+", " ", dedented).strip()
                    result[key] = dedented
                else:
                    result[key] = ""
                continue
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                result[key] = [item.strip() for item in inner.split(",")] if inner else []
                continue
            if value.lower() in ("null", "~", ""):
                if value == "":
                    result[key] = []
                    current_list_key = key
                else:
                    result[key] = None
            elif coerce_types and value.isdigit():
                result[key] = int(value)
            else:
                # Strip surrounding YAML string quotes (single or double)
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                result[key] = value
    # Finalize any trailing empty list key
    if current_list_key is not None and result[current_list_key] == []:
        result[current_list_key] = None
    if "status" in result and isinstance(result["status"], str):
        result["status"] = STATUS_SYNONYMS.get(result["status"], result["status"])
    return result


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    """Extract flat key/value pairs from SKILL.md frontmatter.

    Uses ``yaml.safe_load`` so YAML block scalars (e.g. ``description: |``)
    are resolved to their string content instead of the indicator literal.
    Non-string scalar values are stringified; nested structures are dropped.

    If the frontmatter is not valid YAML (e.g. unquoted colons in values),
    falls back to a permissive line-based scan — top-level ``key: value``
    pairs only, block scalars are not resolved in that path.

    This is the canonical SKILL.md frontmatter parser. Prefer it over the
    general ``parse_frontmatter`` for SKILL.md files: it stringifies scalar
    values (bools/ints) and returns a flat ``dict[str, str]``, which is the
    shape SKILL.md consumers expect. (``parse_frontmatter`` now resolves block
    scalars natively via YAML, but returns a richer ``dict[str, Any]``.)
    """
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm_text = text[3:end]
    try:
        loaded = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        loaded = None
    if isinstance(loaded, dict):
        fm: dict[str, str] = {}
        for key, value in loaded.items():
            if value is None:
                fm[str(key)] = ""
            elif isinstance(value, str):
                fm[str(key)] = value
            elif isinstance(value, bool | int | float):
                fm[str(key)] = str(value).lower() if isinstance(value, bool) else str(value)
        return fm
    fm = {}
    for line in fm_text.splitlines():
        if line and not line.startswith(" ") and not line.startswith("\t") and ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content, returning the body.

    Strips the ``---`` delimited frontmatter block (if present) and
    returns everything after the closing delimiter.

    Args:
        content: File content possibly starting with frontmatter

    Returns:
        Content with frontmatter removed. Returns original content
        unchanged if no valid frontmatter block is found.
    """
    if not content or not content.startswith("---"):
        return content

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return content

    return content[3 + end_match.end() :]


def update_frontmatter(content: str, updates: dict[str, Any]) -> str:
    """Update or add frontmatter fields in content.

    Merges ``updates`` into an existing ``---`` delimited YAML frontmatter
    block, preserving other fields and their order. If no frontmatter block
    exists, a new one is prepended. Existing keys are overwritten with the
    new values.

    When *content* carries more than one frontmatter block (BUG-2955), the
    update is spliced into the **canonical** block — the one carrying an
    ``id`` key — leaving every other block (e.g. an outer ``score_*`` block)
    untouched. Falls back to the first block when no block carries ``id``,
    preserving today's behavior for non-issue frontmatter (agent/skill/loop
    YAML, which has no ``id`` key).

    Args:
        content: Full file content, possibly with existing frontmatter
        updates: Fields to add/update in frontmatter; values may be nested dicts

    Returns:
        Content with updated frontmatter block
    """
    blocks = _iter_frontmatter_blocks(content)
    if not blocks:
        fm_text = yaml.dump(dict(updates), default_flow_style=False, sort_keys=False).strip()
        return f"---\n{fm_text}\n---\n{content}"

    target = _canonical_frontmatter_block(blocks) or blocks[0]
    body_start, body_end = target.body_span
    existing: dict[str, Any] = yaml.safe_load(content[body_start:body_end]) or {}
    existing.update(updates)
    fm_text = yaml.dump(existing, default_flow_style=False, sort_keys=False).strip()
    return f"{content[:body_start]}{fm_text}{content[body_end:]}"


def remove_frontmatter_keys(content: str, keys: Iterable[str]) -> str:
    """Delete *keys* from every frontmatter block in *content*.

    The deletion counterpart to :func:`update_frontmatter`. Operates only within
    the spans reported by :func:`_iter_frontmatter_blocks`, so a body line that
    happens to start with ``<key>:`` — a prose mention, a table cell, a fenced
    example — is never touched. Removes the key's line plus any deeper-indented
    continuation lines (block scalars, list items), which a single-line regex
    would otherwise orphan into invalid YAML.

    Unlike :func:`update_frontmatter` this does not round-trip the block through
    YAML, so the formatting of every surviving key is preserved byte-for-byte.

    Args:
        content: Full file content, possibly with existing frontmatter
        keys: Frontmatter keys to remove; absent keys are ignored

    Returns:
        Content with the keys removed from all frontmatter blocks
    """
    keys = list(keys)
    if not keys:
        return content

    for key in keys:
        key_re = re.compile(
            rf"^{re.escape(key)}:.*(?:\n[ \t]+\S.*|\n[ \t]*-[ \t].*)*\n?", re.MULTILINE
        )
        # Rewrite blocks back-to-front so earlier spans stay valid as we splice.
        for block in reversed(_iter_frontmatter_blocks(content)):
            if key not in block.data:
                continue
            body_start, body_end = block.body_span
            body = key_re.sub("", content[body_start:body_end])
            content = content[:body_start] + body + content[body_end:]
    return content
