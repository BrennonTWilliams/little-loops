"""Resident-cost regression gate for `.claude/CLAUDE.md` H2 sections (ENH-2972).

`## CLI Tools` grew from 3,695 to 4,723 tokens in a single day before this
issue moved it out of the file entirely — a section large enough that nobody
re-reads it on edit drifts silently upward, and nothing failed the suite when
it did. This test reuses `doctor_trim._memory_components()` (the same
estimator `ll-doctor --trim` reports) so there is no second token counter to
keep in sync, and fails the suite the moment any section regrows past the
review bar instead of accumulating unnoticed until the next manual
`ll-doctor --trim` run.
"""

from __future__ import annotations

from pathlib import Path

from little_loops.cli.doctor_trim import _SECTION_REVIEW_TOKENS, _memory_components


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


# ENH-2972 moved only these three sections behind pointers; the rest of
# `.claude/CLAUDE.md` (Distribution, Key Directories, Commands & Skills, ...)
# was already over the review bar before this issue and is out of scope —
# gating them here would fail on unrelated, pre-existing content.
_ENH_2972_GATED_SECTIONS = (
    ".claude/CLAUDE.md § Loop Authoring",
    ".claude/CLAUDE.md § Issue File Format",
)


def test_claude_md_migrated_sections_stay_under_review_bar() -> None:
    root = _plugin_root()
    components = {c.name: c for c in _memory_components(root)}

    over_budget = [
        components[name]
        for name in _ENH_2972_GATED_SECTIONS
        if name in components and components[name].resident_tokens >= _SECTION_REVIEW_TOKENS
    ]
    assert not over_budget, (
        f"the following .claude/CLAUDE.md sections regrew past the "
        f"{_SECTION_REVIEW_TOKENS}-token review bar: "
        + ", ".join(f"{c.name} ({c.resident_tokens} tokens)" for c in over_budget)
    )


def test_claude_md_has_no_cli_tools_section() -> None:
    """ENH-2972 moved this section to docs/reference/CLI.md; it must not regrow here."""
    root = _plugin_root()
    names = {c.name for c in _memory_components(root)}
    assert ".claude/CLAUDE.md § CLI Tools" not in names
