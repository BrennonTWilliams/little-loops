"""Tests for little_loops.env_file — project .env fallback loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from little_loops.env_file import load_env_fallback, parse_env_file


class TestParseEnvFile:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert parse_env_file(tmp_path / ".env") == {}

    def test_basic_pairs_comments_and_blanks(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text(
            "# comment\n\nFOO=bar\nexport TOKEN=sk-ant-oat-abc\n  SPACED = padded value \n"
        )
        assert parse_env_file(tmp_path / ".env") == {
            "FOO": "bar",
            "TOKEN": "sk-ant-oat-abc",
            "SPACED": "padded value",
        }

    def test_quoted_values_stripped(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text('A="double quoted"\nB=\'single quoted\'\nC="unbalanced\n')
        parsed = parse_env_file(tmp_path / ".env")
        assert parsed["A"] == "double quoted"
        assert parsed["B"] == "single quoted"
        assert parsed["C"] == '"unbalanced'

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("no_equals_line\n1BAD=starts-with-digit\nOK=yes\n")
        assert parse_env_file(tmp_path / ".env") == {"OK": "yes"}

    def test_empty_value_kept(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("EMPTY=\n")
        assert parse_env_file(tmp_path / ".env") == {"EMPTY": ""}


class TestLoadEnvFallback:
    def test_sets_absent_keys(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.delenv("LL_ENV_FILE_TEST_VAR", raising=False)
        (tmp_path / ".env").write_text("LL_ENV_FILE_TEST_VAR=from-dotenv\n")

        applied = load_env_fallback(tmp_path)

        assert applied == {"LL_ENV_FILE_TEST_VAR": "from-dotenv"}
        assert os.environ["LL_ENV_FILE_TEST_VAR"] == "from-dotenv"
        monkeypatch.delenv("LL_ENV_FILE_TEST_VAR", raising=False)

    def test_real_env_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setenv("LL_ENV_FILE_TEST_VAR", "from-shell")
        (tmp_path / ".env").write_text("LL_ENV_FILE_TEST_VAR=from-dotenv\n")

        applied = load_env_fallback(tmp_path)

        assert applied == {}
        assert os.environ["LL_ENV_FILE_TEST_VAR"] == "from-shell"

    def test_set_but_empty_env_var_not_overridden(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setenv("LL_ENV_FILE_TEST_VAR", "")
        (tmp_path / ".env").write_text("LL_ENV_FILE_TEST_VAR=from-dotenv\n")

        applied = load_env_fallback(tmp_path)

        assert applied == {}
        assert os.environ["LL_ENV_FILE_TEST_VAR"] == ""

    def test_no_env_file_is_noop(self, tmp_path: Path) -> None:
        assert load_env_fallback(tmp_path) == {}


class TestBRConfigWiring:
    def test_brconfig_init_loads_project_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        from little_loops.config import BRConfig

        monkeypatch.delenv("LL_ENV_FILE_TEST_VAR", raising=False)
        (tmp_path / ".env").write_text("LL_ENV_FILE_TEST_VAR=via-brconfig\n")

        BRConfig(tmp_path)

        assert os.environ["LL_ENV_FILE_TEST_VAR"] == "via-brconfig"
        monkeypatch.delenv("LL_ENV_FILE_TEST_VAR", raising=False)
