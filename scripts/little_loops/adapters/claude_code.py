"""ClaudeCodeEmitter: host adapter for Claude Code (FEAT-3139).

Claude Code discovers skills/commands/agents natively through the plugin
marketplace, so this emitter implements only ``emit_mcp_config`` (writing
``.mcp.json`` at the project root); the other three ``emit_*`` methods are
stubs that keep the ``HostEmitter`` Protocol satisfiable, following the
``gemini``/``omp``/``kimi`` precedent for their unimplemented methods.
"""

from __future__ import annotations

import json
from pathlib import Path

from little_loops.file_utils import atomic_write_json

__all__ = ["ClaudeCodeEmitter"]


class ClaudeCodeEmitter:
    """Output emitter for Claude Code (``--host claude-code``).

    Writes ``.mcp.json`` at the project root, merging the ``ll-mcp`` server
    entry into any existing ``mcpServers`` content rather than overwriting
    it (precedent: ``init/writers.py:merge_settings()``).
    """

    name = "claude-code"

    def emit_skill(self, skill_meta: dict) -> str:
        """No skill emission for Claude Code; the plugin marketplace serves skills natively."""
        return "skipped"

    def emit_command(self, cmd_meta: dict) -> str:
        """No command emission for Claude Code; the plugin marketplace serves commands natively."""
        return "skipped"

    def emit_agent(self, agent_meta: dict) -> str:
        """No agent emission for Claude Code; the plugin marketplace serves agents natively."""
        return "skipped"

    def emit_mcp_config(self, meta: dict) -> str:
        """Merge the ``ll-mcp`` server entry into ``<output_dir>/.mcp.json``."""
        output_dir: Path = meta["output_dir"]
        apply: bool = meta["apply"]
        quiet: bool = meta["quiet"]

        path = output_dir / ".mcp.json"
        if path.exists():
            try:
                data: dict = json.loads(path.read_text())
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        servers: dict = data.setdefault("mcpServers", {})
        new_entry = {"command": "ll-mcp"}

        if servers.get("ll-mcp") == new_entry:
            if not quiet:
                print("  SKIP   mcp-config: already up to date")
            return "skipped"

        servers["ll-mcp"] = new_entry

        if apply:
            atomic_write_json(path, data)
            if not quiet:
                print("  APPLY  mcp-config: ll-mcp")
        else:
            if not quiet:
                print("  DRY    mcp-config: ll-mcp")

        return "adapted"
