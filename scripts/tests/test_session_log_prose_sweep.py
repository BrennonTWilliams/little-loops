"""Session-log hunting-prose regression tests (ENH-2939).

Asserts the 6 swept skill files call ``ll-issues append-log`` (or, for
``manage-issue/templates.md``, point at it) instead of instructing the LLM
to manually hunt for the current session JSONL under ``~/.claude/projects/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent

SWEPT_FILES = [
    PROJECT_ROOT / "skills" / "capture-issue" / "SKILL.md",
    PROJECT_ROOT / "skills" / "confidence-check" / "SKILL.md",
    PROJECT_ROOT / "skills" / "go-no-go" / "SKILL.md",
    PROJECT_ROOT / "skills" / "issue-size-review" / "SKILL.md",
    PROJECT_ROOT / "skills" / "manage-issue" / "SKILL.md",
    PROJECT_ROOT / "skills" / "manage-issue" / "templates.md",
    PROJECT_ROOT / "skills" / "scope-epic" / "SKILL.md",
]


@pytest.mark.parametrize("path", SWEPT_FILES, ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_no_claude_projects_hunting_prose(path: Path) -> None:
    content = path.read_text()
    assert "~/.claude/projects" not in content, (
        f"{path.relative_to(PROJECT_ROOT)} still instructs scanning ~/.claude/projects/ "
        "for the session JSONL (ENH-2939)"
    )


@pytest.mark.parametrize("path", SWEPT_FILES, ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_references_append_log(path: Path) -> None:
    content = path.read_text()
    assert "ll-issues append-log" in content, (
        f"{path.relative_to(PROJECT_ROOT)} must reference the 'll-issues append-log' "
        "CLI instead of manual JSONL hunting (ENH-2939)"
    )
