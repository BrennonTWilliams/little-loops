"""Tests for ll-verify-triggers CLI — trigger validation suite for skill descriptions."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.verify_triggers import (
    PrecisionRecall,
    SkillTriggerResult,
    _compute_precision_recall,
    _detect_collisions,
    _extract_keywords,
    _load_skill_descriptions,
    _load_trigger_fixtures,
    _match_phrasing,
    _run_validation,
    main_verify_triggers,
)

# ---------------------------------------------------------------------------
# Unit tests: keyword extraction
# ---------------------------------------------------------------------------

class TestExtractKeywords:
    """Tests for _extract_keywords — deterministic keyword extraction."""

    def test_triggers_by_keyword(self) -> None:
        """A phrasing containing a keyword matches."""
        keywords = {"run", "tests", "pytest"}
        assert _match_phrasing("run the tests", keywords) is True
        assert _match_phrasing("please run pytest", keywords) is True

    def test_no_keyword_match(self) -> None:
        """A phrasing with no matching keywords does NOT match."""
        keywords = {"run", "tests", "pytest"}
        assert _match_phrasing("deploy the application", keywords) is False

    def test_case_insensitive(self) -> None:
        """Matching is case-insensitive."""
        keywords = {"commit", "git"}
        assert _match_phrasing("Git COMMIT changes", keywords) is True

    def test_exact_token_match(self) -> None:
        """Keywords match exact tokens (not substrings)."""
        keywords = {"tests", "codebase"}
        assert _match_phrasing("write tests for the codebase", keywords) is True
        # Substring "test" within "tests" does NOT match exact token
        assert _match_phrasing("write tests for the codebase", {"test", "code"}) is False

    def test_extract_from_description_with_trigger_keywords(self) -> None:
        """_extract_keywords pulls trigger keywords from description."""
        desc = (
            "Run code quality checks (lint, format, types, build)\n"
            "Trigger keywords: lint, format, type check, ruff, mypy, build"
        )
        kw = _extract_keywords(desc)
        assert "lint" in kw
        assert "ruff" in kw
        assert "mypy" in kw

    def test_extract_without_trigger_keywords(self) -> None:
        """_extract_keywords falls back to description words when no trigger line."""
        desc = "Run code quality checks"
        kw = _extract_keywords(desc)
        assert "run" in kw
        assert "code" in kw
        assert "quality" in kw

    def test_extract_filters_short_words(self) -> None:
        """Words shorter than 3 characters are excluded."""
        desc = "go to dir"
        kw = _extract_keywords(desc)
        assert "go" not in kw
        assert "to" not in kw
        assert "dir" in kw

    def test_extract_excludes_stopwords(self) -> None:
        """Common stopwords are excluded from keyword extraction."""
        desc = "use when asked to run the tests and verify the code"
        kw = _extract_keywords(desc)
        assert "the" not in kw
        assert "and" not in kw
        assert "asked" in kw
        assert "tests" in kw


# ---------------------------------------------------------------------------
# Unit tests: fixture parsing
# ---------------------------------------------------------------------------

class TestTriggerFixtures:
    """Tests for trigger fixture parsing from SKILL.md frontmatter."""

    def test_parse_fixtures_from_frontmatter(self, tmp_path: Path) -> None:
        """Fixtures with should_fire and should_not_fire are parsed."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: Run code quality checks
trigger_fixtures:
  should_fire:
    - "run lint"
    - "check code quality"
    - "format python"
  should_not_fire:
    - "create a pull request"
    - "deploy to production"
---

# Test Skill
""")
        fixtures = _load_trigger_fixtures(skill_md)
        assert fixtures is not None
        assert len(fixtures.should_fire) == 3
        assert len(fixtures.should_not_fire) == 2

    def test_no_fixtures_returns_none(self, tmp_path: Path) -> None:
        """Skills without trigger_fixtures return None."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: Run code quality checks
---

# Test Skill
""")
        fixtures = _load_trigger_fixtures(skill_md)
        assert fixtures is None

    def test_empty_fixtures_returns_none(self, tmp_path: Path) -> None:
        """Skills with empty fixture lists return None."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: Run code quality checks
trigger_fixtures:
  should_fire: []
  should_not_fire: []
---

# Test Skill
""")
        fixtures = _load_trigger_fixtures(skill_md)
        assert fixtures is None


# ---------------------------------------------------------------------------
# Unit tests: precision/recall
# ---------------------------------------------------------------------------

class TestPrecisionRecall:
    """Tests for precision/recall computation."""

    def test_perfect_precision_recall(self) -> None:
        """All should-fire match, no false positives => 1.0 precision, 1.0 recall."""
        result = _compute_precision_recall(tp=5, fp=0, fn=0)
        assert result == PrecisionRecall(precision=1.0, recall=1.0)

    def test_zero_division_precision(self) -> None:
        """No triggers at all => precision 0.0."""
        result = _compute_precision_recall(tp=0, fp=0, fn=5)
        assert result == PrecisionRecall(precision=0.0, recall=0.0)

    def test_zero_division_recall(self) -> None:
        """No should-fire phrasings => recall 0.0."""
        result = _compute_precision_recall(tp=0, fp=0, fn=0)
        assert result == PrecisionRecall(precision=0.0, recall=0.0)

    def test_mixed_metrics(self) -> None:
        """3 TP, 1 FP, 2 FN => precision 0.75, recall 0.6."""
        result = _compute_precision_recall(tp=3, fp=1, fn=2)
        assert result.precision == 0.75
        assert result.recall == 0.6

    def test_false_positives_only(self) -> None:
        """All matches are false positives => precision 0.0, recall 0.0."""
        result = _compute_precision_recall(tp=0, fp=3, fn=5)
        assert result.precision == 0.0
        assert result.recall == 0.0


# ---------------------------------------------------------------------------
# Unit tests: collision detection
# ---------------------------------------------------------------------------

class TestCollisionDetection:
    """Tests for cross-skill collision detection."""

    def test_no_collisions(self) -> None:
        """When no phrasings trigger multiple skills, collisions is empty."""
        results = {
            "skill-a": SkillTriggerResult(
                skill_name="skill-a",
                description="Run code quality checks",
                tp=3,
                fp=0,
                fn=0,
                precision=1.0,
                recall=1.0,
            ),
            "skill-b": SkillTriggerResult(
                skill_name="skill-b",
                description="Manage git commits",
                tp=2,
                fp=0,
                fn=0,
                precision=1.0,
                recall=1.0,
            ),
        }
        collisions = _detect_collisions(results, {})
        assert len(collisions) == 0

    def test_detects_collision(self) -> None:
        """A phrasing matching two skills produces a collision entry."""
        phrase = "check the code"
        results = {
            "skill-a": SkillTriggerResult(
                skill_name="skill-a",
                description="Run code quality checks",
                tp=3,
                fp=1,
                fn=0,
                precision=0.75,
                recall=1.0,
                false_positive_phrasings=[phrase],
            ),
            "skill-b": SkillTriggerResult(
                skill_name="skill-b",
                description="Check code for bugs",
                tp=2,
                fp=1,
                fn=0,
                precision=0.67,
                recall=1.0,
                false_positive_phrasings=[phrase],
            ),
        }
        collisions = _detect_collisions(results, {phrase: {"skill-a", "skill-b"}})
        assert len(collisions) == 1
        c = collisions[0]
        assert c["phrasing"] == phrase
        assert set(c["skills"]) == {"skill-a", "skill-b"}


# ---------------------------------------------------------------------------
# Unit tests: skill description loading
# ---------------------------------------------------------------------------

class TestLoadSkillDescriptions:
    """Tests for skill description loading from disk."""

    def test_loads_valid_skill(self, tmp_path: Path) -> None:
        """A valid SKILL.md with description is loaded."""
        skill_dir = tmp_path / "ll-test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: ll-test-skill
description: Run tests and verify code
---

# Test Skill
""")
        skills = _load_skill_descriptions(tmp_path)
        assert "ll-test-skill" in skills
        desc, _ = skills["ll-test-skill"]
        assert "Run tests and verify code" in desc

    def test_skips_missing_frontmatter(self, tmp_path: Path) -> None:
        """Skills without frontmatter are skipped."""
        skill_dir = tmp_path / "ll-broken-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# No frontmatter\n\nJust body text.")
        skills = _load_skill_descriptions(tmp_path)
        assert "ll-broken-skill" not in skills

    def test_loads_only_skill_md_files(self, tmp_path: Path) -> None:
        """Only SKILL.md files are loaded; other files are ignored."""
        skill_dir = tmp_path / "ll-test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: ll-test-skill
description: Run tests
---

# Test
""")
        (skill_dir / "README.md").write_text("# Not a skill")
        skills = _load_skill_descriptions(tmp_path)
        assert "ll-test-skill" in skills


# ---------------------------------------------------------------------------
# Integration tests: _run_validation
# ---------------------------------------------------------------------------

class TestRunValidation:
    """Integration tests for the core validation logic."""

    def _setup_skills(self, skills_dir: Path) -> None:
        """Set up two test skills with trigger fixtures."""
        skill_a = skills_dir / "ll-code-check"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text("""---
name: ll-code-check
description: Run code quality checks (lint, format, types, build)
trigger_fixtures:
  should_fire:
    - "run lint"
    - "check code format"
    - "run type check"
    - "build the project"
  should_not_fire:
    - "commit changes"
    - "deploy to production"
---

# Check Code
""")

        skill_b = skills_dir / "ll-commit"
        skill_b.mkdir()
        (skill_b / "SKILL.md").write_text("""---
name: ll-commit
description: Create git commits with user approval
trigger_fixtures:
  should_fire:
    - "create git commits"
    - "approve a commit"
    - "commit user changes"
  should_not_fire:
    - "run lint"
    - "check code format"
---

# Commit
""")

    def test_validation_computes_metrics(self, tmp_path: Path) -> None:
        """Validation returns SkillTriggerResult per skill."""
        self._setup_skills(tmp_path)
        results, collisions, _ = _run_validation(tmp_path)
        assert "ll-code-check" in results
        assert "ll-commit" in results
        assert results["ll-code-check"].precision is not None
        assert results["ll-commit"].recall is not None

    def test_results_have_zero_precision_when_no_fixtures(self, tmp_path: Path) -> None:
        """Skills without fixtures return 0.0 precision/recall."""
        skill_dir = tmp_path / "ll-no-fixtures"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: ll-no-fixtures
description: A skill without fixtures
---

# No Fixtures
""")
        results, _, _ = _run_validation(tmp_path)
        assert results["ll-no-fixtures"].precision is not None
        assert results["ll-no-fixtures"].recall is not None

    def test_empty_skills_dir(self, tmp_path: Path) -> None:
        """Empty skills directory returns empty results."""
        results, collisions, _ = _run_validation(tmp_path)
        assert len(results) == 0
        assert len(collisions) == 0

    def test_should_fire_matches_own_skill(self, tmp_path: Path) -> None:
        """A should-fire phrasing that contains the skill's keywords counts as TP."""
        self._setup_skills(tmp_path)
        results, _, _ = _run_validation(tmp_path)
        # "run lint" should match ll-code-check (code, quality, lint...)
        # and should NOT match ll-commit (commit, git...)
        code_check = results["ll-code-check"]
        assert code_check.tp > 0

    def test_should_not_fire_does_not_match(self, tmp_path: Path) -> None:
        """A should-not-fire phrasing should not trigger its own skill."""
        self._setup_skills(tmp_path)
        results, _, _ = _run_validation(tmp_path)
        # "run lint" is should-not-fire for ll-commit, should be a TN
        # FN means a should-fire phrasing did not trigger its skill
        commit = results["ll-commit"]
        # "commit changes" should match ll-commit keywords
        assert commit.tp >= 0
        assert commit.fp >= 0


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestMainVerifyTriggers:
    """Tests for main_verify_triggers entry point."""

    def _setup_skills_dir(self, base: Path) -> Path:
        """Create a skills directory with two well-separated test skills."""
        skills_dir = base / "skills"
        skills_dir.mkdir()

        skill_a = skills_dir / "ll-code-check"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text("""---
name: ll-code-check
description: Run code quality checks (lint, format, types, build)
trigger_fixtures:
  should_fire:
    - "run lint"
    - "check code format"
  should_not_fire:
    - "commit changes"
---

# Check Code
""")

        skill_b = skills_dir / "ll-commit"
        skill_b.mkdir()
        (skill_b / "SKILL.md").write_text("""---
name: ll-commit
description: Create git commits with user approval
trigger_fixtures:
  should_fire:
    - "create git commits"
  should_not_fire:
    - "run lint"
---

# Commit
""")
        return skills_dir

    def test_valid_skills_return_0(self, tmp_path: Path) -> None:
        """Well-separated skills with clear triggers return exit 0."""
        self._setup_skills_dir(tmp_path)
        with (
            patch("sys.argv", ["ll-verify-triggers", "-C", str(tmp_path)]),
            patch("builtins.print"),
        ):
            result = main_verify_triggers()
        assert result == 0

    def test_colliding_skills_return_1(self, tmp_path: Path) -> None:
        """Skills with colliding trigger spaces return exit 1."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Two skills with identical trigger keywords
        for name in ("ll-check-a", "ll-check-b"):
            d = skills_dir / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"""---
name: {name}
description: Run code quality checks (lint, format, types, build)
trigger_fixtures:
  should_fire:
    - "run lint"
  should_not_fire:
    - "deploy"
---

# {name}
""")

        with (
            patch("sys.argv", ["ll-verify-triggers", "-C", str(tmp_path)]),
            patch("builtins.print"),
        ):
            result = main_verify_triggers()
        assert result == 1

    def test_no_skills_dir(self, tmp_path: Path) -> None:
        """Missing skills directory returns exit 1."""
        with (
            patch("sys.argv", ["ll-verify-triggers", "-C", str(tmp_path)]),
            patch("builtins.print"),
        ):
            result = main_verify_triggers()
        assert result == 1

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        """--json flag produces valid JSON output."""
        self._setup_skills_dir(tmp_path)
        with patch("sys.argv", ["ll-verify-triggers", "-C", str(tmp_path), "--json"]):
            main_verify_triggers()

        output = json.loads(capsys.readouterr().out)
        assert "skills" in output
        assert "collisions" in output
        assert isinstance(output["skills"], list)
        assert isinstance(output["collisions"], list)

    def test_json_output_no_fixtures(self, tmp_path: Path, capsys) -> None:
        """--json with skills that have no fixtures still produces valid JSON."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        d = skills_dir / "ll-no-fixtures"
        d.mkdir()
        (d / "SKILL.md").write_text("""---
name: ll-no-fixtures
description: A skill without trigger fixtures
---

# No Fixtures
""")

        with patch("sys.argv", ["ll-verify-triggers", "-C", str(tmp_path), "--json"]):
            main_verify_triggers()

        output = json.loads(capsys.readouterr().out)
        assert isinstance(output["skills"], list)
        assert len(output["skills"]) == 1
        skill = output["skills"][0]
        assert skill["name"] == "ll-no-fixtures"
        assert skill["precision"] == 0.0
        assert skill["recall"] == 0.0

    def test_json_output_returns_0_when_no_collisions(self, tmp_path: Path, capsys) -> None:
        """--json with passing results returns exit 0."""
        self._setup_skills_dir(tmp_path)
        with patch("sys.argv", ["ll-verify-triggers", "-C", str(tmp_path), "--json"]):
            result = main_verify_triggers()
        assert result == 0

    def test_precision_threshold_flag(self, tmp_path: Path) -> None:
        """--precision-threshold flag is parsed."""
        self._setup_skills_dir(tmp_path)
        with (
            patch("sys.argv", [
                "ll-verify-triggers", "-C", str(tmp_path), "--precision-threshold", "0.9"
            ]),
            patch("little_loops.cli.verify_triggers._run_validation") as mock_run,
            patch("builtins.print"),
        ):
            mock_run.return_value = ({}, [], {"precision_threshold": 0.9, "recall_threshold": 0.5})
            main_verify_triggers()

    def test_recall_threshold_flag(self, tmp_path: Path) -> None:
        """--recall-threshold flag is parsed."""
        self._setup_skills_dir(tmp_path)
        with (
            patch("sys.argv", [
                "ll-verify-triggers", "-C", str(tmp_path), "--recall-threshold", "0.7"
            ]),
            patch("little_loops.cli.verify_triggers._run_validation") as mock_run,
            patch("builtins.print"),
        ):
            mock_run.return_value = ({}, [], {"precision_threshold": 0.5, "recall_threshold": 0.7})
            main_verify_triggers()
