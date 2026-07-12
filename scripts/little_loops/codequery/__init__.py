"""Structural code-query provider protocol and registry.

See FEAT-2576 for the design; mirrors the ``adapters/`` package shape
(FEAT-2391): a Protocol, a lazy-import registry, and a ``resolve_*`` factory.
"""

from __future__ import annotations

from little_loops.codequery.core import (
    QUERY_KINDS,
    CodeQueryError,
    CodeQueryProvider,
    CodeRef,
    ProviderStatus,
    Unsupported,
    resolve_provider,
)

__all__ = [
    "QUERY_KINDS",
    "CodeQueryError",
    "CodeQueryProvider",
    "CodeRef",
    "ProviderStatus",
    "Unsupported",
    "resolve_provider",
]
