"""Tests for little_loops.hooks.install_learning_gate (ENH-2212)."""

from __future__ import annotations

import datetime
import json
from collections.abc import Generator
from pathlib import Path

import pytest

from little_loops.hooks.install_learning_gate import (
    _SESSION_CACHE,
    _normalize_pkg,
    gate,
)
from little_loops.hooks.types import LLHookEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bash_event(cmd: str, cwd: str | None = None) -> LLHookEvent:
    return LLHookEvent(
        host="claude-code",
        intent="post_tool_use",
        payload={"tool_name": "Bash", "tool_input": {"command": cmd}},
        cwd=cwd,
    )


def _write_config(
    project_dir: Path,
    *,
    enabled: bool = True,
    stale_after_days: int | None = None,
) -> None:
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    lt_config: dict = {"enabled": enabled}
    if stale_after_days is not None:
        lt_config["stale_after_days"] = stale_after_days
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"learning_tests": lt_config}),
        encoding="utf-8",
    )


def _write_record(project_dir: Path, target: str, status: str, date: str | None = None) -> None:
    lt_dir = project_dir / ".ll" / "learning-tests"
    lt_dir.mkdir(parents=True, exist_ok=True)
    slug = target.lower()
    record_date = date if date is not None else datetime.date.today().isoformat()
    content = (
        f"---\ntarget: {target}\ndate: '{record_date}'\nstatus: {status}\nassertions: []\n---\n"
    )
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
# _normalize_pkg
# ---------------------------------------------------------------------------


class TestNormalizePkg:
    def test_plain_name(self) -> None:
        assert _normalize_pkg("httpx") == "httpx"

    def test_strips_version_specifier_ge(self) -> None:
        assert _normalize_pkg("anthropic>=0.20") == "anthropic"

    def test_strips_version_specifier_eq(self) -> None:
        assert _normalize_pkg("requests==2.31.0") == "requests"

    def test_strips_extras(self) -> None:
        assert _normalize_pkg("anthropic[bedrock]") == "anthropic"

    def test_strips_extras_and_version(self) -> None:
        assert _normalize_pkg("anthropic[bedrock]>=0.20") == "anthropic"

    def test_strips_quotes(self) -> None:
        assert _normalize_pkg('"anthropic[bedrock]"') == "anthropic"

    def test_single_quotes(self) -> None:
        assert _normalize_pkg("'requests'") == "requests"

    def test_flag_returns_none(self) -> None:
        assert _normalize_pkg("-r") is None

    def test_empty_returns_none(self) -> None:
        assert _normalize_pkg("") is None

    def test_double_dash_flag_returns_none(self) -> None:
        assert _normalize_pkg("--requirement") is None

    def test_scoped_npm_package(self) -> None:
        assert _normalize_pkg("@scope/package") == "@scope/package"


# ---------------------------------------------------------------------------
# Gate disabled
# ---------------------------------------------------------------------------


class TestGateDisabled:
    def test_no_op_when_lt_disabled(self, tmp_path: Path) -> None:
        _write_config(tmp_path, enabled=False)
        result = gate(_bash_event("pip install httpx", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_no_op_when_no_config(self, tmp_path: Path) -> None:
        result = gate(_bash_event("pip install httpx", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# Acceptance signals (five from issue spec)
# ---------------------------------------------------------------------------


class TestAcceptanceSignals:
    def test_pip_install_unknown_pkg_nudges(self, tmp_path: Path) -> None:
        """pip install httpx triggers a nudge when no record exists."""
        _write_config(tmp_path)
        result = gate(_bash_event("pip install httpx", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "httpx" in result.feedback
        assert "/ll:explore-api" in result.feedback

    def test_pip_install_proven_pkg_silent(self, tmp_path: Path) -> None:
        """pip install requests with a proven record emits nothing."""
        _write_config(tmp_path)
        _write_record(tmp_path, "requests", "proven")
        result = gate(_bash_event("pip install requests", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_pip_install_requirements_file_skipped(self, tmp_path: Path) -> None:
        """pip install -r requirements.txt is silently skipped."""
        _write_config(tmp_path)
        result = gate(_bash_event("pip install -r requirements.txt", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_version_specifier_stripped(self, tmp_path: Path) -> None:
        """pip install anthropic>=0.20 checks 'anthropic', not 'anthropic>=0.20'."""
        _write_config(tmp_path)
        _write_record(tmp_path, "anthropic", "proven")
        result = gate(_bash_event("pip install anthropic>=0.20", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_extras_stripped(self, tmp_path: Path) -> None:
        """pip install 'anthropic[bedrock]' checks 'anthropic', not 'anthropic[bedrock]'."""
        _write_config(tmp_path)
        _write_record(tmp_path, "anthropic", "proven")
        result = gate(_bash_event('pip install "anthropic[bedrock]"', cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# Additional install command variants
# ---------------------------------------------------------------------------


class TestInstallVariants:
    def test_pip3_install(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        result = gate(_bash_event("pip3 install httpx", cwd=str(tmp_path)))
        assert result.feedback is not None
        assert "httpx" in result.feedback

    def test_uv_add(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        result = gate(_bash_event("uv add httpx", cwd=str(tmp_path)))
        assert result.feedback is not None
        assert "httpx" in result.feedback

    def test_poetry_add(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        result = gate(_bash_event("poetry add httpx", cwd=str(tmp_path)))
        assert result.feedback is not None
        assert "httpx" in result.feedback

    def test_npm_install(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        result = gate(_bash_event("npm install axios", cwd=str(tmp_path)))
        assert result.feedback is not None
        assert "axios" in result.feedback

    def test_yarn_add(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        result = gate(_bash_event("yarn add axios", cwd=str(tmp_path)))
        assert result.feedback is not None
        assert "axios" in result.feedback

    def test_pnpm_add(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        result = gate(_bash_event("pnpm add axios", cwd=str(tmp_path)))
        assert result.feedback is not None
        assert "axios" in result.feedback

    def test_non_install_bash_command_silent(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        result = gate(_bash_event("ls -la scripts/", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# Stale records
# ---------------------------------------------------------------------------


class TestStaleRecords:
    def test_stale_proven_record_nudges(self, tmp_path: Path) -> None:
        """A proven but stale record triggers a 'stale' nudge."""
        _write_config(tmp_path, stale_after_days=30)
        old_date = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
        _write_record(tmp_path, "httpx", "proven", date=old_date)
        result = gate(_bash_event("pip install httpx", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "stale" in result.feedback
        assert "httpx" in result.feedback

    def test_fresh_proven_record_silent(self, tmp_path: Path) -> None:
        """A proven fresh record is silent."""
        _write_config(tmp_path, stale_after_days=30)
        _write_record(tmp_path, "httpx", "proven")
        result = gate(_bash_event("pip install httpx", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None


# ---------------------------------------------------------------------------
# Session cache
# ---------------------------------------------------------------------------


class TestSessionCache:
    def test_cache_hit_proven_silent(self, tmp_path: Path) -> None:
        """Second install of a proven package skips registry read."""
        _write_config(tmp_path)
        _SESSION_CACHE["httpx"] = True
        result = gate(_bash_event("pip install httpx", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_cache_hit_unproven_nudges(self, tmp_path: Path) -> None:
        """Second install of an unproven package nudges from cache."""
        _write_config(tmp_path)
        _SESSION_CACHE["httpx"] = False
        result = gate(_bash_event("pip install httpx", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "httpx" in result.feedback

    def test_cache_populated_after_gate(self, tmp_path: Path) -> None:
        """Gate populates cache so subsequent calls skip registry."""
        _write_config(tmp_path)
        _write_record(tmp_path, "requests", "proven")
        gate(_bash_event("pip install requests", cwd=str(tmp_path)))
        assert _SESSION_CACHE.get("requests") is True
