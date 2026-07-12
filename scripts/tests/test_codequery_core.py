"""Tests for little_loops.codequery.core: registry, resolver, protocol conformance."""

from __future__ import annotations

import pytest

from little_loops.codequery.core import CodeQueryError, CodeQueryProvider, resolve_provider


class TestResolveProvider:
    def test_fallback_returns_fallback_provider(self):
        provider = resolve_provider("fallback")
        assert provider.name == "fallback"

    def test_unknown_provider_raises_code_query_error(self):
        with pytest.raises(CodeQueryError):
            resolve_provider("does-not-exist")

    def test_returned_provider_satisfies_protocol(self):
        provider = resolve_provider("fallback")
        assert isinstance(provider, CodeQueryProvider)

    def test_auto_returns_available_provider(self):
        provider = resolve_provider("auto")
        assert provider.status().available


class TestProtocolConformance:
    """Every registered provider must satisfy the shared protocol contract.

    ENH-2577 (codegraph provider) should extend this class or reuse its
    assertions against its own provider name.
    """

    @pytest.fixture
    def provider(self):
        return resolve_provider("fallback")

    def test_has_name(self, provider):
        assert isinstance(provider.name, str) and provider.name

    def test_capabilities_is_subset_of_query_kinds(self, provider):
        from little_loops.codequery.core import QUERY_KINDS

        assert provider.capabilities() <= QUERY_KINDS

    def test_status_returns_provider_status(self, provider):
        status = provider.status()
        assert status.available in (True, False)
        assert status.freshness in ("fresh", "stale", "unknown")
