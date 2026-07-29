"""Deterministic specificity validator for a `## Program Design` section (ENH-2852 spike).

Proves the net-new half of the gate: classifying a free-text section body as
specific (real signature-shaped lines + at least one repo-resolvable call-path
anchor) or non-specific (prose), with new identifiers required only to be
*shaped*, never resolvable.

The resolver is injected so the shape-parsing algorithm is testable without a
repo, and provably works against a real one (`git_grep_resolver`).
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Resolver = Callable[[str], bool]

# A type expression: dotted/bracketed/union tokens, no bare spaces.
# Subscripts nest one level (`dict[str, list[int]]`) — flat `[^\]]*` stops at the
# inner bracket and rejects legitimate generics.
_SUBSCRIPT = r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]"
_TYPE = r"[\w.]+(?:" + _SUBSCRIPT + r")?(?:\s*\|\s*[\w.]+(?:" + _SUBSCRIPT + r")?)*"

# Leading bullet + optional backtick fence, trailing backtick + punctuation.
_LEAD = r"^[ \t]*(?:[-*+][ \t]+)?`?"
_TAIL = r"`?[ \t]*[.:;]?[ \t]*$"

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

# A parameter list is signature-like only if every entry is an identifier,
# optionally annotated/defaulted — never an English clause.
_PARAM = re.compile(
    r"^[ \t]*(?:\*{0,2})[A-Za-z_]\w*"
    r"(?:[ \t]*:[ \t]*" + _TYPE + r")?"
    r"(?:[ \t]*=[ \t]*\S+)?[ \t]*$"
)

_SUBSECTION = re.compile(r"^[ \t]*#{2,6}[ \t]*(?P<title>.+?)[ \t]*#*[ \t]*$")
_BOLD_SUBSECTION = re.compile(r"^[ \t]*\*\*(?P<title>[^*]+?):?\*\*[ \t]*$")

_BACKTICKED = re.compile(r"`([^`]+)`")
_IDENT = re.compile(r"^[A-Za-z_][\w.]*$")

_CHAIN_SPLIT = re.compile(r"->|→|=>")


@dataclass(frozen=True)
class DesignVerdict:
    """Outcome of grading one `## Program Design` body."""

    signatures: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    is_specific: bool = False
    reasons: list[str] = field(default_factory=list)


def _params_are_signature_like(params: str) -> bool:
    stripped = params.strip()
    if not stripped:
        return True
    return all(_PARAM.match(part) for part in stripped.split(","))


def parse_signature_lines(body: str) -> list[str]:
    """Return lines from *body* that are signature- or field-shaped.

    Whole-line anchored: an English sentence that merely contains parentheses or
    a colon does not match, which is what keeps the gate from being inert.
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


def _call_path_body(body: str) -> str:
    """Return only the `Call Path` subsection of *body* (empty when absent)."""
    lines = body.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        heading = _SUBSECTION.match(line) or _BOLD_SUBSECTION.match(line)
        if heading:
            title = heading.group("title").strip().rstrip(":").lower()
            inside = title == "call path"
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def extract_call_path_anchors(body: str) -> list[str]:
    """Return candidate anchor identifiers named in the `Call Path` subsection."""
    section = _call_path_body(body)
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
    """True when *symbol* is defined somewhere in the repo.

    Mirrors ``FallbackProvider.defines_scan_for``: a word-boundary git grep
    filtered to lines that actually open a definition.
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
        stripped = text.strip()
        if stripped.startswith(openers):
            return True
    return False


def grade_program_design(body: str, resolver: Resolver) -> DesignVerdict:
    """Grade a `## Program Design` body as specific or not.

    Specific iff it carries at least one signature-shaped line **and** at least
    one call-path anchor that resolves against the repo. Newly-introduced
    identifiers are never required to resolve — only the anchors the new code
    hooks into are.
    """
    if not body or not body.strip():
        return DesignVerdict(is_specific=False, reasons=["section is empty"])

    signatures = parse_signature_lines(body)
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
