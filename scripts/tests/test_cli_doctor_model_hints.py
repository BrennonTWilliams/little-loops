"""Tests for the ll-doctor "Model hints" section (ENH-3641)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import little_loops.cli.doctor as doctor_mod


class _Orch:
    def __init__(self, model_hints: Any) -> None:
        self.model_hints = model_hints


class _Cfg:
    def __init__(self, model_hints: Any) -> None:
        self.orchestration = _Orch(model_hints)

    def __call__(self, *_a: Any, **_k: Any) -> _Cfg:
        return self


@pytest.fixture
def catalog_stdout(fixtures_dir: Path) -> str:
    return (fixtures_dir / "codex" / "models-catalog.json").read_text()


@pytest.fixture(autouse=True)
def _no_codex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))


def _configure(monkeypatch: pytest.MonkeyPatch, model_hints: Any) -> None:
    monkeypatch.setattr("little_loops.config.BRConfig", _Cfg(model_hints))


def _runner(detected: bool = True) -> MagicMock:
    runner = MagicMock()
    runner.detect.return_value = detected
    runner.build_version_check.return_value = MagicMock(binary="codex", args=["--version"])
    return runner


def _run_with(
    monkeypatch: pytest.MonkeyPatch,
    model_hints: Any,
    *,
    stdout: str = "",
    returncode: int = 0,
    side_effect: Exception | None = None,
    detected: bool = True,
) -> tuple[list[dict[str, Any]], MagicMock]:
    _configure(monkeypatch, model_hints)
    monkeypatch.setattr("little_loops.host_runner.resolve_host_named", lambda n: _runner(detected))
    with patch("little_loops.cli.doctor.subprocess.run") as mock_run:
        if side_effect is not None:
            mock_run.side_effect = side_effect
        else:
            mock_run.return_value = MagicMock(returncode=returncode, stdout=stdout, stderr="")
        rows = doctor_mod._model_hints_data()
    return rows, mock_run


def _by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["name"]: r for r in rows}


class TestParseCodexCatalog:
    def test_pins_fields(self, catalog_stdout: str) -> None:
        cat = doctor_mod._parse_codex_catalog(catalog_stdout)
        assert cat is not None
        assert cat["gpt-ok"] == {"visibility": "list", "upgrade_model": None, "retirement_at": None}
        assert cat["gpt-hidden"]["visibility"] == "hide"
        assert cat["gpt-future-retire"]["upgrade_model"] == "gpt-next"
        assert cat["gpt-future-retire"]["retirement_at"] == "2999-01-01T00:00:00Z"

    @pytest.mark.parametrize("stdout", ["not json", "[]", "{}", '{"models": {}}', ""])
    def test_schema_surprise_returns_none(self, stdout: str) -> None:
        assert doctor_mod._parse_codex_catalog(stdout) is None


class TestModelHintsVerdicts:
    def test_verdicts(self, monkeypatch: pytest.MonkeyPatch, catalog_stdout: str) -> None:
        hints = {
            "codex": {
                "coding": "gpt-ok",
                "reasoning": "gpt-hidden",
                "burst": "gpt-missing",
            }
        }
        rows, mock_run = _run_with(monkeypatch, hints, stdout=catalog_stdout)
        by = _by_name(rows)
        assert by["codex.coding"]["status"] == "full"
        assert by["codex.reasoning"]["status"] == "partial"
        assert "hidden in codex catalog" in by["codex.reasoning"]["note"]
        assert by["codex.burst"]["status"] == "partial"
        assert "not listed in codex catalog" in by["codex.burst"]["note"]
        assert all(r["severity"] == "informational" and r["checked"] for r in rows)
        # refreshed catalog: no --bundled
        cmd = mock_run.call_args.args[0]
        assert cmd == ["codex", "debug", "models"]

    def test_future_retirement(self, monkeypatch: pytest.MonkeyPatch, catalog_stdout: str) -> None:
        rows, _ = _run_with(
            monkeypatch, {"codex": {"coding": "gpt-future-retire"}}, stdout=catalog_stdout
        )
        note = rows[0]["note"]
        assert rows[0]["status"] == "partial"
        assert "gpt-next" in note and "retires 2999-01-01" in note
        assert 'set orchestration.model_hints.codex.coding to "gpt-next"' in note

    def test_past_retirement(self, monkeypatch: pytest.MonkeyPatch, catalog_stdout: str) -> None:
        rows, _ = _run_with(
            monkeypatch, {"codex": {"coding": "gpt-past-retire"}}, stdout=catalog_stdout
        )
        assert "retired on 2020-01-01" in rows[0]["note"]

    def test_hidden_and_upgraded_is_upgrade_verdict_with_hidden_appended(
        self, monkeypatch: pytest.MonkeyPatch, catalog_stdout: str
    ) -> None:
        rows, _ = _run_with(
            monkeypatch, {"codex": {"coding": "gpt-hidden-upgraded"}}, stdout=catalog_stdout
        )
        note = rows[0]["note"]
        assert "superseded by gpt-next" in note
        assert note.endswith("also hidden in codex catalog")


class TestModelHintsRowShapes:
    def test_none_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows, mock_run = _run_with(monkeypatch, {})
        assert len(rows) == 1
        assert rows[0]["note"] == "none configured" and rows[0]["checked"] is False
        mock_run.assert_not_called()

    def test_false_values_and_no_binary_backends_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hints = {
            "codex": {"coding": False},
            "anthropic-api": {"coding": "opus"},
            "fake": {"burst": "x"},
        }
        rows, mock_run = _run_with(monkeypatch, hints)
        assert [r["note"] for r in rows] == ["none configured"]
        mock_run.assert_not_called()

    def test_backend_without_catalog_not_checked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows, mock_run = _run_with(
            monkeypatch, {"claude-code": {"coding": "sonnet", "burst": "haiku"}}
        )
        assert len(rows) == 1
        assert rows[0]["name"] == "claude-code"
        assert rows[0]["note"] == "not checked: no model catalog for claude-code"
        assert rows[0]["checked"] is False
        mock_run.assert_not_called()

    def test_custom_model_provider_not_checked(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        home = tmp_path / "codex-home"
        home.mkdir()
        (home / "config.toml").write_text('model_provider = "ollama"\n')
        rows, mock_run = _run_with(monkeypatch, {"codex": {"coding": "gpt-ok"}})
        assert rows[0]["note"] == "not checked: custom model_provider ollama"
        assert rows[0]["checked"] is False
        mock_run.assert_not_called()

    def test_openai_model_provider_is_probed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, catalog_stdout: str
    ) -> None:
        home = tmp_path / "codex-home"
        home.mkdir()
        (home / "config.toml").write_text('model_provider = "openai"\n')
        rows, _ = _run_with(monkeypatch, {"codex": {"coding": "gpt-ok"}}, stdout=catalog_stdout)
        assert rows[0]["name"] == "codex.coding" and rows[0]["status"] == "full"

    def test_unreadable_config_toml_treated_as_unset(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, catalog_stdout: str
    ) -> None:
        home = tmp_path / "codex-home"
        home.mkdir()
        (home / "config.toml").write_text("not = [valid toml")
        rows, _ = _run_with(monkeypatch, {"codex": {"coding": "gpt-ok"}}, stdout=catalog_stdout)
        assert rows[0]["status"] == "full"

    def test_non_dict_model_hints_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows, mock_run = _run_with(monkeypatch, MagicMock())
        assert [r["note"] for r in rows] == ["none configured"]
        mock_run.assert_not_called()


class TestModelHintsProbeFailures:
    HINTS = {"codex": {"coding": "gpt-ok"}}

    @pytest.mark.parametrize(
        ("kwargs", "fragment"),
        [
            ({"detected": False}, "binary not detected"),
            ({"returncode": 2}, "exited 2"),
            ({"side_effect": subprocess.TimeoutExpired("codex", 20)}, "timed out"),
            ({"side_effect": FileNotFoundError("codex")}, "FileNotFoundError"),
            ({"stdout": "{not json"}, "unparseable"),
            ({"stdout": '{"other": []}'}, "unparseable"),
            ({"stdout": '{"models": "x"}'}, "unparseable"),
        ],
    )
    def test_failure_rows_never_raise_or_fail_exit(
        self, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any], fragment: str
    ) -> None:
        rows, _ = _run_with(monkeypatch, self.HINTS, **kwargs)
        assert len(rows) == 1
        assert rows[0]["name"] == "codex"
        assert rows[0]["note"].startswith("catalog unavailable:")
        assert fragment in rows[0]["note"]
        assert rows[0]["severity"] == "informational"
        assert doctor_mod._exit_code_for(doctor_mod._model_hints_check()) == 0

    def test_unresolvable_host_is_contained(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from little_loops.host_runner import HostNotConfigured

        _configure(monkeypatch, self.HINTS)

        def boom(_name: str) -> None:
            raise HostNotConfigured("nope")

        monkeypatch.setattr("little_loops.host_runner.resolve_host_named", boom)
        rows = doctor_mod._model_hints_data()
        assert rows[0]["note"].startswith("catalog unavailable:")

    def test_probe_memoized_per_backend(
        self, monkeypatch: pytest.MonkeyPatch, catalog_stdout: str
    ) -> None:
        hints = {"codex": {"coding": "gpt-ok", "burst": "gpt-hidden"}}
        _, mock_run = _run_with(monkeypatch, hints, stdout=catalog_stdout)
        assert mock_run.call_count == 1


class TestModelHintsWiring:
    def test_check_registered_and_exit_neutral(
        self, monkeypatch: pytest.MonkeyPatch, catalog_stdout: str
    ) -> None:
        assert doctor_mod._model_hints_check in doctor_mod._CHECKS
        _run_with(monkeypatch, {"codex": {"coding": "gpt-hidden"}}, stdout=catalog_stdout)
        assert doctor_mod._exit_code_for(doctor_mod._model_hints_check()) == 0

    def test_print_section_uses_dash_for_unchecked(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _configure(monkeypatch, {"claude-code": {"coding": "sonnet"}})
        doctor_mod._print_model_hints_section()
        out = capsys.readouterr().out
        assert "Model hints" in out
        assert "–  claude-code  not checked" in out
        assert "✗" not in out
