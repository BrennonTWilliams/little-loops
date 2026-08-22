"""ll-verify-evidence: certify that quoted evidence exists in its cited artifact (BUG-3282).

`/ll:verify-issues` validates an issue's *code* claims but never checked that
quoted **evidence** — a snippet attributed to another artifact, usually
another `.issues/` file — actually appears there. An issue whose code
references are all accurate but whose motivating evidence is fabricated
passed verification and received `verify_verdict: VALID`. This module is the
deterministic gate that closes that gap.

**Scope.** Only evidence-bearing sections are in scope — ``## Current
Behavior``, ``## Steps to Reproduce``, ``## Root Cause``, ``## Motivation``,
``### Codebase Research Findings``. Forward-looking sections (``## Proposed
Solution``, ``## Expected Behavior``, ``## Implementation Steps``, ``##
Integration Map``, ``## Program Design``) quote code that intentionally does
not exist yet, so a presence check there is meaningless. This is an
allowlist, not a denylist: a section named in neither list is out of scope,
so a template addition can never silently widen the checker.

**Pipeline** (see BUG-3282 Program Design § Decision Rules for the full
rationale of each stage): section filter -> span extraction (fenced blocks
and inline-backtick runs) -> attribution (following-parenthetical, else
nearest-preceding mention, section-bounded, with a command-output exclusion)
-> span-kind filter (drop bare identifiers, command/skill invocations, and
inline output following an invocation) -> char floor -> baseline suppression
-> artifact resolution -> match against the working tree, then the
artifact's blob history newest-first (``--max-revisions``, default 80), each
side normalized identically (whitespace collapse + markdown-emphasis strip).

**Matching** uses one :class:`HistoryIndex` pass (``git log --all --raw``)
plus one long-lived :class:`BlobReader` (``git cat-file --batch``) for the
whole run, rather than two ``git log -p`` invocations per artifact. That is
both far faster (a full-corpus scan went from 13+ minutes to well under one)
and *more correct*: ``git log -p`` interleaves commit-message text with file
content, so the previous implementation certified quotes that existed only
in some commit message and in no revision of the cited artifact.

**Modes**, mirroring ``verify_private_refs``'s three enforcement points:

* **changed-files** (``ll-verify-evidence FILE...``) — whole-file scan, no
  baseline. The skill / host-hook invocation.
* **``--added-only FILE...``** — only spans on lines the staged diff adds.
  The pre-commit hook.
* **``--all``** — full scan of ``issues.base_dir``, compared against the
  tracked ID-keyed span-hash baseline at ``.ll/evidence-baseline.json``. This
  is the pytest CI gate.

A ``<!-- ll-evidence-ok: reason -->`` marker on the span's own or preceding
line suppresses that one finding — required for the *counter-example* class,
where an issue reports a fabricated quote and must therefore reproduce it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context
from little_loops.text_utils import SOURCE_EXTENSIONS, fence_spans, in_fence

if TYPE_CHECKING:
    pass

BASELINE_PATH = Path(".ll") / "evidence-baseline.json"

_SUPPRESS_RE = re.compile(r"ll-evidence-ok:\s*(.+?)\s*(?:-->|$)")

# Section scope is an allowlist (Decision Rules -> Section scope). A section
# heading text matching neither this set nor a "### " subsection variant is
# out of scope by default.
IN_SCOPE_SECTIONS = frozenset(
    {
        "Current Behavior",
        "Steps to Reproduce",
        "Root Cause",
        "Motivation",
        "Codebase Research Findings",
    }
)

# Raw-character floor. Bounded in (13, 24] by the flagship fixture: the
# shortest genuine fabrication is 24 raw chars ("- **(b) Drop the knob.**");
# the designated true-negative ("**Option A**") is 12. Measured on the raw
# span text, before normalization (Decision Rules -> Threshold).
MIN_SPAN_LEN = 20

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.MULTILINE)
_INLINE_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_ISSUE_ID_RE = re.compile(r"\b(?:P[0-5]-)?(?:BUG|FEAT|ENH|EPIC)-(\d+)\b")
_FILE_PATH_CANDIDATE_RE = re.compile(
    r"(?<![\w./])([A-Za-z0-9_.][\w/.-]*\.[A-Za-z0-9_]{1,6})(?::\d+(?:[-,]\d+)*)?(?!\w)"
)
_FOLLOWING_PAREN_RE = re.compile(r"^\s*\(([^)]*)\)")


def _looks_like_file_path(candidate: str) -> bool:
    """A path candidate is a real file-path mention, not a dotted symbol reference.

    Requires either a ``/`` (structural marker of a path) or a recognized
    source-file extension — a bare ``module.method`` code symbol (e.g.
    ``issue_parser.locate``) has neither and must not be misattributed as a
    file-path mention.
    """
    if "/" in candidate:
        return True
    ext = "." + candidate.rsplit(".", 1)[-1].lower()
    return ext in SOURCE_EXTENSIONS


# Command-output exclusion: a line whose backtick run is a shell invocation
# and that ends in a presentation verb attributes the next fenced block to
# *the command's output*, not to the artifact the command names.
_COMMAND_BINARIES = ("ll-", "git", "python3", "python", "ruff", "pytest")
_PRESENTATION_VERB_RE = re.compile(r"(returns|outputs|prints|emits|shows):\s*$")

# Span-kind filter (Decision Rules -> Span kind, load-bearing): a span is only
# checked if it is plausibly a *quote*, not a mention.
_SKILL_INVOCATION_RE = re.compile(r"^/ll:[a-z-]+")


@dataclass(frozen=True)
class Section:
    """One in-scope (or out-of-scope) heading-delimited chunk of an issue body."""

    name: str
    start: int
    end: int


@dataclass(frozen=True)
class CandidateSpan:
    """One quoted span extracted from an in-scope section, pre-filtering."""

    text: str  # raw span content, without backticks/fence delimiters
    start: int  # char offset in the full document
    end: int
    line: int  # 1-indexed line the span starts on
    section: str
    is_fence: bool


@dataclass(frozen=True)
class EvidenceFinding:
    """One evidence span verified absent from its cited artifact."""

    issue_path: Path
    section: str
    line: int
    span: str
    artifact: str


# ---------------------------------------------------------------------------
# Section scoping
# ---------------------------------------------------------------------------


def iter_sections(content: str) -> list[Section]:
    """Split *content* into heading-delimited chunks (## or ### level).

    Each :class:`Section` runs from just after its heading line to the start
    of the next ``##``/``###`` heading (or end of document). Section-bounded
    attribution (Decision Rules -> Attribution rule) relies on these
    boundaries: a mention never attributes a span across a heading.
    """
    matches = list(_HEADING_RE.finditer(content))
    sections: list[Section] = []
    for i, m in enumerate(matches):
        name = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append(Section(name=name, start=start, end=end))
    return sections


def in_scope_sections(content: str) -> list[Section]:
    """Sections whose heading text is in :data:`IN_SCOPE_SECTIONS` (allowlist)."""
    return [s for s in iter_sections(content) if s.name in IN_SCOPE_SECTIONS]


# ---------------------------------------------------------------------------
# Mention extraction (for attribution)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mention:
    pos: int
    ref: str


def _extract_mentions(text: str, base_offset: int) -> list[Mention]:
    """Find issue-ID and file-path mentions in *text*, offset to the document."""
    mentions: list[Mention] = []
    for m in _ISSUE_ID_RE.finditer(text):
        mentions.append(Mention(pos=base_offset + m.start(), ref=m.group(0)))
    for m in _FILE_PATH_CANDIDATE_RE.finditer(text):
        if _looks_like_file_path(m.group(1)):
            mentions.append(Mention(pos=base_offset + m.start(), ref=m.group(1)))
    mentions.sort(key=lambda mm: mm.pos)
    return mentions


# ---------------------------------------------------------------------------
# Span extraction
# ---------------------------------------------------------------------------


def _line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def extract_candidate_spans(content: str, section: Section) -> list[CandidateSpan]:
    """Extract fenced-block and inline-backtick spans within *section*.

    Fenced blocks reuse :func:`fence_spans`/:func:`in_fence`; inline runs are
    a new regex (``text_utils.py`` has no inline-backtick primitive — see
    BUG-3282 Codebase Research Findings). Both span forms matter: the
    flagship regression fixture's must-flag spans are all inline runs.
    """
    section_text = content[section.start : section.end]
    all_fences = fence_spans(content)
    spans: list[CandidateSpan] = []

    # Fenced blocks whose span lies inside this section.
    for fs, fe in all_fences:
        if fs >= section.start and fe <= section.end:
            raw = content[fs:fe]
            # Strip the delimiter lines themselves, keep the body.
            body_lines = raw.splitlines()
            body = "\n".join(body_lines[1:-1]) if len(body_lines) > 2 else ""
            spans.append(
                CandidateSpan(
                    text=body,
                    start=fs,
                    end=fe,
                    line=_line_number(content, fs),
                    section=section.name,
                    is_fence=True,
                )
            )

    # Inline backtick runs, excluding anything inside a fence.
    for m in _INLINE_BACKTICK_RE.finditer(section_text):
        start = section.start + m.start()
        end = section.start + m.end()
        if in_fence(start, end, all_fences):
            continue
        spans.append(
            CandidateSpan(
                text=m.group(1),
                start=start,
                end=end,
                line=_line_number(content, start),
                section=section.name,
                is_fence=False,
            )
        )

    spans.sort(key=lambda s: s.start)
    return spans


# ---------------------------------------------------------------------------
# Command-output exclusion
# ---------------------------------------------------------------------------


def _preceding_nonblank_line(content: str, offset: int) -> str | None:
    """Return the nearest non-blank line before *offset*, crossing blank lines."""
    line_start = content.rfind("\n", 0, offset)
    while True:
        prev_end = line_start
        if prev_end <= 0:
            return None
        prev_start = content.rfind("\n", 0, prev_end)
        line = content[prev_start + 1 : prev_end]
        if line.strip():
            return line
        line_start = prev_start


def _is_command_invocation_line(line: str) -> bool:
    stripped = line.strip().lstrip("`").lstrip("- ").strip()
    return stripped.startswith(_COMMAND_BINARIES) or bool(_SKILL_INVOCATION_RE.match(stripped))


def is_command_output(content: str, span: CandidateSpan) -> bool:
    """True when *span* (a fence) is the output of a command, not a quote.

    Must reach the next fenced block across intervening blank lines — an
    adjacency-only check is dead code on the flagship fixture, where the
    invocation line and the fence it introduces are separated by one blank
    line (Decision Rules -> Attribution rule).
    """
    if not span.is_fence:
        return False
    preceding = _preceding_nonblank_line(content, span.start)
    if preceding is None:
        return False
    return _is_command_invocation_line(preceding) and bool(_PRESENTATION_VERB_RE.search(preceding))


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


_LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])\s")

# Sections where block scope alone is not sufficient evidence of a binding.
# `### Codebase Research Findings` is written by `/ll:refine-issue` and mixes
# *observed* with *proposed* code, so a quote there is as likely to be a
# design sketch as a citation. Measured: after the other precision rules it
# still accounted for 73% of residual findings (942 of 1284), ~100%
# false-positive on a hand-labelled sample. Only an explicit, authored binding
# (a following parenthetical) counts here.
STRICT_BINDING_SECTIONS = frozenset({"Codebase Research Findings"})


def _line_bounds(content: str, pos: int) -> tuple[int, int]:
    start = content.rfind("\n", 0, pos) + 1
    end = content.find("\n", pos)
    return start, len(content) if end == -1 else end


def binding_block(content: str, mention_pos: int, section: Section) -> tuple[int, int]:
    """Char range of the prose block a mention at *mention_pos* governs.

    The block is the list item or paragraph holding the mention, walked back
    to its opening line and forward through its indented continuation lines.
    A block whose text ends in ``:`` additionally governs the block it
    introduces, across at most one blank line — the shape of "…, which
    contains two distinct decision points:" followed by the list that names
    them. Clamped to *section* on both ends, so a mention never binds across
    a heading.

    Chosen over a character window or a paragraph bound, both of which were
    measured on this corpus: their hit-vs-miss lift is only ~1.1, and both
    break the flagship fixture, whose must-flag spans sit 170-311 chars from
    their mention and cross a blank line.
    """
    lo, hi = section.start, section.end

    # Line table for the section, so the walk is index arithmetic rather than
    # offset arithmetic (the latter is where an off-by-one silently swallows
    # or drops a whole block).
    lines: list[tuple[int, int]] = []
    pos = lo
    while pos <= hi:
        end = content.find("\n", pos)
        if end == -1 or end > hi:
            end = hi
        lines.append((pos, end))
        if end >= hi:
            break
        pos = end + 1
    if not lines:
        return lo, hi

    def blank(i: int) -> bool:
        return not content[lines[i][0] : lines[i][1]].strip()

    idx = 0
    for i, (s, e) in enumerate(lines):
        if s <= mention_pos <= e:
            idx = i
            break

    # The mention's paragraph: the maximal run of non-blank lines around it.
    first = idx
    while first > 0 and not blank(first - 1):
        first -= 1
    last = idx
    while last + 1 < len(lines) and not blank(last + 1):
        last += 1

    block_start, block_end = lines[first][0], lines[last][1]

    # A colon-terminated paragraph also governs the paragraph it introduces,
    # across at most one blank line. This is the flagship's shape: "…which
    # contains two distinct decision points:" on one line, a blank, then the
    # numbered list that names them.
    if content[block_start:block_end].rstrip().endswith(":"):
        nxt = last + 1
        if nxt < len(lines) and blank(nxt):
            nxt += 1
        if nxt < len(lines) and not blank(nxt):
            while nxt + 1 < len(lines) and not blank(nxt + 1):
                nxt += 1
            block_end = lines[nxt][1]

    return block_start, min(block_end, hi)


def attribute_span(
    content: str,
    span: CandidateSpan,
    mentions: list[Mention],
    section: Section | None = None,
) -> str | None:
    """Return the artifact reference *span* is attributed to, or ``None``.

    Ordered predicates; falling off the end **abstains**:

    1. A following parenthetical — the only explicit, authored binding form.
    2. Block scope: a mention whose governing block (see :func:`binding_block`)
       covers the span. Abstains when no mention covers it, and abstains when
       the covering mentions name more than one distinct artifact — a block
       naming two artifacts is no evidence of which one a span came from.

    The previous rule bound every span to the nearest preceding mention at
    unbounded distance, which produced ~3790 findings against a 90-entry
    baseline on this corpus, the large majority mis-attributed.
    """
    following = content[span.end : span.end + 200]
    m = _FOLLOWING_PAREN_RE.match(following)
    if m:
        inner = m.group(1)
        id_match = _ISSUE_ID_RE.search(inner)
        if id_match:
            return id_match.group(0)
        path_match = _FILE_PATH_CANDIDATE_RE.search(inner)
        if path_match and _looks_like_file_path(path_match.group(1)):
            return path_match.group(1)

    if section is None:
        return None
    if section.name in STRICT_BINDING_SECTIONS:
        return None

    covering = [
        mm
        for mm in mentions
        if mm.pos < span.start
        and (lambda b: b[0] <= span.start <= b[1])(binding_block(content, mm.pos, section))
    ]
    if not covering:
        return None
    if len({mm.ref for mm in covering}) > 1:
        return None
    return covering[-1].ref


# ---------------------------------------------------------------------------
# Span-kind filter (quote vs. mention)
# ---------------------------------------------------------------------------


def is_mention_class(span_text: str, line_text: str, span_start_col: int) -> bool:
    """True when *span_text* is a reference/mention rather than a claimed quote.

    Excluded shapes (Decision Rules -> Span kind):
    1. Bare identifiers/paths — no internal whitespace.
    2. Command/skill invocations — first token is a known binary or ``/ll:``.
    3. Inline output following an invocation span on the same line.
    4. A markdown heading marker (``## Some Section``) — a reference to a
       section *name* (template shape, e.g. "checks that a `## Steps to
       Reproduce` naming a live artifact..."), not a quote of literal file
       content.
    """
    stripped = span_text.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if " " not in stripped:
        return True
    if stripped.startswith(_COMMAND_BINARIES) or _SKILL_INVOCATION_RE.match(stripped):
        return True
    # Inline output following an invocation earlier on the same line: check
    # whether an excluded invocation backtick run precedes this span's column
    # on its own line.
    prefix = line_text[:span_start_col]
    for m in _INLINE_BACKTICK_RE.finditer(prefix):
        candidate = m.group(1).strip()
        if candidate and (
            " " not in candidate
            or candidate.startswith(_COMMAND_BINARIES)
            or _SKILL_INVOCATION_RE.match(candidate)
        ):
            if candidate.startswith(_COMMAND_BINARIES) or _SKILL_INVOCATION_RE.match(candidate):
                return True
    return False


# ---------------------------------------------------------------------------
# Span-kind exclusions (quote vs. non-quote shapes)
# ---------------------------------------------------------------------------

# An elision marker only disqualifies a span when it sits *between structural
# tokens on both sides* (skipping at most one space). The two-sided
# requirement is what separates `run_claude_command(..., resume_session=True)`
# — an authored abbreviation — from real source text that merely contains an
# ellipsis, such as a Python `...` stub body or `print("Loading...")`.
# Measured on this corpus: the two-sided rule drops 170 findings for 3 real
# hits (57x); a naive "contains ..." rule drops 247 for 16 hits (5x worse on
# exactly the case worth protecting).
_ELISION_STRUCTURAL_RE = re.compile(r"[(\[{,|'\"] ?(?:\.\.\.|…) ?[)\]},|'\"]")
_ELISION_LINE_RE = re.compile(r"^[ \t]*(?:#[ \t]*)?(?:\.\.\.|…)[ \t]*$", re.MULTILINE)

# A comment introducing an arrow that points at the quoted line. Deliberately
# arrow-only: `# NOTE:` / `# TODO:` occur verbatim in real source.
_AUTHOR_ANNOTATION_RE = re.compile(r"(?:#|//|<!--|;)\s*(?:<--|<-|←|⟵)")

# Placeholders an author substitutes for a real value. Applied only when the
# artifact is not markdown: markdown templates legitimately contain these
# (`Decomposed from [PARENT-ID]`, `parent: EPIC-NNN references`), and the
# ungated rule measured 10 lost hits against 1 for the gated form.
_METAVAR_RE = re.compile(
    r"<[A-Za-z][A-Za-z0-9_-]{1,24}>"
    r"|\{[A-Z][A-Z0-9_]{1,24}\}"
    r"|\[[A-Z][A-Z0-9_-]{2,24}\]"
    r"|\bNNN\b|\bXXX\b"
)

# Template label fields whose value points *at* code rather than quoting it.
_REFERENCE_FIELD_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?\*\*(?:Anchor|File|Location|Symbol|Path)\*\*\s*:\s*$", re.I
)
_LOCATION_PHRASE_RE = re.compile(
    r"^in\s+(?:function|method|class|module|file|the)\b", re.I
)


def excluded_span_kind(span: CandidateSpan, artifact_ref: str, content: str = "") -> str | None:
    """Name the non-quote class *span* falls into, or ``None`` if it is checkable.

    A sibling of :func:`is_mention_class` rather than an extension of it, so
    each rule stays separately testable (Decision Rules -> Span kind). The
    returned label names the class for diagnostics.
    """
    text = span.text
    if not text:
        return None

    # Template reference fields. The issue template's Root Cause block is
    # `- **File**: <path>` / `- **Anchor**: <location>` / `- **Cause**: prose`;
    # the File and Anchor values are *pointers to* code, never quotations of
    # it. Measured: 85 of 361 residual findings (24%) sat on such a line.
    if content:
        line_start = content.rfind("\n", 0, span.start) + 1
        if _REFERENCE_FIELD_RE.match(content[line_start : span.start]):
            return "reference_field"

    # The same idea in prose form, for reference lines that carry no template
    # label: "in function foo()", "in method Bar.baz()", "in the decide state".
    if _LOCATION_PHRASE_RE.match(text):
        return "location_phrase"

    # An authored inline code span never opens or closes on whitespace. When
    # one wraps a line, the line-bounded `_INLINE_BACKTICK_RE` pairs its
    # closing backtick with the *next* run's opening backtick and yields the
    # prose in between; that artifact always has a whitespace edge.
    if text[:1].isspace() or text[-1:].isspace():
        return "mispaired_run"

    if _ELISION_STRUCTURAL_RE.search(text) or _ELISION_LINE_RE.search(text):
        return "elision"

    if _AUTHOR_ANNOTATION_RE.search(text):
        return "author_annotation"

    if not artifact_ref.lower().endswith(".md") and _METAVAR_RE.search(text):
        return "metavariable"

    return None


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


def is_suppressed(content: str, span_start: int) -> bool:
    """``<!-- ll-evidence-ok: reason -->`` on the span's own or preceding line."""
    line_start = content.rfind("\n", 0, span_start) + 1
    line_end = content.find("\n", span_start)
    if line_end == -1:
        line_end = len(content)
    own_line = content[line_start:line_end]
    if _SUPPRESS_RE.search(own_line):
        return True
    if line_start == 0:
        return False
    prev_end = line_start - 1
    prev_start = content.rfind("\n", 0, prev_end) + 1
    prev_line = content[prev_start:prev_end]
    return bool(_SUPPRESS_RE.search(prev_line))


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_EMPHASIS_CHARS_RE = re.compile(r"[*_`]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse whitespace and strip markdown emphasis/decoration.

    Identical treatment on both span and artifact text (Decision Rules ->
    Normalization, load-bearing): whitespace-only normalization is not
    enough — the fixture's own designated true-negative (``**Option A**``)
    only holds once emphasis is stripped too.
    """
    stripped = _EMPHASIS_CHARS_RE.sub("", text)
    collapsed = _WHITESPACE_RE.sub(" ", stripped).strip()
    return collapsed


def normalize_query(text: str) -> str:
    """:func:`normalize`, plus trailing sentence punctuation stripped."""
    return normalize(text).rstrip(" .,;:!?")


# ---------------------------------------------------------------------------
# History index (path -> blob OIDs)
# ---------------------------------------------------------------------------

# Newest-first revisions searched per artifact. Measured knee on this repo's
# 3194-issue corpus: 20 -> 12.1s/2681 findings, 80 -> 20.6s/2544, 200 ->
# 26.8s/2515, uncapped -> 111.1s/2503. 80 buys 96% of uncapped coverage for
# 19% of the cost and is a strict superset of the `-n20` this replaces. It
# participates in the verdict-cache key, so raising it invalidates only the
# not-found entries.
DEFAULT_MAX_REVISIONS = 80

_NULL_OID = "0" * 40

# Past this many distinct paths a path-limited `git log` pass costs more than
# one whole-history pass (measured: 5 paths ~0.34s, full history ~1.5s).
_NARROW_PROMOTION_THRESHOLD = 8


class HistoryIndex:
    """``path -> newest-first blob OIDs``, from one ``git log --raw`` pass.

    Replaces the per-artifact ``git log --all [--follow] -p`` tiers, which
    measured 65% of total runtime (and, for ``--follow``, resolved zero spans
    across two independent samples). Blob content is also strictly more
    faithful than a patch stream: ``git log -p`` interleaves *commit message*
    text with file content, so the previous implementation could certify a
    fabricated quote that appeared only in some commit message (verified:
    ``use_design_tokens: false`` matched the patch stream for
    ``cli/loop/lifecycle.py`` while appearing in 0 of its 72 revisions).

    ``--no-renames`` is mandatory: ``diff.renames`` has defaulted on since git
    2.9, and an ``R100`` raw record carries *two* tab-separated paths, which a
    naive parse mis-files under a concatenated path. ``-z`` gives NUL-framed
    paths that are never C-quoted.

    Merge commits show no diff by default, so a blob that only ever existed as
    a merge resolution is not indexed. That matches the coverage of the
    ``git log -p`` tiers this replaces, so it is parity rather than a new gap;
    ``--diff-merges=separate`` is the escape hatch if it ever bites.

    Renames are deliberately *not* followed. ``git log --all -- <path>`` still
    sees the commit that added the file, and an add's post-image blob is the
    complete file content, so a rename only hides text deleted *before* the
    rename. If that ever matters, re-run the pass with ``-M`` and chain the
    ``R``-status records into ``new_path -> old_path`` before unioning blob
    lists — about ten lines, and measured at +2.2s per run for a recall gain
    of zero on this corpus.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self._blobs: dict[str, list[str]] = {}
        self._seen: dict[str, set[str]] = {}
        self._full = False
        self._narrow_paths: set[str] = set()

    @classmethod
    def from_data(cls, base_dir: Path, data: dict[str, tuple[str, ...]]) -> HistoryIndex:
        """Rebuild from :meth:`as_data` output — used to ship the index to pool workers."""
        index = cls(base_dir)
        index._blobs = {path: list(oids) for path, oids in data.items()}
        index._full = True
        return index

    def as_data(self) -> dict[str, tuple[str, ...]]:
        """Picklable snapshot: built once in the parent, shipped once per worker."""
        return {path: tuple(oids) for path, oids in self._blobs.items()}

    def _parse(self, out: str) -> None:
        """Pair each raw metadata record with the path chunk that follows it.

        Each diff entry is ``:<mode_src> <mode_dst> <sha_src> <sha_dst> <status>``
        then NUL then the path then NUL. Both the pre-image and the post-image
        OID are indexed: the pre-image carries content a commit *deleted*,
        which is what the removed (``-``) patch lines used to cover.
        """
        chunks = out.split("\0")
        i = 0
        while i < len(chunks):
            meta = chunks[i].lstrip("\n")
            if not meta.startswith(":"):
                i += 1
                continue
            parts = meta[1:].split(" ")
            if len(parts) < 4 or i + 1 >= len(chunks):
                i += 1
                continue
            path = chunks[i + 1]
            if path:
                seen = self._seen.setdefault(path, set())
                blobs = self._blobs.setdefault(path, [])
                for oid in (parts[3], parts[2]):
                    if oid != _NULL_OID and oid not in seen:
                        seen.add(oid)
                        blobs.append(oid)
            i += 2

    def ensure_full(self) -> None:
        """Index every path in every reachable revision (measured ~1.5s here)."""
        if self._full:
            return
        self._blobs.clear()
        self._seen.clear()
        self._run_full()
        self._full = True

    def _run_full(self) -> None:
        try:
            result = subprocess.run(
                ["git", "log", "--all", "--raw", "-z", "--no-abbrev", "--no-renames", "--format="],
                cwd=self.base_dir,
                capture_output=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return
        if result.returncode == 0:
            self._parse(result.stdout.decode("utf-8", errors="replace"))

    def ensure_paths(self, rel_paths: Iterable[str]) -> None:
        """Index just *rel_paths*, promoting to a full pass once it stops paying."""
        if self._full:
            return
        wanted = {p for p in rel_paths if p not in self._narrow_paths}
        if not wanted:
            return
        self._narrow_paths |= wanted
        if len(self._narrow_paths) > _NARROW_PROMOTION_THRESHOLD:
            self.ensure_full()
            return
        try:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--all",
                    "--raw",
                    "-z",
                    "--no-abbrev",
                    "--no-renames",
                    "--format=",
                    "--",
                    *sorted(wanted),
                ],
                cwd=self.base_dir,
                capture_output=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return
        if result.returncode == 0:
            self._parse(result.stdout.decode("utf-8", errors="replace"))

    def blobs_for(self, rel_path: str) -> tuple[str, ...]:
        """Blob OIDs for *rel_path*, newest revision first.

        An empty tuple means the path never existed in any indexed revision —
        the case that previously cost ~250ms of ``git log`` per miss and now
        costs a dict lookup.
        """
        return tuple(self._blobs.get(rel_path, ()))


class BlobReader:
    """A single long-lived ``git cat-file --batch`` for the whole run.

    Measured 0.048 ms/blob (260 MB/s) on an interactive round-trip, versus a
    ~7ms process spawn for ``git show``. Requests are written and read one at
    a time: queuing many writes without interleaved reads deadlocks against
    git's stdout pipe buffer.

    Owns a subprocess, so it must never be pickled — pool workers construct
    their own in the initializer.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self._proc: subprocess.Popen[bytes] | None = None

    def _ensure(self) -> subprocess.Popen[bytes] | None:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        try:
            self._proc = subprocess.Popen(
                ["git", "cat-file", "--batch"],
                cwd=self.base_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            self._proc = None
        return self._proc

    def read(self, oid: str) -> bytes | None:
        """Return the blob's bytes, or ``None`` when git cannot supply it."""
        proc = self._ensure()
        if proc is None or proc.stdin is None or proc.stdout is None:
            return None
        try:
            proc.stdin.write(f"{oid}\n".encode())
            proc.stdin.flush()
            header = proc.stdout.readline()
        except (OSError, ValueError):
            self.close()
            return None
        if not header:
            self.close()
            return None
        fields = header.decode("utf-8", errors="replace").split()
        if len(fields) < 3:
            return None
        try:
            size = int(fields[2])
        except ValueError:
            return None
        try:
            payload = proc.stdout.read(size)
            proc.stdout.read(1)  # trailing newline
        except (OSError, ValueError):
            self.close()
            return None
        return payload

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
            proc.wait(timeout=5)
        except (OSError, subprocess.SubprocessError, ValueError):
            proc.kill()

    def __enter__(self) -> BlobReader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Artifact resolution
# ---------------------------------------------------------------------------


def build_tracked_index(base_dir: Path) -> frozenset[str]:
    """Single ``git ls-files -z`` call, reused across every span's resolution.

    Resolution is per-candidate-span, and a corpus-wide scan can carry
    thousands of candidates; a subprocess per candidate does not scale
    (measured: ~0.4s/file at 100 files with a per-candidate ``git
    ls-files --error-unmatch`` call). One index built up front makes
    tracked-ness a set lookup instead.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if result.returncode != 0:
        return frozenset()
    names = result.stdout.decode("utf-8", errors="replace").split("\0")
    return frozenset(n for n in names if n)


def _is_tracked(base_dir: Path, rel_path: str, tracked: frozenset[str] | None) -> bool:
    if tracked is not None:
        return rel_path in tracked
    try:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel_path],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def resolve_artifact(
    base_dir: Path,
    ref: str,
    config: object | None,
    tracked: frozenset[str] | None = None,
    cache: dict[str, str | None] | None = None,
) -> str | None:
    """Resolve *ref* (issue ID or file path) to a git-tracked repo-relative path.

    Fail-open (Decision Rules -> Fail-open): an artifact that does not
    resolve, or resolves to an untracked path, is skipped with no finding.
    *tracked*, when given, is a prebuilt index (:func:`build_tracked_index`)
    used instead of a per-call subprocess. *cache*, when given, memoizes by
    *ref* across calls — a corpus-wide scan repeats the same handful of
    heavily-cited issue IDs across hundreds of files, and
    ``resolve_issue_path`` globs the issue tree on every call.
    """
    if cache is not None and ref in cache:
        return cache[ref]

    id_match = _ISSUE_ID_RE.fullmatch(ref)
    if id_match and config is not None:
        from little_loops.issue_parser import resolve_issue_path

        path = resolve_issue_path(config, ref)  # type: ignore[arg-type]
        if path is None:
            result = None
        else:
            try:
                rel = str(path.resolve().relative_to(base_dir.resolve())).replace("\\", "/")
            except ValueError:
                rel = str(path)
            result = rel if _is_tracked(base_dir, rel, tracked) else None
    else:
        rel = ref.replace("\\", "/")
        result = rel if _is_tracked(base_dir, rel, tracked) else None

    if cache is not None:
        cache[ref] = result
    return result


# ---------------------------------------------------------------------------
# Tiered matching
# ---------------------------------------------------------------------------


def _read_working_tree(base_dir: Path, rel_path: str) -> str | None:
    try:
        return (base_dir / rel_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# Blob-memo ceiling in *retained normalized bytes*, not entries: a count-based
# cap evicts small blobs and large ones alike and measured worse (45440 reads
# for 39328 pairs at 4000 entries).
_BLOB_MEMO_MAX_BYTES = 256 * 1024 * 1024


class ArtifactMatcher:
    """Artifact-major matcher: working tree, then the artifact's blob history.

    Replaces the four-tier ``working tree -> HEAD -> git log -p -> git log
    --follow -p`` pipeline. The ``HEAD`` tier is subsumed (the newest indexed
    blob *is* HEAD's whenever HEAD last touched the path) and both ``git log
    -p`` tiers are replaced by a blob walk over :class:`HistoryIndex`, which
    is faster, more complete (full file content per revision rather than
    changed hunks), and immune to the commit-message contamination that let
    the patch-stream implementation certify fabricated quotes.

    ``matches()`` keeps its original signature so every caller and existing
    test is unaffected.
    """

    def __init__(
        self,
        base_dir: Path,
        index: HistoryIndex | None = None,
        reader: BlobReader | None = None,
        *,
        max_revisions: int = DEFAULT_MAX_REVISIONS,
        verdict_cache: VerdictCache | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.index = index if index is not None else HistoryIndex(base_dir)
        self.reader = reader if reader is not None else BlobReader(base_dir)
        self.max_revisions = max_revisions
        self.verdict_cache = verdict_cache
        self._worktree_cache: dict[str, str | None] = {}
        self._worktree_sha: dict[str, str] = {}
        self._blob_cache: dict[str, str] = {}
        self._blob_bytes = 0

    def _worktree_text(self, rel_path: str) -> str | None:
        if rel_path not in self._worktree_cache:
            raw = _read_working_tree(self.base_dir, rel_path)
            self._worktree_cache[rel_path] = normalize(raw) if raw is not None else None
        return self._worktree_cache[rel_path]

    def _blob_text(self, oid: str) -> str | None:
        cached = self._blob_cache.get(oid)
        if cached is not None:
            return cached
        raw = self.reader.read(oid)
        if raw is None:
            return None
        text = normalize(raw.decode("utf-8", errors="replace"))
        if self._blob_bytes >= _BLOB_MEMO_MAX_BYTES:
            self._blob_cache.clear()
            self._blob_bytes = 0
        self._blob_cache[oid] = text
        self._blob_bytes += len(text)
        return text

    def _worktree_fingerprint(self, rel_path: str) -> str:
        if rel_path not in self._worktree_sha:
            try:
                raw = (self.base_dir / rel_path).read_bytes()
            except OSError:
                self._worktree_sha[rel_path] = "-"
            else:
                self._worktree_sha[rel_path] = hashlib.sha256(raw).hexdigest()[:16]
        return self._worktree_sha[rel_path]

    def _blob_fingerprint(self, rel_path: str) -> str:
        oids = self.index.blobs_for(rel_path)[: self.max_revisions]
        return hashlib.sha256("\n".join(oids).encode("utf-8")).hexdigest()[:16]

    def matches(self, rel_path: str, normalized_spans: list[str]) -> dict[str, bool]:
        """Return ``{normalized_span: found}`` for every span, artifact-major."""
        pending = set(normalized_spans)
        found: dict[str, bool] = {}
        cache = self.verdict_cache

        # Cache first, so a fully-memoized artifact costs no I/O at all. The
        # not-found form is revalidated against working-tree and revision-set
        # fingerprints, so a stale entry can only cause redundant work — never
        # a suppressed finding.
        if cache is not None:
            wt_sha = self._worktree_fingerprint(rel_path)
            blob_fp = self._blob_fingerprint(rel_path) if not cache.refs_unchanged else ""
            for span in list(pending):
                verdict = cache.lookup(rel_path, _span_hash(span), blob_fp, wt_sha)
                if verdict is not None:
                    found[span] = verdict
                    pending.discard(span)
            if not pending:
                return found

        text = self._worktree_text(rel_path)
        if text is not None:
            hit = {span for span in pending if span in text}
            found.update(dict.fromkeys(hit, True))
            pending -= hit

        if pending:
            self.index.ensure_paths([rel_path])
            for oid in self.index.blobs_for(rel_path)[: self.max_revisions]:
                if not pending:
                    break
                blob_text = self._blob_text(oid)
                if blob_text is None:
                    continue
                hit = {span for span in pending if span in blob_text}
                found.update(dict.fromkeys(hit, True))
                pending -= hit

        for span in pending:
            found[span] = False

        if cache is not None:
            wt_sha = self._worktree_fingerprint(rel_path)
            blob_fp = self._blob_fingerprint(rel_path)
            for span in normalized_spans:
                cache.record(rel_path, _span_hash(span), found[span], blob_fp, wt_sha)
        return found

    def close(self) -> None:
        self.reader.close()

    def __enter__(self) -> ArtifactMatcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Baseline (--all mode)
# ---------------------------------------------------------------------------


def _span_hash(normalized_span: str) -> str:
    return hashlib.sha256(normalized_span.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Verdict cache (memoization — NOT policy; see the class docstring)
# ---------------------------------------------------------------------------

VERDICT_CACHE_PATH = Path(".ll") / "evidence-verdict-cache.json"
_CACHE_VERSION = 1
_CACHE_ALGO = "blob-v1"


def _refs_signature(base_dir: Path) -> str:
    """Fingerprint of every ref. Unchanged => no path's blob set can have moved."""
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(objectname) %(refname)"],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return hashlib.sha256(result.stdout).hexdigest()[:16]


class VerdictCache:
    """Memoized span-presence verdicts, keyed ``artifact -> span_hash``.

    **This is a cache, not policy.** ``.ll/evidence-baseline.json`` is the
    tracked, curated artifact that decides which findings are grandfathered;
    this file only decides how much work a run repeats. Deleting it changes
    wall time and nothing else, which is why it is gitignored.

    Two verdict forms, because they age differently:

    * ``"1"`` (found) **never expires.** Git history only grows, so a span
      found in some revision is found in that revision forever. The artifacts
      most expensive to search are exactly the ones whose hits never expire.
    * ``"0:<blob_fp>:<wt_sha>"`` (not found) is valid only while both the
      searched revision set and the working-tree content are unchanged — a
      miss legitimately becomes a hit when the artifact gains the text.

    An algorithm change discards everything, hits included: a narrower matcher
    could legitimately un-find a span, so monotonicity does not survive it.
    """

    def __init__(
        self,
        verdicts: dict[str, dict[str, str]],
        refs_sig: str,
        valid: bool,
        max_revisions: int = DEFAULT_MAX_REVISIONS,
    ) -> None:
        self.verdicts = verdicts
        self.refs_sig = refs_sig
        self.max_revisions = max_revisions
        # False when refs moved since the cache was written: not-found entries
        # must then be revalidated against the blob fingerprint too.
        self.refs_unchanged = valid
        self.dirty = False

    def lookup(self, artifact: str, span_hash: str, blob_fp: str, wt_sha: str) -> bool | None:
        entry = self.verdicts.get(artifact, {}).get(span_hash)
        if entry is None:
            return None
        if entry == "1":
            return True
        parts = entry.split(":")
        if len(parts) != 3:
            return None
        _, cached_blob_fp, cached_wt = parts
        if cached_wt != wt_sha:
            return None
        if not self.refs_unchanged and cached_blob_fp != blob_fp:
            return None
        return False

    def record(
        self, artifact: str, span_hash: str, found: bool, blob_fp: str, wt_sha: str
    ) -> None:
        value = "1" if found else f"0:{blob_fp}:{wt_sha}"
        if self.verdicts.setdefault(artifact, {}).get(span_hash) == value:
            return
        self.verdicts[artifact][span_hash] = value
        self.dirty = True


def load_verdict_cache(base_dir: Path, *, max_revisions: int) -> VerdictCache:
    """Read the cache. Any problem yields an empty cache — never an error."""
    refs_sig = _refs_signature(base_dir)
    path = base_dir / VERDICT_CACHE_PATH
    if not path.is_file():
        return VerdictCache({}, refs_sig, False, max_revisions)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return VerdictCache({}, refs_sig, False, max_revisions)
    if not isinstance(data, dict):
        return VerdictCache({}, refs_sig, False, max_revisions)
    if (
        data.get("version") != _CACHE_VERSION
        or data.get("algo") != _CACHE_ALGO
        or data.get("max_revisions") != max_revisions
    ):
        return VerdictCache({}, refs_sig, False, max_revisions)
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, dict):
        return VerdictCache({}, refs_sig, False, max_revisions)
    clean: dict[str, dict[str, str]] = {}
    for artifact, spans in verdicts.items():
        if isinstance(spans, dict):
            clean[str(artifact)] = {str(k): str(v) for k, v in spans.items()}
    return VerdictCache(
        clean, refs_sig, bool(refs_sig) and data.get("refs_sig") == refs_sig, max_revisions
    )


def write_verdict_cache(
    base_dir: Path, cache: VerdictCache, *, tracked: frozenset[str] | None = None
) -> Path | None:
    """Persist the cache, dropping artifacts that are no longer tracked."""
    if not cache.dirty:
        return None
    verdicts = cache.verdicts
    if tracked is not None:
        verdicts = {a: s for a, s in verdicts.items() if a in tracked}
    payload = {
        "version": _CACHE_VERSION,
        "algo": _CACHE_ALGO,
        "max_revisions": cache.max_revisions,
        "refs_sig": cache.refs_sig,
        "_comment": (
            "Memoized ll-verify-evidence span-presence verdicts. NOT policy — safe to "
            "delete at any time; the gate's grandfathering lives in "
            ".ll/evidence-baseline.json. Gitignored."
        ),
        "verdicts": verdicts,
    }
    path = base_dir / VERDICT_CACHE_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return None
    return path


def load_baseline(base_dir: Path) -> dict[str, set[str]]:
    """Read the tracked baseline: issue ID -> set of baselined span hashes.

    An empty/missing/malformed baseline is the strict reading — every finding
    is a regression — the safe failure direction (mirrors
    ``verify_private_refs.load_baseline``).
    """
    path = base_dir / BASELINE_PATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    spans = data.get("spans") if isinstance(data, dict) else None
    if not isinstance(spans, dict):
        return {}
    result: dict[str, set[str]] = {}
    for issue_id, hashes in spans.items():
        if isinstance(hashes, list):
            result[str(issue_id)] = {str(h) for h in hashes}
    return result


def write_baseline(base_dir: Path, keyed_hashes: dict[str, set[str]]) -> Path:
    path = base_dir / BASELINE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": (
            "Grandfathered evidence-unverifiable spans per issue ID (ll-verify-evidence "
            "--all). Keyed on the anchored numeric issue ID (not path — issue files are "
            "renamed constantly) and holding normalized span hashes (never the matched "
            "text). Regenerate with ll-verify-evidence --all --update-baseline. New spans "
            "fail the gate."
        ),
        "spans": {k: sorted(v) for k, v in sorted(keyed_hashes.items())},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def _issue_id_from_frontmatter(content: str, path: Path | None = None) -> str | None:
    """The issue's numeric ID: frontmatter first, else the filename anchor.

    The baseline is keyed on this, so an issue with no resolvable ID can never
    be grandfathered and its findings can never be cleared. Frontmatter alone
    is not enough: **1091 of this repo's 3194 issue files (34%) carry no
    ``id:`` line at all**, their identity living only in the canonical
    ``P<n>-TYPE-NNN-slug.md`` filename. Falling back to
    :func:`parse_issue_filename` keeps the key rename-stable in the way that
    matters — the numeric ID survives renames; only the slug churns.

    Both an ``id: BUG-123`` and a bare ``id: 123`` are accepted: the number is
    the true unique identifier and the type prefix is human-readable shorthand.
    """
    m = re.search(r"^id:\s*(?:(?:BUG|FEAT|ENH|EPIC)-)?(\d+)\s*$", content, re.MULTILINE)
    if m:
        return m.group(1)
    if path is not None:
        from little_loops.issue_parser import parse_issue_filename

        parsed = parse_issue_filename(path.name)
        if parsed is not None:
            return parsed.number
    return None


# ---------------------------------------------------------------------------
# Staged-added-lines filter (pre-commit --added-only mode)
# ---------------------------------------------------------------------------

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def staged_added_lines(base_dir: Path, paths: list[Path]) -> dict[str, set[int]] | None:
    """Map each path to the set of line numbers *added* in the staged diff.

    Ported from ``verify_private_refs.staged_added_lines`` (identical
    contract): ``None`` means the diff could not be computed and callers must
    fail open by scanning everything.
    """
    if not paths:
        return {}
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", *[str(p) for p in paths]],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    added: dict[str, set[int]] = {}
    current: str | None = None
    lineno = 0
    for raw in result.stdout.decode("utf-8", errors="replace").splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            current = target[2:] if target.startswith(("b/", "a/")) else None
            if target == "/dev/null":
                current = None
            continue
        if raw.startswith("@@"):
            match = _HUNK_RE.match(raw)
            lineno = int(match.group(1)) if match else 0
            continue
        if current is None:
            continue
        if raw.startswith("+"):
            added.setdefault(current, set()).add(lineno)
            lineno += 1
        elif raw.startswith("-") or raw.startswith("\\"):
            continue
        else:
            lineno += 1
    return added


def _tracked_issue_files(base_dir: Path, issues_base_dir: str) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", f"{issues_base_dir}/**/*.md"],
            cwd=base_dir,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    names = result.stdout.decode("utf-8", errors="replace").split("\0")
    return [Path(n) for n in names if n]


# ---------------------------------------------------------------------------
# Top-level scan
# ---------------------------------------------------------------------------


def scan_file(
    base_dir: Path,
    path: Path,
    config: object | None,
    *,
    rel_path: Path | None = None,
    allowed_lines: set[int] | None = None,
    baseline: dict[str, set[str]] | None = None,
    matcher: ArtifactMatcher | None = None,
    tracked: frozenset[str] | None = None,
    resolution_cache: dict[str, str | None] | None = None,
) -> tuple[list[EvidenceFinding], dict[str, set[str]]]:
    """Scan one issue file for unverifiable evidence spans.

    Returns ``(findings, {artifact_ref: {normalized_span, ...}})`` — the
    second element groups this file's candidate spans by resolved artifact so
    callers can batch matching artifact-major.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], {}

    display_path = rel_path or path
    issue_id = _issue_id_from_frontmatter(content, display_path)
    baselined = baseline.get(issue_id, set()) if (baseline and issue_id) else set()

    candidates: list[tuple[CandidateSpan, str]] = []
    for section in in_scope_sections(content):
        section_mentions = _extract_mentions(content[section.start : section.end], section.start)
        for span in extract_candidate_spans(content, section):
            if span.is_fence and is_command_output(content, span):
                continue
            if len(span.text) < MIN_SPAN_LEN:
                continue
            if is_suppressed(content, span.start):
                continue
            if allowed_lines is not None and span.line not in allowed_lines:
                continue
            if not span.is_fence:
                line_start = content.rfind("\n", 0, span.start) + 1
                line_end = content.find("\n", span.start)
                line_end = len(content) if line_end == -1 else line_end
                line_text = content[line_start:line_end]
                if is_mention_class(span.text, line_text, span.start - line_start):
                    continue
            artifact = attribute_span(content, span, section_mentions, section)
            if artifact is None:
                continue
            if excluded_span_kind(span, artifact, content) is not None:
                continue
            candidates.append((span, artifact))

    if not candidates:
        return [], {}

    if matcher is None:
        matcher = ArtifactMatcher(base_dir)

    by_artifact: dict[str, list[CandidateSpan]] = {}
    resolved_ref: dict[str, str] = {}
    for span, artifact in candidates:
        resolved = resolve_artifact(base_dir, artifact, config, tracked, resolution_cache)
        if resolved is None:
            continue
        by_artifact.setdefault(resolved, []).append(span)
        resolved_ref[resolved] = artifact

    findings: list[EvidenceFinding] = []
    keyed_hashes: dict[str, set[str]] = {}
    for resolved_path, spans in by_artifact.items():
        to_check: dict[str, list[CandidateSpan]] = {}
        for span in spans:
            normalized = normalize_query(span.text)
            if not normalized:
                continue
            span_hash = _span_hash(normalized)
            if span_hash in baselined:
                continue
            to_check.setdefault(normalized, []).append(span)
        if not to_check:
            continue
        results = matcher.matches(resolved_path, list(to_check.keys()))
        for normalized, spans_for_norm in to_check.items():
            if results.get(normalized, False):
                continue
            if issue_id:
                keyed_hashes.setdefault(issue_id, set()).add(_span_hash(normalized))
            for span in spans_for_norm:
                findings.append(
                    EvidenceFinding(
                        issue_path=display_path,
                        section=span.section,
                        line=span.line,
                        span=span.text,
                        artifact=resolved_ref[resolved_path],
                    )
                )

    findings.sort(key=lambda f: f.line)
    return findings, keyed_hashes


def scan_paths(
    base_dir: Path,
    paths: list[Path],
    config: object | None,
    *,
    added_only: bool = False,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
) -> list[EvidenceFinding]:
    """Scan an explicit file list (skill / host-hook / pre-commit mode)."""
    added = staged_added_lines(base_dir, paths) if added_only else None
    matcher = ArtifactMatcher(base_dir, max_revisions=max_revisions)
    tracked = build_tracked_index(base_dir)
    resolution_cache: dict[str, str | None] = {}
    findings: list[EvidenceFinding] = []
    try:
        findings = _scan_path_list(
            base_dir, paths, config, matcher, tracked, resolution_cache, added, added_only
        )
    finally:
        matcher.close()
    return findings


def _scan_path_list(
    base_dir: Path,
    paths: list[Path],
    config: object | None,
    matcher: ArtifactMatcher,
    tracked: frozenset[str],
    resolution_cache: dict[str, str | None],
    added: dict[str, set[int]] | None,
    added_only: bool,
) -> list[EvidenceFinding]:
    findings: list[EvidenceFinding] = []
    for path in paths:
        abs_path = path if path.is_absolute() else base_dir / path
        if not abs_path.is_file():
            continue
        try:
            rel = abs_path.resolve().relative_to(base_dir.resolve())
        except ValueError:
            rel = path
        allowed_lines: set[int] | None = None
        if added_only:
            if added is None:
                allowed_lines = None  # fail closed -> scan everything
            else:
                allowed_lines = added.get(str(rel).replace("\\", "/"), set())
        file_findings, _ = scan_file(
            base_dir,
            abs_path,
            config,
            rel_path=rel,
            allowed_lines=allowed_lines,
            matcher=matcher,
            tracked=tracked,
            resolution_cache=resolution_cache,
        )
        findings.extend(file_findings)
    return findings


def scan_all(
    base_dir: Path,
    config: object,
    issues_base_dir: str,
    *,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
    use_baseline: bool = True,
) -> tuple[list[EvidenceFinding], dict[str, set[str]]]:
    """Scan every tracked issue file under *issues_base_dir* (Proposed Solution step 8).

    Scoped to the issue corpus, not the whole repo: evidence attribution is
    an issue-file concern, and an unscoped ``--all`` would walk history for
    every source file.
    """
    # A re-seed must scan with an *empty* baseline. Baselined spans are dropped
    # before matching, so they never reach `keyed_hashes`; scanning with the old
    # baseline and then replacing the file would silently un-grandfather every
    # span already in it (observed: a re-seed cut 90 tracked hashes to 0 of the
    # originals and the gate went red on spans it had previously accepted).
    baseline = load_baseline(base_dir) if use_baseline else {}
    tracked = build_tracked_index(base_dir)
    resolution_cache: dict[str, str | None] = {}
    all_findings: list[EvidenceFinding] = []
    all_hashes: dict[str, set[str]] = {}
    cache = load_verdict_cache(base_dir, max_revisions=max_revisions)
    index = HistoryIndex(base_dir)
    # One whole-history pass up front: at corpus scale every artifact would
    # promote the narrow path anyway, and doing it once keeps the per-artifact
    # cost to a dict lookup. Skipped entirely when no ref has moved since the
    # cache was written — then every not-found entry is still valid on its
    # working-tree fingerprint alone.
    if not cache.refs_unchanged:
        index.ensure_full()
    with ArtifactMatcher(
        base_dir, index, max_revisions=max_revisions, verdict_cache=cache
    ) as matcher:
        for rel in _tracked_issue_files(base_dir, issues_base_dir):
            findings, hashes = scan_file(
                base_dir,
                base_dir / rel,
                config,
                rel_path=rel,
                baseline=baseline,
                matcher=matcher,
                tracked=tracked,
                resolution_cache=resolution_cache,
            )
            all_findings.extend(findings)
            for k, v in hashes.items():
                all_hashes.setdefault(k, set()).update(v)
    write_verdict_cache(base_dir, cache, tracked=tracked)
    return all_findings, all_hashes


@dataclass
class _WorkerState:
    """Per-process scan state, built once by the pool initializer."""

    base_dir: Path
    config: object
    matcher: ArtifactMatcher
    tracked: frozenset[str]
    baseline: dict[str, set[str]]
    resolution_cache: dict[str, str | None]


_WORKER: _WorkerState | None = None


def _worker_init(
    base_dir: Path,
    tracked: frozenset[str],
    baseline: dict[str, set[str]],
    index_data: dict[str, tuple[str, ...]],
    max_revisions: int,
) -> None:
    """Build one config/matcher/resolution-cache per *worker*, not per file.

    The previous implementation constructed both per file, which collapsed the
    artifact-major memo to a single file's scope and did roughly 2.4x more git
    work than the serial path — the pool made seeding slower, not faster. It
    also pickled the whole tracked-file frozenset into every task; everything
    here is pickled once per worker instead.
    """
    global _WORKER
    import atexit

    from little_loops.config import BRConfig

    matcher = ArtifactMatcher(
        base_dir,
        HistoryIndex.from_data(base_dir, index_data),
        max_revisions=max_revisions,
    )
    atexit.register(matcher.close)
    _WORKER = _WorkerState(
        base_dir=base_dir,
        config=BRConfig(base_dir),
        matcher=matcher,
        tracked=tracked,
        baseline=baseline,
        resolution_cache={},
    )


def _scan_chunk_worker(
    rels: list[Path],
) -> tuple[list[EvidenceFinding], dict[str, set[str]]]:
    """Scan a chunk of files against the shared per-worker state."""
    state = _WORKER
    assert state is not None, "pool initializer did not run"
    findings: list[EvidenceFinding] = []
    hashes: dict[str, set[str]] = {}
    for rel in rels:
        file_findings, file_hashes = scan_file(
            state.base_dir,
            state.base_dir / rel,
            state.config,
            rel_path=rel,
            baseline=state.baseline,
            matcher=state.matcher,
            tracked=state.tracked,
            resolution_cache=state.resolution_cache,
        )
        findings.extend(file_findings)
        for key, value in file_hashes.items():
            hashes.setdefault(key, set()).update(value)
    return findings, hashes


def _safe_worker_count(requested: int | None) -> int:
    """Worker count, forced to 1 under pytest.

    A nested process pool multiplies against pytest-xdist workers, so the
    in-test path stays single-process regardless of what was requested — the
    CLI runs as a subprocess of the gate test and inherits pytest's
    environment. This makes the constraint structural rather than a matter of
    call-site discipline.
    """
    import os

    if any(
        os.environ.get(var)
        for var in ("PYTEST_CURRENT_TEST", "PYTEST_XDIST_WORKER", "PYTEST_VERSION")
    ):
        return 1
    if requested is not None:
        return max(1, requested)
    return max(1, min(8, os.cpu_count() or 2))


def scan_all_parallel(
    base_dir: Path,
    issues_base_dir: str,
    *,
    workers: int | None = None,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
    chunk_size: int = 64,
    use_baseline: bool = True,
) -> tuple[list[EvidenceFinding], dict[str, set[str]]]:
    """Parallel form of :func:`scan_all`, for one-time baseline seeding only.

    Implementation Steps step 4: the git calls are read-only and safe under a
    process pool, but the pool must stay out of the pytest path (a nested
    pool multiplies against pytest-xdist workers) — this is called only from
    ``--all --update-baseline``, never from the plain ``--all`` gate check,
    and :func:`_safe_worker_count` enforces that even if it were.
    """
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool

    from little_loops.config import BRConfig

    baseline = load_baseline(base_dir) if use_baseline else {}
    tracked = build_tracked_index(base_dir)
    rels = _tracked_issue_files(base_dir, issues_base_dir)
    all_findings: list[EvidenceFinding] = []
    all_hashes: dict[str, set[str]] = {}

    # Build the index once in the parent: N workers each running `git log
    # --all --raw` concurrently would serialize on the object store anyway.
    index = HistoryIndex(base_dir)
    index.ensure_full()
    index_data = index.as_data()

    n_workers = _safe_worker_count(workers)
    if n_workers == 1:
        return scan_all(
            base_dir,
            BRConfig(base_dir),
            issues_base_dir,
            max_revisions=max_revisions,
            use_baseline=use_baseline,
        )

    chunks = [rels[i : i + chunk_size] for i in range(0, len(rels), chunk_size)]
    # `spawn` is explicit: deterministic across macOS/Linux, and it keeps the
    # parent's open session-store sqlite handle from being inherited.
    ctx = multiprocessing.get_context("spawn")
    try:
        with ProcessPoolExecutor(
            max_workers=n_workers,
            mp_context=ctx,
            initializer=_worker_init,
            initargs=(base_dir, tracked, baseline, index_data, max_revisions),
        ) as executor:
            # `map`, not `as_completed`: restores deterministic finding order.
            for findings, hashes in executor.map(_scan_chunk_worker, chunks):
                all_findings.extend(findings)
                for k, v in hashes.items():
                    all_hashes.setdefault(k, set()).update(v)
    except BrokenProcessPool:
        # A worker that dies during startup (an embedded/`spawn`-hostile
        # `__main__`, an OOM kill) must degrade to the serial path rather than
        # leave the caller waiting — this tool's whole failure history is
        # hangs, not crashes.
        return scan_all(
            base_dir,
            BRConfig(base_dir),
            issues_base_dir,
            max_revisions=max_revisions,
            use_baseline=use_baseline,
        )
    return all_findings, all_hashes


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_text_report(findings: list[EvidenceFinding]) -> str:
    if not findings:
        return "ll-verify-evidence: PASS — no unverifiable evidence spans"
    lines = [f"ll-verify-evidence: {len(findings)} finding(s)", ""]
    for f in findings:
        lines.append(f"  {f.issue_path}:{f.line}: [{f.section}] quoted, attributed to {f.artifact}")
        lines.append(f"      “{f.span.strip()}” — not found in any revision of {f.artifact}")
    lines.append("")
    lines.append(
        "An evidence quote must exist in the artifact it is attributed to. Fix the "
        "quote, correct the attribution, or suppress a reviewed counter-example with "
        "'<!-- ll-evidence-ok: reason -->' on the line or the one above."
    )
    return "\n".join(lines)


def _findings_to_json(findings: list[EvidenceFinding], mode: str) -> dict:
    return {
        "ok": not findings,
        "mode": mode,
        "count": len(findings),
        "findings": [
            {
                "file": str(f.issue_path),
                "line": f.line,
                "section": f.section,
                "span": f.span,
                "artifact": f.artifact,
            }
            for f in findings
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main_verify_evidence(argv: list[str] | None = None) -> int:
    """Entry point for ``ll-verify-evidence``.

    Returns 0 when clean, 1 on any unsuppressed finding (changed-files /
    added-only mode) or any finding beyond baseline (``--all``).
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-evidence", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-evidence",
            description=(
                "Certify that quoted evidence attributed to a named artifact (file path "
                "or issue ID) actually exists there, at HEAD, in the working tree, or in "
                "any git revision (BUG-3282)."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""\
Examples:
  %(prog)s FILE...                     # Gate specific issue files (skill / hook)
  %(prog)s --added-only FILE...        # Only lines the staged diff adds (pre-commit)
  %(prog)s --all                       # Full scan of issues.base_dir vs. baseline
  %(prog)s --all --update-baseline     # Re-record the grandfathered corpus
  %(prog)s --all --json                # Machine-readable output

Suppress a reviewed counter-example (a quote reported *because* it is
fabricated) on the matching line or the one above:
  <!-- ll-evidence-ok: reason -->

Exit codes:
  0 - Clean (or no findings beyond baseline under --all)
  1 - One or more unsuppressed findings
""",
        )
        parser.add_argument(
            "paths",
            nargs="*",
            type=Path,
            help="Issue files to scan (changed-files mode). Omit with --all.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Scan every tracked issue file, comparing against the baseline.",
        )
        parser.add_argument(
            "--update-baseline",
            action="store_true",
            help="Rewrite the baseline from the current full scan (requires --all).",
        )
        parser.add_argument(
            "--added-only",
            action="store_true",
            help=(
                "Report only spans on lines added in the staged diff. Used by the "
                "pre-commit gate. Incompatible with --all."
            ),
        )
        parser.add_argument(
            "--max-revisions",
            type=int,
            default=DEFAULT_MAX_REVISIONS,
            metavar="N",
            help=(
                f"Newest-first revisions searched per artifact (default: "
                f"{DEFAULT_MAX_REVISIONS}). Higher is more thorough and slower."
            ),
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Project root to scan (default: cwd)",
        )
        add_json_arg(parser)

        args = parser.parse_args(argv)

        if args.update_baseline and not args.all:
            parser.error("--update-baseline requires --all")
        if args.added_only and args.all:
            parser.error("--added-only applies to changed-files mode, not --all")
        if not args.all and not args.paths:
            parser.error("provide one or more paths, or use --all")

        configure_output()
        logger = Logger(use_color=use_color_enabled())
        base_dir = args.directory or Path.cwd()

        from little_loops.config import BRConfig

        config = BRConfig(base_dir)

        if args.all:
            mode = "all"
            issues_base_dir = config.issues.base_dir
            if args.update_baseline:
                # Seeding is one-time and safe to parallelize (read-only git);
                # the steady-state gate path below stays serial and out of
                # the pool (Implementation Steps step 4).
                findings, hashes = scan_all_parallel(
                    base_dir,
                    issues_base_dir,
                    max_revisions=args.max_revisions,
                    use_baseline=False,
                )
            else:
                findings, hashes = scan_all(
                    base_dir, config, issues_base_dir, max_revisions=args.max_revisions
                )
            if args.update_baseline:
                write_baseline(base_dir, hashes)
                logger.success(f"Baseline updated: {BASELINE_PATH} ({len(findings)} occurrence(s))")
                return 0
            reported = findings
        else:
            mode = "paths"
            reported = scan_paths(
                base_dir,
                args.paths,
                config,
                added_only=args.added_only,
                max_revisions=args.max_revisions,
            )

        if args.json:
            print_json(_findings_to_json(reported, mode))
            return 1 if reported else 0

        print(_format_text_report(reported))
        if reported:
            logger.error(f"{len(reported)} unverifiable evidence finding(s)")
            return 1
        logger.success("No unverifiable evidence spans")
        return 0
