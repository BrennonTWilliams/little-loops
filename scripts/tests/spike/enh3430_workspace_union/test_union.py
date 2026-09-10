"""AC suite for the ENH-3430 per-host workspace-union spike.

Retires the issue's flagged risk: "No shared 'dedupe a list of Path's
across hosts' utility exists in the codebase ... this step's mechanism is
genuinely new code with no confirming precedent anywhere." Every test drives
the real ``session_store.sessions`` seam and the real ``cli.logs`` filter
against synthetic fixture homes -- see ``fixtures.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.tests.spike.enh3430_workspace_union.fixtures import (
    write_claude_project,
    write_codex_project,
)
from scripts.tests.spike.enh3430_workspace_union.union import union_workspaces


class TestUnionDedupe:
    def test_same_cwd_under_two_hosts_collapses_to_one_entry(self, tmp_path):
        home = tmp_path / "home"
        cwd = tmp_path / "project"
        cwd.mkdir(parents=True)

        write_claude_project(home, cwd, "claude-sess")
        write_codex_project(home, cwd, "codex-sess")

        workspaces = union_workspaces(["claude-code", "codex"], home=home)

        assert len(workspaces) == 1
        assert workspaces[0].resolve() == cwd.resolve()

    def test_distinct_cwds_across_hosts_both_survive(self, tmp_path):
        home = tmp_path / "home"
        cwd_a = tmp_path / "project-a"
        cwd_b = tmp_path / "project-b"
        cwd_a.mkdir(parents=True)
        cwd_b.mkdir(parents=True)

        write_claude_project(home, cwd_a, "claude-sess")
        write_codex_project(home, cwd_b, "codex-sess")

        workspaces = union_workspaces(["claude-code", "codex"], home=home)

        resolved = {w.resolve() for w in workspaces}
        assert resolved == {cwd_a.resolve(), cwd_b.resolve()}

    def test_resolved_vs_as_recorded_spelling_still_dedupes(self, tmp_path):
        home = tmp_path / "home"
        real_dir = tmp_path / "real_project"
        real_dir.mkdir(parents=True)
        link_dir = tmp_path / "linked_project"
        link_dir.symlink_to(real_dir)

        # claude-code records the symlinked (as-recorded) spelling; the
        # project directory is still encoded from the *resolved* path, since
        # that is what _cwd_spellings(link_dir) tries first.
        write_claude_project(home, link_dir, "claude-sess", encode_cwd=real_dir)
        # codex records the already-resolved spelling directly.
        write_codex_project(home, real_dir, "codex-sess")

        workspaces = union_workspaces(["claude-code", "codex"], home=home)

        assert len(workspaces) == 1
        assert workspaces[0].resolve() == real_dir.resolve()

    def test_ll_activity_filter_excludes_non_ll_workspace(self, tmp_path):
        home = tmp_path / "home"
        ll_cwd = tmp_path / "ll-project"
        quiet_cwd = tmp_path / "quiet-project"
        ll_cwd.mkdir(parents=True)
        quiet_cwd.mkdir(parents=True)

        write_claude_project(home, ll_cwd, "claude-sess", ll_relevant=True)
        write_claude_project(home, quiet_cwd, "claude-sess-2", ll_relevant=False)

        workspaces = union_workspaces(["claude-code"], home=home)

        assert len(workspaces) == 1
        assert workspaces[0].resolve() == ll_cwd.resolve()

    def test_never_calls_detect_sessions_with_host_none_per_workspace(self, tmp_path):
        home = tmp_path / "home"
        cwd = tmp_path / "project"
        cwd.mkdir(parents=True)
        write_claude_project(home, cwd, "claude-sess")
        write_codex_project(home, cwd, "codex-sess")

        calls: list[tuple[Path, str]] = []
        union_workspaces(["claude-code", "codex"], home=home, detect_sessions_calls=calls)

        assert calls, "expected detect_sessions to be called at least once"
        for _workspace, host in calls:
            assert host is not None
            assert isinstance(host, str)


class TestSpikeIsolation:
    def test_spike_does_not_import_cli_logs_discover_all_projects(self):
        union_source = (Path(__file__).parent / "union.py").read_text(encoding="utf-8")
        tree = ast.parse(union_source)
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)

        assert "discover_all_projects" not in imported_names
