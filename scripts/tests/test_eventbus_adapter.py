"""Tests for FEAT-3384: EventBusAdapter and EventBusAdapterExtension."""

from __future__ import annotations

import pytest

from little_loops.events import EventBus
from little_loops.fsm.adapters.eventbus_adapter import EventBusAdapter, EventBusAdapterExtension
from little_loops.fsm.communication_adapter import (
    HUMAN_RESPONSE_EVENT,
    AdapterResponse,
    TimeoutResponse,
)


def emit_response(bus: EventBus, **fields) -> None:
    bus.emit({"event": HUMAN_RESPONSE_EVENT, "ts": "t", **fields})


class TestSendAlert:
    def test_returns_hex_id_and_emits_nothing(self) -> None:
        bus = EventBus()
        received: list[dict] = []
        bus.register(received.append)
        adapter = EventBusAdapter(bus)

        alert_id = adapter.send_alert("l", "s", "p", {})

        assert isinstance(alert_id, str) and alert_id
        assert len(alert_id) == 32  # uuid4().hex
        assert received == []


class TestVerdictResolution:
    def test_approve(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        emit_response(bus, alert_id=alert_id, verdict="approve")
        result = adapter.await_response(alert_id, timeout=0.01)

        assert result == AdapterResponse(verdict="approve")

    def test_reject_with_reason(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        emit_response(bus, alert_id=alert_id, verdict="reject", reason="not ready")
        result = adapter.await_response(alert_id, timeout=0.01)

        assert result == AdapterResponse(verdict="reject", reason="not ready")

    def test_edit_with_text(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        emit_response(bus, alert_id=alert_id, verdict="edit", edited_text="revised")
        result = adapter.await_response(alert_id, timeout=0.01)

        assert result == AdapterResponse(verdict="edit", edited_text="revised")


class TestIgnoredEvents:
    def test_non_matching_alert_id_ignored(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        emit_response(bus, alert_id="some-other-id", verdict="approve")
        result = adapter.await_response(alert_id, timeout=0.01)

        assert isinstance(result, TimeoutResponse)

    def test_non_str_alert_id_ignored(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        emit_response(bus, alert_id=["not", "a", "string"], verdict="approve")
        result = adapter.await_response(alert_id, timeout=0.01)

        assert isinstance(result, TimeoutResponse)

    def test_unknown_verdict_ignored_and_alert_stays_pending(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        emit_response(bus, alert_id=alert_id, verdict="maybe")
        result = adapter.await_response(alert_id, timeout=0.01)

        assert isinstance(result, TimeoutResponse)
        assert alert_id in adapter._pending

    def test_non_str_verdict_ignored(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        emit_response(bus, alert_id=alert_id, verdict=123)
        result = adapter.await_response(alert_id, timeout=0.01)

        assert isinstance(result, TimeoutResponse)

    def test_non_str_edited_text_and_reason_treated_as_absent(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        emit_response(bus, alert_id=alert_id, verdict="edit", edited_text=123, reason=456)
        result = adapter.await_response(alert_id, timeout=0.01)

        assert isinstance(result, AdapterResponse)
        assert result.edited_text is None
        assert result.reason is None


class TestReentrancy:
    def test_retains_verdict_across_timeout_calls(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        first = adapter.await_response(alert_id, timeout=0.01)
        assert isinstance(first, TimeoutResponse)

        emit_response(bus, alert_id=alert_id, verdict="approve")

        second = adapter.await_response(alert_id, timeout=0.01)
        assert second == AdapterResponse(verdict="approve")

        third = adapter.await_response(alert_id, timeout=0.01)
        assert third == AdapterResponse(verdict="approve")

    def test_unknown_alert_id_raises_key_error(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        with pytest.raises(KeyError):
            adapter.await_response("nonexistent", timeout=0.01)


class TestCancelAlert:
    def test_cancel_withdraws_pending_alert(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})

        adapter.cancel_alert(alert_id)

        assert alert_id not in adapter._pending

    def test_late_verdict_after_cancel_is_ignored(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        alert_id = adapter.send_alert("l", "s", "p", {})
        adapter.cancel_alert(alert_id)

        emit_response(bus, alert_id=alert_id, verdict="approve")

        assert alert_id not in adapter._pending


class TestObserverLifecycle:
    def test_registered_once_in_init_and_still_registered_after_cancel(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        assert len(bus._observers) == 1

        alert_id = adapter.send_alert("l", "s", "p", {})
        adapter.cancel_alert(alert_id)

        assert len(bus._observers) == 1


class TestSupportsAsync:
    def test_returns_true(self) -> None:
        bus = EventBus()
        adapter = EventBusAdapter(bus)
        assert adapter.supports_async() is True


class TestEventBusAdapterExtension:
    def test_bind_event_bus_then_provided_adapters_returns_same_instance(self) -> None:
        bus = EventBus()
        ext = EventBusAdapterExtension()
        ext.bind_event_bus(bus)

        first = ext.provided_adapters()
        second = ext.provided_adapters()

        assert first["eventbus"] is second["eventbus"]
        assert isinstance(first["eventbus"], EventBusAdapter)

    def test_provided_adapters_before_bind_raises(self) -> None:
        ext = EventBusAdapterExtension()
        with pytest.raises(RuntimeError):
            ext.provided_adapters()

    def test_no_on_event(self) -> None:
        ext = EventBusAdapterExtension()
        assert not hasattr(ext, "on_event")
