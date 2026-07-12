"""CLI-layer tests for ll-code subcommands (FEAT-2576)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from little_loops.cli.code import main_code as main


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--initial-branch", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    return path


def _write_and_commit(repo: Path, rel_path: str, content: str) -> None:
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", rel_path)
    _git(repo, "commit", "-m", f"add {rel_path}")


def test_status_json_output_is_valid_json(capsys):
    # Pin --provider fallback: this repo's own .codegraph/codegraph.db is a
    # real index (ENH-2613), so "auto" may resolve to codegraph here instead
    # of fallback. This test only cares that status JSON is well-formed.
    with patch.object(sys, "argv", ["ll-code", "--json", "--provider", "fallback", "status"]):
        exit_code = main()
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["provider"] == "fallback"
    assert data["available"] is True


def test_no_command_prints_help_and_returns_1(capsys):
    with patch.object(sys, "argv", ["ll-code"]):
        exit_code = main()
    assert exit_code == 1


def test_unknown_provider_returns_exit_code_2(capsys):
    with patch.object(sys, "argv", ["ll-code", "--provider", "nope", "status"]):
        exit_code = main()
    assert exit_code == 2


def test_defines_json_schema_and_exit_code(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(repo, "pkg/mod.py", "def helper():\n    pass\n")
    monkeypatch.chdir(repo)

    with patch.object(sys, "argv", ["ll-code", "--json", "defines", "pkg/mod.py"]):
        exit_code = main()

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["provider"] == "fallback"
    assert data["query"] == "defines"
    assert any(r["symbol"] == "helper" for r in data["results"])


def test_defines_no_hits_returns_exit_code_1(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(repo, "pkg/mod.py", "x = 1\n")
    monkeypatch.chdir(repo)

    with patch.object(sys, "argv", ["ll-code", "--json", "defines", "pkg/mod.py"]):
        exit_code = main()

    assert exit_code == 1


def test_provider_codegraph_status_reports_unavailable_without_index(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(repo, "pkg/mod.py", "def helper():\n    pass\n")
    monkeypatch.chdir(repo)

    with patch.object(sys, "argv", ["ll-code", "--json", "--provider", "codegraph", "status"]):
        exit_code = main()

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["provider"] == "codegraph"
    assert data["available"] is False
    assert data["freshness"] == "unknown"


def test_default_provider_is_sourced_from_config(tmp_path, monkeypatch, capsys):
    repo = _init_repo(tmp_path / "repo")
    _write_and_commit(repo, "pkg/mod.py", "def helper():\n    pass\n")
    ll_dir = repo / ".ll"
    ll_dir.mkdir()
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"code_query": {"provider": "fallback"}}), encoding="utf-8"
    )
    monkeypatch.chdir(repo)

    with patch.object(sys, "argv", ["ll-code", "--json", "status"]):
        exit_code = main()

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["provider"] == "fallback"
