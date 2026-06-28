"""Host-parameterized adapter core for skill/command/agent emission.

Defines the :class:`HostEmitter` Protocol and a registry-backed
:func:`resolve_emitter` factory.  Concrete emitters live in sibling modules
(``codex.py``, ``gemini.py``, ``omp.py``); this module owns only the shared
interface and the registry.

See FEAT-2260 for the full design.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class AdapterError(Exception):
    """Raised when a host emitter cannot fulfil the request."""


@runtime_checkable
class HostEmitter(Protocol):
    """Protocol for host-specific output emitters.

    Implementations convert ll skill/command/agent metadata into the target
    host's discovery format.  Structurally matched — any class with ``name``
    and the three ``emit_*`` methods satisfies this Protocol without explicit
    subclassing.  ``@runtime_checkable`` enables ``isinstance`` registry checks.
    """

    name: str

    def emit_skill(self, skill_meta: dict) -> str: ...
    def emit_command(self, cmd_meta: dict) -> str: ...
    def emit_agent(self, agent_meta: dict) -> str: ...


class CodexEmitter:
    """Output emitter for the Codex host (``--host codex``)."""

    name = "codex"

    def emit_skill(self, skill_meta: dict) -> str:
        raise NotImplementedError

    def emit_command(self, cmd_meta: dict) -> str:
        raise NotImplementedError

    def emit_agent(self, agent_meta: dict) -> str:
        raise NotImplementedError


class GeminiEmitter:
    """Output emitter for the Gemini host (``--host gemini``)."""

    name = "gemini"

    def emit_skill(self, skill_meta: dict) -> str:
        raise NotImplementedError

    def emit_command(self, cmd_meta: dict) -> str:
        raise NotImplementedError

    def emit_agent(self, agent_meta: dict) -> str:
        raise NotImplementedError


class OmpEmitter:
    """Stub emitter for the omp surface (``--host omp``).

    Registered so ``--host omp`` produces a descriptive error rather than a
    ``KeyError``.  Absent from auto-detection.  Full omp support is a
    separate follow-on under EPIC-2258.
    """

    name = "omp"

    def emit_skill(self, skill_meta: dict) -> str:
        raise AdapterError("omp emitter not yet implemented — open a PR adding adapters/omp.py")

    def emit_command(self, cmd_meta: dict) -> str:
        raise AdapterError("omp emitter not yet implemented — open a PR adding adapters/omp.py")

    def emit_agent(self, agent_meta: dict) -> str:
        raise AdapterError("omp emitter not yet implemented — open a PR adding adapters/omp.py")


_EMITTER_REGISTRY: dict[str, type[HostEmitter]] = {
    "codex": CodexEmitter,
    "gemini": GeminiEmitter,
    "omp": OmpEmitter,
}


def resolve_emitter(host: str) -> HostEmitter:
    """Return a :class:`HostEmitter` instance for *host*.

    Args:
        host: One of ``"codex"``, ``"gemini"``, ``"omp"``.

    Returns:
        A :class:`HostEmitter` ready to emit skills, commands, and agents.

    Raises:
        AdapterError: if *host* is not registered.
    """
    cls = _EMITTER_REGISTRY.get(host)
    if cls is None:
        raise AdapterError(
            f"Host {host!r} is not registered. Available: {sorted(_EMITTER_REGISTRY)}."
        )
    return cls()
