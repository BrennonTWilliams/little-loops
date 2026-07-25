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
import re
import sys
import tomllib
from pathlib import Path

from little_loops.init.writers import _LL_PERMISSIONS
from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context

# Non-ll- entry points (mcp-call is not part of the ll- CLI surface the
# presets document) — excluded from the parity check.
_NON_LL_TOOLS = frozenset({"mcp-call"})

_PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"

_AREAS_MD_PATH = Path(__file__).resolve().parents[3] / "skills" / "configure" / "areas.md"

_TOOL_TOKEN_RE = re.compile(r"\bll-[a-z0-9-]+\b")


def _all_ll_entry_points(pyproject_path: Path = _PYPROJECT_PATH) -> set[str]:
    """Return every ``ll-``-prefixed ``[project.scripts]`` entry point name."""
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    scripts = data["project"]["scripts"]
    return {name for name in scripts if name.startswith("ll-") and name not in _NON_LL_TOOLS}


def _areas_md_preset_tools(areas_md_path: Path = _AREAS_MD_PATH) -> set[str]:
    """Return the ``ll-`` tool names listed in the "All ll- commands" preset line."""
    text = areas_md_path.read_text(encoding="utf-8")
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
    """Return ``(exit_code, {preset_name: missing_tool_names})``."""
    canonical = _all_ll_entry_points()
    missing = {
        "areas.md": sorted(canonical - _areas_md_preset_tools()),
        "writers._LL_PERMISSIONS": sorted(canonical - _writers_preset_tools()),
    }
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
