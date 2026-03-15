"""mcp-call — thin CLI wrapper for direct MCP tool invocation.

Usage:
    mcp-call server/tool-name '{"param": "value"}'

Reads .mcp.json from the current working directory, spawns the MCP server
subprocess, performs the JSON-RPC initialize handshake, calls tools/call,
and writes the MCP response envelope to stdout.

Exit codes:
    0   → success (isError: false)
    1   → tool_error (isError: true)
    124 → timeout (transport-level)
    127 → not_found (server or tool missing from .mcp.json)
    2   → usage/config error
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

MCP_PROTOCOL_VERSION = "2024-11-05"
_DEFAULT_TIMEOUT = 30  # seconds


def _load_mcp_config(cwd: Path) -> dict[str, Any]:
    """Load .mcp.json from the current working directory.

    Args:
        cwd: Directory to search for .mcp.json

    Returns:
        Parsed .mcp.json content

    Raises:
        FileNotFoundError: If .mcp.json not found
        json.JSONDecodeError: If .mcp.json is invalid JSON
    """
    mcp_path = cwd / ".mcp.json"
    if not mcp_path.exists():
        raise FileNotFoundError(f".mcp.json not found in {cwd}")
    result: dict[str, Any] = json.loads(mcp_path.read_text())
    return result


def _find_server_config(mcp_config: dict[str, Any], server_name: str) -> dict[str, Any] | None:
    """Find server configuration by name in .mcp.json.

    Args:
        mcp_config: Parsed .mcp.json content
        server_name: Server name to find

    Returns:
        Server config dict, or None if not found
    """
    servers: dict[str, Any] = mcp_config.get("mcpServers", {})
    found: dict[str, Any] | None = servers.get(server_name)
    return found


def _send_jsonrpc(
    proc: subprocess.Popen[str],
    request: dict[str, Any],
    request_id: int | None,
    timeout: float,
) -> dict[str, Any] | None:
    """Send a JSON-RPC request and optionally wait for a response.

    Args:
        proc: Running MCP server process
        request: JSON-RPC request dict
        request_id: Expected response id (None for notifications)
        timeout: Seconds to wait for response

    Returns:
        Parsed response dict, or None for notifications
    """
    assert proc.stdin is not None
    line = json.dumps(request) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()

    if request_id is None:
        # Notification — no response expected
        return None

    # Read response lines until we find the matching id or timeout
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc.stdout.readable()
        try:
            response_line = proc.stdout.readline()
        except (OSError, ValueError):
            break
        if not response_line:
            break
        response_line = response_line.strip()
        if not response_line:
            continue
        try:
            response: dict[str, Any] = json.loads(response_line)
            if response.get("id") == request_id:
                return response
        except json.JSONDecodeError:
            continue

    return None


def call_mcp_tool(
    server_name: str,
    tool_name: str,
    params: dict[str, Any],
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: Path | None = None,
) -> tuple[dict[str, Any], int]:
    """Call an MCP tool via JSON-RPC and return the response envelope + exit code.

    Args:
        server_name: MCP server name (from .mcp.json mcpServers key)
        tool_name: Tool name to call
        params: Tool arguments
        timeout: Timeout in seconds
        cwd: Directory containing .mcp.json (defaults to Path.cwd())

    Returns:
        Tuple of (MCP response envelope dict, exit code)
        Exit codes:
            0   → success
            1   → tool_error
            124 → timeout
            127 → not_found
            2   → config/usage error
    """
    if cwd is None:
        cwd = Path.cwd()

    # Load .mcp.json
    try:
        mcp_config = _load_mcp_config(cwd)
    except FileNotFoundError as e:
        return {"isError": True, "content": [{"type": "text", "text": str(e)}]}, 127
    except json.JSONDecodeError as e:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Invalid .mcp.json: {e}"}],
        }, 2

    # Find server config
    server_config = _find_server_config(mcp_config, server_name)
    if server_config is None:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Server '{server_name}' not found in .mcp.json"}],
        }, 127

    # Build server command
    command = server_config.get("command")
    if not command:
        return {
            "isError": True,
            "content": [
                {"type": "text", "text": f"Server '{server_name}' has no 'command' in .mcp.json"}
            ],
        }, 2

    args = server_config.get("args", [])
    env_overrides = server_config.get("env", {})

    import os

    env = os.environ.copy()
    env.update({k: str(v) for k, v in env_overrides.items()})

    cmd = [command] + args

    # Spawn server
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except FileNotFoundError:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Server command not found: {command}"}],
        }, 127

    stderr_chunks: list[str] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_chunks.append(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        # Step 1: Send initialize request
        init_response = _send_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-call", "version": "1.0"},
                },
            },
            request_id=1,
            timeout=timeout,
        )

        if init_response is None:
            proc.kill()
            return {
                "isError": True,
                "content": [
                    {"type": "text", "text": "No response to initialize request (timeout)"}
                ],
            }, 124

        if "error" in init_response:
            proc.kill()
            return {
                "isError": True,
                "content": [
                    {"type": "text", "text": f"Initialize failed: {init_response['error']}"}
                ],
            }, 1

        # Step 2: Send initialized notification
        _send_jsonrpc(
            proc,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            request_id=None,
            timeout=0,
        )

        # Step 3: Call tools/call
        call_response = _send_jsonrpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": params},
            },
            request_id=2,
            timeout=timeout,
        )

        if call_response is None:
            proc.kill()
            return {
                "isError": True,
                "content": [
                    {"type": "text", "text": "No response to tools/call request (timeout)"}
                ],
            }, 124

        if "error" in call_response:
            err = call_response["error"]
            # JSON-RPC method not found → tool not found
            if isinstance(err, dict) and err.get("code") == -32601:
                return {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool '{tool_name}' not found on server '{server_name}'",
                        }
                    ],
                }, 127
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"tools/call error: {err}"}],
            }, 1

        # Unwrap result from JSON-RPC envelope
        result = call_response.get("result", {})
        is_error = result.get("isError", False)
        exit_code = 1 if is_error else 0
        return result, exit_code

    except subprocess.TimeoutExpired:
        proc.kill()
        return {
            "isError": True,
            "content": [{"type": "text", "text": "MCP tool call timed out"}],
        }, 124
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        stderr_thread.join(timeout=5)


def main() -> None:
    """Entry point for mcp-call CLI."""
    if len(sys.argv) < 3:
        print(
            'Usage: mcp-call server/tool-name \'{"param": "value"}\'',
            file=sys.stderr,
        )
        sys.exit(2)

    spec = sys.argv[1]
    params_json = sys.argv[2]

    # Parse server/tool-name
    if "/" not in spec:
        print(
            f"Error: spec must be 'server/tool-name', got: {spec!r}",
            file=sys.stderr,
        )
        sys.exit(2)

    server_name, tool_name = spec.split("/", 1)

    # Parse params JSON
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError as e:
        print(f"Error: invalid params JSON: {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(params, dict):
        print("Error: params must be a JSON object", file=sys.stderr)
        sys.exit(2)

    envelope, exit_code = call_mcp_tool(
        server_name=server_name,
        tool_name=tool_name,
        params=params,
    )

    print(json.dumps(envelope))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
