"""Tests for prepatch_check.py (ENH-3142)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from little_loops.config.core import BRConfig
from little_loops.prepatch_check import (
    PrePatchCandidate,
    PrePatchEvidence,
    PrePatchTestOutcome,
    _assign_flag,
    _parse_diff,
    _parse_junit,
    collect_candidates,
    run_prepatch_check,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hello\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _commit_file(repo: Path, path: str, content: str) -> str:
    full = repo / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"add {path}")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _diff_for_new_file(path: str, lines: list[str]) -> str:
    body = "\n".join(f"+{line}" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}\n"
    )


class TestParseDiff:
    def test_touched_lines_are_added_lines_only(self) -> None:
        diff = (
            "diff --git a/tests/test_x.py b/tests/test_x.py\n"
            "--- a/tests/test_x.py\n"
            "+++ b/tests/test_x.py\n"
            "@@ -1,3 +1,4 @@\n"
            " context\n"
            "-removed\n"
            "+added one\n"
            "+added two\n"
        )
        touched = _parse_diff(diff)
        assert touched == {"tests/test_x.py": [2, 3]}

    def test_deleted_file_target_is_excluded(self) -> None:
        diff = (
            "diff --git a/tests/test_x.py b/tests/test_x.py\n"
            "--- a/tests/test_x.py\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
            "-gone\n"
            "-also gone\n"
        )
        assert _parse_diff(diff) == {}

    def test_pure_deletion_hunk_maps_to_empty_list(self) -> None:
        diff = (
            "diff --git a/tests/test_x.py b/tests/test_x.py\n"
            "--- a/tests/test_x.py\n"
            "+++ b/tests/test_x.py\n"
            "@@ -1,2 +1,1 @@\n"
            " keep\n"
            "-removed\n"
        )
        assert _parse_diff(diff) == {"tests/test_x.py": []}


class TestCollectCandidatesAddedVsModified:
    def test_new_file_new_function_is_added(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/test_a.py", "")
        (git_repo / "tests" / "test_new.py").write_text("def test_something():\n    assert True\n")
        diff = _diff_for_new_file("tests/test_new.py", ["def test_something():", "    assert True"])
        candidates = collect_candidates(diff, git_repo, base_ref)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.nodeid == "tests/test_new.py::test_something"
        assert c.added is True
        assert c.attribution == "function"

    def test_modified_function_in_existing_file_is_not_added(self, git_repo: Path) -> None:
        base_ref = _commit_file(
            git_repo,
            "tests/test_b.py",
            "def test_thing():\n    assert 1 == 1\n",
        )
        (git_repo / "tests" / "test_b.py").write_text(
            "def test_thing():\n    assert 1 == 1\n    assert True\n"
        )
        diff = (
            "diff --git a/tests/test_b.py b/tests/test_b.py\n"
            "--- a/tests/test_b.py\n"
            "+++ b/tests/test_b.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def test_thing():\n"
            "     assert 1 == 1\n"
            "+    assert True\n"
        )
        candidates = collect_candidates(diff, git_repo, base_ref)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.nodeid == "tests/test_b.py::test_thing"
        assert c.added is False
        assert c.attribution == "function"

    def test_new_function_added_alongside_existing_untouched_function(self, git_repo: Path) -> None:
        base_ref = _commit_file(
            git_repo,
            "tests/test_c.py",
            "def test_untouched():\n    assert True\n",
        )
        (git_repo / "tests" / "test_c.py").write_text(
            "def test_untouched():\n    assert True\n\n\ndef test_fresh():\n    assert True\n"
        )
        diff = (
            "diff --git a/tests/test_c.py b/tests/test_c.py\n"
            "--- a/tests/test_c.py\n"
            "+++ b/tests/test_c.py\n"
            "@@ -1,1 +1,5 @@\n"
            " def test_untouched():\n"
            "     assert True\n"
            "+\n"
            "+\n"
            "+def test_fresh():\n"
            "+    assert True\n"
        )
        candidates = collect_candidates(diff, git_repo, base_ref)
        assert len(candidates) == 1
        assert candidates[0].nodeid == "tests/test_c.py::test_fresh"
        assert candidates[0].added is True

    def test_zero_candidates_when_diff_touches_no_test_files(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "src/foo.py", "x = 1\n")
        diff = (
            "diff --git a/src/foo.py b/src/foo.py\n"
            "--- a/src/foo.py\n"
            "+++ b/src/foo.py\n"
            "@@ -1,1 +1,2 @@\n"
            " x = 1\n"
            "+y = 2\n"
        )
        assert collect_candidates(diff, git_repo, base_ref) == []

    def test_conftest_with_no_test_functions_yields_no_candidate(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/conftest.py", "")
        (git_repo / "tests" / "conftest.py").write_text(
            "import pytest\n\n\ndef fixture_helper():\n    pass\n"
        )
        diff = (
            "diff --git a/tests/conftest.py b/tests/conftest.py\n"
            "--- a/tests/conftest.py\n"
            "+++ b/tests/conftest.py\n"
            "@@ -0,0 +1,4 @@\n"
            "+import pytest\n"
            "+\n"
            "+\n"
            "+def fixture_helper():\n"
            "+    pass\n"
        )
        assert collect_candidates(diff, git_repo, base_ref) == []


class TestCollectCandidatesFallback:
    def test_class_based_test_falls_back_to_file(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/test_placeholder.py", "")
        content = "class TestFoo:\n    def test_bar(self):\n        assert True\n"
        (git_repo / "tests" / "test_d.py").write_text(content)
        diff = _diff_for_new_file(
            "tests/test_d.py",
            ["class TestFoo:", "    def test_bar(self):", "        assert True"],
        )
        candidates = collect_candidates(diff, git_repo, base_ref)
        assert len(candidates) == 1
        assert candidates[0].nodeid == "tests/test_d.py"
        assert candidates[0].attribution == "file-fallback"
        assert candidates[0].added is True

    def test_module_level_edit_outside_any_function_falls_back(self, git_repo: Path) -> None:
        base_ref = _commit_file(
            git_repo,
            "tests/test_e.py",
            "def test_existing():\n    assert True\n",
        )
        (git_repo / "tests" / "test_e.py").write_text(
            "FOO = 1\n\n\ndef test_existing():\n    assert True\n"
        )
        diff = (
            "diff --git a/tests/test_e.py b/tests/test_e.py\n"
            "--- a/tests/test_e.py\n"
            "+++ b/tests/test_e.py\n"
            "@@ -1,2 +1,5 @@\n"
            "+FOO = 1\n"
            "+\n"
            "+\n"
            " def test_existing():\n"
            "     assert True\n"
        )
        candidates = collect_candidates(diff, git_repo, base_ref)
        assert len(candidates) == 1
        assert candidates[0].attribution == "file-fallback"
        assert candidates[0].added is False  # file pre-existed at base_ref


class TestTestFilesContract:
    def test_materializes_post_patch_content_not_base_ref(self, git_repo: Path) -> None:
        from little_loops.prepatch_check import _post_patch_test_files

        _commit_file(git_repo, "tests/test_f.py", "def test_old():\n    pass\n")
        (git_repo / "tests" / "test_f.py").write_text("def test_new():\n    pass\n")
        diff = (
            "diff --git a/tests/test_f.py b/tests/test_f.py\n"
            "--- a/tests/test_f.py\n"
            "+++ b/tests/test_f.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-def test_old():\n"
            "+def test_new():\n"
            "     pass\n"
        )
        config = BRConfig(git_repo)
        files = _post_patch_test_files(diff, git_repo, config)
        assert files == {"tests/test_f.py": "def test_new():\n    pass\n"}

    def test_touched_conftest_is_included(self, git_repo: Path) -> None:
        from little_loops.prepatch_check import _post_patch_test_files

        _commit_file(git_repo, "tests/conftest.py", "")
        (git_repo / "tests" / "conftest.py").write_text("import pytest\n")
        diff = (
            "diff --git a/tests/conftest.py b/tests/conftest.py\n"
            "--- a/tests/conftest.py\n"
            "+++ b/tests/conftest.py\n"
            "@@ -0,0 +1,1 @@\n"
            "+import pytest\n"
        )
        config = BRConfig(git_repo)
        files = _post_patch_test_files(diff, git_repo, config)
        assert files == {"tests/conftest.py": "import pytest\n"}


class TestJunitParsing:
    def _write_junit(self, path: Path, xml_body: str) -> None:
        path.write_text(xml_body)

    def test_passing_testcase(self, tmp_path: Path) -> None:
        xml = (
            '<?xml version="1.0"?>\n'
            '<testsuites><testsuite><testcase classname="tests.test_x" '
            'name="test_ok" file="tests/test_x.py" line="1" time="0.01"/>'
            "</testsuite></testsuites>"
        )
        path = tmp_path / "j.xml"
        self._write_junit(path, xml)
        results = _parse_junit(path)
        assert results == {"tests/test_x.py::test_ok": ("pass", None)}

    def test_failure_is_fail(self, tmp_path: Path) -> None:
        xml = (
            '<?xml version="1.0"?>\n'
            '<testsuites><testsuite><testcase classname="tests.test_x" '
            'name="test_bad" file="tests/test_x.py" line="1">'
            '<failure message="assert 1 == 2">boom</failure>'
            "</testcase></testsuite></testsuites>"
        )
        path = tmp_path / "j.xml"
        self._write_junit(path, xml)
        results = _parse_junit(path)
        assert results["tests/test_x.py::test_bad"] == ("fail", None)

    def test_error_is_error_with_collection_kind(self, tmp_path: Path) -> None:
        xml = (
            '<?xml version="1.0"?>\n'
            '<testsuites><testsuite><testcase classname="tests.test_x" '
            'name="test_imp" file="tests/test_x.py" line="1">'
            '<error message="ModuleNotFoundError: no module">trace</error>'
            "</testcase></testsuite></testsuites>"
        )
        path = tmp_path / "j.xml"
        self._write_junit(path, xml)
        results = _parse_junit(path)
        assert results["tests/test_x.py::test_imp"] == ("error", "collection")

    def test_error_is_error_with_infrastructure_kind(self, tmp_path: Path) -> None:
        xml = (
            '<?xml version="1.0"?>\n'
            '<testsuites><testsuite><testcase classname="tests.test_x" '
            'name="test_fx" file="tests/test_x.py" line="1">'
            '<error message="fixture not found: some_fixture">trace</error>'
            "</testcase></testsuite></testsuites>"
        )
        path = tmp_path / "j.xml"
        self._write_junit(path, xml)
        results = _parse_junit(path)
        assert results["tests/test_x.py::test_fx"] == ("error", "infrastructure")

    def test_missing_xml_returns_empty(self, tmp_path: Path) -> None:
        assert _parse_junit(tmp_path / "missing.xml") == {}

    def test_truncated_xml_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "j.xml"
        path.write_text("<testsuites><testsuite><testcase")
        assert _parse_junit(path) == {}


class TestFlagAssignment:
    def test_added_and_pass_is_hard(self) -> None:
        flag, reason = _assign_flag(
            added=True, category="pass", modified_hard=False, base_dirty=None
        )
        assert flag == "hard"
        assert reason

    def test_modified_and_pass_is_soft_by_default(self) -> None:
        flag, reason = _assign_flag(
            added=False, category="pass", modified_hard=False, base_dirty=None
        )
        assert flag == "soft"
        assert reason

    def test_modified_and_pass_is_hard_when_modified_hard_enabled(self) -> None:
        flag, reason = _assign_flag(
            added=False, category="pass", modified_hard=True, base_dirty=None
        )
        assert flag == "hard"

    def test_flaky_is_soft(self) -> None:
        flag, reason = _assign_flag(
            added=True, category="flaky", modified_hard=False, base_dirty=None
        )
        assert flag == "soft"
        assert reason

    def test_hard_downgraded_to_soft_when_base_dirty(self) -> None:
        flag, reason = _assign_flag(
            added=True, category="pass", modified_hard=False, base_dirty=True
        )
        assert flag == "soft"
        assert reason
        assert "dirty" in reason

    def test_fail_and_error_are_no_flag(self) -> None:
        for category in ("fail", "error", "timeout"):
            flag, reason = _assign_flag(
                added=True, category=category, modified_hard=False, base_dirty=None
            )
            assert flag == "none"
            assert reason is None


class TestRunPrepatchCheckArgvAndEnv:
    """Assert on the captured subprocess.run call; no real pytest run needed."""

    def _base_kwargs(self, git_repo: Path, base_ref: str, step_diff: str) -> dict:
        logger = MagicMock()
        git_lock = MagicMock()
        return {
            "step_diff": step_diff,
            "repo_root": git_repo,
            "worktree_base": ".worktrees",
            "base_sha": base_ref,
            "base_dirty": None,
            "base_branch": "main",
            "logger": logger,
            "git_lock": git_lock,
        }

    def test_disabled_by_config_records_skipped_reason(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/test_g.py", "")
        diff = _diff_for_new_file("tests/test_g.py", ["def test_x():", "    assert True"])
        config = BRConfig(git_repo)
        assert config.prepatch_check.enabled is False
        evidence = run_prepatch_check(config=config, **self._base_kwargs(git_repo, base_ref, diff))
        assert evidence.verdict == "skipped"
        assert evidence.skipped_reason == "pre-patch check skipped by config"
        assert evidence.base_source == "dequeue-stamp"

    def test_zero_candidates_records_skipped_reason(self, git_repo: Path, tmp_path: Path) -> None:
        base_ref = _commit_file(git_repo, "src/foo.py", "x = 1\n")
        diff = (
            "diff --git a/src/foo.py b/src/foo.py\n"
            "--- a/src/foo.py\n"
            "+++ b/src/foo.py\n"
            "@@ -1,1 +1,2 @@\n"
            " x = 1\n"
            "+y = 2\n"
        )
        config_path = git_repo / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"prepatch_check": {"enabled": true}}')
        config = BRConfig(git_repo)
        evidence = run_prepatch_check(config=config, **self._base_kwargs(git_repo, base_ref, diff))
        assert evidence.verdict == "skipped"
        assert evidence.skipped_reason == "no candidate tests identified"

    def test_merge_base_fallback_used_when_no_base_sha(self, git_repo: Path, monkeypatch) -> None:
        _commit_file(git_repo, "tests/test_h.py", "")
        config_path = git_repo / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"prepatch_check": {"enabled": true}}')
        config = BRConfig(git_repo)
        kwargs = self._base_kwargs(git_repo, base_ref="unused", step_diff="")
        kwargs["base_sha"] = None
        evidence = run_prepatch_check(config=config, **kwargs)
        assert evidence.base_source == "merge-base"
        assert evidence.verdict == "skipped"

    def test_no_database_access(self, git_repo: Path) -> None:
        """run_prepatch_check performs no database access — inspectable via sqlite3.connect."""
        import sqlite3

        base_ref = _commit_file(git_repo, "tests/test_i.py", "")
        diff = _diff_for_new_file("tests/test_i.py", ["def test_x():", "    assert True"])
        config = BRConfig(git_repo)
        real_connect = sqlite3.connect
        calls = []

        def _tracking_connect(*args, **kwargs):
            calls.append(args)
            return real_connect(*args, **kwargs)

        sqlite3.connect = _tracking_connect
        try:
            run_prepatch_check(config=config, **self._base_kwargs(git_repo, base_ref, diff))
        finally:
            sqlite3.connect = real_connect
        assert calls == []

    def test_argv_env_and_junit_flag(self, git_repo: Path, monkeypatch) -> None:
        base_ref = _commit_file(git_repo, "tests/test_j.py", "")
        (git_repo / "tests" / "test_j.py").write_text("def test_x():\n    assert True\n")
        diff = _diff_for_new_file("tests/test_j.py", ["def test_x():", "    assert True"])
        config_path = git_repo / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"prepatch_check": {"enabled": true, "timeout_s": 45}}')
        config = BRConfig(git_repo)

        worktree_path = git_repo  # reuse repo as the "worktree" for this test
        captured_calls = []

        def _fake_setup_prepatch_worktree(*args, **kwargs):
            return worktree_path

        def _fake_run(cmd, cwd=None, env=None, timeout=None, capture_output=None, text=None):
            captured_calls.append({"cmd": cmd, "cwd": cwd, "env": env, "timeout": timeout})
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(
            "little_loops.prepatch_check.setup_prepatch_worktree", _fake_setup_prepatch_worktree
        )
        monkeypatch.setattr("little_loops.prepatch_check.subprocess.run", _fake_run)

        evidence = run_prepatch_check(config=config, **self._base_kwargs(git_repo, base_ref, diff))

        # subprocess.run is patched globally, so the collect_candidates()-phase
        # `git show` calls land in captured_calls too; isolate the pytest invocation.
        pytest_calls = [c for c in captured_calls if c["cmd"][:3] == ["python", "-m", "pytest"]]
        assert len(pytest_calls) == 1  # no retry since nothing reported "pass"
        call = pytest_calls[0]
        assert call["timeout"] == 45
        junit_arg = next(a for a in call["cmd"] if a.startswith("--junit-xml="))
        assert junit_arg == f"--junit-xml={worktree_path / '.prepatch-run' / 'prepatch.xml'}"
        assert "tests/test_j.py::test_x" in call["cmd"]
        assert "scripts/tests" not in call["cmd"]
        assert "." not in call["cmd"]
        expected_src_dir = str(worktree_path / config.project.src_dir)
        assert call["env"]["PYTHONPATH"].startswith(expected_src_dir)
        assert (
            evidence.verdict == "clean"
        )  # no junit produced by fake -> defaults to "error"/"timeout", never hard


class TestRunPrepatchCheckRetryAndFlags:
    def _run_with_fake_pytest(self, git_repo, base_ref, diff, first_xml, retry_xml, config=None):
        logger = MagicMock()
        git_lock = MagicMock()
        if config is None:
            config_path = git_repo / ".ll" / "ll-config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text('{"prepatch_check": {"enabled": true}}')
            config = BRConfig(git_repo)

        worktree_path = git_repo
        run_dir = worktree_path / ".prepatch-run"
        run_dir.mkdir(exist_ok=True)
        (run_dir / "prepatch.xml").write_text(first_xml)
        if retry_xml is not None:
            (run_dir / "prepatch-retry.xml").write_text(retry_xml)

        import little_loops.prepatch_check as pc

        def _fake_setup(*args, **kwargs):
            return worktree_path

        def _fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "", "")

        orig_setup = pc.setup_prepatch_worktree
        orig_run = pc.subprocess.run
        pc.setup_prepatch_worktree = _fake_setup
        pc.subprocess.run = _fake_run
        try:
            return run_prepatch_check(
                step_diff=diff,
                repo_root=git_repo,
                worktree_base=".worktrees",
                base_sha=base_ref,
                base_dirty=None,
                base_branch="main",
                logger=logger,
                git_lock=git_lock,
                config=config,
            )
        finally:
            pc.setup_prepatch_worktree = orig_setup
            pc.subprocess.run = orig_run

    def test_retry_invocation_targets_only_first_pass_node_ids(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/test_o.py", "")
        (git_repo / "tests" / "test_o.py").write_text(
            "def test_pass():\n    assert True\n\n\ndef test_fail():\n    assert False\n"
        )
        diff = _diff_for_new_file(
            "tests/test_o.py",
            [
                "def test_pass():",
                "    assert True",
                "",
                "",
                "def test_fail():",
                "    assert False",
            ],
        )
        first_xml = (
            '<?xml version="1.0"?><testsuites><testsuite>'
            '<testcase classname="tests.test_o" name="test_pass" file="tests/test_o.py" line="1"/>'
            '<testcase classname="tests.test_o" name="test_fail" file="tests/test_o.py" line="5">'
            '<failure message="assert False">boom</failure></testcase>'
            "</testsuite></testsuites>"
        )
        retry_xml = (
            '<?xml version="1.0"?><testsuites><testsuite>'
            '<testcase classname="tests.test_o" name="test_pass" file="tests/test_o.py" line="1"/>'
            "</testsuite></testsuites>"
        )
        logger = MagicMock()
        git_lock = MagicMock()
        config_path = git_repo / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"prepatch_check": {"enabled": true}}')
        config = BRConfig(git_repo)
        worktree_path = git_repo
        run_dir = worktree_path / ".prepatch-run"
        run_dir.mkdir(exist_ok=True)
        (run_dir / "prepatch.xml").write_text(first_xml)
        (run_dir / "prepatch-retry.xml").write_text(retry_xml)

        import little_loops.prepatch_check as pc

        captured = []

        def _fake_run(cmd, **kwargs):
            captured.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        orig_setup = pc.setup_prepatch_worktree
        orig_run = pc.subprocess.run
        pc.setup_prepatch_worktree = lambda *a, **k: worktree_path
        pc.subprocess.run = _fake_run
        try:
            evidence = run_prepatch_check(
                step_diff=diff,
                repo_root=git_repo,
                worktree_base=".worktrees",
                base_sha=base_ref,
                base_dirty=None,
                base_branch="main",
                logger=logger,
                git_lock=git_lock,
                config=config,
            )
        finally:
            pc.setup_prepatch_worktree = orig_setup
            pc.subprocess.run = orig_run

        pytest_calls = [c for c in captured if c[:3] == ["python", "-m", "pytest"]]
        assert len(pytest_calls) == 2
        first_call, retry_call = pytest_calls
        assert "tests/test_o.py::test_pass" in first_call
        assert "tests/test_o.py::test_fail" in first_call
        assert "tests/test_o.py::test_pass" in retry_call
        assert "tests/test_o.py::test_fail" not in retry_call

        outcomes_by_nodeid = {o.nodeid: o for o in evidence.outcomes}
        assert outcomes_by_nodeid["tests/test_o.py::test_pass"].category == "pass"
        assert outcomes_by_nodeid["tests/test_o.py::test_fail"].category == "fail"

    def test_pass_then_fail_on_retry_is_flaky(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/test_k.py", "")
        (git_repo / "tests" / "test_k.py").write_text("def test_x():\n    assert True\n")
        diff = _diff_for_new_file("tests/test_k.py", ["def test_x():", "    assert True"])
        first_xml = (
            '<?xml version="1.0"?><testsuites><testsuite>'
            '<testcase classname="tests.test_k" name="test_x" file="tests/test_k.py" line="1"/>'
            "</testsuite></testsuites>"
        )
        retry_xml = (
            '<?xml version="1.0"?><testsuites><testsuite>'
            '<testcase classname="tests.test_k" name="test_x" file="tests/test_k.py" line="1">'
            '<failure message="assert False">boom</failure></testcase>'
            "</testsuite></testsuites>"
        )
        evidence = self._run_with_fake_pytest(git_repo, base_ref, diff, first_xml, retry_xml)
        assert len(evidence.outcomes) == 1
        outcome = evidence.outcomes[0]
        assert outcome.category == "flaky"
        assert outcome.flag == "soft"
        assert evidence.verdict == "clean"

    def test_added_pass_confirmed_on_retry_is_hard_flag(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/test_l.py", "")
        (git_repo / "tests" / "test_l.py").write_text("def test_x():\n    assert True\n")
        diff = _diff_for_new_file("tests/test_l.py", ["def test_x():", "    assert True"])
        xml = (
            '<?xml version="1.0"?><testsuites><testsuite>'
            '<testcase classname="tests.test_l" name="test_x" file="tests/test_l.py" line="1"/>'
            "</testsuite></testsuites>"
        )
        evidence = self._run_with_fake_pytest(git_repo, base_ref, diff, xml, xml)
        assert len(evidence.outcomes) == 1
        outcome = evidence.outcomes[0]
        assert outcome.category == "pass"
        assert outcome.flag == "hard"
        assert evidence.verdict == "flagged"

    def test_dirty_base_downgrades_hard_to_soft(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/test_m.py", "")
        (git_repo / "tests" / "test_m.py").write_text("def test_x():\n    assert True\n")
        diff = _diff_for_new_file("tests/test_m.py", ["def test_x():", "    assert True"])
        xml = (
            '<?xml version="1.0"?><testsuites><testsuite>'
            '<testcase classname="tests.test_m" name="test_x" file="tests/test_m.py" line="1"/>'
            "</testsuite></testsuites>"
        )
        logger = MagicMock()
        git_lock = MagicMock()
        config_path = git_repo / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"prepatch_check": {"enabled": true}}')
        config = BRConfig(git_repo)
        worktree_path = git_repo
        run_dir = worktree_path / ".prepatch-run"
        run_dir.mkdir(exist_ok=True)
        (run_dir / "prepatch.xml").write_text(xml)
        (run_dir / "prepatch-retry.xml").write_text(xml)

        import little_loops.prepatch_check as pc

        orig_setup = pc.setup_prepatch_worktree
        orig_run = pc.subprocess.run
        pc.setup_prepatch_worktree = lambda *a, **k: worktree_path
        pc.subprocess.run = lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, "", "")
        try:
            evidence = run_prepatch_check(
                step_diff=diff,
                repo_root=git_repo,
                worktree_base=".worktrees",
                base_sha=base_ref,
                base_dirty=True,
                base_branch="main",
                logger=logger,
                git_lock=git_lock,
                config=config,
            )
        finally:
            pc.setup_prepatch_worktree = orig_setup
            pc.subprocess.run = orig_run

        outcome = evidence.outcomes[0]
        assert outcome.flag == "soft"
        assert outcome.flag_reason and "dirty" in outcome.flag_reason
        assert evidence.verdict == "clean"

    def test_timeout_with_no_junit_reports_timeout_category(self, git_repo: Path) -> None:
        base_ref = _commit_file(git_repo, "tests/test_n.py", "")
        (git_repo / "tests" / "test_n.py").write_text("def test_x():\n    assert True\n")
        diff = _diff_for_new_file("tests/test_n.py", ["def test_x():", "    assert True"])
        logger = MagicMock()
        git_lock = MagicMock()
        config_path = git_repo / ".ll" / "ll-config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"prepatch_check": {"enabled": true}}')
        config = BRConfig(git_repo)
        worktree_path = git_repo

        import little_loops.prepatch_check as pc

        def _timeout_run(cmd, timeout=None, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

        orig_setup = pc.setup_prepatch_worktree
        orig_run = pc.subprocess.run
        pc.setup_prepatch_worktree = lambda *a, **k: worktree_path
        pc.subprocess.run = _timeout_run
        try:
            evidence = run_prepatch_check(
                step_diff=diff,
                repo_root=git_repo,
                worktree_base=".worktrees",
                base_sha=base_ref,
                base_dirty=None,
                base_branch="main",
                logger=logger,
                git_lock=git_lock,
                config=config,
            )
        finally:
            pc.setup_prepatch_worktree = orig_setup
            pc.subprocess.run = orig_run

        assert len(evidence.outcomes) == 1
        assert evidence.outcomes[0].category == "timeout"
        assert evidence.outcomes[0].flag == "none"


class TestDataclasses:
    def test_evidence_to_dict_serializes_nested_outcomes(self) -> None:
        outcome = PrePatchTestOutcome(
            nodeid="a::b",
            file="a",
            added=True,
            category="pass",
            error_kind=None,
            flag="hard",
            flag_reason="newly added test passed pre-patch",
        )
        evidence = PrePatchEvidence(
            base_ref="abc123",
            base_source="dequeue-stamp",
            base_dirty=False,
            outcomes=[outcome],
            verdict="flagged",
            skipped_reason=None,
        )
        d = evidence.to_dict()
        assert d["outcomes"] == [outcome.to_dict()]
        assert d["verdict"] == "flagged"

    def test_candidate_is_plain_dataclass(self) -> None:
        c = PrePatchCandidate(nodeid="a::b", file="a", added=True, attribution="function")
        assert c.nodeid == "a::b"
