"""Tests for little_loops.issues.cli_surface (FEAT-3048)."""

from __future__ import annotations

import subprocess

import pytest

from little_loops.issues import cli_surface
from little_loops.issues.cli_surface import (
    CliSurfaceIndex,
    build_cli_surface_index,
    cli_surface_accepts,
)

# Real `ll-learning-tests --help` output (BUG-3074): a metavar-based
# subparsers action ("COMMAND", no brace choices list) with subcommand
# entries nested 4 spaces deep, one of them ("orphans") wrapping its
# description onto a further-indented continuation line.
_METAVAR_SUBCOMMANDS_HELP = """usage: ll-learning-tests [-h] COMMAND ...

Query and manage the little-loops learning test registry

positional arguments:
  COMMAND
    check       Print a record as JSON; exit 1 if not found
    list        Print all records as a JSON array
    mark-stale  Mark a record as stale; exit 1 if not found
    orphans     List records for packages no longer imported; exit 1 if any
                found
    prove       Trigger proving for a target; print the refreshed record

options:
  -h, --help    show this help message and exit
"""

# A "positional arguments:" block whose lone entry is a plain positional
# (not a subparsers action) -- no 4-space-indented subcommand entries
# beneath it, so the subcommand list cannot be determined.
_AMBIGUOUS_POSITIONAL_HELP = """usage: ll-fake-tool [-h] FILE

positional arguments:
  FILE  path to input file

options:
  -h, --help  show this help message and exit
"""


@pytest.fixture
def index() -> CliSurfaceIndex:
    return CliSurfaceIndex(
        surface={"ll-issues": {"link": {"--blocked-by", "--depends-on", "--relates-to"}}},
        unscrapable={"ll-broken-tool"},
    )


def test_accepts_known_subcommand_and_flag(index: CliSurfaceIndex) -> None:
    assert cli_surface_accepts(index, "ll-issues", "link", "--blocked-by") is True


def test_rejects_unknown_flag(index: CliSurfaceIndex) -> None:
    assert cli_surface_accepts(index, "ll-issues", "link", "--parent") is False


def test_rejects_unknown_subcommand(index: CliSurfaceIndex) -> None:
    assert cli_surface_accepts(index, "ll-issues", "no-such-subcommand") is False


def test_subcommand_only_query_accepts_known_subcommand(index: CliSurfaceIndex) -> None:
    assert cli_surface_accepts(index, "ll-issues", "link") is True


def test_fails_open_for_unscrapable_tool(index: CliSurfaceIndex) -> None:
    assert cli_surface_accepts(index, "ll-broken-tool", "anything", "--flag") is None


def test_fails_open_for_unregistered_tool(index: CliSurfaceIndex) -> None:
    assert cli_surface_accepts(index, "ll-not-a-real-tool", "anything") is None


def test_build_cli_surface_index_spawns_no_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("build_cli_surface_index must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    idx = build_cli_surface_index()
    assert idx.surface == {}
    assert idx.unscrapable == set()


def test_cache_hit_avoids_a_second_scrape(
    index: CliSurfaceIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("a cached tool must not be re-scraped")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert cli_surface_accepts(index, "ll-issues", "link", "--blocked-by") is True
    assert cli_surface_accepts(index, "ll-issues", "link", "--parent") is False


def test_scrape_tool_recognizes_metavar_style_subcommands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run_help(args: list[str]) -> str:
        if args == ["ll-learning-tests", "--help"]:
            return _METAVAR_SUBCOMMANDS_HELP
        return "usage: ...\n\noptions:\n  -h, --help  show this help message and exit\n"

    monkeypatch.setattr(cli_surface, "_run_help", _fake_run_help)
    surface = cli_surface._scrape_tool("ll-learning-tests")
    assert surface is not None
    assert set(surface) == {"check", "list", "mark-stale", "orphans", "prove"}


def test_scrape_tool_fails_open_for_undetermined_positional_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_surface, "_run_help", lambda args: _AMBIGUOUS_POSITIONAL_HELP)
    assert cli_surface._scrape_tool("ll-fake-tool") is None


def test_cli_surface_accepts_fails_open_for_undetermined_subcommand_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_surface, "_run_help", lambda args: _AMBIGUOUS_POSITIONAL_HELP)
    idx = CliSurfaceIndex(_known_tools={"ll-fake-tool"})
    assert cli_surface_accepts(idx, "ll-fake-tool", "anything") is None


@pytest.mark.timeout(120)
@pytest.mark.parametrize(
    "tool,expected_subcommands",
    [
        ("ll-learning-tests", {"check", "list", "mark-stale", "orphans", "prove"}),
        ("ll-queue", {"add", "list", "status", "remove", "run", "requeue"}),
        ("ll-harness", {"skill", "cmd", "mcp", "prompt", "dsl"}),
        ("ll-action", {"invoke", "capabilities", "list"}),
    ],
)
def test_build_cli_surface_index_against_real_metavar_tools(
    tool: str, expected_subcommands: set[str]
) -> None:
    """Integration: BUG-3074 regression -- these four tools set ``metavar=``
    on ``add_subparsers`` (so ``--help`` shows COMMAND/RUNNER, not a brace
    choices list); every subcommand their real ``--help`` documents must be
    accepted, not misread as having no subcommands at all.
    """
    idx = build_cli_surface_index()
    for sub in expected_subcommands:
        assert cli_surface_accepts(idx, tool, sub) is True


@pytest.mark.timeout(120)
def test_build_cli_surface_index_against_real_ll_issues_link() -> None:
    """Integration: scrapes this repo's real installed `ll-issues` CLI and
    reproduces the exact FEAT-2942 regression this issue exists to catch —
    `ll-issues link --parent` (no such flag) — while confirming a real,
    existing flag still resolves. build_cli_surface_index() itself is
    instant/empty; the first cli_surface_accepts() query triggers (and
    caches) the actual --help scrape.
    """
    idx = build_cli_surface_index()
    assert idx.surface == {}
    assert cli_surface_accepts(idx, "ll-issues", "link", "--blocked-by") is True
    assert "ll-issues" in idx.surface
    assert cli_surface_accepts(idx, "ll-issues", "link", "--parent") is False
