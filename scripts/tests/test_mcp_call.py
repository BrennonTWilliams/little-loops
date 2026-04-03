"""Tests for little_loops.mcp_call module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.mcp_call import (
    _find_server_config,
    _load_mcp_config,
    call_mcp_tool,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_MCP_CONFIG = {
    "mcpServers": {
        "my-server": {
            "command": "node",
            "args": ["server.js"],
        }
    }
}


def _make_mcp_json(tmp_path: Path, config: dict | None = None) -> Path:
    """Write a .mcp.json file and return the directory."""
    content = config if config is not None else _VALID_MCP_CONFIG
    (tmp_path / ".mcp.json").write_text(json.dumps(content))
    return tmp_path


# ---------------------------------------------------------------------------
# _load_mcp_config
# ---------------------------------------------------------------------------


class TestLoadMcpConfig:
    """Tests for _load_mcp_config."""

    def test_loads_valid_file(self, tmp_path: Path) -> None:
        """Returns parsed dict when .mcp.json exists and is valid."""
        _make_mcp_json(tmp_path)
        result = _load_mcp_config(tmp_path)
        assert result == _VALID_MCP_CONFIG

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when .mcp.json is absent."""
        with pytest.raises(FileNotFoundError, match=r"\.mcp\.json not found"):
            _load_mcp_config(tmp_path)

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        """Raises json.JSONDecodeError when .mcp.json is not valid JSON."""
        (tmp_path / ".mcp.json").write_text("{ bad json }")
        with pytest.raises(json.JSONDecodeError):
            _load_mcp_config(tmp_path)


# ---------------------------------------------------------------------------
# _find_server_config
# ---------------------------------------------------------------------------


class TestFindServerConfig:
    """Tests for _find_server_config."""

    def test_finds_existing_server(self) -> None:
        """Returns server config dict when server name exists."""
        result = _find_server_config(_VALID_MCP_CONFIG, "my-server")
        assert result == {"command": "node", "args": ["server.js"]}

    def test_returns_none_for_missing_server(self) -> None:
        """Returns None when server name is not in mcpServers."""
        result = _find_server_config(_VALID_MCP_CONFIG, "nonexistent")
        assert result is None

    def test_returns_none_when_no_mcp_servers_key(self) -> None:
        """Returns None when mcpServers key is absent from config."""
        result = _find_server_config({}, "any-server")
        assert result is None


# ---------------------------------------------------------------------------
# call_mcp_tool — config/startup errors
# ---------------------------------------------------------------------------


class TestCallMcpToolConfigErrors:
    """Tests for call_mcp_tool when .mcp.json is missing or broken."""

    def test_missing_mcp_json_returns_127(self, tmp_path: Path) -> None:
        """Returns exit code 127 when .mcp.json does not exist."""
        envelope, code = call_mcp_tool("server", "tool", {}, cwd=tmp_path)
        assert code == 127
        assert envelope["isError"] is True

    def test_invalid_json_returns_2(self, tmp_path: Path) -> None:
        """Returns exit code 2 when .mcp.json is not valid JSON."""
        (tmp_path / ".mcp.json").write_text("not json")
        envelope, code = call_mcp_tool("server", "tool", {}, cwd=tmp_path)
        assert code == 2
        assert envelope["isError"] is True

    def test_unknown_server_returns_127(self, tmp_path: Path) -> None:
        """Returns exit code 127 when server name is not in .mcp.json."""
        _make_mcp_json(tmp_path)
        envelope, code = call_mcp_tool("unknown-server", "tool", {}, cwd=tmp_path)
        assert code == 127
        assert "not found" in envelope["content"][0]["text"]

    def test_server_missing_command_returns_2(self, tmp_path: Path) -> None:
        """Returns exit code 2 when server config has no 'command' key."""
        config = {"mcpServers": {"bad-server": {"args": []}}}
        _make_mcp_json(tmp_path, config)
        envelope, code = call_mcp_tool("bad-server", "tool", {}, cwd=tmp_path)
        assert code == 2
        assert "no 'command'" in envelope["content"][0]["text"]

    def test_server_command_not_found_returns_127(self, tmp_path: Path) -> None:
        """Returns exit code 127 when the server executable does not exist."""
        config = {"mcpServers": {"s": {"command": "/nonexistent/binary_xyz"}}}
        _make_mcp_json(tmp_path, config)
        envelope, code = call_mcp_tool("s", "tool", {}, cwd=tmp_path)
        assert code == 127
        assert envelope["isError"] is True


# ---------------------------------------------------------------------------
# call_mcp_tool — successful JSON-RPC round-trips (mocked process)
# ---------------------------------------------------------------------------


def _make_proc_mock(init_response: dict, call_response: dict) -> MagicMock:
    """Create a mock Popen process that returns two JSON-RPC responses."""
    responses = [json.dumps(init_response) + "\n", json.dumps(call_response) + "\n"]
    proc = MagicMock()
    proc.stdin = MagicMock()
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.__iter__ = MagicMock(return_value=iter([]))
    proc.stdout.readline.side_effect = responses
    proc.stdout.readable.return_value = True
    proc.wait.return_value = 0
    return proc


class TestCallMcpToolSuccess:
    """Tests for call_mcp_tool with a successful round-trip (mocked subprocess)."""

    def _setup(self, tmp_path: Path) -> None:
        _make_mcp_json(tmp_path)

    def test_success_returns_0(self, tmp_path: Path) -> None:
        """Successful tool call returns exit code 0 and isError=False."""
        self._setup(tmp_path)
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05"}}
        call_resp = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"isError": False, "content": [{"type": "text", "text": "ok"}]},
        }
        proc = _make_proc_mock(init_resp, call_resp)
        with patch("little_loops.mcp_call.subprocess.Popen", return_value=proc):
            envelope, code = call_mcp_tool("my-server", "my-tool", {}, cwd=tmp_path)
        assert code == 0
        assert envelope["isError"] is False
        assert envelope["content"][0]["text"] == "ok"

    def test_tool_error_returns_1(self, tmp_path: Path) -> None:
        """Tool call returning isError=True yields exit code 1."""
        self._setup(tmp_path)
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        call_resp = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"isError": True, "content": [{"type": "text", "text": "fail"}]},
        }
        proc = _make_proc_mock(init_resp, call_resp)
        with patch("little_loops.mcp_call.subprocess.Popen", return_value=proc):
            envelope, code = call_mcp_tool("my-server", "tool", {}, cwd=tmp_path)
        assert code == 1
        assert envelope["isError"] is True


class TestCallMcpToolTimeout:
    """Tests for call_mcp_tool when the server does not respond in time."""

    def test_initialize_timeout_returns_124(self, tmp_path: Path) -> None:
        """Returns exit code 124 when initialize response never arrives."""
        _make_mcp_json(tmp_path)
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.stderr.__iter__ = MagicMock(return_value=iter([]))
        proc.stdout.readable.return_value = True
        # readline returns empty string immediately → EOF / no response
        proc.stdout.readline.return_value = ""
        proc.wait.return_value = 0

        with patch("little_loops.mcp_call.subprocess.Popen", return_value=proc):
            envelope, code = call_mcp_tool(
                "my-server", "tool", {}, timeout=0, cwd=tmp_path
            )
        assert code == 124
        assert "timeout" in envelope["content"][0]["text"].lower()

    def test_tools_call_timeout_returns_124(self, tmp_path: Path) -> None:
        """Returns exit code 124 when tools/call response never arrives."""
        _make_mcp_json(tmp_path)
        init_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.stderr.__iter__ = MagicMock(return_value=iter([]))
        proc.stdout.readable.return_value = True
        # First call returns initialize response, subsequent calls return ""
        proc.stdout.readline.side_effect = [init_resp, ""]
        proc.wait.return_value = 0

        with patch("little_loops.mcp_call.subprocess.Popen", return_value=proc):
            envelope, code = call_mcp_tool(
                "my-server", "tool", {}, timeout=0, cwd=tmp_path
            )
        assert code == 124


class TestCallMcpToolRpcErrors:
    """Tests for call_mcp_tool when JSON-RPC returns error objects."""

    def _setup(self, tmp_path: Path) -> None:
        _make_mcp_json(tmp_path)

    def test_initialize_error_returns_1(self, tmp_path: Path) -> None:
        """Returns exit code 1 when initialize response contains an error."""
        self._setup(tmp_path)
        init_resp = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "bad"}}
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.stderr.__iter__ = MagicMock(return_value=iter([]))
        proc.stdout.readable.return_value = True
        proc.stdout.readline.return_value = json.dumps(init_resp) + "\n"
        proc.wait.return_value = 0
        with patch("little_loops.mcp_call.subprocess.Popen", return_value=proc):
            envelope, code = call_mcp_tool("my-server", "tool", {}, cwd=tmp_path)
        assert code == 1
        assert "Initialize failed" in envelope["content"][0]["text"]

    def test_tool_not_found_returns_127(self, tmp_path: Path) -> None:
        """Returns exit code 127 when tools/call returns JSON-RPC method-not-found."""
        self._setup(tmp_path)
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        call_resp = {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": -32601, "message": "Method not found"},
        }
        proc = _make_proc_mock(init_resp, call_resp)
        with patch("little_loops.mcp_call.subprocess.Popen", return_value=proc):
            envelope, code = call_mcp_tool("my-server", "my-tool", {}, cwd=tmp_path)
        assert code == 127
        assert "not found" in envelope["content"][0]["text"]

    def test_generic_rpc_error_returns_1(self, tmp_path: Path) -> None:
        """Returns exit code 1 for a generic JSON-RPC error in tools/call."""
        self._setup(tmp_path)
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        call_resp = {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": -32000, "message": "server error"},
        }
        proc = _make_proc_mock(init_resp, call_resp)
        with patch("little_loops.mcp_call.subprocess.Popen", return_value=proc):
            envelope, code = call_mcp_tool("my-server", "tool", {}, cwd=tmp_path)
        assert code == 1
        assert "tools/call error" in envelope["content"][0]["text"]
