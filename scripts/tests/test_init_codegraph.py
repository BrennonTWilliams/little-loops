"""Tests for little_loops.init.codegraph — code-graph detection, install, indexing."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.init import codegraph as cg


def _status(
    tmp_path: Path,
    *,
    binary: str | None = None,
    index: bool = False,
    npm: str | None = None,
    npx: str | None = None,
) -> cg.CodegraphStatus:
    return cg.CodegraphStatus(
        binary=binary,
        index_present=index,
        db_path=tmp_path / ".codegraph" / "codegraph.db",
        node=None,
        npm=npm,
        npx=npx,
    )


class TestDetectCodegraph:
    def test_nothing_available(self, tmp_path: Path) -> None:
        with patch("little_loops.init.codegraph.shutil.which", return_value=None):
            status = cg.detect_codegraph(tmp_path)
        assert status.binary is None and status.npm is None and status.index_present is False
        assert status.db_path == tmp_path / ".codegraph" / "codegraph.db"
        assert status.recommended_action == "commands"

    def test_binary_and_index(self, tmp_path: Path) -> None:
        (tmp_path / ".codegraph").mkdir()
        (tmp_path / ".codegraph" / "codegraph.db").write_bytes(b"")
        with (
            patch(
                "little_loops.init.codegraph.shutil.which",
                side_effect=lambda b: f"/bin/{b}" if b in ("codegraph", "npm") else None,
            ),
            patch(
                "little_loops.init.codegraph.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="0.9.8\n"),
            ),
        ):
            status = cg.detect_codegraph(tmp_path, probe_version=True)
        assert status.binary == "/bin/codegraph"
        assert status.version == "0.9.8"
        assert status.index_present is True
        assert status.recommended_action == "ready"

    def test_custom_db_path(self, tmp_path: Path) -> None:
        with patch("little_loops.init.codegraph.shutil.which", return_value=None):
            status = cg.detect_codegraph(tmp_path, "custom/graph.db")
        assert status.db_path == tmp_path / "custom" / "graph.db"

    def test_to_dict_is_json_friendly(self, tmp_path: Path) -> None:
        data = _status(tmp_path, npm="/bin/npm").to_dict()
        assert data["recommended_action"] == "install"
        assert data["manual_commands"][0].startswith("npm install -g ")


class TestManualCommands:
    def test_full_chain_when_nothing_installed(self, tmp_path: Path) -> None:
        assert cg.manual_commands(_status(tmp_path)) == [
            f"npm install -g {cg.CODEGRAPH_PACKAGE}",
            "codegraph init .",
            "ll-code status",
        ]

    def test_only_index_when_binary_present(self, tmp_path: Path) -> None:
        assert cg.manual_commands(_status(tmp_path, binary="/bin/codegraph")) == [
            "codegraph init .",
            "ll-code status",
        ]

    def test_only_status_when_indexed(self, tmp_path: Path) -> None:
        assert cg.manual_commands(_status(tmp_path, binary="/b", index=True)) == ["ll-code status"]


class TestResolveAction:
    @pytest.mark.parametrize(
        ("mode", "binary", "npm", "npx", "expected"),
        [
            ("auto", None, None, None, "commands"),
            ("auto", None, "/npm", "/npx", "commands"),  # auto never installs
            ("auto", "/cg", None, None, "index"),
            ("install", None, "/npm", None, "install"),
            ("install", None, None, None, "commands"),
            ("install", "/cg", "/npm", None, "index"),  # already installed → just index
            ("index", None, None, "/npx", "index"),  # npx one-shot
            ("index", None, None, None, "commands"),
            ("commands", "/cg", "/npm", "/npx", "commands"),
            ("skip", "/cg", "/npm", "/npx", "skip"),
        ],
    )
    def test_matrix(
        self,
        tmp_path: Path,
        mode: str,
        binary: str | None,
        npm: str | None,
        npx: str | None,
        expected: str,
    ) -> None:
        status = _status(tmp_path, binary=binary, npm=npm, npx=npx)
        assert cg.resolve_code_graph_action(mode, status) == expected

    def test_index_present_is_ready_unless_skip(self, tmp_path: Path) -> None:
        status = _status(tmp_path, binary="/cg", index=True)
        for mode in ("auto", "install", "index", "commands"):
            assert cg.resolve_code_graph_action(mode, status) == "ready"
        assert cg.resolve_code_graph_action("skip", status) == "skip"


class TestInstallCodegraph:
    def test_no_npm(self) -> None:
        with patch("little_loops.init.codegraph.shutil.which", return_value=None):
            result = cg.install_codegraph()
        assert result.ok is False and "npm not found" in result.detail

    def test_dry_run_does_not_execute(self) -> None:
        with (
            patch("little_loops.init.codegraph.shutil.which", return_value="/bin/npm"),
            patch("little_loops.init.codegraph.subprocess.run") as run,
        ):
            result = cg.install_codegraph(dry_run=True)
        run.assert_not_called()
        assert result.ok is False and result.commands == [
            ["/bin/npm", "install", "-g", cg.CODEGRAPH_PACKAGE]
        ]

    def test_eacces_adds_prefix_hint_and_never_sudo(self) -> None:
        with (
            patch("little_loops.init.codegraph.shutil.which", return_value="/bin/npm"),
            patch(
                "little_loops.init.codegraph.subprocess.run",
                return_value=MagicMock(
                    returncode=243, stdout="", stderr="npm ERR! EACCES: permission denied"
                ),
            ) as run,
        ):
            result = cg.install_codegraph()
        assert result.ok is False
        assert "npm config set prefix" in result.detail
        assert "npx --yes" in result.detail
        assert all("sudo" not in " ".join(c.args[0]) for c in run.call_args_list)

    def test_success(self) -> None:
        with (
            patch("little_loops.init.codegraph.shutil.which", return_value="/bin/npm"),
            patch(
                "little_loops.init.codegraph.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="added 1 package", stderr=""),
            ),
        ):
            result = cg.install_codegraph()
        assert result.ok is True and result.action == "install"


class TestIndexCodegraph:
    def _make_db(self, tmp_path: Path) -> None:
        (tmp_path / ".codegraph").mkdir(exist_ok=True)
        (tmp_path / ".codegraph" / "codegraph.db").write_bytes(b"")

    def test_uses_binary_and_verifies_db(self, tmp_path: Path) -> None:
        status = _status(tmp_path, binary="/bin/codegraph")

        def _run(argv, **kwargs):
            self._make_db(tmp_path)
            return MagicMock(returncode=0, stdout="done", stderr="")

        with (
            patch("little_loops.init.codegraph.shutil.which", return_value="/bin/codegraph"),
            patch("little_loops.init.codegraph.subprocess.run", side_effect=_run) as run,
        ):
            result = cg.index_codegraph(tmp_path, status)
        assert result.ok is True
        assert run.call_args.args[0] == ["/bin/codegraph", "init", "."]
        assert run.call_args.kwargs["cwd"] == str(tmp_path)

    def test_exit_zero_without_db_is_failure(self, tmp_path: Path) -> None:
        status = _status(tmp_path, binary="/bin/codegraph")
        with (
            patch("little_loops.init.codegraph.shutil.which", return_value="/bin/codegraph"),
            patch(
                "little_loops.init.codegraph.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="", stderr=""),
            ),
        ):
            result = cg.index_codegraph(tmp_path, status)
        assert result.ok is False and "no index" in result.detail

    def test_npx_fallback(self, tmp_path: Path) -> None:
        status = _status(tmp_path, npx="/bin/npx")
        with (
            patch("little_loops.init.codegraph.shutil.which", return_value=None),
            patch("little_loops.init.codegraph.subprocess.run") as run,
        ):
            result = cg.index_codegraph(tmp_path, status, dry_run=True)
        run.assert_not_called()
        assert result.commands == [["/bin/npx", "--yes", cg.CODEGRAPH_PACKAGE, "init", "."]]

    def test_nothing_available(self, tmp_path: Path) -> None:
        with patch("little_loops.init.codegraph.shutil.which", return_value=None):
            result = cg.index_codegraph(tmp_path, _status(tmp_path))
        assert result.ok is False and "not found" in result.detail

    def test_timeout_is_failure(self, tmp_path: Path) -> None:
        status = _status(tmp_path, binary="/bin/codegraph")
        with (
            patch("little_loops.init.codegraph.shutil.which", return_value="/bin/codegraph"),
            patch(
                "little_loops.init.codegraph.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="codegraph", timeout=1),
            ),
        ):
            result = cg.index_codegraph(tmp_path, status, timeout=1)
        assert result.ok is False and "timed out" in result.detail


class TestRunCodeGraphStep:
    def test_commands_mode_logs_manual_commands(self, tmp_path: Path) -> None:
        logs: list[str] = []
        status = _status(tmp_path)
        out_status, result = cg.run_code_graph_step(
            "auto", tmp_path, log=logs.append, warn=logs.append, status=status
        )
        assert result is None and out_status is status
        assert any("npm install -g" in line for line in logs)
        assert any("codegraph init ." in line for line in logs)

    def test_ready_when_indexed(self, tmp_path: Path) -> None:
        logs: list[str] = []
        status = _status(tmp_path, binary="/cg", index=True)
        _, result = cg.run_code_graph_step("auto", tmp_path, log=logs.append, status=status)
        assert result is None
        assert any("ll-code will use it" in line for line in logs)

    def test_install_then_index(self, tmp_path: Path) -> None:
        logs: list[str] = []
        warns: list[str] = []
        status = _status(tmp_path, npm="/bin/npm")
        indexed = _status(tmp_path, binary="/bin/codegraph", index=True)
        with (
            patch(
                "little_loops.init.codegraph.install_codegraph",
                return_value=cg.CodegraphActionResult(True, "install", "installed", [["npm"]]),
            ),
            patch(
                "little_loops.init.codegraph.index_codegraph",
                return_value=cg.CodegraphActionResult(True, "index", "indexed", [["codegraph"]]),
            ),
            patch("little_loops.init.codegraph.detect_codegraph", return_value=indexed),
        ):
            out_status, result = cg.run_code_graph_step(
                "install", tmp_path, log=logs.append, warn=warns.append, status=status
            )
        assert result is not None and result.ok and result.action == "index"
        assert out_status.index_present is True
        assert warns == []

    def test_install_failure_stops_before_index(self, tmp_path: Path) -> None:
        warns: list[str] = []
        status = _status(tmp_path, npm="/bin/npm")
        with (
            patch(
                "little_loops.init.codegraph.install_codegraph",
                return_value=cg.CodegraphActionResult(False, "install", "EACCES", [["npm"]]),
            ),
            patch("little_loops.init.codegraph.index_codegraph") as index,
        ):
            _, result = cg.run_code_graph_step(
                "install", tmp_path, log=lambda m: None, warn=warns.append, status=status
            )
        index.assert_not_called()
        assert result is not None and result.ok is False
        assert any("install failed" in w for w in warns)
        assert any("codegraph init ." in w for w in warns)

    def test_skip(self, tmp_path: Path) -> None:
        logs: list[str] = []
        _, result = cg.run_code_graph_step(
            "skip", tmp_path, log=logs.append, status=_status(tmp_path, binary="/cg")
        )
        assert result is None and logs == []
