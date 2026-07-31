"""Tests for little_loops.test_tamper_guard: guard core (ENH-2933).

Tests cover:
- snapshot_test_paths hashing (present/missing paths)
- compare_snapshots finding-kind detection (modified/deleted/added)
- resolved_pytest_config_paths priority order across config file kinds
- apply_tamper_policy's revert/fail/allow matrix (tracked vs untracked)
- run_tamper_guard end-to-end scenarios (commented-out assertion, skip
  marker, deleted/added test file, untouched tests, config-only tamper)
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
    TamperFinding,
    TamperPolicy,
    TamperReport,
    TamperSnapshot,
    apply_tamper_policy,
    compare_snapshots,
    resolved_pytest_config_paths,
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
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )


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
