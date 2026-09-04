"""Communication adapter protocol for async HITL channels (FEAT-1930).

Decouples the FSM ``human_approval`` state from transport-specific I/O.
Adapters implement :class:`CommunicationAdapter` and register through the
extension system (``CommunicationAdapterExtension`` in ``extension.py``) so
they are discoverable and config-swappable via ``hitl.channel``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

# Canonical event names shared by FEAT-1794 (emitter), the eventbus adapter,
# and FEAT-3323 (read-only relay). Follows the RATE_LIMIT_WAITING_EVENT
# string-constant convention; LLEvent is never subclassed in this codebase.
HUMAN_APPROVAL_REQUESTED_EVENT = "human_approval_requested"
HUMAN_RESPONSE_EVENT = "human_response"

Verdict = Literal["approve", "reject", "edit"]


@dataclass
class AdapterResponse:
    """Operator verdict returned by an adapter.

    Named to avoid colliding with FEAT-1794's ``HumanResponse`` event-bus
    payload.
    """

    verdict: Verdict
    edited_text: str | None = None  # populated for "edit"
    reason: str | None = None


@dataclass
class TimeoutResponse:
    """Returned when no verdict arrived within ``timeout``.

    ``timed_out`` is always True; it exists as a cheap discriminator so
    callers can ``match``/``isinstance`` without importing both types.
    """

    timed_out: bool = True
    elapsed_seconds: float = 0.0


class CommunicationAdapterNotFound(LookupError):
    """Raised by the executor resolver when ``hitl.channel`` names no
    registered adapter. Message follows the resolve_host / resolve_emitter
    template: ``"... is not registered. Available: [...]."``
    """


class CommunicationAdapter(ABC):
    """Abstract base class for HITL communication channels."""

    @abstractmethod
    def send_alert(
        self,
        loop_name: str,
        state_name: str,
        prompt: str,
        captured_context: dict,
    ) -> str:
        """Deliver an approval request to the operator. Returns alert_id."""

    @abstractmethod
    def await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse:
        """Block up to ``timeout`` seconds for the operator's verdict on ``alert_id``.

        Re-entrant per alert: the executor polls this in short ticks so
        shutdown stays responsive. Repeat calls for the same ``alert_id`` are
        expected; a verdict that arrives between calls must be retained and
        returned on the next call. A ``TimeoutResponse`` does not invalidate
        the alert — only ``cancel_alert()`` does.
        """

    @abstractmethod
    def supports_async(self) -> bool:
        """True if this channel can reach an operator not watching the terminal."""

    def cancel_alert(self, alert_id: str) -> None:
        """Withdraw a pending alert (e.g. on the timeout route). No-op by default."""
        return None
