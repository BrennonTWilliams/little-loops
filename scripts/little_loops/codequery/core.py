"""CodeQuery provider core: Protocol, dataclasses, registry, and resolver.

Mirrors ``little_loops.adapters.core`` (FEAT-2391): a ``@runtime_checkable``
Protocol, a lazy-import name→(module, class) registry, and a
``resolve_provider`` factory. Concrete providers live in sibling modules
(``fallback.py``, ``codegraph.py``); this module owns only the shared
interface, registry, and dataclasses.

See FEAT-2576 for the full design.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Literal, Protocol, cast, runtime_checkable

# The full set of query kinds a provider may implement. A provider's
# ``capabilities()`` return value is a subset of this.
QUERY_KINDS = frozenset(
    {
        "callers_of",
        "callees_of",
        "importers_of",
        "defines",
        "references",
        "impact_of",
    }
)

Freshness = Literal["fresh", "stale", "unknown"]
Confidence = Literal["exact", "heuristic"]


class CodeQueryError(Exception):
    """Raised when a code-query provider cannot fulfil a request."""


class Unsupported(CodeQueryError):
    """Raised by a provider for a query kind outside its ``capabilities()``.

    The resolver catches this to fall through to the fallback provider for
    that query only, rather than failing the whole request.
    """


@dataclass(frozen=True)
class CodeRef:
    """A single structural code reference returned by a provider query."""

    path: str
    line: int
    symbol: str
    kind: str
    confidence: Confidence
    provider: str


@dataclass(frozen=True)
class ProviderStatus:
    """Provider availability and index metadata."""

    available: bool
    freshness: Freshness
    indexed_at: str | None
    detail: str


@runtime_checkable
class CodeQueryProvider(Protocol):
    """Protocol for structural code-query providers.

    Implementations answer "who calls/imports/defines/references X" and
    "what is impacted if these files change" without external tooling being
    required — see the fallback provider (``fallback.py``) for the always-
    available reference implementation. Structurally matched — any class
    with ``name`` and the required methods satisfies this Protocol without
    explicit subclassing.
    """

    name: str

    def capabilities(self) -> set[str]: ...
    def status(self) -> ProviderStatus: ...
    def callers_of(self, symbol: str) -> list[CodeRef]: ...
    def callees_of(self, symbol: str) -> list[CodeRef]: ...
    def importers_of(self, module: str) -> list[CodeRef]: ...
    def defines(self, path: str) -> list[CodeRef]: ...
    def references(self, symbol: str) -> list[CodeRef]: ...
    def impact_of(self, paths: list[str], depth: int = 2) -> list[CodeRef]: ...


# Lazy-import registry: provider name → (module_path, class_name).
# Concrete modules import from this module (CodeQueryError, dataclasses), so
# we must not import them at module level — only resolve on demand via
# importlib. Order matters for "auto": graph providers first, fallback last.
_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "codegraph": ("little_loops.codequery.codegraph", "CodegraphProvider"),
    "fallback": ("little_loops.codequery.fallback", "FallbackProvider"),
}


def resolve_provider(name: str = "auto") -> CodeQueryProvider:
    """Return a :class:`CodeQueryProvider` instance for *name*.

    Args:
        name: A registered provider name, or ``"auto"`` to pick the first
            registered provider (in registration order) whose ``status()``
            reports ``available``.

    Returns:
        A :class:`CodeQueryProvider` instance ready to answer queries.

    Raises:
        CodeQueryError: if *name* is not registered, or ``"auto"`` finds no
            available provider.
    """
    if name == "auto":
        for candidate in _PROVIDER_MAP:
            provider = _instantiate(candidate)
            if provider.status().available:
                return provider
        raise CodeQueryError("No available code-query provider found.")

    return _instantiate(name)


def _instantiate(name: str) -> CodeQueryProvider:
    entry = _PROVIDER_MAP.get(name)
    if entry is None:
        raise CodeQueryError(
            f"Provider {name!r} is not registered. Available: {sorted(_PROVIDER_MAP)}."
        )
    module_path, cls_name = entry
    module = importlib.import_module(module_path)
    return cast(CodeQueryProvider, getattr(module, cls_name)())
