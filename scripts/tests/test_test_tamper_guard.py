"""Tests for little_loops.test_tamper_guard: guard core (ENH-2933).

Tests cover:
- snapshot_test_paths hashing (present/missing paths)
- compare_snapshots finding-kind detection (modified/deleted/added)
- resolved_pytest_config_paths priority order across config file kinds
- resolved_pytest_config_targets / hash_config_target section-scoped
  comparison for multi-purpose config files (BUG-2957)
- apply_tamper_policy's revert/fail/allow matrix (tracked vs untracked)
- run_tamper_guard end-to-end scenarios (commented-out assertion, skip
  marker, deleted/added test file, untouched tests, config-only tamper,
  pyproject.toml section-scoped tamper)
- the fsm/issue_manager/worker_pool/work_verification import boundary
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from little_loops.test_tamper_guard import (
    DEFAULT_TAMPER_POLICY,
    ConfigTarget,
    TamperFinding,
    TamperPolicy,
    TamperReport,
    TamperSnapshot,
    TestStrength,
    apply_tamper_policy,
    compare_snapshots,
    filter_weakening_findings,
    hash_config_target,
    is_weakening,
    measure_test_strength,
    read_paths_at_ref,
    resolved_pytest_config_paths,
    resolved_pytest_config_targets,
    run_tamper_guard,
    snapshot_test_paths,
    snapshot_test_paths_at_ref,
    tamper_guard_candidate_paths,
    tamper_guard_changed_files,
)
from tests.helpers import copy_git_template

MODULE_PATH = Path(__file__).parent.parent / "little_loops" / "test_tamper_guard.py"


def _config_with_patterns(patterns: list[str]) -> SimpleNamespace:
    return SimpleNamespace(project=SimpleNamespace(test_patterns=patterns))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> Path:
    copy_git_template(path)
    return path


class TestTypes:
    def test_types_defined_per_program_design(self) -> None:
        assert TamperPolicy is not None
        finding = TamperFinding(path="tests/test_x.py", kind="modified", is_config=False)
        assert finding.path == "tests/test_x.py"
        assert finding.kind == "modified"
        assert finding.is_config is False

        report = TamperReport(policy="fail", findings=[finding], reverted=[], passed=False)
        assert report.findings == [finding]

        snap: TamperSnapshot = {"a.py": "abc123", "b.py": None}
        assert snap["b.py"] is None

    def test_default_policy_is_fail(self) -> None:
        assert DEFAULT_TAMPER_POLICY == "fail"


class TestSnapshotTestPaths:
    def test_hashes_existing_file_content(self, tmp_path: Path) -> None:
        (tmp_path / "test_x.py").write_text("def test_x(): assert True\n")
        snap = snapshot_test_paths(["test_x.py"], tmp_path)
        assert snap["test_x.py"] is not None
        assert len(snap["test_x.py"]) == 64  # sha256 hex digest length

    def test_missing_path_snapshots_as_none(self, tmp_path: Path) -> None:
        snap = snapshot_test_paths(["nope.py"], tmp_path)
        assert snap["nope.py"] is None

    def test_identical_content_hashes_equal(self, tmp_path: Path) -> None:
        (tmp_path / "test_x.py").write_text("def test_x(): assert True\n")
        first = snapshot_test_paths(["test_x.py"], tmp_path)
        second = snapshot_test_paths(["test_x.py"], tmp_path)
        assert first == second


class TestCompareSnapshots:
    def test_unchanged_file_produces_no_finding(self) -> None:
        before: TamperSnapshot = {"test_x.py": "hash1"}
        after: TamperSnapshot = {"test_x.py": "hash1"}
        assert compare_snapshots(before, after) == []

    def test_modified_file_detected(self) -> None:
        before: TamperSnapshot = {"test_x.py": "hash1"}
        after: TamperSnapshot = {"test_x.py": "hash2"}
        findings = compare_snapshots(before, after)
        assert len(findings) == 1
        assert findings[0].path == "test_x.py"
        assert findings[0].kind == "modified"

    def test_deleted_file_detected(self) -> None:
        before: TamperSnapshot = {"test_x.py": "hash1"}
        after: TamperSnapshot = {"test_x.py": None}
        findings = compare_snapshots(before, after)
        assert findings[0].kind == "deleted"

    def test_added_file_detected(self) -> None:
        before: TamperSnapshot = {"test_x.py": None}
        after: TamperSnapshot = {"test_x.py": "hash1"}
        findings = compare_snapshots(before, after)
        assert findings[0].kind == "added"

    def test_finding_default_is_config_false(self) -> None:
        before: TamperSnapshot = {"test_x.py": "hash1"}
        after: TamperSnapshot = {"test_x.py": "hash2"}
        assert compare_snapshots(before, after)[0].is_config is False


class TestResolvedPytestConfigPaths:
    def test_pytest_ini_takes_priority(self, tmp_path: Path) -> None:
        (tmp_path / "pytest.ini").write_text("[pytest]\n")
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
        )
        assert resolved_pytest_config_paths(tmp_path) == ["pytest.ini"]

    def test_pyproject_ini_options_detected(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
        )
        assert resolved_pytest_config_paths(tmp_path) == ["pyproject.toml"]

    def test_pyproject_without_ini_options_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
        assert resolved_pytest_config_paths(tmp_path) == []

    def test_tox_ini_pytest_section_detected(self, tmp_path: Path) -> None:
        (tmp_path / "tox.ini").write_text("[pytest]\ntestpaths = tests\n")
        assert resolved_pytest_config_paths(tmp_path) == ["tox.ini"]

    def test_setup_cfg_tool_pytest_section_detected(self, tmp_path: Path) -> None:
        (tmp_path / "setup.cfg").write_text("[tool:pytest]\ntestpaths = tests\n")
        assert resolved_pytest_config_paths(tmp_path) == ["setup.cfg"]

    def test_no_config_files_returns_empty(self, tmp_path: Path) -> None:
        assert resolved_pytest_config_paths(tmp_path) == []


class TestResolvedPytestConfigTargets:
    """BUG-2957: section-aware successor to resolved_pytest_config_paths."""

    def test_pytest_ini_has_no_section(self, tmp_path: Path) -> None:
        (tmp_path / "pytest.ini").write_text("[pytest]\n")
        targets = resolved_pytest_config_targets(tmp_path)
        assert targets == [ConfigTarget(path="pytest.ini", section=None)]

    def test_pyproject_ini_options_gets_section(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
        )
        targets = resolved_pytest_config_targets(tmp_path)
        assert targets == [
            ConfigTarget(path="pyproject.toml", section=("tool", "pytest", "ini_options"))
        ]

    def test_tox_ini_has_no_section(self, tmp_path: Path) -> None:
        (tmp_path / "tox.ini").write_text("[pytest]\ntestpaths = tests\n")
        targets = resolved_pytest_config_targets(tmp_path)
        assert targets == [ConfigTarget(path="tox.ini", section=None)]

    def test_setup_cfg_has_no_section(self, tmp_path: Path) -> None:
        (tmp_path / "setup.cfg").write_text("[tool:pytest]\ntestpaths = tests\n")
        assert resolved_pytest_config_targets(tmp_path) == [
            ConfigTarget(path="setup.cfg", section=None)
        ]

    def test_no_config_files_returns_empty(self, tmp_path: Path) -> None:
        assert resolved_pytest_config_targets(tmp_path) == []

    def test_paths_wrapper_matches_targets(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
        )
        targets = resolved_pytest_config_targets(tmp_path)
        assert resolved_pytest_config_paths(tmp_path) == [t.path for t in targets]


class TestHashConfigTarget:
    """BUG-2957: section-scoped hashing so unrelated pyproject.toml edits don't trip."""

    def test_no_section_hashes_whole_source(self) -> None:
        target = ConfigTarget(path="pytest.ini", section=None)
        source = "[pytest]\ntestpaths = tests\n"
        assert hash_config_target(source, target) == hash_config_target(source, target)
        assert hash_config_target(source, target) != hash_config_target(source + "x", target)

    def test_edit_outside_section_does_not_change_hash(self) -> None:
        target = ConfigTarget(path="pyproject.toml", section=("tool", "pytest", "ini_options"))
        before = (
            '[project]\nversion = "1.0.0"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        after = '[project]\nversion = "1.0.1"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        assert hash_config_target(before, target) == hash_config_target(after, target)

    def test_edit_inside_section_changes_hash(self) -> None:
        target = ConfigTarget(path="pyproject.toml", section=("tool", "pytest", "ini_options"))
        before = (
            '[project]\nversion = "1.0.0"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        after = (
            '[project]\nversion = "1.0.0"\n\n'
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\naddopts = "-p no:randomly"\n'
        )
        assert hash_config_target(before, target) != hash_config_target(after, target)

    def test_unparseable_toml_falls_back_to_whole_source(self) -> None:
        target = ConfigTarget(path="pyproject.toml", section=("tool", "pytest", "ini_options"))
        before = "not valid toml [[["
        after = "not valid toml [[[ either"
        assert hash_config_target(before, target) != hash_config_target(after, target)
        assert hash_config_target(before, target) == hash_config_target(before, target)

    def test_missing_section_falls_back_to_whole_source(self) -> None:
        target = ConfigTarget(path="pyproject.toml", section=("tool", "pytest", "ini_options"))
        source = "[tool.ruff]\nline-length = 100\n"
        assert hash_config_target(source, target) == hash_config_target(source, target)
        assert hash_config_target(source, target) != hash_config_target(source + "x", target)


class TestSnapshotTestPathsAtRef:
    """ENH-2935: reconstructing "before" from git history for the non-FSM path."""

    def test_hashes_content_at_ref(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        (repo / "test_x.py").write_text("def test_x(): pass\n")

        at_head = snapshot_test_paths_at_ref(repo, "HEAD", ["test_x.py"])
        on_disk = snapshot_test_paths(["test_x.py"], repo)
        assert at_head["test_x.py"] != on_disk["test_x.py"]

    def test_path_absent_at_ref_maps_to_none(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "README.md").write_text("hi\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "init")

        snap = snapshot_test_paths_at_ref(repo, "HEAD", ["test_new.py"])
        assert snap["test_new.py"] is None


class TestTamperGuardCandidatePaths:
    """ENH-2935: shared enumeration used by both the FSM and non-FSM adapters."""

    def test_finds_tracked_test_files(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "tests").mkdir()
        (repo / "tests" / "test_x.py").write_text("def test_x(): assert True\n")
        (repo / "README.md").write_text("hi\n")
        _git(repo, "add", "tests/test_x.py", "README.md")
        _git(repo, "commit", "-m", "init")

        paths = tamper_guard_candidate_paths(repo)
        assert "tests/test_x.py" in paths
        assert "README.md" not in paths

    def test_includes_untracked_test_files(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "README.md").write_text("hi\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "init")
        (repo / "tests").mkdir()
        (repo / "tests" / "test_new.py").write_text("def test_new(): assert True\n")

        paths = tamper_guard_candidate_paths(repo)
        assert "tests/test_new.py" in paths


class TestTamperGuardChangedFiles:
    """ENH-2935: shared changed-files enumeration used by both adapters."""

    def test_detects_modified_and_untracked(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        (repo / "test_x.py").write_text("def test_x(): pass\n")
        (repo / "test_new.py").write_text("def test_new(): assert True\n")

        changed = tamper_guard_changed_files(repo)
        assert "test_x.py" in changed
        assert "test_new.py" in changed

    def test_no_changes_returns_empty(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "README.md").write_text("hi\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "init")

        assert tamper_guard_changed_files(repo) == []


class TestApplyTamperPolicy:
    def test_no_findings_always_passes(self, tmp_path: Path) -> None:
        for policy in ("revert", "fail", "allow"):
            report = apply_tamper_policy(policy, [], tmp_path)
            assert report.passed is True
            assert report.findings == []
            assert report.reverted == []

    def test_allow_never_mutates_and_always_passes(self, tmp_path: Path) -> None:
        finding = TamperFinding(path="test_x.py", kind="modified")
        report = apply_tamper_policy("allow", [finding], tmp_path)
        assert report.passed is True
        assert report.reverted == []
        assert report.findings == [finding]

    def test_fail_reports_without_mutating(self, tmp_path: Path) -> None:
        (tmp_path / "test_x.py").write_text("tampered\n")
        finding = TamperFinding(path="test_x.py", kind="modified")
        report = apply_tamper_policy("fail", [finding], tmp_path)
        assert report.passed is False
        assert report.reverted == []
        assert (tmp_path / "test_x.py").read_text() == "tampered\n"

    def test_revert_restores_tracked_modified_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        (repo / "test_x.py").write_text("def test_x(): pass  # tampered\n")
        finding = TamperFinding(path="test_x.py", kind="modified")
        report = apply_tamper_policy("revert", [finding], repo)

        assert report.reverted == ["test_x.py"]
        assert report.passed is True
        assert (repo / "test_x.py").read_text() == "def test_x(): assert True\n"

    def test_revert_restores_tracked_deleted_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        (repo / "test_x.py").unlink()
        finding = TamperFinding(path="test_x.py", kind="deleted")
        report = apply_tamper_policy("revert", [finding], repo)

        assert report.reverted == ["test_x.py"]
        assert report.passed is True
        assert (repo / "test_x.py").exists()

    def test_revert_never_touches_added_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_new.py").write_text("def test_new(): assert True\n")
        finding = TamperFinding(path="test_new.py", kind="added")
        report = apply_tamper_policy("revert", [finding], repo)

        assert report.reverted == []
        assert (repo / "test_new.py").exists()
        assert report.passed is True  # nothing revertable; added is out of scope here

    def test_revert_cannot_restore_untracked_modified_file(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_untracked.py").write_text("original\n")
        # Never added/committed -- untracked from git's perspective.
        finding = TamperFinding(path="test_untracked.py", kind="modified")
        report = apply_tamper_policy("revert", [finding], repo)

        assert report.reverted == []
        assert report.passed is False
        assert finding in report.findings

    def test_revert_reports_findings_regardless_of_success(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("original\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")
        (repo / "test_x.py").write_text("tampered\n")

        finding = TamperFinding(path="test_x.py", kind="modified", is_config=True)
        report = apply_tamper_policy("revert", [finding], repo)
        assert finding in report.findings
        assert finding.is_config is True


class TestRunTamperGuard:
    def test_untouched_tests_produce_no_findings(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["test_x.py"], repo)

        report = run_tamper_guard(before, [], config, "fail", repo)
        assert report.findings == []
        assert report.passed is True

    def test_commented_out_assertion_detected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x():\n    assert 1 == 1\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["test_x.py"], repo)

        (repo / "test_x.py").write_text("def test_x():\n    pass  # assert 1 == 1\n")

        report = run_tamper_guard(before, ["test_x.py"], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.findings[0].kind == "modified"
        assert report.passed is False

    def test_added_skip_marker_detected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x():\n    assert 1 == 1\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["test_x.py"], repo)

        (repo / "test_x.py").write_text(
            "import pytest\n\n\n@pytest.mark.skip\ndef test_x():\n    assert 1 == 1\n"
        )

        report = run_tamper_guard(before, ["test_x.py"], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.findings[0].kind == "modified"

    def test_deleted_test_file_detected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["test_x.py"], repo)
        (repo / "test_x.py").unlink()

        report = run_tamper_guard(before, ["test_x.py"], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.findings[0].kind == "deleted"

    def test_newly_added_test_file_detected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "README.md").write_text("hi\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "init")

        config = _config_with_patterns(["test_*.py"])
        before = snapshot_test_paths([], repo)
        (repo / "test_new.py").write_text("def test_new(): assert True\n")

        report = run_tamper_guard(before, ["test_new.py"], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.findings[0].kind == "added"
        assert report.findings[0].path == "test_new.py"

    def test_config_only_tamper_marked_is_config(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "pytest.ini").write_text("[pytest]\n")
        _git(repo, "add", "pytest.ini")
        _git(repo, "commit", "-m", "add pytest config")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["pytest.ini"], repo)
        (repo / "pytest.ini").write_text("[pytest]\naddopts = --deselect test_x.py::test_x\n")

        report = run_tamper_guard(before, [], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.findings[0].is_config is True
        assert report.findings[0].path == "pytest.ini"

    def test_pyproject_version_bump_does_not_trip(self, tmp_path: Path) -> None:
        """BUG-2957: an unrelated edit to pyproject.toml must not veto completion."""
        repo = _init_repo(tmp_path / "repo")
        (repo / "pyproject.toml").write_text(
            '[project]\nversion = "1.0.0"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        _git(repo, "add", "pyproject.toml")
        _git(repo, "commit", "-m", "add pyproject config")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["pyproject.toml"], repo)
        (repo / "pyproject.toml").write_text(
            '[project]\nversion = "1.0.1"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )

        report = run_tamper_guard(before, [], config, "fail", repo)
        assert report.findings == []
        assert report.passed is True

    def test_pyproject_ini_options_edit_trips(self, tmp_path: Path) -> None:
        """BUG-2957: an edit inside [tool.pytest.ini_options] must still be caught."""
        repo = _init_repo(tmp_path / "repo")
        (repo / "pyproject.toml").write_text(
            '[project]\nversion = "1.0.0"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        _git(repo, "add", "pyproject.toml")
        _git(repo, "commit", "-m", "add pyproject config")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["pyproject.toml"], repo)
        (repo / "pyproject.toml").write_text(
            '[project]\nversion = "1.0.0"\n\n'
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
            'addopts = "-p no:randomly"\n'
        )

        report = run_tamper_guard(before, [], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.findings[0].path == "pyproject.toml"
        assert report.passed is False

    def test_pytest_ini_whole_file_behavior_unchanged(self, tmp_path: Path) -> None:
        """BUG-2957: pytest.ini (no section) keeps whole-file comparison."""
        repo = _init_repo(tmp_path / "repo")
        (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
        _git(repo, "add", "pytest.ini")
        _git(repo, "commit", "-m", "add pytest config")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["pytest.ini"], repo)
        (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n# a comment\n")

        report = run_tamper_guard(before, [], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.findings[0].is_config is True
        assert report.findings[0].path == "pytest.ini"

    def test_unparseable_pyproject_falls_back_to_whole_file(self, tmp_path: Path) -> None:
        """BUG-2957: unparseable TOML fails closed rather than silently passing."""
        repo = _init_repo(tmp_path / "repo")
        (repo / "pyproject.toml").write_text(
            '[project]\nversion = "1.0.0"\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        _git(repo, "add", "pyproject.toml")
        _git(repo, "commit", "-m", "add pyproject config")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["pyproject.toml"], repo)
        (repo / "pyproject.toml").write_text("not valid toml [[[")

        report = run_tamper_guard(before, [], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.findings[0].path == "pyproject.toml"
        assert report.passed is False

    @pytest.mark.parametrize("policy", ["revert", "fail", "allow"])
    def test_report_always_includes_findings_regardless_of_policy(
        self, tmp_path: Path, policy: TamperPolicy
    ) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["test_x.py"], repo)
        (repo / "test_x.py").write_text("def test_x(): pass\n")

        report = run_tamper_guard(before, ["test_x.py"], config, policy, repo)
        assert len(report.findings) == 1
        assert report.policy == policy


class TestMeasureTestStrength:
    """BUG-2954: content-aware strength metric feeding the weakening classifier."""

    def test_non_python_path_returns_none(self) -> None:
        assert measure_test_strength("[pytest]\n", "pytest.ini") is None

    def test_unparseable_source_returns_none(self) -> None:
        assert measure_test_strength("def test_x(:\n    pass\n", "test_x.py") is None

    def test_counts_asserts_test_functions_and_skip_markers(self) -> None:
        source = (
            "import pytest\n\n"
            "def test_a():\n"
            "    assert 1 == 1\n"
            "    assert 2 == 2\n\n"
            "@pytest.mark.skip\n"
            "def test_b():\n"
            "    pytest.skip('nope')\n\n"
            "class T:\n"
            "    def test_c(self):\n"
            "        self.assertEqual(1, 1)\n"
            "        with pytest.raises(ValueError):\n"
            "            raise ValueError\n"
        )
        strength = measure_test_strength(source, "test_x.py")
        assert strength is not None
        assert strength.test_functions == 3
        # 2 asserts + self.assertEqual + pytest.raises = 4
        assert strength.assertions == 4
        # @pytest.mark.skip decorator + pytest.skip(...) call = 2
        assert strength.skip_markers == 2

    def test_xfail_decorator_counts_as_skip_marker(self) -> None:
        source = "import pytest\n\n@pytest.mark.xfail\ndef test_a():\n    assert True\n"
        strength = measure_test_strength(source, "test_x.py")
        assert strength is not None
        assert strength.skip_markers == 1

    def test_skipif_decorator_counts_as_skip_marker(self) -> None:
        """BUG-2954 follow-up: ``skipif`` is the natural way to disable a test
        while looking legitimate, so it must count alongside ``skip``/``xfail``."""
        source = (
            "import pytest\n\n"
            '@pytest.mark.skipif(True, reason="disabled")\n'
            "def test_a():\n"
            "    assert True\n"
        )
        strength = measure_test_strength(source, "test_x.py")
        assert strength is not None
        assert strength.skip_markers == 1

    def test_empty_source_has_zero_counts(self) -> None:
        strength = measure_test_strength("", "test_x.py")
        assert strength == TestStrength(assertions=0, test_functions=0, skip_markers=0)


class TestIsWeakening:
    """BUG-2954: is_weakening discriminates tampering from legitimate additive edits."""

    def test_adding_a_test_case_is_not_weakening(self) -> None:
        before = "def test_a():\n    assert True\n"
        after = "def test_a():\n    assert True\n\ndef test_b():\n    assert True\n"
        assert is_weakening(before, after, "test_x.py") is False

    def test_removing_an_assertion_is_weakening(self) -> None:
        before = "def test_a():\n    assert 1 == 1\n    assert 2 == 2\n"
        after = "def test_a():\n    assert 1 == 1\n"
        assert is_weakening(before, after, "test_x.py") is True

    def test_deleting_a_test_function_is_weakening(self) -> None:
        before = "def test_a():\n    assert True\n\ndef test_b():\n    assert True\n"
        after = "def test_a():\n    assert True\n"
        assert is_weakening(before, after, "test_x.py") is True

    def test_adding_a_skip_marker_is_weakening(self) -> None:
        before = "def test_a():\n    assert True\n"
        after = "import pytest\n\n@pytest.mark.skip\ndef test_a():\n    assert True\n"
        assert is_weakening(before, after, "test_x.py") is True

    def test_adding_a_skipif_marker_is_weakening(self) -> None:
        before = "def test_a():\n    assert True\n"
        after = (
            "import pytest\n\n"
            '@pytest.mark.skipif(True, reason="disabled")\n'
            "def test_a():\n"
            "    assert True\n"
        )
        assert is_weakening(before, after, "test_x.py") is True

    def test_unmeasurable_side_is_conservatively_weakening(self) -> None:
        before = "def test_a():\n    assert True\n"
        after = "def test_a((:\n    pass\n"
        assert is_weakening(before, after, "test_x.py") is True


class TestReadPathsAtRef:
    def test_reads_text_content_at_ref(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        texts = read_paths_at_ref(repo, "HEAD", ["test_x.py"])
        assert texts["test_x.py"] == "def test_x(): assert True\n"

    def test_path_absent_at_ref_maps_to_none(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "README.md").write_text("hi\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-m", "init")

        texts = read_paths_at_ref(repo, "HEAD", ["test_new.py"])
        assert texts["test_new.py"] is None


class TestFilterWeakeningFindings:
    """BUG-2954: the classifier applied by _run_non_fsm_tamper_guard via finding_filter."""

    def test_additive_edit_to_existing_file_is_dropped(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_a():\n    assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")
        (repo / "test_x.py").write_text(
            "def test_a():\n    assert True\n\ndef test_b():\n    assert True\n"
        )

        finding = TamperFinding(path="test_x.py", kind="modified")
        kept = filter_weakening_findings([finding], repo, "HEAD")
        assert kept == []

    def test_weakening_edit_is_kept(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_a():\n    assert 1 == 1\n    assert 2 == 2\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")
        (repo / "test_x.py").write_text("def test_a():\n    assert 1 == 1\n")

        finding = TamperFinding(path="test_x.py", kind="modified")
        kept = filter_weakening_findings([finding], repo, "HEAD")
        assert kept == [finding]

    def test_deleted_finding_always_kept(self, tmp_path: Path) -> None:
        finding = TamperFinding(path="test_x.py", kind="deleted")
        kept = filter_weakening_findings([finding], Path("/nonexistent"), "HEAD")
        assert kept == [finding]

    def test_added_finding_always_dropped(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        finding = TamperFinding(path="test_new.py", kind="added")
        kept = filter_weakening_findings([finding], repo, "HEAD")
        assert kept == []

    def test_config_finding_always_kept(self, tmp_path: Path) -> None:
        finding = TamperFinding(path="pytest.ini", kind="modified", is_config=True)
        kept = filter_weakening_findings([finding], Path("/nonexistent"), "HEAD")
        assert kept == [finding]


class TestRunTamperGuardFindingFilter:
    """BUG-2954: the optional finding_filter hook, and FSM-default preservation."""

    def test_default_finding_filter_is_none_and_unaffected(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["test_x.py"], repo)
        (repo / "test_x.py").write_text("def test_x(): assert True\n\ndef test_y(): assert True\n")

        # No finding_filter passed -> byte-level strictness, same as the FSM adapter.
        report = run_tamper_guard(before, ["test_x.py"], config, "fail", repo)
        assert len(report.findings) == 1
        assert report.passed is False

    def test_finding_filter_drops_additive_edit(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x(): assert True\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["test_x.py"], repo)
        (repo / "test_x.py").write_text("def test_x(): assert True\n\ndef test_y(): assert True\n")

        from functools import partial

        finding_filter = partial(filter_weakening_findings, repo_root=repo, ref="HEAD")
        report = run_tamper_guard(
            before, ["test_x.py"], config, "fail", repo, finding_filter=finding_filter
        )
        assert report.findings == []
        assert report.passed is True

    def test_finding_filter_keeps_weakening_edit(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path / "repo")
        (repo / "test_x.py").write_text("def test_x():\n    assert 1 == 1\n    assert 2 == 2\n")
        _git(repo, "add", "test_x.py")
        _git(repo, "commit", "-m", "add test")

        config = _config_with_patterns(["**/test_*.py"])
        before = snapshot_test_paths(["test_x.py"], repo)
        (repo / "test_x.py").write_text("def test_x():\n    assert 1 == 1\n")

        from functools import partial

        finding_filter = partial(filter_weakening_findings, repo_root=repo, ref="HEAD")
        report = run_tamper_guard(
            before, ["test_x.py"], config, "fail", repo, finding_filter=finding_filter
        )
        assert len(report.findings) == 1
        assert report.passed is False


class TestNoDependencyOnAdapters:
    def test_no_import_of_fsm_issue_manager_or_orchestrator_modules(self) -> None:
        source = MODULE_PATH.read_text()
        tree = ast.parse(source)
        banned_prefixes = (
            "little_loops.fsm",
            "little_loops.issue_manager",
            "little_loops.parallel.worker_pool",
            "little_loops.work_verification",
        )
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(banned_prefixes):
                    offenders.append(node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(banned_prefixes):
                        offenders.append(alias.name)
        assert offenders == [], f"test_tamper_guard.py must not import: {offenders}"
        # Positive assertion: it depends on the intended primitive.
        assert "from little_loops.test_file_patterns import filter_test_files" in source
