"""Tests for little_loops.hooks.learning_tests_gate (FEAT-1742)."""

from __future__ import annotations

import datetime
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
    stale_after_days: int | None = None,
) -> None:
    ll_dir = project_dir / ".ll"
    ll_dir.mkdir(parents=True, exist_ok=True)
    disc: dict = {"mode": mode}
    if skip_packages is not None:
        disc["skip_packages"] = skip_packages
    lt_config: dict = {"enabled": enabled, "discoverability": disc}
    if stale_after_days is not None:
        lt_config["stale_after_days"] = stale_after_days
    (ll_dir / "ll-config.json").write_text(
        json.dumps({"learning_tests": lt_config}),
        encoding="utf-8",
    )


def _write_record(project_dir: Path, target: str, status: str, date: str | None = None) -> None:
    """Write a minimal learning-test record as a frontmatter YAML file.

    ``date`` defaults to today so proven records are fresh unless explicitly overridden.
    """
    lt_dir = project_dir / ".ll" / "learning-tests"
    lt_dir.mkdir(parents=True, exist_ok=True)
    slug = target.lower()
    record_date = date if date is not None else datetime.date.today().isoformat()
    content = f"---\ntarget: {target}\ndate: '{record_date}'\nstatus: {status}\nassertions: []\n---\n"
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


# ---------------------------------------------------------------------------
# Stale-age gate (ENH-2208)
# ---------------------------------------------------------------------------


class TestStaleAgeGate:
    def test_proven_record_older_than_threshold_triggers_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A proven record older than stale_after_days triggers the gate."""
        _write_config(tmp_path, enabled=True, mode="warn", stale_after_days=30)
        _write_record(tmp_path, "stripe", "proven", date="2020-01-01")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is not None
        assert "stripe" in result.feedback

    def test_proven_record_within_threshold_passes_silently(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A proven record within stale_after_days passes silently."""
        _write_config(tmp_path, enabled=True, mode="warn", stale_after_days=30)
        _write_record(tmp_path, "stripe", "proven")  # defaults to today (fresh)
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 0
        assert result.feedback is None

    def test_stale_proven_record_cached_as_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stale proven record is cached as False so repeated checks short-circuit."""
        _write_config(tmp_path, enabled=True, mode="warn", stale_after_days=30)
        _write_record(tmp_path, "stripe", "proven", date="2020-01-01")
        monkeypatch.chdir(tmp_path)
        gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert _SESSION_CACHE.get("stripe") is False

    def test_hint_includes_stale_age(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The hint message includes '(stale: N days old)' for stale records."""
        _write_config(tmp_path, enabled=True, mode="warn", stale_after_days=30)
        _write_record(tmp_path, "stripe", "proven", date="2020-01-01")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.feedback is not None
        assert "stale" in result.feedback

    def test_block_mode_rejects_stale_record(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Block mode returns exit_code=2 for stale proven records."""
        _write_config(tmp_path, enabled=True, mode="block", stale_after_days=30)
        _write_record(tmp_path, "stripe", "proven", date="2020-01-01")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.exit_code == 2
        assert result.feedback is not None

    def test_stale_after_days_zero_clamped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stale_after_days=0 is clamped to 1; old records are still treated as stale."""
        _write_config(tmp_path, enabled=True, mode="warn", stale_after_days=0)
        _write_record(tmp_path, "stripe", "proven", date="2020-01-01")
        monkeypatch.chdir(tmp_path)
        result = gate(_event(content="import stripe\n", cwd=str(tmp_path)))
        assert result.feedback is not None


# ---------------------------------------------------------------------------
# is_record_stale helper (ENH-2208)
# ---------------------------------------------------------------------------


class TestIsRecordStale:
    """Tests for the is_record_stale helper in little_loops.learning_tests.gate."""

    def _make_record(self, date: str) -> object:
        from little_loops.learning_tests import LearnTestRecord

        return LearnTestRecord(
            target="stripe", date=date, status="proven", assertions=[], raw_output_path=None
        )

    def test_old_record_is_stale(self) -> None:
        from little_loops.learning_tests.gate import is_record_stale

        assert is_record_stale(self._make_record("2020-01-01"), 30) is True

    def test_fresh_record_is_not_stale(self) -> None:
        from little_loops.learning_tests.gate import is_record_stale

        today = datetime.date.today().isoformat()
        assert is_record_stale(self._make_record(today), 30) is False

    def test_stale_after_days_zero_clamped_to_one(self) -> None:
        from little_loops.learning_tests.gate import is_record_stale

        assert is_record_stale(self._make_record("2020-01-01"), 0) is True

    def test_invalid_date_treated_as_fresh(self) -> None:
        from little_loops.learning_tests.gate import is_record_stale

        assert is_record_stale(self._make_record("not-a-date"), 30) is False

    def test_exactly_at_threshold_is_not_stale(self) -> None:
        """A record exactly at the threshold (age_days == stale_after_days) is NOT stale."""
        from little_loops.learning_tests.gate import is_record_stale

        threshold = 30
        edge_date = (datetime.date.today() - datetime.timedelta(days=threshold)).isoformat()
        assert is_record_stale(self._make_record(edge_date), threshold) is False

    def test_one_day_over_threshold_is_stale(self) -> None:
        from little_loops.learning_tests.gate import is_record_stale

        threshold = 30
        stale_date = (datetime.date.today() - datetime.timedelta(days=threshold + 1)).isoformat()
        assert is_record_stale(self._make_record(stale_date), threshold) is True
