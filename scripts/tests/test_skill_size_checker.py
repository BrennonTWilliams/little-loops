"""Tests for check_skill_sizes() in doc_counts.py."""

from __future__ import annotations

from pathlib import Path

from little_loops.doc_counts import check_skill_sizes


def _make_skill(
    skills_dir: Path,
    name: str,
    line_count: int,
    disable_model_invocation: bool = False,
) -> None:
    """Write a SKILL.md with exactly line_count total lines (including frontmatter)."""
    skill_dir = skills_dir / name
    skill_dir.mkdir()
    flag_line = "disable-model-invocation: true\n" if disable_model_invocation else ""
    frontmatter = f"---\n{flag_line}description: {name} skill\n---\n"
    # frontmatter contributes 3 lines (or 4 if flag_line present); compute body size
    fm_lines = len(frontmatter.splitlines())
    body_count = max(0, line_count - fm_lines)
    body = "\n".join(f"line {i}" for i in range(body_count))
    (skill_dir / "SKILL.md").write_text(frontmatter + body)


class TestCheckSkillSizes:
    """Tests for check_skill_sizes function."""

    def test_empty_skills_dir_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty list when no skills directory exists."""
        violations = check_skill_sizes(base_dir=tmp_path)
        assert violations == []

    def test_skill_under_limit_not_flagged(self, tmp_path: Path) -> None:
        """SKILL.md at or under 500 lines is not flagged."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "small-skill", 499)

        violations = check_skill_sizes(base_dir=tmp_path)
        assert violations == []

    def test_skill_exactly_at_limit_not_flagged(self, tmp_path: Path) -> None:
        """SKILL.md at exactly 500 lines is not flagged."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "limit-skill", 500)

        violations = check_skill_sizes(base_dir=tmp_path)
        assert violations == []

    def test_skill_over_limit_is_flagged(self, tmp_path: Path) -> None:
        """SKILL.md exceeding 500 lines is returned as a violation."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "big-skill", 501)

        violations = check_skill_sizes(base_dir=tmp_path)
        assert len(violations) == 1
        path, lines = violations[0]
        assert path.parent.name == "big-skill"
        assert lines == 501

    def test_only_skill_md_counted_not_companions(self, tmp_path: Path) -> None:
        """Companion files alongside SKILL.md are not counted toward the limit."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "skill-with-companion"
        skill_dir.mkdir()
        # SKILL.md is under limit
        (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\n" + "line\n" * 490)
        # Large companion file that should NOT be counted
        (skill_dir / "templates.md").write_text("companion line\n" * 1000)

        violations = check_skill_sizes(base_dir=tmp_path)
        assert violations == []

    def test_disable_model_invocation_skill_skipped(self, tmp_path: Path) -> None:
        """Skills with disable-model-invocation: true are not flagged even if over limit."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "gated-skill", 600, disable_model_invocation=True)

        violations = check_skill_sizes(base_dir=tmp_path)
        assert violations == []

    def test_custom_limit_respected(self, tmp_path: Path) -> None:
        """Custom limit overrides the default 500-line threshold."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "medium-skill", 450)

        # Under default limit (500): no violations
        assert check_skill_sizes(base_dir=tmp_path, limit=500) == []
        # Over custom limit (400): one violation
        violations = check_skill_sizes(base_dir=tmp_path, limit=400)
        assert len(violations) == 1
        assert violations[0][1] == 450

    def test_multiple_violations_all_returned(self, tmp_path: Path) -> None:
        """All violating SKILL.md files are returned."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "skill-a", 510)
        _make_skill(skills_dir, "skill-b", 480)  # under limit
        _make_skill(skills_dir, "skill-c", 520)

        violations = check_skill_sizes(base_dir=tmp_path)
        assert len(violations) == 2
        names = {path.parent.name for path, _ in violations}
        assert names == {"skill-a", "skill-c"}
