"""Tests for little_loops.hooks.learning_tests_gate (FEAT-1742)."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest

from little_loops.hooks.learning_tests_gate import _SESSION_CACHE, _extract_packages, gate
from little_loops.hooks.types import LLHookEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    tool_name: str = "Write",
    content: str = "",
    file_path: str = "foo.py",
    cwd: str | None = None,
) -> LLHookEvent:
    if tool_name == "Write":
        tool_input: dict = {"file_path": file_path, "content": content}
    else:
        tool_input = {"file_path": file_path, "new_string": content}
    return LLHookEvent(
        host="claude-code",
        intent="pre_tool_use",
        payload={"tool_name": tool_name, "tool_input": tool_input},
        cwd=cwd,
    )


def _write_config(
    project_dir: Path,
    *,
    enabled: bool = True,
    mode: str = "warn",
    skip_packages: list[str] | None = None,
) -> None:
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    disc: dict = {"mode": mode}
    if skip_packages is not None:
        disc["skip_packages"] = skip_packages
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"learning_tests": {"enabled": enabled, "discoverability": disc}}),
        encoding="utf-8",
    )


def _write_record(project_dir: Path, target: str, status: str) -> None:
    """Write a minimal learning-test record as a frontmatter YAML file."""
    lt_dir = project_dir / ".ll" / "learning-tests"
    lt_dir.mkdir(parents=True, exist_ok=True)
    slug = target.lower()
    content = f"---\ntarget: {target}\ndate: '2026-01-01'\nstatus: {status}\nassertions: []\n---\n"
    (lt_dir / f"{slug}.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_session_cache() -> Generator[None, None, None]:
    """Clear module-level session cache before and after each test."""
    _SESSION_CACHE.clear()
    yield
    _SESSION_CACHE.clear()


# ---------------------------------------------------------------------------
# Gate disabled / off
# ---------------------------------------------------------------------------


class TestGateDisabled:
    def test_no_op_when_lt_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, enabled=False)
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_no_op_when_mode_off(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, enabled=True, mode="off")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_no_op_when_no_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_no_op_on_empty_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# Warn mode
# ---------------------------------------------------------------------------


class TestGateWarnMode:
    def test_warn_on_unfamiliar_import(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "stripe" in result.feedback
        assert "proof-first" in result.feedback

    def test_no_suggestion_when_proven(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        _write_record(tmp_path, "stripe", "proven")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_suggestion_fires_for_refuted_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        _write_record(tmp_path, "stripe", "refuted")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "stripe" in result.feedback

    def test_suggestion_fires_for_stale_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        _write_record(tmp_path, "stripe", "stale")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None

    def test_skip_packages_honored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_config(
            tmp_path,
            enabled=True,
            mode="warn",
            skip_packages=["stripe", "std", "typing", "os", "sys"],
        )
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_default_skip_packages_not_flagged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        monkeypatch.chdir(tmp_path)
        content = "import os\nimport sys\nfrom typing import List\n"
        result = gate(_event(content=content, cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_builtin_skip_not_flagged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        monkeypatch.chdir(tmp_path)
        content = "from __future__ import annotations\nimport re\nimport json\n"
        result = gate(_event(content=content, cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_multiple_missing_packages_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        monkeypatch.chdir(tmp_path)
        content = "import stripe\nimport httpx\n"
        result = gate(_event(content=content, cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "stripe" in result.feedback
        assert "httpx" in result.feedback


# ---------------------------------------------------------------------------
# Block mode
# ---------------------------------------------------------------------------


class TestGateBlockMode:
    def test_block_on_unfamiliar_import(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="block")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 2
        assert result.feedback is not None
        assert "stripe" in result.feedback

    def test_block_passes_when_proven(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="block")
        _write_record(tmp_path, "stripe", "proven")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# Edit tool
# ---------------------------------------------------------------------------


class TestEditTool:
    def test_edit_new_string_is_checked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        monkeypatch.chdir(tmp_path)
        result = gate(
            _event(
                tool_name="Edit",
                content="from httpx import AsyncClient\n",
                cwd=str(tmp_path),
            )
        )
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "httpx" in result.feedback

    def test_edit_proven_import_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        _write_record(tmp_path, "httpx", "proven")
        monkeypatch.chdir(tmp_path)
        result = gate(
            _event(tool_name="Edit", content="from httpx import AsyncClient\n", cwd=str(tmp_path))
        )
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# Non-Write/Edit tools
# ---------------------------------------------------------------------------


class TestNonWriteEditTools:
    def test_bash_tool_passes_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="block")
        monkeypatch.chdir(tmp_path)
        event = LLHookEvent(
            host="claude-code",
            intent="pre_tool_use",
            payload={"tool_name": "Bash", "tool_input": {"command": "pip install stripe"}},
            cwd=str(tmp_path),
        )
        result = gate(event)
        assert result.exit_code == 0
        assert result.feedback is None

    def test_read_tool_passes_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="block")
        monkeypatch.chdir(tmp_path)
        event = LLHookEvent(
            host="claude-code",
            intent="pre_tool_use",
            payload={"tool_name": "Read", "tool_input": {"file_path": "stripe_client.py"}},
            cwd=str(tmp_path),
        )
        result = gate(event)
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# Session cache
# ---------------------------------------------------------------------------


class TestSessionCache:
    def test_cache_populated_on_first_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        monkeypatch.chdir(tmp_path)
        assert "stripe" not in _SESSION_CACHE
        gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert "stripe" in _SESSION_CACHE
        assert _SESSION_CACHE["stripe"] is False

    def test_cache_true_for_proven_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_config(tmp_path, enabled=True, mode="warn")
        _write_record(tmp_path, "stripe", "proven")
        monkeypatch.chdir(tmp_path)
        gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert _SESSION_CACHE.get("stripe") is True


# ---------------------------------------------------------------------------
# Import detection (_extract_packages)
# ---------------------------------------------------------------------------


class TestExtractPackages:
    def test_python_import_statement(self) -> None:
        pkgs = _extract_packages("import stripe\nfrom httpx import Client\n", "foo.py")
        assert "stripe" in pkgs
        assert "httpx" in pkgs

    def test_python_stdlib_detected_for_skip_filtering(self) -> None:
        pkgs = _extract_packages("import os\nimport sys\n", "foo.py")
        assert "os" in pkgs
        assert "sys" in pkgs

    def test_js_require(self) -> None:
        pkgs = _extract_packages("const stripe = require('stripe')\n", "index.js")
        assert "stripe" in pkgs

    def test_js_import_from(self) -> None:
        pkgs = _extract_packages("import Stripe from 'stripe'\n", "index.ts")
        assert "stripe" in pkgs

    def test_js_relative_imports_excluded(self) -> None:
        pkgs = _extract_packages("import foo from './local'\nimport bar from '../util'\n", "x.ts")
        assert "./local" not in pkgs
        assert "../util" not in pkgs
        assert "local" not in pkgs

    def test_no_packages_in_empty_string(self) -> None:
        assert _extract_packages("", "foo.py") == []

    def test_deduplication(self) -> None:
        content = "import stripe\nimport stripe\nfrom stripe import Client\n"
        pkgs = _extract_packages(content, "foo.py")
        assert pkgs.count("stripe") == 1
