"""Occurrence-aware citation checks and coverage metadata (BUG-3691).

``verify-issues`` used to judge ``path:line`` / ``file:symbol`` citations from
the model's ad-hoc reads, so coverage differed between passes over an unchanged
issue. This module is the deterministic half: it walks the citation-bearing
sections of an issue, checks the mechanical properties format-check can really
examine, and reports

* advisory findings (fixed gap keys on :class:`~little_loops.issue_parser.FormatGaps`,
  never blocking), and
* ``examined_refs`` coverage — one :class:`CitationCheck` per
  (occurrence, property) that was *actually* checked — so a consumer can tell
  "checked and fine" from "never looked".

Coverage is honest by construction: an entry exists only after its property has
been examined. Missing/unsupported forms, an absent or empty index, an absent
root, unreadable files, planned-new or untracked-by-design refs, suppressed
claims and breadth-capped claims produce no entry for the property they leave
unexamined. Positions are 1-based line/column in the original full issue file
(frontmatter included), so sections are scanned in place and never rebuilt from
concatenated bodies.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from little_loops.issues.symbol_claims import (
    _BACKTICK_SPAN_RE,
    _EXPLICIT_RE,
    _LINE_NUMBER_REF_RE,
    SymbolClaim,
    SymbolIndex,
    _is_suppressed,
    classify_symbol_claim,
    classify_symbol_definition,
    iter_symbol_claim_occurrences,
)
from little_loops.text_utils import (
    _PLANNED_NEW_RE,
    SOURCE_EXTENSIONS,
    RefIndex,
    RefStatus,
    _has_extension_like_directory_component,
    _strip_untracked_prefix_marker,
    fence_spans,
    in_fence,
    suffix_match_candidates,
)

PROPERTY_PATH = "path_resolves"
PROPERTY_LINE = "line_in_range"
PROPERTY_SYMBOL_RESOLVES = "symbol_resolves_in"
PROPERTY_SYMBOL_DEFINED = "symbol_defined_in"

# `path.ext:N` / `path.ext:N-M`. The lookbehind keeps URL hosts ("//x.com:80")
# and mid-token matches out; the lookahead rejects `:N:M` / `:N,M` forms this
# checker does not support (they get no entry rather than a truncated one).
_LINE_CITATION_RE = re.compile(
    r"(?<![\w/.\-:])((?:[\w.\-]+/)*[\w.\-]+\.[A-Za-z0-9]{1,6}):(\d+)(?:[-–](\d+))?(?!\w|[,:]\d)"
)

# Sections whose symbol claims the pre-existing blocking rules already cover.
_CURRENT_STATE_H2 = ("Summary", "Current Behavior", "Root Cause", "Context")
# Newly covered scope (advisory only): Integration Map (its nested Tests
# subsection rides along), standalone Tests, and the Wiring Phase.
_ADVISORY_H2 = ("Integration Map",)
_ADVISORY_HEADING_RES = (
    re.compile(r"^(#{2,3})[ \t]+Tests[ \t]*$", re.MULTILINE),
    re.compile(r"^(#{2,3})[ \t]+Wiring Phase\b[^\n]*$", re.MULTILINE),
)


@dataclass(frozen=True)
class CitationCheck:
    """One examined (occurrence, property) pair."""

    ref: str
    issue_line: int
    issue_column: int
    property: str
    result: str

    def sort_key(self) -> tuple[int, int, str, str, str]:
        return (self.issue_line, self.issue_column, self.ref, self.property, self.result)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "issue_line": self.issue_line,
            "issue_column": self.issue_column,
            "property": self.property,
            "result": self.result,
        }


@dataclass
class CitationReport:
    """Advisory findings plus coverage from one :func:`check_citations` call."""

    checks: list[CitationCheck] = field(default_factory=list)
    advisory_stale_file_ref: list[str] = field(default_factory=list)
    advisory_ambiguous_file_ref: list[str] = field(default_factory=list)
    advisory_stale_symbol_ref: list[str] = field(default_factory=list)
    advisory_mislocated_symbol_ref: list[str] = field(default_factory=list)
    stale_line_ref: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Region:
    body: str
    offset: int  # body's start offset within the full issue file
    current_state: bool


def _heading_end(content: str, start: int, level: int, spans: list[tuple[int, int]]) -> int:
    """End of a section body: the next non-fenced heading of equal-or-higher level."""
    terminator = re.compile(rf"^#{{1,{level}}}\s", re.MULTILINE)
    for term in terminator.finditer(content, start):
        if not in_fence(term.start(), term.end(), spans):
            return term.start()
    return len(content)


def _regions(content: str) -> list[_Region]:
    """Citation-bearing regions, current-state scope first."""
    from little_loops.issue_parser import _section_body_with_offset

    spans = fence_spans(content)
    regions: list[_Region] = []
    for name in _CURRENT_STATE_H2:
        found = _section_body_with_offset(content, name)
        if found and found[0]:
            regions.append(_Region(found[0], found[1], True))
    for name in _ADVISORY_H2:
        found = _section_body_with_offset(content, name)
        if found and found[0]:
            regions.append(_Region(found[0], found[1], False))
    for pattern in _ADVISORY_HEADING_RES:
        for m in pattern.finditer(content):
            if in_fence(m.start(), m.end(), spans):
                continue
            end = _heading_end(content, m.end(), len(m.group(1)), spans)
            regions.append(_Region(content[m.end() : end], m.end(), False))
    return regions


def _line_count(root: Path, rel: str, cache: dict[str, int | None]) -> int | None:
    """Number of lines in ``root/rel`` (editor-style: ``\\n``-terminated), or None."""
    if rel not in cache:
        try:
            text = (root / rel).read_bytes().decode("utf-8", errors="replace")
        except OSError:
            cache[rel] = None
        else:
            cache[rel] = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return cache[rel]


@dataclass(frozen=True)
class _PathVerdict:
    status: str  # "ok" | "stale" | "ambiguous"
    resolved: str | None = None
    candidates: tuple[str, ...] = ()


def _resolve_path(path_part: str, line_text: str, index: RefIndex) -> _PathVerdict | None:
    """Resolve a cited path against the tracked-file index; None when unexaminable.

    Unlike ``classify_file_ref`` this also accepts a bare filename (callers
    gate which forms may reach it) and tells "several mirror-only matches"
    apart from "no match": ``suffix_match_candidates`` returns an empty list for
    both, and reading the empty list as absence would call a present file stale.
    """
    if not index.by_basename:
        return None  # an empty/failed index cannot authorize a path verdict
    if path_part.startswith(("~", "/")) or "<" in path_part or ">" in path_part:
        return None
    if _has_extension_like_directory_component(path_part):
        return None
    if _PLANNED_NEW_RE.search(line_text):
        return None
    filtered = suffix_match_candidates(path_part, index)
    if len(filtered) == 1:
        return _PathVerdict("ok", resolved=filtered[0])
    if len(filtered) > 1:
        return _PathVerdict("ambiguous", candidates=tuple(sorted(filtered)))
    basename = path_part.rsplit("/", 1)[-1]
    raw = sorted(
        p
        for p in index.by_basename.get(basename, [])
        if p == path_part or p.endswith("/" + path_part)
    )
    if raw:
        return _PathVerdict("ambiguous", candidates=tuple(raw))
    if any(
        path_part.startswith(_strip_untracked_prefix_marker(prefix))
        for prefix in index.untracked_by_design
    ):
        return None
    return _PathVerdict("stale")


def _format_candidates(candidates: tuple[str, ...]) -> str:
    shown = ", ".join(candidates[:3])
    if len(candidates) > 3:
        shown += ", …"
    return f"{len(candidates)}: {shown}"


def check_citations(
    content: str,
    *,
    ref_index: RefIndex,
    symbol_index: SymbolIndex | None = None,
    project_root: Path | None = None,
    legacy_path_status: dict[str, RefStatus] | None = None,
    legacy_symbol_outcomes: dict[SymbolClaim, str | None] | None = None,
) -> CitationReport:
    """Check every citation occurrence in the citation-bearing sections of *content*.

    Args:
        content: Full issue file text (frontmatter included — positions are
            reported against it).
        ref_index: Tracked-file index; path properties need it.
        symbol_index: Symbol index; symbol properties need it, and its ``root``
            is the fallback project root.
        project_root: Explicit root for reading cited files (never the process
            cwd). Without a root (or ``symbol_index.root``) line bounds stay
            unexamined.
        legacy_path_status: ``classify_issue_refs`` result the existing blocking
            ``stale_file_ref`` / ``ambiguous_file_ref`` rules acted on — an
            occurrence they already reported keeps that key instead of being
            duplicated as an advisory finding.
        legacy_symbol_outcomes: Per-claim outcome (``"ok"``/``"stale"``/
            ``"mislocated"``/``None``) the existing current-state symbol rules
            produced; current-state occurrences take their result from it.
    """
    report = CitationReport()
    root = project_root or (symbol_index.root if symbol_index is not None else None)
    legacy_path_status = legacy_path_status or {}
    legacy_symbol_outcomes = legacy_symbol_outcomes or {}
    all_spans = fence_spans(content)
    line_starts = [0] + [m.end() for m in re.finditer(r"\n", content)]
    lines = content.split("\n")
    line_cache: dict[str, int | None] = {}
    checks: dict[tuple[int, int, str, str], CitationCheck] = {}
    seen: set[tuple[str, int]] = set()

    def locate(abs_pos: int) -> tuple[int, int]:
        idx = bisect_right(line_starts, abs_pos) - 1
        return idx + 1, abs_pos - line_starts[idx] + 1

    def record(ref: str, abs_pos: int, prop: str, result: str) -> None:
        line, col = locate(abs_pos)
        checks.setdefault((line, col, ref, prop), CitationCheck(ref, line, col, prop, result))

    def path_property(ref: str, path_part: str, abs_pos: int) -> _PathVerdict | None:
        verdict = _resolve_path(path_part, lines[locate(abs_pos)[0] - 1], ref_index)
        if verdict is None:
            return None
        if verdict.status == "ok":
            record(ref, abs_pos, PROPERTY_PATH, "ok")
            return verdict
        legacy = legacy_path_status.get(path_part) if "/" in path_part else None
        if verdict.status == "stale":
            if legacy == "stale":
                record(ref, abs_pos, PROPERTY_PATH, "stale_file_ref")
            else:
                record(ref, abs_pos, PROPERTY_PATH, "advisory_stale_file_ref")
                report.advisory_stale_file_ref.append(ref)
        else:
            if legacy == "ambiguous":
                record(ref, abs_pos, PROPERTY_PATH, "ambiguous_file_ref")
            elif legacy == "stale":
                return verdict  # the legacy key would mislabel mirror-only ambiguity
            else:
                record(ref, abs_pos, PROPERTY_PATH, "advisory_ambiguous_file_ref")
                report.advisory_ambiguous_file_ref.append(
                    f"{ref} ({_format_candidates(verdict.candidates)})"
                )
        return verdict

    for region in _regions(content):
        body = region.body
        fences = [
            (max(fs - region.offset, 0), min(fe - region.offset, len(body)))
            for fs, fe in all_spans
            if fe > region.offset and fs < region.offset + len(body)
        ]

        explicit_ok: dict[int, bool] = {}
        for m in _BACKTICK_SPAN_RE.finditer(body):
            if in_fence(m.start(), m.end(), fences) or _is_suppressed(body, m.start()):
                continue
            text = m.group(1)
            explicit = _EXPLICIT_RE.match(text)
            if not explicit or _LINE_NUMBER_REF_RE.match(explicit.group(2)):
                continue  # `path:L12` is a line-number shorthand, not a supported form
            abs_pos = region.offset + m.start(1)
            if ("explicit", abs_pos) in seen:
                continue
            seen.add(("explicit", abs_pos))
            path_part = explicit.group(1)
            # A bare filename is only a supported path citation as `name.ext:symbol()`.
            if "/" in path_part or text.endswith("()"):
                verdict = path_property(text, path_part, abs_pos)
                explicit_ok[m.start(1)] = verdict is not None and verdict.status == "ok"
            else:
                line_text = lines[locate(abs_pos)[0] - 1]
                explicit_ok[m.start(1)] = not _PLANNED_NEW_RE.search(line_text)

        for m in _LINE_CITATION_RE.finditer(body):
            if in_fence(m.start(), m.end(), fences) or _is_suppressed(body, m.start()):
                continue
            path_part = m.group(1)
            if Path(path_part).suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            abs_pos = region.offset + m.start()
            if ("line", abs_pos) in seen:
                continue
            seen.add(("line", abs_pos))
            ref = m.group(0)
            verdict = path_property(ref, path_part, abs_pos)
            if verdict is None or verdict.status != "ok" or verdict.resolved is None:
                continue
            if root is None:
                continue
            count = _line_count(root, verdict.resolved, line_cache)
            if count is None:
                continue
            first = int(m.group(2))
            last = int(m.group(3)) if m.group(3) else first
            if 1 <= first <= last <= count:
                record(ref, abs_pos, PROPERTY_LINE, "ok")
            else:
                record(ref, abs_pos, PROPERTY_LINE, "stale_line_ref")
                report.stale_line_ref.append(f"{ref} (file has {count} line(s))")

        if symbol_index is None:
            continue
        for occ in iter_symbol_claim_occurrences(body, ref_index, fences=fences):
            if occ.form == "explicit" and not explicit_ok.get(occ.start, False):
                continue  # path not verified (or `path:L12` shorthand): no symbol coverage
            abs_pos = region.offset + occ.start
            if ("symbol", abs_pos) in seen:
                continue
            seen.add(("symbol", abs_pos))
            claim = occ.claim
            if region.current_state:
                outcome = legacy_symbol_outcomes.get(claim)
            else:
                outcome = classify_symbol_claim(symbol_index, claim)
            if outcome is None:
                continue
            if outcome == "ok":
                record(occ.ref, abs_pos, PROPERTY_SYMBOL_RESOLVES, "ok")
            elif region.current_state:
                record(occ.ref, abs_pos, PROPERTY_SYMBOL_RESOLVES, f"{outcome}_symbol_ref")
                continue
            else:
                key = f"advisory_{outcome}_symbol_ref"
                record(occ.ref, abs_pos, PROPERTY_SYMBOL_RESOLVES, key)
                getattr(report, key).append(f"{claim.symbol} (claimed in {claim.file})")
                continue
            if not occ.definition_shaped:
                continue
            definition = classify_symbol_definition(symbol_index, claim)
            if definition is None:
                continue
            if definition[0] == "ok":
                record(occ.ref, abs_pos, PROPERTY_SYMBOL_DEFINED, "ok")
            else:
                record(occ.ref, abs_pos, PROPERTY_SYMBOL_DEFINED, "advisory_mislocated_symbol_ref")
                report.advisory_mislocated_symbol_ref.append(
                    f"{claim.symbol} (claimed in {claim.file}; imported there, "
                    f"defined in {definition[1]})"
                )

    report.checks = sorted(checks.values(), key=CitationCheck.sort_key)
    for name in (
        "advisory_stale_file_ref",
        "advisory_ambiguous_file_ref",
        "advisory_stale_symbol_ref",
        "advisory_mislocated_symbol_ref",
        "stale_line_ref",
    ):
        setattr(report, name, sorted(set(getattr(report, name))))
    return report
