"""Fold repeated ``### Codebase Research Findings`` blocks into one per H2 (ENH-2993).

Every ``/ll:refine-issue`` pass used to *append* a fresh
``### Codebase Research Findings`` subsection rather than merging into the one
already sitting under the same H2. Across repeated passes these accumulate —
one issue in the corpus carries 12 — and the reader must hold all of them to
know the current state of a claim.

This module supplies the write-side primitive that was missing. The three
existing section-extraction helpers are all read-oriented and H2-only
(:func:`~little_loops.issue_history.doc_synthesis._extract_section`,
:func:`~little_loops.issue_parser._section_body_with_offset`,
:func:`~little_loops.issue_parser._iter_h2_sections`); the one that does match
``###`` (:func:`~little_loops.issue_parser._heading_bodies`) is document-wide
and carries no parent-section information. Folding needs both levels at once:
an H3 located *inside* a named H2's slice.

Three shapes, all handled by :func:`fold_research_findings`:

* **0 existing blocks** — create one at the end of the H2 slice (after any
  nested H3s, before the next ``##``). The position is pinned rather than left
  to the caller: for an H2 like ``## Integration Map`` that owns
  ``### Files to Modify`` … ``### Configuration``, "end of slice", "after the
  last H3" and "before the first H3" produce three different files, and
  non-deterministic placement across passes would defeat the very invariant
  this module exists to hold.
* **1 existing block** — append the new batch beneath it, under its own dated
  provenance line. Same insert-relative-to-a-known-anchor shape as
  :func:`~little_loops.session_log.append_session_log_entry`.
* **N>1 existing blocks (fold-on-touch)** — collapse all N into the *first*
  block's position, concatenating their bodies in document order, then append
  the new batch. Without this the fold is a no-op on exactly the corpus that
  motivated it, and the ``duplicate_findings_block`` gap would be permanently
  red for reasons the current pass did not cause.

**Relocation only.** Nothing is deleted, summarized, or deduped: every bullet
and every existing provenance line survives, in order. Consequently the
transform is *not* idempotent on bullets — folding the same batch twice yields
it twice, by design. The invariants are the heading count (exactly one per H2)
and provenance-line conservation (M in, M+1 out).

``sub_heading`` and ``marker`` are parameterized so ``/ll:wire-issue``'s
``_Wiring pass added by …_`` markers can become a later *caller* rather than a
rewrite; every caller in ENH-2993's scope passes the defaults.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime

#: The H3 subsection this module folds by default.
SUB_HEADING = "Codebase Research Findings"

_MARKER_PREFIX = "_Added by `/ll:refine-issue`"
_MARKER_SUFFIX = "based on codebase analysis:_"

#: Undated provenance line, kept as the signature default for callers that
#: supply their own dating (the CLI wrapper passes :func:`dated_marker`).
DEFAULT_MARKER = f"{_MARKER_PREFIX} — {_MARKER_SUFFIX}"

#: ``(body, start_offset, end_offset)``. See :func:`find_subsections`.
Span = tuple[str, int, int]


def dated_marker(day: str | None = None) -> str:
    """Return the provenance line for one merged batch, carrying *day*.

    The fold collapses the *heading* to one per H2 but keeps a provenance line
    per batch, because pass boundaries are load-bearing downstream: ENH-2995's
    superseded-line carve-out fires on "this pass's findings only", and
    ENH-2992's contradiction detection relies on later findings superseding
    earlier ones. A single undifferentiated bullet list would erase both
    discriminators.

    Args:
        day: ISO date (``YYYY-MM-DD``). Defaults to today, UTC.
    """
    stamp = day or datetime.now(UTC).strftime("%Y-%m-%d")
    return f"{_MARKER_PREFIX} — {stamp} — {_MARKER_SUFFIX}"


def _h2_slice(content: str, parent_heading: str) -> tuple[int, int] | None:
    """Return ``(body_start, body_end)`` for the ``## parent_heading`` section.

    Matched case-insensitively with surrounding whitespace stripped, so callers
    may pass ``--section "proposed solution "`` verbatim. The **first**
    occurrence wins when an H2 is duplicated: findings belong to the canonical
    section, and a duplicated H2 is itself a format-check gap rather than
    something this transform should silently pick a side on.
    """
    target = parent_heading.strip().casefold()
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", content, re.MULTILINE))
    for i, m in enumerate(matches):
        if m.group(1).strip().casefold() != target:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        return start, end
    return None


def find_subsections(content: str, parent_heading: str, sub_heading: str) -> list[Span]:
    """Locate every ``### sub_heading`` nested inside ``## parent_heading``.

    Returns **all** matches in document order, not one. A singular
    ``tuple | None`` cannot express the corpus's common case — ~1,140 refined
    issues carry N>1 stacked blocks under a single H2 — and the two primitives
    usually cited as precedent disagree on which one it would pick
    (``_extract_section`` is first-match, ``_section_body_with_offset`` is
    last-match-wins), so a singular signature would invite the caller to
    inherit whichever convention they read last. The full list is what makes
    both the fold-on-touch collapse and the ``duplicate_findings_block``
    detector (``len(spans) > 1`` within one H2 slice) fall out of one call.

    Args:
        content: Full issue markdown.
        parent_heading: H2 heading text, without the leading ``## ``.
        sub_heading: H3 heading text, without the leading ``### ``.

    Returns:
        ``(body, start_offset, end_offset)`` per match, where *start_offset* is
        the start of the ``###`` heading line, *end_offset* is exclusive, and
        *body* is the text between them — i.e. ``content[start:end]`` is the
        whole block (heading included) while *body* is only what follows the
        heading. Empty when *parent_heading* or *sub_heading* is absent.

        The end boundary is the next heading of level **≤ 3** or the end of the
        H2 slice, whichever comes first. Scanning only to the next ``##`` would
        splice new bullets past unrelated sibling H3s — a findings block is
        routinely followed by one (``### Documentation``, ``### Tests``).
    """
    bounds = _h2_slice(content, parent_heading)
    if bounds is None:
        return []
    slice_start, slice_end = bounds
    body_region = content[slice_start:slice_end]

    spans: list[Span] = []
    pattern = rf"^###\s+{re.escape(sub_heading)}\s*$"
    for match in re.finditer(pattern, body_region, re.MULTILINE):
        block_start = slice_start + match.start()
        body_start = slice_start + match.end()
        following = re.search(r"^#{1,3}\s", content[body_start:slice_end], re.MULTILINE)
        end = body_start + following.start() if following else slice_end
        spans.append((content[body_start:end], block_start, end))
    return spans


def _batch(marker: str, new_content: str) -> str:
    """Render one provenance line plus its verbatim payload block.

    Returns ``""`` when *new_content* is whitespace-only — a pass with no
    findings must contribute nothing, not a marker with an empty body
    (BUG-3245).
    """
    stripped = new_content.strip(chr(10))
    if not stripped.strip():
        return ""
    return f"{marker}\n\n{stripped}"


def fold_research_findings(
    content: str,
    parent_heading: str,
    new_content: str,
    sub_heading: str = SUB_HEADING,
    marker: str = DEFAULT_MARKER,
) -> str:
    """Merge *new_content* into the one findings block under *parent_heading*.

    *new_content* is an **opaque markdown block, never a parsed bullet list**.
    Two payload shapes must both survive and neither is a flat bullet list:
    findings bullets wrap across lines with a 2-space continuation indent, and
    ``commands/refine-issue.md`` § 5a sends ``**Option A**`` / ``**Option B**``
    / ``**Recommended**`` blocks at column 0 with no leading ``- `` at all —
    and it is precisely that text ``count_enumerable_options()`` must still
    find afterward. Any bullet-parsing step would either drop the option labels
    or glue them onto a neighbouring bullet. The payload is inserted verbatim
    apart from trailing-newline normalization, which also makes the
    multi-line-continuation hazard structurally impossible rather than a rule
    the caller must remember.

    Pure function on ``str``: file I/O and the ``--dry-run`` branch live in the
    CLI wrapper, so dry-run is "call the transform, print instead of write"
    rather than a second code path.

    Args:
        content: Full issue markdown.
        parent_heading: H2 the block is addressed by. Findings are always
            scoped to their nearest H2 ancestor even when the bullets logically
            belong to an H3 beneath it (``### Files to Modify`` under
            ``## Integration Map``); one block per H2 is the invariant.
        new_content: Markdown block to append, verbatim.
        sub_heading: H3 heading text to fold on.
        marker: Provenance line written above *new_content*. The heading and
            this line are supplied here so callers never hand-write them.

    Returns:
        The rewritten markdown, or *content* unchanged when *parent_heading* is
        absent — the CLI creates the section first (see :func:`ensure_section`),
        so that path is a defensive no-op rather than a supported mode.
    """
    bounds = _h2_slice(content, parent_heading)
    if bounds is None:
        return content
    spans = find_subsections(content, parent_heading, sub_heading)
    batch = _batch(marker, new_content)

    if not spans:
        if not batch:
            # No findings and no existing block — nothing to create (BUG-3245).
            return content
        _, slice_end = bounds
        head = content[:slice_end].rstrip("\n")
        tail = content[slice_end:]
        block = f"### {sub_heading}\n\n{batch}\n"
        return f"{head}\n\n{block}" + (f"\n{tail}" if tail else "")

    if len(spans) == 1 and not batch:
        # No findings and no duplicates to collapse — a true no-op (BUG-3245).
        return content

    # N>=1: everything collapses into the first block's position. First, not
    # last, because it is the one whose surrounding prose was written to
    # introduce the block. Bodies are carried over verbatim and in order, so
    # every bullet and every pre-existing provenance line survives.
    bodies = [body.strip("\n") for body, _, _ in spans]
    parts = [b for b in bodies if b]
    if batch:
        parts.append(batch)
    merged = "\n\n".join(parts)
    block = f"### {sub_heading}\n\n{merged}\n"

    out = content
    for _, start, end in reversed(spans[1:]):
        out = out[:start] + out[end:]
    first_start, first_end = spans[0][1], spans[0][2]
    tail = out[first_end:]
    return out[:first_start] + block + (f"\n{tail}" if tail.strip() else "")


def ensure_section(content: str, heading: str, order: Sequence[str]) -> str:
    """Create ``## heading`` in *order* position if absent; else return unchanged.

    A missing parent H2 must not be a hard error: ``/ll:refine-issue`` *creates*
    sections that do not yet exist (§ Enrichment Rules populates
    ``## Integration Map``, ``## Program Design`` and ``## Root Cause`` on
    issues that lack them). Erroring there would push the model back to
    hand-``Edit`` — precisely the inert-adoption failure the CLI route exists to
    prevent.

    Args:
        content: Full issue markdown.
        heading: H2 heading text, without the leading ``## ``.
        order: Canonical section order (v2.0 template order); the new heading is
            inserted before the first section that follows it in *order* and is
            actually present. When no such anchor exists it is appended.
    """
    if _h2_slice(content, heading) is not None:
        return content

    lowered = [h.strip().casefold() for h in order]
    target = heading.strip().casefold()
    successors = lowered[lowered.index(target) + 1 :] if target in lowered else []

    block = f"## {heading}\n\n"
    for successor in successors:
        match = next(
            (
                m
                for m in re.finditer(r"^##\s+(.+?)\s*$", content, re.MULTILINE)
                if m.group(1).strip().casefold() == successor
            ),
            None,
        )
        if match is None:
            continue
        insert_at = _hr_aware_start(content, match.start())
        return content[:insert_at] + block + content[insert_at:]

    return f"{content.rstrip(chr(10))}\n\n## {heading}\n"


def _hr_aware_start(content: str, heading_start: int) -> int:
    """Back up over a ``---`` rule preceding the heading at *heading_start*.

    The v2.0 footer is ``\\n---\\n\\n## Status``; inserting between the rule and
    the heading would orphan the rule above the new section.
    """
    before = content[:heading_start].rstrip("\n")
    if before.endswith("\n---") or before == "---":
        return len(before) - len("---")
    return heading_start
