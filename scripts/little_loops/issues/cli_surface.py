"""CLI surface introspection via ``--help`` scraping (FEAT-3048).

§ CLI-Flag Introspection Mechanism, option (a): most ``ll-*`` console
scripts build their ``ArgumentParser`` inline inside ``main_*()`` and
dispatch in the same function (93 inline ``ArgumentParser(`` sites across
``cli/``), so there is nothing to import without executing the command.
This module subprocess-scrapes ``<tool> --help`` and ``<tool> <sub>
--help`` instead, caching the result into ``{tool: {subcommand:
set[long_flag]}}``.

Scraping is **lazy, per tool**, on a shared :class:`CliSurfaceIndex` built
once per ``format-check`` invocation: a tool is only scraped the first time
a claim actually names it, and the result is cached on the index for every
later lookup in the same invocation (including the repo-wide sweep). Eagerly
scraping all ~50 registered tools up front was tried first and rejected —
most invocations cite zero or one tool, so paying the full-surface cost
every time made every single-issue ``format-check`` call multiple seconds
slower for no benefit, and it is unnecessary to satisfy the "no repeated
subprocess spawning per issue" requirement the shared, cached index already
provides.

A tool whose ``--help`` cannot be parsed contributes no claims rather than
false ones — recorded in :attr:`CliSurfaceIndex.unscrapable`, the same
fail-open convention as :class:`little_loops.text_utils.RefIndex`.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

_SUBCOMMAND_CHOICES_RE = re.compile(r"\{([a-z0-9_,-]+)\}")
# Option-definition lines in argparse's default HelpFormatter are indented
# exactly two spaces (description continuation lines are indented further),
# e.g. "  --format {text,json}, -f {text,json}" or "  -h, --help".
_LONG_FLAG_RE = re.compile(r"^  (?:-\w, )?(--[a-z][a-z0-9-]*)", re.MULTILINE)
_HELP_TIMEOUT_SECONDS = 10
_MAX_WORKERS = 12


@dataclass
class CliSurfaceIndex:
    """``{tool: {subcommand: set[long_flag]}}`` plus the set of unscrapable tools.

    Both fields double as a lazy-population cache: :func:`cli_surface_accepts`
    fills them in on first query for a given tool rather than
    :func:`build_cli_surface_index` filling them in eagerly for every
    registered tool.
    """

    surface: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    unscrapable: set[str] = field(default_factory=set)
    _known_tools: set[str] | None = field(default=None, repr=False, compare=False)


def _all_ll_tools() -> set[str]:
    """Every ``ll-``-prefixed ``console_scripts`` entry point (installed metadata)."""
    try:
        dist = importlib_metadata.distribution("little-loops")
    except importlib_metadata.PackageNotFoundError:
        return set()
    return {
        ep.name
        for ep in dist.entry_points
        if ep.group == "console_scripts" and ep.name.startswith("ll-")
    }


def _run_help(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_HELP_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def _scrape_tool(tool: str) -> dict[str, set[str]] | None:
    top_help = _run_help([tool, "--help"])
    if top_help is None:
        return None

    subs_match = _SUBCOMMAND_CHOICES_RE.search(top_help)
    if not subs_match:
        # No subparsers -- top-level flags only, keyed under "".
        return {"": set(_LONG_FLAG_RE.findall(top_help))}

    subcommands = sorted({s for s in subs_match.group(1).split(",") if s})
    tool_surface: dict[str, set[str]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        sub_helps = pool.map(lambda sub: (sub, _run_help([tool, sub, "--help"])), subcommands)
        for sub, sub_help in sub_helps:
            if sub_help is not None:
                tool_surface[sub] = set(_LONG_FLAG_RE.findall(sub_help))
    return tool_surface


def build_cli_surface_index() -> CliSurfaceIndex:
    """Return an empty, lazily-populated :class:`CliSurfaceIndex`.

    Cheap and instant — no subprocess spawned here. Built once per
    ``format-check`` invocation and threaded into
    :func:`~little_loops.issue_parser.check_format_gaps` via the
    ``cli_index`` kwarg; actual scraping happens in
    :func:`cli_surface_accepts`, on first query per tool.
    """
    return CliSurfaceIndex()


def _tool_surface(index: CliSurfaceIndex, tool: str) -> dict[str, set[str]] | None:
    """Return *tool*'s cached surface, scraping and caching it on first query."""
    if tool in index.surface:
        return index.surface[tool]
    if tool in index.unscrapable:
        return None

    if index._known_tools is None:
        index._known_tools = _all_ll_tools()
    if tool not in index._known_tools:
        index.unscrapable.add(tool)
        return None

    surface = _scrape_tool(tool)
    if surface is None:
        index.unscrapable.add(tool)
        return None
    index.surface[tool] = surface
    return surface


def cli_surface_accepts(
    index: CliSurfaceIndex, tool: str, subcommand: str, flag: str | None = None
) -> bool | None:
    """Does *tool*'s CLI surface accept *subcommand* (and, if given, *flag*)?

    Scrapes and caches *tool*'s surface onto *index* on first query for that
    tool (see module docstring); every later call for the same tool, on the
    same or a different issue within the same invocation, is a cache hit.

    Returns:
        True/False, or ``None`` (fail open) when *tool* was unscrapable or is
        not a registered ``ll-*`` console script.
    """
    tool_surface = _tool_surface(index, tool)
    if tool_surface is None:
        return None
    if subcommand not in tool_surface:
        return False
    if flag is None:
        return True
    return flag in tool_surface[subcommand]
