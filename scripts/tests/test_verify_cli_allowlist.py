"""Tests for ll-verify-cli-allowlist (BUG-2764)."""

from unittest.mock import patch

from little_loops.cli.verify_cli_allowlist import (
    _all_ll_entry_points,
    _areas_md_preset_tools,
    _run,
    _writers_preset_tools,
    main_verify_cli_allowlist,
)


class TestAllLlEntryPoints:
    def test_excludes_mcp_call(self) -> None:
        tools = _all_ll_entry_points()
        assert "mcp-call" not in tools
        assert all(name.startswith("ll-") for name in tools)

    def test_includes_known_tools(self) -> None:
        tools = _all_ll_entry_points()
        assert "ll-action" in tools
        assert "ll-verify-cli-allowlist" in tools


class TestPresetParsers:
    def test_areas_md_preset_tools_nonempty(self) -> None:
        assert "ll-action" in _areas_md_preset_tools()

    def test_writers_preset_tools_nonempty(self) -> None:
        assert "ll-action" in _writers_preset_tools()


class TestRun:
    def test_clean_state_returns_zero(self) -> None:
        exit_code, missing = _run()
        assert exit_code == 0
        assert missing == {"areas.md": [], "writers._LL_PERMISSIONS": []}

    def test_dirty_state_returns_one_with_missing_tool(self) -> None:
        with patch(
            "little_loops.cli.verify_cli_allowlist._all_ll_entry_points",
            return_value={"ll-action", "ll-mystery-tool"},
        ):
            exit_code, missing = _run()
        assert exit_code == 1
        assert missing["areas.md"] == ["ll-mystery-tool"]
        assert missing["writers._LL_PERMISSIONS"] == ["ll-mystery-tool"]


class TestMainVerifyCliAllowlist:
    def test_clean_state_returns_zero(self) -> None:
        with patch("sys.argv", ["ll-verify-cli-allowlist"]):
            assert main_verify_cli_allowlist() == 0

    def test_dirty_state_returns_one_with_error(self, capsys) -> None:
        with (
            patch("sys.argv", ["ll-verify-cli-allowlist"]),
            patch(
                "little_loops.cli.verify_cli_allowlist._all_ll_entry_points",
                return_value={"ll-action", "ll-mystery-tool"},
            ),
        ):
            ret = main_verify_cli_allowlist()
        captured = capsys.readouterr()
        assert ret == 1
        assert "ll-mystery-tool" in captured.err
