"""Tests for little_loops.issues.cli_surface (FEAT-3048)."""

from __future__ import annotations

import subprocess

import pytest

from little_loops.issues.cli_surface import (
    CliSurfaceIndex,
    build_cli_surface_index,
    cli_surface_accepts,
)


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
