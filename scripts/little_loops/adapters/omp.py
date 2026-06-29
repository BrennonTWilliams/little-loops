"""OmpEmitter stub (``--host omp``).

Registered so ``--host omp`` produces a descriptive error rather than a
``KeyError``.  Full omp support is a separate follow-on under EPIC-2258.
"""

from __future__ import annotations

from little_loops.adapters.core import AdapterError

__all__ = ["OmpEmitter"]

_REMEDIATION = "omp emitter not yet implemented — open a PR adding adapters/omp.py"


class OmpEmitter:
    """Stub emitter for the omp surface.  All methods raise :class:`AdapterError`."""

    name = "omp"

    def emit_skill(self, skill_meta: dict) -> str:
        raise AdapterError(_REMEDIATION)

    def emit_command(self, cmd_meta: dict) -> str:
        raise AdapterError(_REMEDIATION)

    def emit_agent(self, agent_meta: dict) -> str:
        raise AdapterError(_REMEDIATION)
