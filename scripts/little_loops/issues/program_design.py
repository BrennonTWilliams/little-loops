"""Deterministic specificity grading for an issue's ``## Program Design`` section (ENH-2852).

The refinement chain names *which files* a change touches, but nothing required an
issue to name the concrete types, signatures, and call path before implementation.
This module is the mechanical half of that gate: it classifies a ``## Program Design``
body as **specific** (real signature-shaped lines plus at least one repo-resolvable
call-path anchor) or **non-specific** (prose), with no LLM involved.

Two contracts are load-bearing:

* **Resolution-indifference for new identifiers.** Only anchors named in the
  ``Call Path`` subsection carry a resolution *requirement*. Everything else is graded
  on shape alone, and a new identifier that *happens* to resolve — because its code
  landed between refinement and the gate re-check, or because the name collides with an
  existing symbol — must never flip the verdict. (Excluding "symbols defined in the
  diff" is not an option: at format-check time no diff exists yet.)
* **Fail open.** The cutoff lives in a per-project ``.ll/program-design-cutover.json``
  stamp. Absent or unparseable, the gate is off entirely — every downstream install and
  fresh ``ll-init`` project starts unstamped, and mass-deferring their backlog on
  upgrade is not acceptable. Arming the gate is writing the stamp.

Consumed by :func:`little_loops.issue_parser.check_format_gaps`, so every consumer of
the gap set (``ll-issues format-check``, ``rn-remediate.yaml``'s ``ensure_formatted``,
``ll-issues sequence`` drift detection) inherits both the check and the exemption from
one place.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

# moved to little_loops.paths (ENH-2924)
from little_loops.paths import find_project_root  # noqa: F401

logger = logging.getLogger(__name__)

#: Injected repo-resolution predicate: ``symbol -> is defined somewhere in the repo``.
Resolver = Callable[[str], bool]

#: Filename of the per-project cutover stamp, resolved under ``.ll/``.
CUTOVER_STAMP_NAME = "program-design-cutover.json"

#: The section this module grades, and the subsections its evidence is read from.
SECTION_TITLE = "Program Design"
DESIGN_SUBSECTIONS = ("types", "signatures", "call path")

# A type expression: dotted/bracketed/union tokens, no bare spaces.
# Subscripts nest one level (`dict[str, list[int]]`) — a flat `[^\]]*` stops at the
# inner bracket and would reject any realistic return type.
_SUBSCRIPT = r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]"
_TYPE = r"[\w.]+(?:" + _SUBSCRIPT + r")?(?:\s*\|\s*[\w.]+(?:" + _SUBSCRIPT + r")?)*"

# Leading bullet + optional backtick fence, trailing backtick + punctuation.
_LEAD = r"^[ \t]*(?:[-*+][ \t]+)?`?"
# Trailing backtick, optional punctuation, and an optional separator-delimited
# description clause (` — does a thing`). The separator is mandatory for the
# description branch so a bare sentence containing parens still fails to match.
_TAIL = r"`?[ \t]*[.:;]?[ \t]*(?:(?:—|--|–|:)[ \t]*\S.*)?$"

# Call-shaped: `def foo(a: int) -> Bar`, `Class.method(self, x)`, `foo() -> None`.
_SIG_CALL = re.compile(
    _LEAD + r"(?:async[ \t]+)?(?:def[ \t]+)?"
    r"(?P<name>[A-Za-z_][\w.]*)[ \t]*"
    r"\((?P<params>[^()]*)\)"
    r"(?:[ \t]*->[ \t]*" + _TYPE + r")?" + _TAIL
)

# Dataclass/field-shaped: `sha: str`, `entries: list[CodeRef]`.
_SIG_FIELD = re.compile(
    _LEAD + r"(?P<name>[A-Za-z_]\w*)[ \t]*:[ \t]*(?P<type>" + _TYPE + r")" + _TAIL
)

# A parameter list is signature-like only if every entry is an identifier, optionally
# annotated/defaulted — never an English clause. This is what keeps the gate honest:
# without it, "It returns a verdict (specific or not) to the caller." parses as a call.
# A bare `*` or `/` (keyword-only / positional-only markers) is also accepted.
_PARAM = re.compile(
    r"^[ \t]*(?:[*/]|(?:\*{0,2})[A-Za-z_]\w*"
    r"(?:[ \t]*:[ \t]*" + _TYPE + r")?"
    r"(?:[ \t]*=[ \t]*\S+)?)[ \t]*$"
)

_SUBSECTION = re.compile(r"^[ \t]*#{2,6}[ \t]*(?P<title>.+?)[ \t]*#*[ \t]*$")
_BOLD_SUBSECTION = re.compile(r"^[ \t]*\*\*(?P<title>[^*]+?):?\*\*[ \t]*$")

_BACKTICKED = re.compile(r"`([^`]+)`")
_IDENT = re.compile(r"^[A-Za-z_][\w.]*$")
_CHAIN_SPLIT = re.compile(r"->|→|=>")

# `- `/ll:refine-issue` - 2026-07-27T16:20:16 - `abc.jsonl``
_REFINE_ENTRY = re.compile(
    r"`/ll:refine-issue`[^\n]*?(?P<ts>\d{4}-\d{2}-\d{2})(?:[T ][\d:]+)?",
)


@dataclass(frozen=True)
class DesignVerdict:
    """Outcome of grading one ``## Program Design`` body.

    ``unresolved`` is informational only — a new identifier's resolution status must
    never change :attr:`is_specific` (see the module docstring's resolution-indifference
    contract).
    """

    signatures: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    is_specific: bool = False
    reasons: list[str] = field(default_factory=list)


def _split_top_level(params: str) -> list[str]:
    """Split *params* on commas at bracket/paren/brace depth 0.

    Keeps a parameter annotation's own commas intact — `Literal["x", "y"]` and
    `dict[str, int]` are each one entry, not two. Quoted-string contents never
    perturb depth, mirroring the string-aware brace scan in
    :mod:`little_loops.output.parse`.
    """
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    for i, ch in enumerate(params):
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(params[start:i])
            start = i + 1
    tail = params[start:]
    if tail or parts:
        parts.append(tail)
    if not params.strip():
        return []
    return [stripped for p in parts if (stripped := p.strip())]


def _params_are_signature_like(params: str) -> bool:
    """True when every top-level entry of *params* is an identifier, not prose."""
    stripped = params.strip()
    if not stripped:
        return True
    return all(_PARAM.match(part) for part in _split_top_level(stripped))


def _subsection_title(line: str) -> str | None:
    """Return the normalized title when *line* opens a subsection, else None."""
    heading = _SUBSECTION.match(line) or _BOLD_SUBSECTION.match(line)
    if heading is None:
        return None
    return heading.group("title").strip().rstrip(":").lower()


def _subsection_body(body: str, title: str) -> str:
    """Return the text under the *title* subsection of *body* (empty when absent)."""
    out: list[str] = []
    inside = False
    for line in body.splitlines():
        heading = _subsection_title(line)
        if heading is not None:
            inside = heading == title
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def _evidence_body(body: str) -> str:
    """Return only the parts of *body* that may supply specificity evidence.

    Evidence is read from the ``Types``/``Signatures``/``Call Path`` subsections plus
    any preamble before the first subsection. An appended ``Deviations`` note
    (ENH-2871) is therefore inert: it can neither rescue a prose section nor break a
    valid one.
    """
    lines = body.splitlines()
    parts: list[str] = []
    current: str | None = None  # None == preamble
    for line in lines:
        heading = _subsection_title(line)
        if heading is not None:
            current = heading
            continue
        if current is None or current in DESIGN_SUBSECTIONS:
            parts.append(line)
    return "\n".join(parts)


def parse_signature_lines(body: str) -> list[str]:
    """Return lines from *body* that are signature- or field-shaped.

    Whole-line anchored: an English sentence that merely contains parentheses or a
    colon does not match, which is what keeps the gate from being inert.
    """
    found: list[str] = []
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        call = _SIG_CALL.match(line)
        if call and _params_are_signature_like(call.group("params")):
            found.append(line.strip())
            continue
        fieldish = _SIG_FIELD.match(line)
        if fieldish and not _SUBSECTION.match(line):
            found.append(line.strip())
    return found


def extract_call_path_anchors(body: str) -> list[str]:
    """Return candidate anchor identifiers named in the ``Call Path`` subsection.

    Anchors are read from ``Call Path`` **only** — these are the existing callers and
    types the new code hooks into, and the only identifiers required to resolve.
    """
    section = _subsection_body(body, "call path")
    anchors: list[str] = []

    def _add(token: str) -> None:
        token = token.strip().strip("`*_").rstrip(".,;:")
        if token.endswith("()"):
            token = token[:-2]
        token = token.split("(", 1)[0].strip()
        if not token or not _IDENT.match(token):
            return
        if token not in anchors:
            anchors.append(token)

    for match in _BACKTICKED.finditer(section):
        _add(match.group(1))
    for line in section.splitlines():
        if not _CHAIN_SPLIT.search(line):
            continue
        for part in _CHAIN_SPLIT.split(line):
            _add(part.lstrip("-*+ "))
    return anchors


def _short_symbol(symbol: str) -> str:
    return symbol.rsplit(".", 1)[-1]


def git_grep_resolver(symbol: str, root: Path | None = None) -> bool:
    """True when *symbol* is defined somewhere in the repo rooted at *root*.

    Mirrors :meth:`little_loops.codequery.fallback.FallbackProvider.defines_scan_for`:
    a word-boundary ``git grep`` filtered to lines that actually open a definition.
    Returns False (never raises) when git is unavailable or *root* is not a repo.
    """
    short = _short_symbol(symbol)
    if not short or not _IDENT.match(short):
        return False
    cwd = root or Path.cwd()
    try:
        proc = subprocess.run(
            ["git", "grep", "-n", "-w", "--", short],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    openers = (f"def {short}(", f"async def {short}(", f"class {short}")
    for line in proc.stdout.splitlines():
        _, _, text = line.partition(":")
        _, _, text = text.partition(":")
        if text.strip().startswith(openers):
            return True
    return False


def grade_program_design(body: str, resolver: Resolver) -> DesignVerdict:
    """Grade a ``## Program Design`` body as specific or not.

    Specific iff it carries at least one signature-shaped line **and** at least one
    call-path anchor that resolves against the repo. Newly-introduced identifiers are
    never required to resolve — and their resolving anyway never changes the verdict.

    Args:
        body: Raw text of the section (everything under the ``## Program Design``
            heading, exclusive of it).
        resolver: Predicate answering "is this symbol defined in the repo?".

    Returns:
        A :class:`DesignVerdict`; ``reasons`` is empty exactly when specific.
    """
    if not body or not body.strip():
        return DesignVerdict(is_specific=False, reasons=["section is empty"])

    evidence = _evidence_body(body)
    signatures = parse_signature_lines(evidence)
    anchors = extract_call_path_anchors(body)
    resolved = [a for a in anchors if resolver(a)]
    unresolved = [a for a in anchors if a not in resolved]

    reasons: list[str] = []
    if not signatures:
        reasons.append("no signature-shaped line found in Types/Signatures")
    if not anchors:
        reasons.append("no call-path anchors named in Call Path")
    elif not resolved:
        reasons.append(f"no call-path anchor resolves against the repo: {', '.join(anchors)}")

    return DesignVerdict(
        signatures=signatures,
        anchors=anchors,
        resolved=resolved,
        unresolved=unresolved,
        is_specific=not reasons,
        reasons=reasons,
    )


# --------------------------------------------------------------------- cutover stamp


def _is_true(value: Any) -> bool:
    """True for a YAML-ish truthy scalar.

    ``parse_frontmatter`` is a naive line parser that yields strings, so a raw
    ``is True`` check would silently never fire — the same coercion the ``testable``
    flag uses in :mod:`little_loops.issue_parser`.
    """
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() in ("true", "yes", "1")


def _coerce_date(value: Any) -> date | None:
    """Best-effort ``date`` from a YAML/JSON scalar; None when unparseable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().strip("'\"")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def read_cutover_stamp(root: Path) -> date | None:
    """Return the cutover date from ``<root>/.ll/program-design-cutover.json``.

    Returns None when the stamp is absent, unreadable, not JSON, or carries no
    parseable ``date`` — every one of which means "gate off" (fail open).
    """
    path = root / ".ll" / CUTOVER_STAMP_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return _coerce_date(payload.get("date"))


def issue_design_timestamp(content: str) -> date | None:
    """Return the date an issue was last refined, else its ``discovered_date``.

    The Session Log's most recent ``/ll:refine-issue`` entry takes precedence — that
    is what makes grandfathering reversible per-issue by simply re-refining. Falls back
    to ``discovered_date`` when no entry is present or none parses.
    """
    from little_loops.frontmatter import parse_frontmatter

    refine_dates = [
        parsed
        for match in _REFINE_ENTRY.finditer(content)
        if (parsed := _coerce_date(match.group("ts"))) is not None
    ]
    if refine_dates:
        return max(refine_dates)

    try:
        fm = parse_frontmatter(content)
    except Exception:
        return None
    return _coerce_date(fm.get("discovered_date"))


def program_design_gate_active(issue_path: Path, content: str) -> bool:
    """True when the Program Design gate applies to this issue.

    False (gate off) when: the project has no parseable cutover stamp, the issue opts
    out via ``program_design_not_applicable: true``, or the issue's design timestamp is
    strictly earlier than the stamped date (grandfathered).
    """
    from little_loops.frontmatter import parse_frontmatter

    root = find_project_root(issue_path)
    if root is None:
        return False
    cutover = read_cutover_stamp(root)
    if cutover is None:
        return False

    try:
        fm = parse_frontmatter(content)
    except Exception:
        fm = {}
    if _is_true(fm.get("program_design_not_applicable")):
        return False

    stamp = issue_design_timestamp(content)
    if stamp is not None and stamp < cutover:
        return False
    return True


def grade_issue_section(issue_path: Path, body: str) -> DesignVerdict:
    """Grade *body* using a git-grep resolver rooted at the issue's project root."""
    root = find_project_root(issue_path) or Path.cwd()
    return grade_program_design(body, lambda symbol: git_grep_resolver(symbol, root))
