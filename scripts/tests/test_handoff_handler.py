"""Tests for handoff_handler module."""

from unittest.mock import patch

from little_loops.fsm.handoff_handler import (
    HandoffBehavior,
    HandoffHandler,
    HandoffResult,
)


class TestHandoffBehavior:
    """Tests for HandoffBehavior enum."""

    def test_enum_values(self) -> None:
        """Verify enum string values."""
        assert HandoffBehavior.TERMINATE.value == "terminate"
        assert HandoffBehavior.PAUSE.value == "pause"
        assert HandoffBehavior.SPAWN.value == "spawn"

    def test_from_string(self) -> None:
        """Create enum from string value."""
        assert HandoffBehavior("pause") == HandoffBehavior.PAUSE
        assert HandoffBehavior("spawn") == HandoffBehavior.SPAWN
        assert HandoffBehavior("terminate") == HandoffBehavior.TERMINATE


class TestHandoffHandler:
    """Tests for HandoffHandler class."""

    def test_default_behavior_is_pause(self) -> None:
        """Default behavior is pause."""
        handler = HandoffHandler()
        assert handler.behavior == HandoffBehavior.PAUSE

    def test_terminate_behavior(self) -> None:
        """Terminate returns without spawning."""
        handler = HandoffHandler(HandoffBehavior.TERMINATE)
        result = handler.handle("test-loop", "continuation prompt")

        assert result.behavior == HandoffBehavior.TERMINATE
        assert result.continuation_prompt == "continuation prompt"
        assert result.spawned_process is None

    def test_pause_behavior(self) -> None:
        """Pause returns without spawning."""
        handler = HandoffHandler(HandoffBehavior.PAUSE)
        result = handler.handle("test-loop", "continuation prompt")

        assert result.behavior == HandoffBehavior.PAUSE
        assert result.continuation_prompt == "continuation prompt"
        assert result.spawned_process is None

    def test_spawn_behavior(self) -> None:
        """Spawn launches Claude process."""
        with patch("subprocess.Popen") as mock_popen:
            handler = HandoffHandler(HandoffBehavior.SPAWN)
            result = handler.handle("test-loop", "continuation prompt")

            assert result.behavior == HandoffBehavior.SPAWN
            assert result.continuation_prompt == "continuation prompt"
            mock_popen.assert_called_once()

            # Verify command structure
            cmd = mock_popen.call_args[0][0]
            assert cmd[0] == "claude"
            assert "-p" in cmd

            # Verify prompt includes loop name and continuation
            prompt = cmd[cmd.index("-p") + 1]
            assert "ll-loop resume test-loop" in prompt
            assert "continuation prompt" in prompt

    def test_spawn_with_none_continuation(self) -> None:
        """Spawn handles None continuation prompt."""
        with patch("subprocess.Popen") as mock_popen:
            handler = HandoffHandler(HandoffBehavior.SPAWN)
            result = handler.handle("test-loop", None)

            assert result.continuation_prompt is None
            mock_popen.assert_called_once()

            cmd = mock_popen.call_args[0][0]
            prompt = cmd[cmd.index("-p") + 1]
            assert "ll-loop resume test-loop" in prompt

    def test_none_continuation(self) -> None:
        """Handles None continuation prompt."""
        handler = HandoffHandler(HandoffBehavior.PAUSE)
        result = handler.handle("test-loop", None)

        assert result.continuation_prompt is None


class TestHandoffResult:
    """Tests for HandoffResult dataclass."""

    def test_default_spawned_process(self) -> None:
        """Default spawned_process is None."""
        result = HandoffResult(
            behavior=HandoffBehavior.PAUSE,
            continuation_prompt="test",
        )
        assert result.spawned_process is None

    def test_with_spawned_process(self) -> None:
        """Can set spawned_process."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = mock_popen.return_value
            result = HandoffResult(
                behavior=HandoffBehavior.SPAWN,
                continuation_prompt="test",
                spawned_process=mock_process,
            )
            assert result.spawned_process is mock_process
