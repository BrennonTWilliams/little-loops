"""Tests for documentation count verification."""

from pathlib import Path

from little_loops.doc_counts import (
    BRIDGE_MARKER,
    CountResult,
    SkillBudgetResult,
    VerificationResult,
    check_skill_budget,
    count_files,
    extract_count_from_line,
    fix_counts,
    format_result_json,
    format_result_markdown,
    format_result_text,
    verify_documentation,
)
from little_loops.fsm import is_runnable_loop


class TestCountFiles:
    """Tests for count_files function."""

    def test_count_commands(self, tmp_path: Path) -> None:
        """Count command markdown files."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "cmd1.md").write_text("# Command 1")
        (commands_dir / "cmd2.md").write_text("# Command 2")

        count = count_files("commands", "*.md", tmp_path)
        assert count == 2

    def test_count_skills_with_subdirs(self, tmp_path: Path) -> None:
        """Count skill files in subdirectories."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill1_dir = skills_dir / "skill1"
        skill1_dir.mkdir()
        (skill1_dir / "SKILL.md").write_text("# Skill 1")

        count = count_files("skills", "*/SKILL.md", tmp_path)
        assert count == 1

    def test_count_loops_top_level_glob_non_recursive(self, tmp_path: Path) -> None:
        """count_files() itself is a thin glob wrapper — confirm it stays non-recursive.

        Recursive enumeration with runnable-loop filtering is the responsibility
        of verify_documentation() (see TestVerifyDocumentation for that path);
        keeping count_files() simple lets the other three targets (commands,
        agents, skills) keep using it unchanged.
        """
        loops_dir = tmp_path / "loops"
        loops_dir.mkdir()
        (loops_dir / "loop1.yaml").write_text("name: loop1")
        (loops_dir / "loop2.yaml").write_text("name: loop2")
        oracles_dir = loops_dir / "oracles"
        oracles_dir.mkdir()
        (oracles_dir / "oracle.yaml").write_text("name: oracle")

        count = count_files("loops", "*.yaml", tmp_path)
        assert count == 2

    def test_count_nonexistent_directory(self, tmp_path: Path) -> None:
        """Return 0 for nonexistent directory."""
        count = count_files("nonexistent", "*.md", tmp_path)
        assert count == 0

    def test_count_empty_directory(self, tmp_path: Path) -> None:
        """Return 0 for empty directory."""
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()

        count = count_files("commands", "*.md", tmp_path)
        assert count == 0


class TestIsRunnableLoop:
    """Tests for is_runnable_loop predicate (BUG-1633)."""

    def test_valid_loop_with_states(self, fsm_fixtures: Path) -> None:
        """Valid loop with name + initial + states returns True."""
        assert is_runnable_loop(fsm_fixtures / "valid-loop.yaml") is True

    def test_flow_shorthand_accepted(self, tmp_path: Path) -> None:
        """`flow:` shorthand (alternative to states:) is accepted."""
        path = tmp_path / "flow-loop.yaml"
        path.write_text(
            "name: flow-loop\ninitial: step1\nflow:\n  - step1: echo hi\n  - step2: echo bye\n"
        )
        assert is_runnable_loop(path) is True

    def test_missing_name_returns_false(self, fsm_fixtures: Path) -> None:
        """YAML missing `name:` is not runnable."""
        assert is_runnable_loop(fsm_fixtures / "missing-name.yaml") is False

    def test_missing_initial_returns_false(self, tmp_path: Path) -> None:
        """YAML with name + states but no `initial:` is not runnable (lib fragment shape)."""
        path = tmp_path / "no-initial.yaml"
        path.write_text("name: fragment\nstates:\n  s:\n    terminal: true\n")
        assert is_runnable_loop(path) is False

    def test_missing_states_and_flow_returns_false(self, fsm_fixtures: Path) -> None:
        """YAML with neither states: nor flow: is not runnable."""
        assert is_runnable_loop(fsm_fixtures / "missing-states.yaml") is False

    def test_incomplete_loop_returns_false(self, fsm_fixtures: Path) -> None:
        """YAML with only `name:` is not runnable (library fragment)."""
        assert is_runnable_loop(fsm_fixtures / "incomplete-loop.yaml") is False

    def test_non_dict_root_returns_false(self, fsm_fixtures: Path) -> None:
        """YAML whose top-level is a list (not a mapping) is not runnable."""
        assert is_runnable_loop(fsm_fixtures / "non-dict-root.yaml") is False

    def test_malformed_yaml_returns_false(self, tmp_path: Path) -> None:
        """Malformed YAML (parse error) is not runnable; predicate must not raise."""
        path = tmp_path / "bad.yaml"
        path.write_text("name: bad\n  bogus: : : indent: chaos\n[")
        assert is_runnable_loop(path) is False

    def test_oracle_capture_issue_is_runnable(self) -> None:
        """Real nested oracle loop is recognized as runnable (the case BUG-1633 missed)."""
        from pathlib import Path as _Path

        oracle = (
            _Path(__file__).resolve().parents[1]
            / "little_loops"
            / "loops"
            / "oracles"
            / "oracle-capture-issue.yaml"
        )
        # Only assert if the file is present — keep the test tolerant of future moves.
        if oracle.exists():
            assert is_runnable_loop(oracle) is True

    def test_generator_evaluator_is_runnable(self) -> None:
        """generator-evaluator oracle sub-loop is recognized as runnable."""
        from pathlib import Path as _Path

        oracle = (
            _Path(__file__).resolve().parents[1]
            / "little_loops"
            / "loops"
            / "oracles"
            / "generator-evaluator.yaml"
        )
        if oracle.exists():
            assert is_runnable_loop(oracle) is True

    def test_enumerate_and_prove_is_runnable(self) -> None:
        """enumerate-and-prove oracle sub-loop is recognized as runnable."""
        from pathlib import Path as _Path

        oracle = (
            _Path(__file__).resolve().parents[1]
            / "little_loops"
            / "loops"
            / "oracles"
            / "enumerate-and-prove.yaml"
        )
        if oracle.exists():
            assert is_runnable_loop(oracle) is True

    def test_implement_issue_chain_is_runnable(self) -> None:
        """implement-issue-chain oracle sub-loop is recognized as runnable."""
        from pathlib import Path as _Path

        oracle = (
            _Path(__file__).resolve().parents[1]
            / "little_loops"
            / "loops"
            / "oracles"
            / "implement-issue-chain.yaml"
        )
        if oracle.exists():
            assert is_runnable_loop(oracle) is True

    def test_research_coverage_is_runnable(self) -> None:
        """research-coverage oracle sub-loop is recognized as runnable."""
        from pathlib import Path as _Path

        oracle = (
            _Path(__file__).resolve().parents[1]
            / "little_loops"
            / "loops"
            / "oracles"
            / "research-coverage.yaml"
        )
        if oracle.exists():
            assert is_runnable_loop(oracle) is True

    def test_lib_fragments_are_not_runnable(self) -> None:
        """All real library fragments under loops/lib/ are excluded by the predicate."""
        from pathlib import Path as _Path

        lib_dir = _Path(__file__).resolve().parents[1] / "little_loops" / "loops" / "lib"
        if not lib_dir.exists():
            return
        for fragment in lib_dir.glob("*.yaml"):
            assert is_runnable_loop(fragment) is False, (
                f"library fragment {fragment.name} should not be counted as runnable"
            )


class TestExtractCountFromLine:
    """Tests for extract_count_from_line function."""

    def test_extract_simple_count(self) -> None:
        """Extract simple '34 commands' pattern."""
        count = extract_count_from_line("34 commands", "commands")
        assert count == 34

    def test_extract_with_adjective(self) -> None:
        """Extract '34 slash commands' pattern."""
        count = extract_count_from_line("34 slash commands", "commands")
        assert count == 34

    def test_extract_agents(self) -> None:
        """Extract '8 specialized agents' pattern."""
        count = extract_count_from_line("8 specialized agents", "agents")
        assert count == 8

    def test_extract_skills(self) -> None:
        """Extract '6 skill definitions' pattern."""
        count = extract_count_from_line("6 skill definitions", "skills")
        assert count == 6

    def test_no_match_skill_descriptions_phrase(self) -> None:
        """Do not match '0 skill descriptions dropped' (quoted CLI output, not a count)."""
        count = extract_count_from_line('verify "0 skill descriptions dropped"', "skills")
        assert count is None

    def test_no_match_returns_none(self) -> None:
        """Return None when pattern doesn't match."""
        count = extract_count_from_line("no numbers here", "commands")
        assert count is None

    def test_case_insensitive(self) -> None:
        """Match regardless of case."""
        count = extract_count_from_line("34 Commands", "commands")
        assert count == 34

    def test_extract_with_markdown_bold(self) -> None:
        """Extract count from markdown bold text."""
        count = extract_count_from_line("**34 slash commands** for workflows", "commands")
        assert count == 34

    def test_extract_loops_fsm_format(self) -> None:
        """Extract count from '49 FSM loops' phrasing."""
        count = extract_count_from_line("49 FSM loops", "loops")
        assert count == 49

    def test_extract_loops_plain_format(self) -> None:
        """Extract count from plain '12 loops' phrasing."""
        count = extract_count_from_line("12 loops", "loops")
        assert count == 12


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_add_result_tracks_mismatches(self) -> None:
        """Adding mismatched result updates state."""
        result = VerificationResult(total_checked=0)
        mismatch = CountResult(
            category="commands",
            actual=35,
            documented=34,
            file="README.md",
            line=10,
            matches=False,
        )

        result.add_result(mismatch)

        assert not result.all_match
        assert len(result.mismatches) == 1
        assert result.mismatches[0].category == "commands"

    def test_add_result_matching(self) -> None:
        """Adding matched result doesn't change all_match."""
        result = VerificationResult(total_checked=0)
        match = CountResult(
            category="commands",
            actual=34,
            documented=34,
            file="README.md",
            line=10,
            matches=True,
        )

        result.add_result(match)

        assert result.all_match
        assert len(result.mismatches) == 0


class TestFormatResultText:
    """Tests for format_result_text function."""

    def test_format_all_match(self) -> None:
        """Format when all counts match."""
        result = VerificationResult(total_checked=3, all_match=True)

        output = format_result_text(result)

        assert "All 3 count(s) match" in output
        assert "✓" in output

    def test_format_with_mismatches(self) -> None:
        """Format with mismatched counts."""
        result = VerificationResult(total_checked=3, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_text(result)

        assert "1 mismatch" in output
        assert "commands:" in output
        assert "documented=34, actual=35" in output
        assert "README.md:10" in output


class TestFormatResultJson:
    """Tests for format_result_json function."""

    def test_format_valid_json(self) -> None:
        """Output is valid JSON."""
        import json

        result = VerificationResult(total_checked=2, all_match=True)

        output = format_result_json(result)

        data = json.loads(output)
        assert data["all_match"] is True
        assert data["total_checked"] == 2

    def test_format_includes_mismatches(self) -> None:
        """JSON includes mismatch details."""
        import json

        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_json(result)
        data = json.loads(output)

        assert len(data["mismatches"]) == 1
        assert data["mismatches"][0]["category"] == "commands"
        assert data["mismatches"][0]["actual"] == 35


class TestFormatResultMarkdown:
    """Tests for format_result_markdown function."""

    def test_format_all_match_markdown(self) -> None:
        """Format markdown when all counts match."""
        result = VerificationResult(total_checked=3, all_match=True)

        output = format_result_markdown(result)

        assert "# Documentation Count Verification" in output
        assert "All Counts Match" in output
        assert "✅" in output

    def test_format_with_mismatches_table(self) -> None:
        """Format markdown with mismatches table."""
        result = VerificationResult(total_checked=3, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=10,
                matches=False,
            )
        )

        output = format_result_markdown(result)

        assert "| Category | Documented | Actual |" in output
        assert "| commands | 34 | 35 |" in output
        assert "`README.md:10`" in output


class TestFixCounts:
    """Tests for fix_counts function."""

    def test_fix_replaces_count(self, tmp_path: Path) -> None:
        """Fix replaces incorrect count with actual."""
        # Create test file with wrong count
        test_file = tmp_path / "README.md"
        test_file.write_text("## 34 commands\n")

        # Create result with mismatch
        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,  # Actual count
                documented=34,  # Documented (wrong)
                file="README.md",
                line=1,
                matches=False,
            )
        )

        # Fix
        fix_result = fix_counts(tmp_path, result)

        # Verify
        assert fix_result.fixed_count == 1
        assert len(fix_result.files_modified) == 1

        updated = test_file.read_text()
        assert "35 commands" in updated
        assert "34 commands" not in updated

    def test_fix_preserves_line_format(self, tmp_path: Path) -> None:
        """Fix preserves surrounding text and format."""
        test_file = tmp_path / "README.md"
        test_file.write_text("- **34 slash commands** for workflows\n")

        result = VerificationResult(total_checked=1, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=1,
                matches=False,
            )
        )

        fix_counts(tmp_path, result)

        updated = test_file.read_text()
        assert "- **35 slash commands** for workflows" in updated

    def test_fix_multiple_mismatches_same_file(self, tmp_path: Path) -> None:
        """Fix multiple mismatches in the same file."""
        test_file = tmp_path / "README.md"
        test_file.write_text("## 34 commands\n## 8 agents\n")

        result = VerificationResult(total_checked=2, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=1,
                matches=False,
            )
        )
        result.mismatches.append(
            CountResult(
                category="agents",
                actual=9,
                documented=8,
                file="README.md",
                line=2,
                matches=False,
            )
        )

        fix_result = fix_counts(tmp_path, result)

        assert fix_result.fixed_count == 2
        updated = test_file.read_text()
        assert "35 commands" in updated
        assert "9 agents" in updated

    def test_fix_multiple_files(self, tmp_path: Path) -> None:
        """Fix mismatches across multiple files."""
        readme = tmp_path / "README.md"
        readme.write_text("## 34 commands\n")

        contributing = tmp_path / "CONTRIBUTING.md"
        contributing.write_text("## 8 agents\n")

        result = VerificationResult(total_checked=2, all_match=False)
        result.mismatches.append(
            CountResult(
                category="commands",
                actual=35,
                documented=34,
                file="README.md",
                line=1,
                matches=False,
            )
        )
        result.mismatches.append(
            CountResult(
                category="agents",
                actual=9,
                documented=8,
                file="CONTRIBUTING.md",
                line=1,
                matches=False,
            )
        )

        fix_result = fix_counts(tmp_path, result)

        assert fix_result.fixed_count == 2
        assert len(fix_result.files_modified) == 2
        assert "README.md" in fix_result.files_modified
        assert "CONTRIBUTING.md" in fix_result.files_modified

    def test_fix_no_changes_when_all_match(self, tmp_path: Path) -> None:
        """No changes made when all counts match."""
        test_file = tmp_path / "README.md"
        original_content = "## 34 commands\n"
        test_file.write_text(original_content)

        result = VerificationResult(total_checked=1, all_match=True)

        fix_result = fix_counts(tmp_path, result)

        assert fix_result.fixed_count == 0
        assert len(fix_result.files_modified) == 0
        assert test_file.read_text() == original_content


class TestVerifyDocumentation:
    """Integration tests for verify_documentation function."""

    def test_verify_with_all_counts_matching(self, tmp_path: Path) -> None:
        """Verify returns all_match when counts are correct."""
        # Create directories with files
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        for i in range(3):
            (commands_dir / f"cmd{i}.md").write_text(f"# Command {i}")

        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        for i in range(2):
            (agents_dir / f"agent{i}.md").write_text(f"# Agent {i}")

        # Create documentation with correct counts
        readme = tmp_path / "README.md"
        readme.write_text("## 3 commands\n## 2 agents\n")

        result = verify_documentation(tmp_path)

        assert result.all_match is True
        assert result.total_checked == 2
        assert len(result.mismatches) == 0

    def test_verify_detects_mismatches(self, tmp_path: Path) -> None:
        """Verify detects when documented counts don't match."""
        # Create directories with files
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        for i in range(5):
            (commands_dir / f"cmd{i}.md").write_text(f"# Command {i}")

        # Create documentation with wrong count
        readme = tmp_path / "README.md"
        readme.write_text("## 3 commands\n")

        result = verify_documentation(tmp_path)

        assert result.all_match is False
        assert result.total_checked == 1
        assert len(result.mismatches) == 1
        assert result.mismatches[0].category == "commands"
        assert result.mismatches[0].documented == 3
        assert result.mismatches[0].actual == 5

    def test_verify_skips_nonexistent_doc_files(self, tmp_path: Path) -> None:
        """Verify gracefully handles missing documentation files."""
        # Create directories but no documentation files
        commands_dir = tmp_path / "commands"
        commands_dir.mkdir()
        (commands_dir / "cmd1.md").write_text("# Command 1")

        result = verify_documentation(tmp_path)

        # Should not crash, just return empty result
        assert result.total_checked == 0
        assert result.all_match is True

    def test_verify_with_skills_subdirectories(self, tmp_path: Path) -> None:
        """Verify correctly counts skills in subdirectories."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for i in range(3):
            skill_dir = skills_dir / f"skill{i}"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(f"# Skill {i}")

        readme = tmp_path / "README.md"
        readme.write_text("## 3 skills\n")

        result = verify_documentation(tmp_path)

        assert result.all_match is True
        assert result.total_checked == 1

    def test_verify_detects_loops_mismatch(self, tmp_path: Path) -> None:
        """Verify detects when documented loop count doesn't match actual."""
        loops_dir = tmp_path / "scripts" / "little_loops" / "loops"
        loops_dir.mkdir(parents=True)
        for i in range(3):
            (loops_dir / f"loop{i}.yaml").write_text(
                f"name: loop{i}\ninitial: start\nstates:\n  start:\n    terminal: true\n"
            )

        readme = tmp_path / "README.md"
        readme.write_text("## 5 FSM loops\n")

        result = verify_documentation(tmp_path)

        assert result.all_match is False
        assert any(m.category == "loops" for m in result.mismatches)
        loops_mismatch = next(m for m in result.mismatches if m.category == "loops")
        assert loops_mismatch.documented == 5
        assert loops_mismatch.actual == 3

    def test_verify_loops_recursive_excludes_fragments(self, tmp_path: Path) -> None:
        """verify_documentation() walks loops/ recursively but excludes fragments.

        Regression guard for BUG-1633: a non-recursive glob silently missed
        nested runnable loops (e.g. loops/oracles/oracle-capture-issue.yaml),
        making the verifier rubber-stamp stale README counts.
        """
        loops_dir = tmp_path / "scripts" / "little_loops" / "loops"
        loops_dir.mkdir(parents=True)
        # Two runnable top-level loops
        for i in range(2):
            (loops_dir / f"loop{i}.yaml").write_text(
                f"name: loop{i}\ninitial: start\nstates:\n  start:\n    terminal: true\n"
            )
        # One runnable nested loop under oracles/
        oracles_dir = loops_dir / "oracles"
        oracles_dir.mkdir()
        (oracles_dir / "oracle1.yaml").write_text(
            "name: oracle1\ninitial: start\nstates:\n  start:\n    terminal: true\n"
        )
        # Two library fragments under lib/ — missing initial:/states:, must NOT count
        lib_dir = loops_dir / "lib"
        lib_dir.mkdir()
        (lib_dir / "fragment-a.yaml").write_text("name: fragment-a\n")
        (lib_dir / "fragment-b.yaml").write_text("name: fragment-b\n")

        readme = tmp_path / "README.md"
        readme.write_text("## 3 FSM loops\n")  # matches 2 top-level + 1 oracle

        result = verify_documentation(tmp_path)

        assert result.all_match is True
        loops_results = [m for m in result.mismatches if m.category == "loops"]
        assert loops_results == []

    def test_verify_skills_excludes_bridge_skills(self, tmp_path: Path) -> None:
        """Skill count excludes bridge skills (auto-generated from commands/)."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # Two canonical skills
        for i in range(2):
            d = skills_dir / f"real-skill{i}"
            d.mkdir()
            (d / "SKILL.md").write_text(f"# Skill {i}")
        # One bridge skill (should not be counted)
        bridge_dir = skills_dir / "bridge-skill"
        bridge_dir.mkdir()
        (bridge_dir / "SKILL.md").write_text(f"{BRIDGE_MARKER}some-command.md`\n# Bridge")

        readme = tmp_path / "README.md"
        readme.write_text("## 2 skills\n")

        result = verify_documentation(tmp_path)

        assert result.all_match is True
        assert result.total_checked == 1


class TestCheckSkillBudget:
    """Tests for check_skill_budget function."""

    def _make_skill(
        self, skills_dir: Path, name: str, description: str, disable_model_invocation: bool = False
    ) -> None:
        skill_dir = skills_dir / name
        skill_dir.mkdir()
        flag_line = "disable-model-invocation: true\n" if disable_model_invocation else ""
        (skill_dir / "SKILL.md").write_text(
            f"---\n{flag_line}description: {description}\n---\n# {name}\n"
        )

    def test_skips_disable_model_invocation_skills(self, tmp_path: Path) -> None:
        """Skills with disable-model-invocation: true are excluded from the budget count."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        self._make_skill(skills_dir, "normal-skill", "A normal skill description")
        self._make_skill(
            skills_dir,
            "gated-skill",
            "A gated skill that should be skipped",
            disable_model_invocation=True,
        )

        result: SkillBudgetResult = check_skill_budget(base_dir=tmp_path)

        included_descs = [d for _, d, _ in result.skill_breakdown]
        assert "A normal skill description" in included_descs
        assert "A gated skill that should be skipped" not in included_descs

    def test_counts_tokens_for_enabled_skills(self, tmp_path: Path) -> None:
        """Token count is based only on enabled skills."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        description = "x" * 40  # 40 chars = 10 tokens
        self._make_skill(skills_dir, "skill-a", description)
        self._make_skill(skills_dir, "skill-b", "should not count", disable_model_invocation=True)

        result = check_skill_budget(base_dir=tmp_path)

        assert result.total_tokens == 10
        assert len(result.skill_breakdown) == 1

    def test_empty_skills_dir(self, tmp_path: Path) -> None:
        """Returns zero budget with no skills directory."""
        result = check_skill_budget(base_dir=tmp_path)
        assert result.total_tokens == 0
        assert result.under_budget is True

    def test_block_scalar_description_parsed_correctly(self, tmp_path: Path) -> None:
        """Block-scalar `description: |` is resolved to its string content, not '|'."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "block-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "description: |\n"
            "  Real multi-line content here\n"
            "  Trigger keywords: foo\n"
            "---\n"
            "# block-skill\n"
        )

        result: SkillBudgetResult = check_skill_budget(base_dir=tmp_path)

        assert len(result.skill_breakdown) == 1
        _, desc, tokens = result.skill_breakdown[0]
        assert desc != "|"  # regression guard: old parser returned literal "|"
        assert "Real multi-line content" in desc
        assert tokens > 0
