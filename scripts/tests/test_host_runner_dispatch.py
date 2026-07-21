"""Tests for FEAT-2716 live-dispatch functions in host_runner.py.

Covers ``dispatch_anthropic_request``, ``dispatch_batch_request``, and
``poll_batch_result`` — the first production call sites that construct a real
``anthropic.Anthropic()`` client. Mocks at
``patch("anthropic.Anthropic")``, the module-dotted
path the ``anthropic`` package is lazily imported under inside each dispatch
function (mirrors ``test_fsm_runners.py``'s
``little_loops.fsm.runners.subprocess.Popen`` mocking convention).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from little_loops.host_runner import (
    BatchPollTimeout,
    dispatch_anthropic_request,
    dispatch_batch_request,
    poll_batch_result,
)
from little_loops.prompts import FragmentStore


def _fake_message(
    text: str = "hello",
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 10,
    output_tokens: int = 5,
    cache_read: int | None = 0,
    cache_creation: int | None = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=model,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
        ),
    )


class TestDispatchAnthropicRequest:
    def test_builds_action_result_from_sdk_response(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_message(text="hi there")

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = dispatch_anthropic_request(
                action="say hi",
                model="claude-sonnet-4-6",
                fragment_store=FragmentStore(),
            )

        assert result.exit_code == 0
        assert result.output == "hi there"
        assert result.stderr == ""
        assert len(result.usage_events) == 1
        usage = result.usage_events[0]
        assert usage.input_tokens == 10
        assert usage.output_tokens == 5
        assert usage.model == "claude-sonnet-4-6"
        assert usage.is_batch is False

    def test_concatenates_multiple_text_blocks(self) -> None:
        fake_client = MagicMock()
        message = _fake_message()
        message.content = [
            SimpleNamespace(type="text", text="part one "),
            SimpleNamespace(type="text", text="part two"),
        ]
        fake_client.messages.create.return_value = message

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = dispatch_anthropic_request(
                action="say hi",
                model="claude-sonnet-4-6",
                fragment_store=FragmentStore(),
            )

        assert result.output == "part one part two"

    def test_api_error_returns_nonzero_exit_code(self) -> None:
        import anthropic

        fake_client = MagicMock()
        fake_request = MagicMock()
        fake_client.messages.create.side_effect = anthropic.APIError(
            "boom", request=fake_request, body=None
        )

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = dispatch_anthropic_request(
                action="say hi",
                model="claude-sonnet-4-6",
                fragment_store=FragmentStore(),
            )

        assert result.exit_code == 1
        assert result.output == ""
        assert "boom" in result.stderr
        assert result.usage_events == []

    def test_null_cache_usage_fields_normalize_to_zero(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.create.return_value = _fake_message(
            cache_read=None, cache_creation=None
        )

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = dispatch_anthropic_request(
                action="say hi",
                model="claude-sonnet-4-6",
                fragment_store=FragmentStore(),
            )

        usage = result.usage_events[0]
        assert usage.cache_read_tokens == 0
        assert usage.cache_creation_tokens == 0


class TestDispatchBatchRequest:
    def test_returns_batch_id(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.batches.create.return_value = SimpleNamespace(id="msgbatch_abc")

        with patch("anthropic.Anthropic", return_value=fake_client):
            batch_id = dispatch_batch_request(
                custom_id="req-1",
                action="say hi",
                model="claude-sonnet-4-6",
                fragment_store=FragmentStore(),
            )

        assert batch_id == "msgbatch_abc"
        assert fake_client.messages.batches.create.called


class TestPollBatchResult:
    def test_happy_path_returns_matched_result(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.batches.retrieve.return_value = SimpleNamespace(
            processing_status="ended"
        )
        succeeded_result = SimpleNamespace(
            type="succeeded", message=_fake_message(text="batch output")
        )
        fake_client.messages.batches.results.return_value = [
            SimpleNamespace(custom_id="req-1", result=succeeded_result)
        ]

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = poll_batch_result(batch_id="msgbatch_abc", custom_id="req-1")

        assert result.exit_code == 0
        assert result.output == "batch output"
        assert result.usage_events[0].is_batch is True

    def test_polls_until_ended(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.batches.retrieve.side_effect = [
            SimpleNamespace(processing_status="in_progress"),
            SimpleNamespace(processing_status="in_progress"),
            SimpleNamespace(processing_status="ended"),
        ]
        succeeded_result = SimpleNamespace(type="succeeded", message=_fake_message())
        fake_client.messages.batches.results.return_value = [
            SimpleNamespace(custom_id="req-1", result=succeeded_result)
        ]

        with (
            patch("anthropic.Anthropic", return_value=fake_client),
            patch("time.sleep"),
        ):
            result = poll_batch_result(
                batch_id="msgbatch_abc", custom_id="req-1", poll_interval_seconds=0.01
            )

        assert result.exit_code == 0
        assert fake_client.messages.batches.retrieve.call_count == 3

    def test_timeout_raises_batch_poll_timeout(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.batches.retrieve.return_value = SimpleNamespace(
            processing_status="in_progress"
        )

        with (
            patch("anthropic.Anthropic", return_value=fake_client),
            patch("time.sleep"),
        ):
            with pytest.raises(BatchPollTimeout):
                poll_batch_result(
                    batch_id="msgbatch_abc",
                    custom_id="req-1",
                    max_wait_seconds=0.0,
                    poll_interval_seconds=0.01,
                )

    def test_no_matching_custom_id_returns_error_result(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.batches.retrieve.return_value = SimpleNamespace(
            processing_status="ended"
        )
        fake_client.messages.batches.results.return_value = []

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = poll_batch_result(batch_id="msgbatch_abc", custom_id="req-missing")

        assert result.exit_code == 1
        assert "req-missing" in result.stderr

    def test_failed_batch_entry_returns_error_result(self) -> None:
        fake_client = MagicMock()
        fake_client.messages.batches.retrieve.return_value = SimpleNamespace(
            processing_status="ended"
        )
        failed_result = SimpleNamespace(type="errored")
        fake_client.messages.batches.results.return_value = [
            SimpleNamespace(custom_id="req-1", result=failed_result)
        ]

        with patch("anthropic.Anthropic", return_value=fake_client):
            result = poll_batch_result(batch_id="msgbatch_abc", custom_id="req-1")

        assert result.exit_code == 1
        assert "errored" in result.stderr
