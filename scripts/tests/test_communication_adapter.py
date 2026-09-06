"""Tests for the CommunicationAdapter protocol (FEAT-1930): ABC contract,
extension registration, and FSMExecutor.resolve_communication_adapter()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.events import EventBus
from little_loops.extension import CommunicationAdapterExtension, wire_extensions
from little_loops.fsm.communication_adapter import (
    HUMAN_APPROVAL_REQUESTED_EVENT,
    HUMAN_RESPONSE_EVENT,
    AdapterResponse,
    CommunicationAdapter,
    CommunicationAdapterNotFound,
    TimeoutResponse,
)
from little_loops.fsm.executor import FSMExecutor


class _MockAdapter(CommunicationAdapter):
    """Minimal concrete adapter for tests: retains one unconsumed verdict."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self._pending_verdict: AdapterResponse | None = None
        self.timeout_calls_before_verdict = 0
        self._calls = 0

    def send_alert(
        self, loop_name: str, state_name: str, prompt: str, captured_context: dict
    ) -> str:
        return "alert-1"

    def await_response(self, alert_id: str, timeout: float) -> AdapterResponse | TimeoutResponse:
        self._calls += 1
        if self._calls <= self.timeout_calls_before_verdict:
            return TimeoutResponse(elapsed_seconds=timeout)
        return AdapterResponse(verdict="approve")

    def supports_async(self) -> bool:
        return True


class TestCommunicationAdapterABC:
    """ABC contract: abstract methods enforced, cancel_alert defaults to no-op."""

    def test_incomplete_subclass_raises_type_error(self) -> None:
        """A subclass missing an abstract method fails at instantiation, not at first call."""

        class IncompleteAdapter(CommunicationAdapter):
            def send_alert(self, loop_name, state_name, prompt, captured_context) -> str:
                return "a1"

            def await_response(self, alert_id, timeout):
                return TimeoutResponse()

            # supports_async() intentionally omitted

        with pytest.raises(TypeError):
            IncompleteAdapter()  # type: ignore[abstract]

    def test_complete_subclass_instantiates(self) -> None:
        """A subclass implementing all three abstract methods instantiates cleanly."""
        adapter = _MockAdapter()
        assert isinstance(adapter, CommunicationAdapter)

    def test_cancel_alert_default_is_noop(self) -> None:
        """cancel_alert() is concrete with a no-op default — no override required."""
        adapter = _MockAdapter()
        assert adapter.cancel_alert("alert-1") is None

    def test_adapter_response_verdict_literals(self) -> None:
        """AdapterResponse carries verdict, not a bare approved: bool."""
        approve = AdapterResponse(verdict="approve")
        reject = AdapterResponse(verdict="reject", reason="not ready")
        edit = AdapterResponse(verdict="edit", edited_text="revised prompt")
        assert approve.verdict == "approve"
        assert reject.verdict == "reject"
        assert edit.verdict == "edit"
        assert edit.edited_text == "revised prompt"

    def test_timeout_response_discriminator(self) -> None:
        """TimeoutResponse.timed_out is a constant-True discriminator."""
        timeout = TimeoutResponse(elapsed_seconds=5.0)
        assert timeout.timed_out is True
        assert timeout.elapsed_seconds == 5.0


class TestAwaitResponseReentrancy:
    """await_response() re-entrancy contract (Pre-implementation Review #12)."""

    def test_retains_verdict_across_timeout_calls(self) -> None:
        """Two TimeoutResponses then the verdict — a TimeoutResponse never invalidates the alert."""
        adapter = _MockAdapter()
        adapter.timeout_calls_before_verdict = 2

        first = adapter.await_response("alert-1", timeout=1.0)
        second = adapter.await_response("alert-1", timeout=1.0)
        third = adapter.await_response("alert-1", timeout=1.0)

        assert isinstance(first, TimeoutResponse)
        assert isinstance(second, TimeoutResponse)
        assert isinstance(third, AdapterResponse)
        assert third.verdict == "approve"


class TestEventConstants:
    """Canonical event-name constants."""

    def test_event_constant_values(self) -> None:
        assert HUMAN_APPROVAL_REQUESTED_EVENT == "human_approval_requested"
        assert HUMAN_RESPONSE_EVENT == "human_response"


class TestCommunicationAdapterExtensionProtocol:
    """Structural typing for the extension registration Protocol."""

    def test_protocol_satisfied(self) -> None:
        class MyAdapterProvider:
            def provided_adapters(self) -> dict[str, CommunicationAdapter]:
                return {"mock": _MockAdapter()}

        provider = MyAdapterProvider()
        _: CommunicationAdapterExtension = provider  # type: ignore[assignment]


def _executor_with_config(tmp_path: Path, hitl_channel: str | None) -> FSMExecutor:
    """Build a bare FSMExecutor with a working_dir pointing at a written ll-config.json."""
    (tmp_path / ".ll").mkdir(exist_ok=True)
    config: dict = {}
    if hitl_channel is not None:
        config["hitl"] = {"channel": hitl_channel}
    (tmp_path / ".ll" / "ll-config.json").write_text(json.dumps(config))

    executor = FSMExecutor.__new__(FSMExecutor)
    executor._contributed_actions = {}
    executor._contributed_evaluators = {}
    executor._contributed_adapters = {}
    executor._interceptors = []
    executor.working_dir = tmp_path
    executor._br_config = None
    return executor


class TestResolveCommunicationAdapter:
    """FSMExecutor.resolve_communication_adapter(): hit, miss, config-driven selection."""

    def test_resolves_registered_channel(self, tmp_path: Path) -> None:
        executor = _executor_with_config(tmp_path, hitl_channel="mock")
        adapter = _MockAdapter()
        executor._contributed_adapters["mock"] = adapter

        resolved = executor.resolve_communication_adapter()

        assert resolved is adapter

    def test_defaults_to_terminal_when_unset(self, tmp_path: Path) -> None:
        executor = _executor_with_config(tmp_path, hitl_channel=None)
        terminal_adapter = _MockAdapter()
        executor._contributed_adapters["terminal"] = terminal_adapter

        resolved = executor.resolve_communication_adapter()

        assert resolved is terminal_adapter

    def test_miss_raises_communication_adapter_not_found(self, tmp_path: Path) -> None:
        executor = _executor_with_config(tmp_path, hitl_channel="eventbus")

        with pytest.raises(CommunicationAdapterNotFound, match="not registered"):
            executor.resolve_communication_adapter()

    def test_miss_message_lists_requested_and_available_channels(self, tmp_path: Path) -> None:
        executor = _executor_with_config(tmp_path, hitl_channel="eventbus")
        executor._contributed_adapters["terminal"] = _MockAdapter()

        with pytest.raises(CommunicationAdapterNotFound) as exc_info:
            executor.resolve_communication_adapter()

        message = str(exc_info.value)
        assert "'eventbus'" in message
        assert "terminal" in message


class TestWireExtensionsAdapters:
    """wire_extensions() populates _contributed_adapters and enforces conflict detection."""

    def test_populates_contributed_adapters(self, tmp_path: Path) -> None:
        adapter = _MockAdapter()

        class AdapterExt:
            def provided_adapters(self) -> dict[str, CommunicationAdapter]:
                return {"mock": adapter}

        from unittest.mock import patch

        from little_loops.extension import ExtensionLoader

        executor = _executor_with_config(tmp_path, hitl_channel="mock")
        bus = EventBus()
        with patch.object(ExtensionLoader, "load_all", return_value=[AdapterExt()]):
            wire_extensions(bus, executor=executor)

        assert executor._contributed_adapters["mock"] is adapter

    def test_eventbus_extension_observes_the_wired_bus(self, tmp_path: Path) -> None:
        """EventBusAdapterExtension.provided_adapters() resolves against the same
        bus instance passed into wire_extensions() (FEAT-3384)."""
        from unittest.mock import patch

        from little_loops.fsm.adapters.eventbus_adapter import EventBusAdapter

        executor = _executor_with_config(tmp_path, hitl_channel="eventbus")
        bus = EventBus()
        with patch("little_loops.extension.entry_points", return_value=[]):
            wire_extensions(bus, executor=executor)

        adapter = executor._contributed_adapters["eventbus"]
        assert isinstance(adapter, EventBusAdapter)

        alert_id = adapter.send_alert("l", "s", "p", {})
        bus.emit(
            {"event": HUMAN_RESPONSE_EVENT, "ts": "t", "alert_id": alert_id, "verdict": "approve"}
        )
        result = adapter.await_response(alert_id, timeout=0.01)
        assert result == AdapterResponse(verdict="approve")

    def test_conflict_detection_raises_value_error(self, tmp_path: Path) -> None:
        class ExtA:
            def provided_adapters(self) -> dict[str, CommunicationAdapter]:
                return {"shared": _MockAdapter()}

        class ExtB:
            def provided_adapters(self) -> dict[str, CommunicationAdapter]:
                return {"shared": _MockAdapter()}

        from unittest.mock import patch

        from little_loops.extension import ExtensionLoader

        executor = _executor_with_config(tmp_path, hitl_channel="shared")
        bus = EventBus()
        with (
            patch.object(ExtensionLoader, "load_all", return_value=[ExtA(), ExtB()]),
            pytest.raises(ValueError, match="already registered"),
        ):
            wire_extensions(bus, executor=executor)
