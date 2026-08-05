"""CLI-flag claim extractor (FEAT-3048).

Peer of :mod:`little_loops.issues.prose_deps` /
:mod:`little_loops.issues.symbol_claims`: fence-aware, regex-based, extended
to a third claim class — a backticked ``ll-<tool> <subcommand> [--flag ...]``
invocation. Grammar (§ Claim Grammar): ``ll-<tool>`` must be a registered
console script (checked by the resolver, not here); subcommand and each long
flag are checked independently; short flags are ignored (ambiguous in
prose — ``-a`` collides across tools).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from little_loops.text_utils import _CODE_FENCE

_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")
# Subcommand is required for a match (a bare `ll-<tool>` is not a claim — see
# extract_cli_flag_claims). Short flags (`-a`) are tolerated inline but never
# captured — _FLAG_RE below only pulls the `--long` tokens out of group 3.
_CLI_INVOCATION_RE = re.compile(
    r"^(ll-[a-z0-9-]+)\s+([a-z][a-z0-9-]*)((?:\s+(?:--[a-z][a-z0-9-]*|-[a-z]))*)\s*$"
)
_FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")

# <!-- ll-prose-ok: ... --> suppression convention (mirrors symbol_claims.py
# / cli/verify_skill_prose.py's _SUPPRESS_RE).
_SUPPRESS_RE = re.compile(r"<!--\s*ll-prose-ok:\s*(.+?)\s*-->")


@dataclass(frozen=True)
class CliFlagClaim:
    """One ``ll-<tool> <subcommand> [--flag ...]`` claim extracted from a body."""

    tool: str
    subcommand: str
    flags: tuple[str, ...]
    raw: str


def _in_fence(start: int, end: int, fence_spans: list[tuple[int, int]]) -> bool:
    return any(fs <= start and end <= fe for fs, fe in fence_spans)


def _is_suppressed(body: str, match_start: int) -> bool:
    line_start = body.rfind("\n", 0, match_start) + 1
    if line_start == 0:
        return False
    prev_newline_pos = line_start - 1
    prev_line_start = body.rfind("\n", 0, prev_newline_pos) + 1
    preceding = body[prev_line_start:prev_newline_pos]
    return bool(_SUPPRESS_RE.search(preceding))


def extract_cli_flag_claims(body: str) -> set[CliFlagClaim]:
    """Extract ``ll-<tool> <subcommand> [--flag ...]`` claims from an issue body.

    A backticked span with a tool name but no subcommand (bare ``` `ll-issues` ```)
    is not a claim — there is nothing to verify beyond registration, which
    ``ll-verify-cli-allowlist`` already covers.

    Args:
        body: Issue markdown body.

    Returns:
        A set of :class:`CliFlagClaim`.
    """
    if not body:
        return set()

    fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(body)]
    claims: set[CliFlagClaim] = set()

    for m in _BACKTICK_SPAN_RE.finditer(body):
        if _in_fence(m.start(), m.end(), fence_spans):
            continue
        if _is_suppressed(body, m.start()):
            continue
        text = m.group(1).strip()
        cm = _CLI_INVOCATION_RE.match(text)
        if not cm:
            continue
        tool, subcommand, flags_part = cm.group(1), cm.group(2), cm.group(3)
        if not subcommand:
            continue
        flags = tuple(sorted(set(_FLAG_RE.findall(flags_part or ""))))
        claims.add(CliFlagClaim(tool=tool, subcommand=subcommand, flags=flags, raw=text))

    return claims
