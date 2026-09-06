"""EventBus ``CommunicationAdapter`` for async HITL approval (FEAT-3384).

The async channel for unattended runs: an out-of-process relay (Hermes, the
``--serve`` dashboard's socket/SSE consumers, or any ``EventBus`` observer)
answers a ``human_approval_requested`` alert by putting a matching
``human_response`` event back on the bus. Unlike ``TerminalAdapter``, this
adapter never blocks on a real fd — it registers one bus observer at
construction and polls its own per-alert pending state.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import cast

from little_loops.events import EventBus
from little_loops.fsm.communication_adapter import (
    HUMAN_RESPONSE_EVENT,
    AdapterResponse,
    CommunicationAdapter,
    TimeoutResponse,
    Verdict,
)

logger = logging.getLogger(__name__)

_VALID_VERDICTS: tuple[Verdict, ...] = ("approve", "reject", "edit")


class EventBusAdapter(CommunicationAdapter):
    """``EventBus``-backed implementation of the HITL communication protocol.

    Async adapter: ``send_alert()`` emits nothing (the executor is the sole
    emitter of ``human_approval_requested``); ``await_response()`` resolves
    from a matching ``human_response`` event observed on the bus. The bus
    observer is registered once in ``__init__`` and never unregistered — it
    is a no-op dict lookup while nothing is pending, so the register/
    unregister lifecycle a synchronous adapter would need is unnecessary here.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._pending: dict[str, AdapterResponse | None] = {}
        event_bus.register(self._on_event, filter=HUMAN_RESPONSE_EVENT)

    def _on_event(self, event: dict) -> None:
        """Bus observer: stash a matching verdict into ``_pending``.

        Untrusted payload (Third Review #13): ``alert_id``/``verdict`` are
        type-checked before use so a malformed inbound POST is logged and
        ignored rather than raising inside the callback.
        """
        alert_id = event.get("alert_id")
        if not isinstance(alert_id, str) or alert_id not in self._pending:
            return
        verdict = event.get("verdict")
        if not isinstance(verdict, str) or verdict not in _VALID_VERDICTS:
            logger.warning("EventBusAdapter: ignoring human_response with verdict %r", verdict)
            return
        edited_text = event.get("edited_text")
        if not isinstance(edited_text, str):
            edited_text = None
        reason = event.get("reason")
        if not isinstance(reason, str):
            reason = None
        self._pending[alert_id] = AdapterResponse(
            verdict=cast(Verdict, verdict), edited_text=edited_text, reason=reason
        )

    def send_alert(
        self,
        loop_name: str,
        state_name: str,
        prompt: str,
        captured_context: dict,
    ) -> str:
        """Record pending state and return a generated alert_id. Emits nothing.

        The executor emits ``human_approval_requested`` itself, after this
        call returns, so it can carry the ``alert_id`` (Pre-implementation
        Review #2).
        """
        alert_id = uuid.uuid4().hex
        self._pending[alert_id] = None
        return alert_id

    def await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse:
        """Return a retained verdict immediately, else wait up to ``timeout``.

        Every production verdict arrives via ``_drain_inbound()`` on the
        executor's main thread, strictly between calls to this method, so a
        single check → sleep → re-check is equivalent to a polling tick loop
        (Third Review #17).
        """
        start = time.monotonic()
        pending = self._pending[alert_id]
        if pending is not None:
            return pending

        time.sleep(max(0.0, timeout))

        result = self._pending.get(alert_id)
        if isinstance(result, AdapterResponse):
            return result
        return TimeoutResponse(elapsed_seconds=time.monotonic() - start)

    def supports_async(self) -> bool:
        """The eventbus channel doesn't require an operator watching the terminal."""
        return True

    def cancel_alert(self, alert_id: str) -> None:
        """Withdraw a pending alert. A late verdict for it is then ignored."""
        self._pending.pop(alert_id, None)


class EventBusAdapterExtension:
    """Registers ``EventBusAdapter`` under the ``"eventbus"`` channel.

    Deliberately defines no ``on_event`` — ``wire_extensions()`` would
    otherwise subscribe this registration-only shim to every event on every
    run (Second Review #7).
    """

    def __init__(self) -> None:
        self._adapter: EventBusAdapter | None = None

    def bind_event_bus(self, bus: EventBus) -> None:
        """Construct the one ``EventBusAdapter`` instance for this run's bus.

        Called by ``wire_extensions()`` before the ``provided_*`` passes.
        """
        self._adapter = EventBusAdapter(bus)

    def provided_adapters(self) -> dict[str, CommunicationAdapter]:
        """Return the same adapter instance on every call (Third Review #12).

        ``wire_extensions()`` calls ``provided_adapters()`` twice per
        extension (a conflict-check pass, then a merge pass); a fresh
        ``EventBusAdapter`` per call would register two observers and lose one.
        """
        if self._adapter is None:
            raise RuntimeError(
                "EventBusAdapterExtension.provided_adapters() called before "
                "bind_event_bus() — wire_extensions() must call bind_event_bus() first."
            )
        return {"eventbus": self._adapter}
