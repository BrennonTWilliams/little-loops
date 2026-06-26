"""Pytest fixtures and options for host conformance tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --conformance-host option for filtering conformance tests to a single host."""
    parser.addoption(
        "--conformance-host",
        action="store",
        default=None,
        metavar="HOST",
        help="Run conformance tests for a specific host only (e.g. --conformance-host codex).",
    )


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear host env vars so resolve_host() starts from a known state."""
    monkeypatch.delenv("LL_HOST_CLI", raising=False)
    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    yield
