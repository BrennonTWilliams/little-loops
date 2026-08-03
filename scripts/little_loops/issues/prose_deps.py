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


def _normalize(issue_type: str, number: str) -> str:
    return f"{issue_type.upper()}-{number}"


def _in_fence(start: int, end: int, fence_spans: list[tuple[int, int]]) -> bool:
    return any(fs <= start and end <= fe for fs, fe in fence_spans)


def extract_prose_deps(body: str) -> set[str]:
    """Extract issue IDs claimed as dependencies in prose.

    Matches canonical phrasings only: "Depends on <ID>", "Blocked by <ID>",
    "Requires <ID>", and IDs listed in the body of a "## Blocked By" section.
    IDs inside fenced code blocks are ignored.

    Args:
        body: Issue markdown body (frontmatter already stripped).

    Returns:
        Set of normalized issue IDs (e.g. {"FEAT-109"}).
    """
    if not body:
        return set()

    fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(body)]

    deps: set[str] = set()

    for m in _PHRASE_RE.finditer(body):
        if _in_fence(m.start(), m.end(), fence_spans):
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
