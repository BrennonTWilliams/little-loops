"""ll-issues size: deterministic size scoring for issue-size-review (ENH-2945).

Ports Phases 1-3 of skills/issue-size-review/SKILL.md's hand-computed scoring
table into Python: file-path counts, section word counts, `##`-subsection
counts, cross-issue references, and total word count. Phases 4-5 (split
judgment) and Phase 6 (child-issue creation) stay the skill's job.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

# Ported verbatim from skills/issue-size-review/SKILL.md's Phase 2 table (L116-124).
# Single source of truth for the skill (--auto/--check) and this CLI so they can't diverge.
SIZE_SIGNAL_WEIGHTS: dict[str, int] = {
    "file_count": 2,
    "section_complexity": 2,
    "multiple_concerns": 3,
    "dependency_mentions": 2,
    "word_count": 2,
}

_FILE_COUNT_THRESHOLD = 3  # "multiple" distinct file paths mentioned
_WORD_COUNT_THRESHOLD = 800
_SECTION_WORD_THRESHOLD = 300

_MULTIPLE_CONCERNS_PHRASES = ("additionally", "also need to")
_DEPENDENCY_ID_RE = re.compile(r"\b(BUG|FEAT|ENH|EPIC)-(\d+)\b")
_DEPENDENCY_PHRASES = ("depends on", "blocked by")
_SUBSECTION_RE = re.compile(r"^###\s+\S", re.MULTILINE)
_SOLUTION_HEADINGS = ("Proposed Solution", "Implementation Steps", "Implementation")


@dataclass
class SizeScore:
    """A single issue's deterministic size score."""

    id: str
    score: int
    label: str
    signals: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a JSON-ready dict."""
        return {
            "id": self.id,
            "score": self.score,
            "label": self.label,
            "signals": dict(self.signals),
        }


def label_for(score: int) -> str:
    """Map a 0-11 score to its size label (skill's Size Thresholds table)."""
    if score <= 2:
        return "Small"
    if score <= 4:
        return "Medium"
    if score <= 7:
        return "Large"
    return "Very Large"


def _strip_frontmatter(content: str) -> str:
    """Drop the leading YAML frontmatter block, if any."""
    if content.startswith("---") and content.count("---") >= 2:
        return content.split("---", 2)[2]
    return content


def _find_solution_section(body: str) -> str | None:
    from little_loops.issue_parser import _section_body

    for heading in _SOLUTION_HEADINGS:
        text = _section_body(body, heading)
        if text:
            return text
    return None


def _file_count_signal(body: str) -> int:
    from little_loops.text_utils import extract_file_paths

    paths = extract_file_paths(body)
    return SIZE_SIGNAL_WEIGHTS["file_count"] if len(paths) >= _FILE_COUNT_THRESHOLD else 0


def _section_complexity_signal(body: str) -> int:
    section = _find_solution_section(body)
    if section and len(section.split()) > _SECTION_WORD_THRESHOLD:
        return SIZE_SIGNAL_WEIGHTS["section_complexity"]
    return 0


def _multiple_concerns_signal(body: str) -> int:
    section = _find_solution_section(body)
    subsection_count = len(_SUBSECTION_RE.findall(section)) if section else 0
    lowered = body.lower()
    has_phrase = any(phrase in lowered for phrase in _MULTIPLE_CONCERNS_PHRASES)
    return SIZE_SIGNAL_WEIGHTS["multiple_concerns"] if subsection_count >= 2 or has_phrase else 0


def _dependency_mentions_signal(body: str, self_id: str) -> int:
    ids = {f"{m.group(1)}-{m.group(2)}" for m in _DEPENDENCY_ID_RE.finditer(body)}
    ids.discard(self_id)
    lowered = body.lower()
    has_phrase = any(phrase in lowered for phrase in _DEPENDENCY_PHRASES)
    return SIZE_SIGNAL_WEIGHTS["dependency_mentions"] if ids or has_phrase else 0


def _word_count_signal(body: str) -> int:
    return SIZE_SIGNAL_WEIGHTS["word_count"] if len(body.split()) > _WORD_COUNT_THRESHOLD else 0


def compute_size(issue: IssueInfo, body: str) -> SizeScore:
    """Compute a deterministic size score for one issue.

    Args:
        issue: Parsed issue metadata (used for `.issue_id`).
        body: The full raw issue file text (frontmatter included) as read
            from disk; frontmatter is stripped internally before signals are
            computed so `type:`/`epic:` fields never count as content.

    Returns:
        A SizeScore with per-signal breakdown and the total (0-11) score.
    """
    content = _strip_frontmatter(body)
    signals = {
        "file_count": _file_count_signal(content),
        "section_complexity": _section_complexity_signal(content),
        "multiple_concerns": _multiple_concerns_signal(content),
        "dependency_mentions": _dependency_mentions_signal(content, issue.issue_id),
        "word_count": _word_count_signal(content),
    }
    score = sum(signals.values())
    return SizeScore(id=issue.issue_id, score=score, label=label_for(score), signals=signals)


def write_size(issue_path: Path, score: SizeScore) -> None:
    """Stamp `size:` frontmatter with *score*'s label."""
    from little_loops.frontmatter import update_frontmatter

    content = issue_path.read_text(encoding="utf-8")
    new_content = update_frontmatter(content, {"size": score.label})
    issue_path.write_text(new_content, encoding="utf-8")


def add_size_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the `size` subparser on *subs*."""
    from little_loops.cli_args import add_config_arg

    p = subs.add_parser(
        "size",
        help="Deterministic size scoring (file/section/word-count signals) for issue-size-review",
    )
    p.set_defaults(command="size")
    p.add_argument("issue_id", nargs="?", help="Specific issue ID to score (e.g. ENH-179)")
    p.add_argument("--all", action="store_true", help="Score all active bugs/features/enhancements")
    p.add_argument("--sprint", metavar="NAME", help="Score only the issues in .sprints/NAME.yaml")
    p.add_argument(
        "--write", action="store_true", help="Stamp size: frontmatter with the computed label"
    )
    p.add_argument("--json", action="store_true", help="Print scores as JSON")
    add_config_arg(p)
    return p


def cmd_size(config: BRConfig, args: argparse.Namespace) -> int:
    """Entry point for `ll-issues size <id|--all|--sprint NAME> [--write] [--json]`."""
    from little_loops.issue_parser import IssueParser, find_issues

    issue_id = getattr(args, "issue_id", None)
    all_mode = bool(getattr(args, "all", False))
    sprint_name = getattr(args, "sprint", None)

    if sum(bool(x) for x in (issue_id, all_mode, sprint_name)) != 1:
        print("Error: specify exactly one of ISSUE_ID, --all, or --sprint NAME", file=sys.stderr)
        return 1

    issues: list[IssueInfo] = []
    if issue_id:
        from little_loops.cli.issues.show import _resolve_issue_id

        path = _resolve_issue_id(config, issue_id)
        if path is None:
            print(f"Error: Issue '{issue_id}' not found.", file=sys.stderr)
            return 1
        issues = [IssueParser(config).parse_file(path)]
    elif sprint_name:
        from little_loops.sprint import Sprint

        sprints_dir = Path(config.sprints.sprints_dir)
        if not sprints_dir.is_absolute():
            sprints_dir = config.project_root / sprints_dir
        sprint = Sprint.load(sprints_dir, sprint_name)
        if sprint is None:
            print(f"Error: Sprint '{sprint_name}' not found.", file=sys.stderr)
            return 1
        issues = find_issues(config, only_ids=sprint.issues)
    else:
        issues = find_issues(config, type_prefixes={"BUG", "FEAT", "ENH"})

    scores: list[SizeScore] = []
    for info in issues:
        body = info.path.read_text(encoding="utf-8")
        score = compute_size(info, body)
        scores.append(score)
        if getattr(args, "write", False):
            write_size(info.path, score)

    if getattr(args, "json", False):
        print(json.dumps([s.to_dict() for s in scores], indent=2))
    else:
        for s in scores:
            breakdown = ", ".join(f"{k}(+{v})" for k, v in s.signals.items() if v)
            suffix = f" — {breakdown}" if breakdown else ""
            print(f"[{s.id}] size: score {s.score} ({s.label}){suffix}")

    return 0
