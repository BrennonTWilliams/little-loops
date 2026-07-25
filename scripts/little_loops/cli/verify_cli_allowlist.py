"""ll-verify-cli-allowlist: assert the ll- permission presets cover every console entry point (BUG-2764).

Parses ``[project.scripts]`` from ``scripts/pyproject.toml`` and asserts every
``ll-``-prefixed entry point (minus an explicit exclusion list) appears in both
hand-maintained permission presets: ``skills/configure/areas.md``'s "All ll-
commands" preset and ``little_loops.init.writers._LL_PERMISSIONS``. Catches the
drift this issue fixes: new CLI tools added to ``pyproject.toml`` without a
matching update to either preset.

Exit codes:
    0 - both presets cover every non-excluded ll- entry point
    1 - one or more tools are missing from one or both presets
"""

from __future__ import annotations

import argparse
import importlib.metadata as importlib_metadata
import re
import sys
from pathlib import Path

from little_loops.init.writers import _LL_PERMISSIONS
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# Non-ll- entry points (mcp-call is not part of the ll- CLI surface the
# presets document) — excluded from the parity check.
_NON_LL_TOOLS = frozenset({"mcp-call"})

_TOOL_TOKEN_RE = re.compile(r"\bll-[a-z0-9-]+\b")


def _areas_md_path() -> Path:
    """Return the path to ``skills/configure/areas.md`` in the plugin repo.

    Resolved via the shared plugin-root helper (``CLAUDE_PLUGIN_ROOT`` first)
    rather than a ``__file__`` walk: this file lives in the installed package,
    but ``areas.md`` ships in the plugin repo, so the two are only adjacent in
    a source checkout.
    """
    from little_loops.skill_expander import _find_plugin_root

    return _find_plugin_root() / "skills" / "configure" / "areas.md"


def _all_ll_entry_points() -> set[str]:
    """Return every ``ll-``-prefixed ``console_scripts`` entry point name.

    Reads installed distribution metadata instead of ``pyproject.toml``, which
    is absent from a wheel.
    """
    dist = importlib_metadata.distribution("little-loops")
    return {
        ep.name
        for ep in dist.entry_points
        if ep.group == "console_scripts"
        and ep.name.startswith("ll-")
        and ep.name not in _NON_LL_TOOLS
    }


def _areas_md_preset_tools(areas_md_path: Path | None = None) -> set[str]:
    """Return the ``ll-`` tool names listed in the "All ll- commands" preset line."""
    text = (areas_md_path or _areas_md_path()).read_text(encoding="utf-8")
    marker = "Authorize all"
    idx = text.find(marker)
    if idx == -1:
        return set()
    line_end = text.find("\n", idx)
    line = text[idx : line_end if line_end != -1 else len(text)]
    return set(_TOOL_TOKEN_RE.findall(line))


def _writers_preset_tools() -> set[str]:
    """Return the ``ll-`` tool names in ``writers._LL_PERMISSIONS``."""
    tools: set[str] = set()
    for entry in _LL_PERMISSIONS:
        match = re.match(r"Bash\((ll-[a-z0-9-]+):", entry)
        if match:
            tools.add(match.group(1))
    return tools


def _run() -> tuple[int, dict[str, list[str]]]:
    """Return ``(exit_code, {preset_name: missing_tool_names})``.

    ``areas.md`` lives in the plugin repo, not the installed package, so it is
    unavailable to a plain ``pip install``. Its absence is reported as a skip
    rather than a crash; the ``_LL_PERMISSIONS`` half still runs.
    """
    canonical = _all_ll_entry_points()
    missing: dict[str, list[str]] = {}

    areas_md = _areas_md_path()
    if areas_md.is_file():
        missing["areas.md"] = sorted(canonical - _areas_md_preset_tools(areas_md))
    else:
        print(
            f"SKIP: {areas_md} not found (plugin repo not available); "
            "checking writers._LL_PERMISSIONS only.",
            file=sys.stderr,
        )

    missing["writers._LL_PERMISSIONS"] = sorted(canonical - _writers_preset_tools())
    exit_code = 1 if any(missing.values()) else 0
    return exit_code, missing


def main_verify_cli_allowlist() -> int:
    """Entry point for ``ll-verify-cli-allowlist``."""
    with cli_event_context(DEFAULT_DB_PATH, "ll-verify-cli-allowlist", sys.argv[1:]):
        parser = argparse.ArgumentParser(
            prog="ll-verify-cli-allowlist",
            description=(
                "Assert skills/configure/areas.md and writers._LL_PERMISSIONS cover "
                "every ll- console entry point in pyproject.toml. Exits 1 on drift "
                "(BUG-2764)."
            ),
        )
        parser.parse_args()

        exit_code, missing = _run()
        if exit_code == 0:
            print("OK: all ll- CLI presets cover every pyproject.toml entry point.")
            return 0

        for preset_name, tools in missing.items():
            if tools:
                print(
                    f"ERROR: missing from {preset_name}: {', '.join(tools)}",
                    file=sys.stderr,
                )
        return exit_code


if __name__ == "__main__":
    sys.exit(main_verify_cli_allowlist())
