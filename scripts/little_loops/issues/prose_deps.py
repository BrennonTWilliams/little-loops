"""Prose dependency extractor (FEAT-2849).

Scans an issue body for canonical prose dependency phrasings ("Depends on
FEAT-109", "Blocked by BUG-5", "Requires ENH-10", their unambiguous synonyms
("blocked on", "gated on", "waiting on", "contingent on", "predicated on",
"depends upon"), and ``## Blocked By`` section bodies) and returns the
referenced issue IDs, normalized to ``TYPE-NNN``.

Deliberately conservative: only the phrasings above are matched. Recall
matters less than not crying wolf (see FEAT-2849 for rationale).
Callers are expected to pass the issue *body* only (post
``strip_frontmatter()``) — this module does not parse frontmatter itself.
"""

from __future__ import annotations

import re

from little_loops.text_utils import _CODE_FENCE

_ID_RE = r"(?:P[0-5]-)?(BUG|FEAT|ENH|EPIC)-(\d+)"

# "Depends on FEAT-109", "Blocked by BUG-5", "Requires ENH-10", plus the
# unambiguous blocker synonyms ("blocked on BUG-5", "gated on FEAT-9", ...).
# Deliberately excludes temporal/narrative phrasings ("after X", "once X",
# "pending X", "needs X") — those are dominated by history, not live edges,
# and a wrong blocked_by edge silently hides an issue from `ll-issues ready`.
_PHRASE_RE = re.compile(
    rf"\b(?:Depends on|Depends upon|Blocked by|Blocked on|Requires"
    rf"|Gated on|Waiting on|Contingent on|Predicated on)\s+{_ID_RE}",
    re.IGNORECASE,
)

# "## Blocked By" section heading; body scanned up to the next "## " heading.
_BLOCKED_BY_HEADING_RE = re.compile(r"^##\s+Blocked By\s*$", re.IGNORECASE | re.MULTILINE)
_NEXT_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)
_ID_ONLY_RE = re.compile(_ID_RE)

# Inline code spans ("`Depends on FEAT-109`"), suppressed the same as fenced
# blocks (ENH-3061). Matches the single-backtick pattern already used by
# `symbol_claims._BACKTICK_SPAN_RE` and `cli_claims._BACKTICK_SPAN_RE`.
_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")


# BUG-3057: boundaries that start a new attribution scope. A dependency
# phrase describes whichever issue is the subject of its own sentence or list
# item -- an EPIC's "## Children" list ("- **FEAT-3044** ... (depends on
# FEAT-3042)") states FEAT-3044's dependency, not the EPIC's, and charging it
# to the host issue turned the repo-wide drift gate red on correct data.
_SCOPE_BOUNDARY_RE = re.compile(
    r"[.!?][\s)\"']"  # sentence terminator
    r"|\n\s*\n"  # blank line (paragraph break)
    r"|^[ \t]*(?:[-*+]|\d+\.)\s",  # markdown list-item marker
    re.MULTILINE,
)


def _normalize(issue_type: str, number: str) -> str:
    return f"{issue_type.upper()}-{number}"


def _scope_subject(body: str, match_start: int) -> str | None:
    """Return the issue ID that owns the dependency phrase at *match_start*.

    The scope is the enclosing sentence or list item; the subject is the last
    issue ID mentioned inside it before the phrase. ``None`` means no other
    issue was named, so the phrase belongs to the host issue.

    Scoping to the sentence (rather than the paragraph) is what keeps
    "This builds on BUG-5. Depends on FEAT-109." attributed to the host --
    BUG-5 sits in a different sentence and is not the subject.
    """
    scope_start = 0
    for boundary in _SCOPE_BOUNDARY_RE.finditer(body, 0, match_start):
        scope_start = boundary.end()
    preceding = body[scope_start:match_start]
    subject = None
    for id_match in _ID_ONLY_RE.finditer(preceding):
        subject = _normalize(id_match.group(1), id_match.group(2))
    return subject


def _in_fence(start: int, end: int, fence_spans: list[tuple[int, int]]) -> bool:
    return any(fs <= start and end <= fe for fs, fe in fence_spans)


def extract_prose_deps(body: str, host_id: str | None = None) -> set[str]:
    """Extract issue IDs claimed as dependencies in prose.

    Matches canonical phrasings only: "Depends on <ID>", "Blocked by <ID>",
    "Requires <ID>", and IDs listed in the body of a "## Blocked By" section.
    IDs inside fenced code blocks or inline backticks are ignored.

    Args:
        body: Issue markdown body (frontmatter already stripped).
        host_id: Normalized ID of the issue *body* belongs to (e.g.
            ``"EPIC-3041"``). When given, a dependency phrase whose sentence
            or list item names a different issue as its subject is attributed
            to that issue and excluded (BUG-3057) -- an EPIC listing its
            children's dependencies is not declaring its own. ``None``
            disables attribution and preserves the original behavior.

    Returns:
        Set of normalized issue IDs (e.g. {"FEAT-109"}).
    """
    if not body:
        return set()

    fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(body)]
    fence_spans += [(m.start(), m.end()) for m in _BACKTICK_SPAN_RE.finditer(body)]

    deps: set[str] = set()

    for m in _PHRASE_RE.finditer(body):
        if _in_fence(m.start(), m.end(), fence_spans):
            continue
        if host_id is not None:
            subject = _scope_subject(body, m.start())
            if subject is not None and subject != host_id.upper():
                continue
        deps.add(_normalize(m.group(1), m.group(2)))

    heading_match = _BLOCKED_BY_HEADING_RE.search(body)
    if heading_match and not _in_fence(heading_match.start(), heading_match.end(), fence_spans):
        section_start = heading_match.end()
        next_heading = _NEXT_HEADING_RE.search(body, section_start)
        section_end = next_heading.start() if next_heading else len(body)
        section_body = body[section_start:section_end]
        section_offset = section_start
        for id_match in _ID_ONLY_RE.finditer(section_body):
            abs_start = section_offset + id_match.start()
            abs_end = section_offset + id_match.end()
            if _in_fence(abs_start, abs_end, fence_spans):
                continue
            deps.add(_normalize(id_match.group(1), id_match.group(2)))

    return deps
