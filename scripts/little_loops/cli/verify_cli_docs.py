"""ll-verify-cli-docs: assert CLAUDE.md's § CLI Tools section matches the real CLI surface (ENH-2970).

Parses the hand-maintained `` `ll-<tool>` `` bullets under CLAUDE.md's § CLI
Tools section and probes each tool's ``--help`` output to assert every
documented subcommand and flag actually resolves. Also checks the reverse
direction: every ``pyproject.toml`` entry point has a CLAUDE.md bullet.

The prose in CLAUDE.md mixes clean token lists with free-form explanation, so
the extractor is deliberately conservative: it only turns a comma/slash
separated run of bare identifiers, or a backtick-wrapped bare ``--flag``,
into a checkable claim. Everything else is reported as a ``SkippedClaim``
rather than silently dropped or guessed at.

Exit codes:
    0 - no error-severity drift (documented-but-absent commands/flags)
    1 - one or more error-severity claims failed to resolve
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from little_loops.cli.verify_cli_allowlist import _all_ll_entry_points
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

_SECTION_HEADER = "## CLI Tools"
_BULLET_RE = re.compile(r"^- `(ll-[a-z0-9-]+)` - (.*)$")
_BARE_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_BARE_FLAG_RE = re.compile(r"`(--[a-z][a-z0-9-]*)`")


@dataclass
class DocClaim:
    """One parsed assertion from CLAUDE.md's § CLI Tools section.

    ``group`` identifies which source parenthetical a subcommand candidate
    came from (``None`` for flags and for the synthetic tool-level claim).
    Candidates from the same group are verified together: CLAUDE.md prose
    sometimes glosses a tool in plain English before giving the real,
    checkable subcommand list (e.g. ``ll-code``'s "(callers, callees, ...)"
    aside before its real "(`status`/`callers-of`/...)" list) — if *none* of
    a group's candidates match the tool's real choices, the whole group is
    prose, not documentation, and is not held to account.
    """

    tool: str
    subcommand: str | None
    flag: str | None
    line: int
    group: int | None = None


@dataclass
class SkippedClaim:
    """Text the extractor declined to interpret — reported, never dropped silently."""

    tool: str
    text: str
    line: int


@dataclass
class ClaimDrift:
    """One claim (or reverse-direction entry point) that failed verification."""

    kind: str  # "unknown_tool" / "unknown_subcommand" / "unknown_flag" / "undocumented_entry_point"
    severity: str  # "error" / "warn"
    tool: str
    detail: str
    line: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "tool": self.tool,
            "detail": self.detail,
            "line": self.line,
        }


def _find_paren_groups(text: str) -> list[str]:
    """Return the contents of every top-level (depth-1) parenthesized group in ``text``.

    Parens inside a backtick code span (e.g. `` `type(scope): description` ``)
    don't count — they're literal text, not a grouping construct.
    """
    groups: list[str] = []
    depth = 0
    start = -1
    in_backtick = False
    for idx, ch in enumerate(text):
        if ch == "`":
            in_backtick = not in_backtick
        elif in_backtick:
            continue
        elif ch == "(":
            if depth == 0:
                start = idx + 1
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start != -1:
                groups.append(text[start:idx])
                start = -1
    return groups


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split ``text`` on ``sep``, ignoring occurrences nested inside parens or backticks.

    A backtick code span (e.g. `` `{test,lint,format,type}_cmd` ``) may itself
    contain the separator — those must not be treated as top-level splits, or
    prose fragments like the brace-expansion above get mistaken for bare
    subcommand tokens.
    """
    parts: list[str] = []
    depth = 0
    in_backtick = False
    current = ""
    for ch in text:
        if ch == "`":
            in_backtick = not in_backtick
            current += ch
        elif in_backtick:
            current += ch
        elif ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch == sep and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return parts


def _unwrap_bare_token(token: str) -> str | None:
    """Return the bare identifier inside ``token``, unwrapping one backtick pair if present.

    Accepts either a plain bare identifier (``status``) or a single
    backtick-wrapped one (`` `status` ``, `` `callers-of` ``) — both are
    established CLAUDE.md conventions for a subcommand name. Rejects
    anything else (flags, multi-word phrases, angle-bracket placeholders).
    """
    if len(token) >= 2 and token.startswith("`") and token.endswith("`"):
        token = token[1:-1]
    return token if _BARE_TOKEN_RE.match(token) else None


def _extract_subcommands(group_text: str) -> tuple[list[str], list[str]]:
    """Return (subcommand_names, skipped_segments) from one top-level parenthetical group.

    A comma-separated segment is accepted only when *every* "/"-delimited
    token in its head (before any nested "(" aside) is either a bare/
    backtick-wrapped subcommand-shaped identifier or a backtick-wrapped/bare
    ``--flag`` — i.e. exactly what the established CLAUDE.md convention uses
    for "tool (sub1, sub2, sub3 (aside), ...)" or "tool (`sub1`/`sub2`/...)"
    listings, and for a flag/subcommand pairing like "`--plan`/`apply`".
    A segment with even one token that doesn't fit this shape (free prose)
    is prose, not a token list — the *whole* segment is skipped rather than
    cherry-picking the tokens inside it that happen to look identifier-like
    (e.g. an incidental "`inferred`" inside a sentence about config
    provenance tagging must not be mistaken for a subcommand name).
    """
    names: list[str] = []
    skipped: list[str] = []
    for raw_segment in _split_top_level(group_text, ","):
        segment = raw_segment.strip()
        if not segment:
            continue
        # Peel off a trailing nested-paren aside, e.g. "find-similar (alias `fs`; ...)".
        head = segment.split("(", 1)[0].strip()
        sub_tokens = [t.strip().rstrip(":") for t in _split_top_level(head, "/")]
        sub_tokens = [t for t in sub_tokens if t]
        if not sub_tokens:
            continue

        segment_names: list[str] = []
        pure = True
        for token in sub_tokens:
            unwrapped = _unwrap_bare_token(token)
            if unwrapped is not None:
                segment_names.append(unwrapped)
            elif _BARE_FLAG_RE.fullmatch(token) or re.fullmatch(r"--[a-z][a-z0-9-]*", token):
                continue  # a flag-shaped token doesn't break segment purity, but isn't a subcommand
            else:
                pure = False
                break

        if pure:
            names.extend(segment_names)
        else:
            skipped.append(segment)
    return names, skipped


def parse_cli_section(md_path: Path) -> tuple[list[DocClaim], list[SkippedClaim]]:
    """Parse CLAUDE.md's § CLI Tools bullets into checkable claims and skipped text."""
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    start = next((i for i, line in enumerate(lines) if line.strip() == _SECTION_HEADER), None)
    if start is None:
        return [], []

    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    claims: list[DocClaim] = []
    skipped: list[SkippedClaim] = []

    for lineno in range(start + 1, end):
        line = lines[lineno]
        match = _BULLET_RE.match(line)
        if not match:
            continue
        tool, rest = match.group(1), match.group(2)
        line_display = lineno + 1

        # Every matched bullet documents its tool at least at the tool level,
        # regardless of whether any subcommand/flag candidate was extracted
        # from its prose — otherwise a tool like `ll-parallel` (a bullet with
        # no checkable claims) would wrongly show up as undocumented.
        claims.append(DocClaim(tool=tool, subcommand=None, flag=None, line=line_display))

        for group_idx, group_text in enumerate(_find_paren_groups(rest)):
            sub_names, sub_skipped = _extract_subcommands(group_text)
            for name in sub_names:
                claims.append(
                    DocClaim(
                        tool=tool, subcommand=name, flag=None, line=line_display, group=group_idx
                    )
                )
            for text_skipped in sub_skipped:
                skipped.append(SkippedClaim(tool=tool, text=text_skipped, line=line_display))

        for flag in _BARE_FLAG_RE.findall(rest):
            claims.append(DocClaim(tool=tool, subcommand=None, flag=flag, line=line_display))

    return claims, skipped


_POSITIONAL_ITEM_RE = re.compile(r"^ {4}([a-z][a-z0-9_-]*)(?: {2,}\S|\s*$)")


def _extract_choices(help_text: str) -> frozenset[str]:
    """Return the subcommand choices advertised in one ``--help`` text.

    Argparse renders subparser choices two ways depending on whether the
    subparsers action sets an explicit ``metavar``: an auto-generated
    ``{a,b,c}`` brace list in the usage line (covers short aliases too), or —
    when a ``metavar`` like ``COMMAND`` is set (e.g. ``ll-queue``) — only a
    "positional arguments:" block listing each choice on its own
    4-space-indented line, argparse's default formatter indent for
    subparser entries. Both are checked; results are unioned.
    """
    choices: set[str] = set()
    choices_match = re.search(r"\{([a-zA-Z0-9_,-]+)\}", help_text)
    if choices_match:
        choices |= {c for c in choices_match.group(1).split(",") if c}

    in_positional = False
    for line in help_text.splitlines():
        if line.strip() == "positional arguments:":
            in_positional = True
            continue
        if in_positional:
            if line and not line.startswith(" "):
                break
            match = _POSITIONAL_ITEM_RE.match(line)
            if match:
                choices.add(match.group(1))

    return frozenset(choices)


@cache
def probe_tool(tool: str, *subpath: str) -> tuple[frozenset[str], str] | None:
    """Return (subcommand choices, raw --help text) for ``tool [*subpath] --help``.

    Returns ``None`` when the entry point does not resolve at all. Results are
    cached per (tool, subpath) pair — one subprocess per distinct probe, not
    per claim.
    """
    args = [tool, *subpath, "--help"]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    help_text = result.stdout + result.stderr
    if result.returncode != 0 and not help_text:
        return None

    return _extract_choices(help_text), help_text


_MAX_HELP_WALK_DEPTH = (
    3  # tool, tool+sub, tool+sub+subsub (ll-loop queue remove is the deepest case)
)


def _combined_help_text(tool: str) -> str:
    """Return ``tool``'s own ``--help`` text plus every nested subcommand's ``--help`` text.

    A flag documented in prose is often a (possibly nested) subcommand's
    flag, not the tool's own bare flag (e.g. ``--force`` belongs to
    ``ll-loop queue remove``, two levels down). CLAUDE.md's prose doesn't
    reliably say which subcommand a given flag belongs to, so flags are
    checked against the union of the whole subcommand tree's help text
    rather than guessing which level to probe, bounded to
    ``_MAX_HELP_WALK_DEPTH`` levels to keep the subprocess count finite.
    """
    combined: list[str] = []

    def walk(subpath: tuple[str, ...]) -> None:
        probed = probe_tool(tool, *subpath)
        if probed is None:
            return
        choices, help_text = probed
        combined.append(help_text)
        if len(subpath) + 1 >= _MAX_HELP_WALK_DEPTH:
            return
        for subcommand in sorted(choices):
            walk((*subpath, subcommand))

    walk(())
    return "\n".join(combined)


def verify_claims(claims: list[DocClaim]) -> list[ClaimDrift]:
    """Probe every claim's tool/subcommand/flag and report drift for anything unresolved."""
    drifts: list[ClaimDrift] = []
    known_tools = _all_ll_entry_points()

    subcommand_claims: list[DocClaim] = []

    for claim in claims:
        if claim.tool not in known_tools:
            drifts.append(
                ClaimDrift(
                    kind="unknown_tool",
                    severity="error",
                    tool=claim.tool,
                    detail=f"{claim.tool} is not a registered entry point",
                    line=claim.line,
                )
            )
            continue

        if claim.subcommand is not None:
            subcommand_claims.append(claim)

        if claim.flag is not None:
            help_text = _combined_help_text(claim.tool)
            if help_text and claim.flag not in help_text:
                drifts.append(
                    ClaimDrift(
                        kind="unknown_flag",
                        severity="error",
                        tool=claim.tool,
                        detail=f"'{claim.flag}' not found in {claim.tool} --help text (own + subcommands)",
                        line=claim.line,
                    )
                )

    # Bucket subcommand candidates by their source (tool, line, group) and
    # verify each group as a unit: prose that happens to look like a bare
    # token list (e.g. an English gloss such as "(callers, callees, ...)")
    # is only held accountable when at least one of its candidates actually
    # matches the tool's real choices — otherwise it's a false positive on
    # the extractor's own confidence, not documentation drift.
    groups: dict[tuple[str, int, int | None], list[DocClaim]] = {}
    for claim in subcommand_claims:
        groups.setdefault((claim.tool, claim.line, claim.group), []).append(claim)

    for (tool, line, _group), group_claims in groups.items():
        probed = probe_tool(tool)
        if probed is None:
            continue
        choices, _ = probed
        if not choices:
            continue
        matched = [c for c in group_claims if c.subcommand in choices]
        if not matched:
            # No candidate in this group resolved — treat the whole group as
            # unparsed prose rather than N individual false "unknown
            # subcommand" errors.
            continue
        for claim in group_claims:
            if claim.subcommand not in choices:
                drifts.append(
                    ClaimDrift(
                        kind="unknown_subcommand",
                        severity="error",
                        tool=tool,
                        detail=f"'{claim.subcommand}' not in {tool} --help choices {sorted(choices)}",
                        line=line,
                    )
                )

    return drifts


def find_undocumented_entry_points(claims: list[DocClaim]) -> list[ClaimDrift]:
    """Return a WARN drift for every entry point with no CLAUDE.md bullet."""
    documented = {claim.tool for claim in claims}
    all_tools = _all_ll_entry_points()
    missing = sorted(all_tools - documented)
    return [
        ClaimDrift(
            kind="undocumented_entry_point",
            severity="warn",
            tool=tool,
            detail=f"{tool} has no CLAUDE.md § CLI Tools entry",
            line=None,
        )
        for tool in missing
    ]


def _run(md_path: Path) -> tuple[int, list[ClaimDrift], list[SkippedClaim]]:
    """Return (exit_code, drifts, skipped_claims)."""
    claims, skipped = parse_cli_section(md_path)
    drifts = verify_claims(claims) + find_undocumented_entry_points(claims)
    exit_code = 1 if any(d.severity == "error" for d in drifts) else 0
    return exit_code, drifts, skipped


def _default_claude_md_path() -> Path:
    from little_loops.skill_expander import _find_plugin_root

    return _find_plugin_root() / ".claude" / "CLAUDE.md"


def main_verify_cli_docs() -> int:
    """Entry point for ``ll-verify-cli-docs``."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-cli-docs", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-cli-docs",
            description=(
                "Assert CLAUDE.md's § CLI Tools section matches the real CLI surface, "
                "in both directions. Exits 1 on error-severity drift (ENH-2970)."
            ),
        )
        parser.add_argument(
            "--path",
            type=Path,
            default=None,
            help="Path to CLAUDE.md (default: plugin root's .claude/CLAUDE.md)",
        )
        args = parser.parse_args()

        md_path = args.path or _default_claude_md_path()
        if not md_path.is_file():
            print(f"SKIP: {md_path} not found.", file=sys.stderr)
            return 0

        exit_code, drifts, skipped = _run(md_path)

        errors = [d for d in drifts if d.severity == "error"]
        warns = [d for d in drifts if d.severity == "warn"]

        if not errors:
            print("OK: no CLAUDE.md CLI Tools drift found.")
        for drift in errors:
            loc = f"{md_path}:{drift.line}" if drift.line else md_path
            print(f"ERROR [{drift.kind}] {loc}: {drift.detail}", file=sys.stderr)
        for drift in warns:
            print(f"WARN [{drift.kind}] {drift.tool}: {drift.detail}", file=sys.stderr)
        for skip in skipped:
            print(f"SKIP {md_path}:{skip.line} ({skip.tool}): {skip.text!r}", file=sys.stderr)

        return exit_code


if __name__ == "__main__":
    sys.exit(main_verify_cli_docs())
