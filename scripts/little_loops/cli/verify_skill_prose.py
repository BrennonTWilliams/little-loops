"""ll-verify-skill-prose: lint gate for algorithm-as-prose in skill/command markdown.

EPIC-2938's headline invariant is "no skill/command markdown contains a prose
reimplementation of an algorithm that exists in ``scripts/little_loops/``".
This is a curated marker scanner, not a general duplicate-algorithm detector —
it catches six known shapes of regression cheaply:

1. Jaccard/word-overlap formula (``intersection / union``, ``∩``/``∪`` over
   word sets) — owned by ``text_utils.calculate_word_overlap``.
2. An inline stop-word list — owned by ``text_utils.extract_words``.
3. Scanning ``~/.claude/projects/`` for session JSONL — owned by
   ``ll-issues append-log``.
4. Inline ``python3 -c`` computation the model is told to run — owned by the
   relevant CLI.
5. ``git mv`` loops over globbed/bracketed issue filenames — owned by
   ``ll-issues normalize``.
6. Union-find / cluster-merge instructions — owned by ``ll-issues link-epics``.

A ``<!-- ll-prose-ok: reason -->`` comment on the line immediately preceding a
match suppresses that one finding.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from little_loops.cli.output import configure_output, print_json, use_color_enabled
from little_loops.cli_args import add_json_arg
from little_loops.frontmatter import parse_skill_frontmatter
from little_loops.logger import Logger
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# ---------------------------------------------------------------------------
# Marker table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProseMarker:
    """One curated algorithm-as-prose shape and the CLI that owns it."""

    name: str
    pattern: re.Pattern[str]
    owner_cli: str
    rationale: str


_STOPWORD_CANDIDATES = (
    "the", "and", "for", "with", "from", "are", "was", "were", "been", "have",
    "has", "had", "not", "but", "can", "will", "should", "would", "could",
    "may", "might", "must", "all", "any", "into", "more", "also", "when",
    "which", "their", "they", "use", "new", "via", "per", "set", "run",
    "one", "its", "add",
)  # fmt: skip
_STOPWORD_ALT = "|".join(_STOPWORD_CANDIDATES)

PROSE_MARKERS: tuple[ProseMarker, ...] = (
    ProseMarker(
        name="jaccard_word_overlap",
        pattern=re.compile(
            r"(?:\bwords?\w*\s*[∩∪])"
            r"|(?:[∩∪]\s*\w*words?\b)"
            r"|(?:intersection\s*/\s*union)",
            re.IGNORECASE,
        ),
        owner_cli="text_utils.calculate_word_overlap",
        rationale="Jaccard/word-overlap formula spelled out in prose instead of calling the CLI helper.",
    ),
    ProseMarker(
        name="inline_stopword_list",
        pattern=re.compile(
            rf"(?:`(?:{_STOPWORD_ALT})`[,.\s]*){{3,}}",
            re.IGNORECASE,
        ),
        owner_cli="text_utils.extract_words",
        rationale="Inline stop-word list duplicating text_utils's canonical stop-word set.",
    ),
    ProseMarker(
        name="session_jsonl_scan",
        pattern=re.compile(
            r"(?=.*~/\.claude/projects/)(?=.*jsonl)",
            re.IGNORECASE,
        ),
        owner_cli="ll-issues append-log",
        rationale="Manual session-JSONL scanning instructions instead of calling ll-issues append-log.",
    ),
    ProseMarker(
        name="inline_python_computation",
        pattern=re.compile(r"\bpython3?\s+-c\b"),
        owner_cli="the owning CLI",
        rationale="Inline python -c computation the model is told to run instead of a CLI call.",
    ),
    ProseMarker(
        name="git_mv_glob_loop",
        pattern=re.compile(r"git mv\b.*\[.*\.md"),
        owner_cli="ll-issues normalize",
        rationale="git mv loop over globbed/bracketed issue filenames duplicating ll-issues normalize.",
    ),
    ProseMarker(
        name="union_find_cluster_merge",
        pattern=re.compile(r"union[- ]find|cluster[- ]merge", re.IGNORECASE),
        owner_cli="ll-issues link-epics",
        rationale="Union-find/cluster-merge instructions duplicating ll-issues link-epics.",
    ),
)

_SUPPRESS_RE = re.compile(r"<!--\s*ll-prose-ok:\s*(.+?)\s*-->")

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ProseFinding:
    """A single unsuppressed algorithm-as-prose match."""

    path: Path
    line: int
    marker: str
    owner_cli: str


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def _lint_file(md_file: Path, markers: tuple[ProseMarker, ...]) -> list[ProseFinding]:
    """Scan one markdown file for unsuppressed marker matches."""
    try:
        lines = md_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    findings: list[ProseFinding] = []
    for line_no, line in enumerate(lines, start=1):
        preceding = lines[line_no - 2] if line_no >= 2 else ""
        if _SUPPRESS_RE.search(preceding):
            continue
        for marker in markers:
            if marker.pattern.search(line):
                findings.append(
                    ProseFinding(
                        path=md_file,
                        line=line_no,
                        marker=marker.name,
                        owner_cli=marker.owner_cli,
                    )
                )
    return findings


def scan_prose(base_dir: Path) -> list[ProseFinding]:
    """Scan ``skills/*/SKILL.md`` and ``commands/*.md`` under base_dir for prose markers."""
    findings: list[ProseFinding] = []

    skills_dir = base_dir / "skills"
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            text = skill_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = parse_skill_frontmatter(text)
        if fm.get("disable-model-invocation", "").lower() in ("true", "yes", "1"):
            continue
        findings.extend(_lint_file(skill_file, PROSE_MARKERS))

    commands_dir = base_dir / "commands"
    for command_file in sorted(commands_dir.glob("*.md")):
        findings.extend(_lint_file(command_file, PROSE_MARKERS))

    return findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_text_report(findings: list[ProseFinding], base_dir: Path) -> str:
    if not findings:
        return "ll-verify-skill-prose: PASS — no algorithm-as-prose markers found"

    lines = [f"ll-verify-skill-prose: {len(findings)} finding(s)", ""]
    for f in findings:
        rel = f.path.relative_to(base_dir) if f.path.is_relative_to(base_dir) else f.path
        lines.append(f"  {rel}:{f.line}: [{f.marker}] owned by {f.owner_cli}")
    return "\n".join(lines)


def _findings_to_json(findings: list[ProseFinding], base_dir: Path) -> dict:
    return {
        "ok": not findings,
        "count": len(findings),
        "findings": [
            {
                "file": str(
                    f.path.relative_to(base_dir) if f.path.is_relative_to(base_dir) else f.path
                ),
                "line": f.line,
                "marker": f.marker,
                "owner_cli": f.owner_cli,
            }
            for f in findings
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main_verify_skill_prose(argv: list[str] | None = None) -> int:
    """Entry point for ll-verify-skill-prose.

    Returns 0 when no unsuppressed algorithm-as-prose markers are found in
    skills/*/SKILL.md or commands/*.md; returns 1 otherwise.
    """
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-skill-prose", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-skill-prose",
            description=(
                "Scan skills/*/SKILL.md and commands/*.md for prose reimplementations "
                "of algorithms that exist in scripts/little_loops/."
            ),
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""\
Examples:
  %(prog)s                     # Scan from cwd
  %(prog)s -C /path/to/root    # Scan a specific project root
  %(prog)s --json              # Machine-readable JSON output

Suppress a checked-in false positive with a comment on the preceding line:
  <!-- ll-prose-ok: reason -->

Exit codes:
  0 - No unsuppressed findings
  1 - One or more unsuppressed findings
""",
        )
        parser.add_argument(
            "-C",
            "--directory",
            type=Path,
            default=None,
            help="Project root containing skills/ and commands/ (default: cwd)",
        )
        add_json_arg(parser)

        args = parser.parse_args(argv)

        configure_output()
        logger = Logger(use_color=use_color_enabled())

        base_dir = args.directory or Path.cwd()
        findings = scan_prose(base_dir)

        if args.json:
            print_json(_findings_to_json(findings, base_dir))
            return 1 if findings else 0

        print(_format_text_report(findings, base_dir))
        if findings:
            logger.error(f"{len(findings)} algorithm-as-prose finding(s)")
            return 1
        logger.success("No algorithm-as-prose markers found")
        return 0
