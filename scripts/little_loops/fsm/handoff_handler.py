"""Handoff handling for FSM loop execution.

This module provides behavior handlers for context handoff signals,
supporting pause, spawn, and terminate behaviors.

The handler is Claude-specific and knows how to spawn continuation sessions
via the Claude CLI.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum


class HandoffBehavior(Enum):
    """Behavior when a handoff signal is detected.

    - TERMINATE: Stop loop execution immediately, no state preservation
    - PAUSE: Save state with continuation prompt and exit (default)
    - SPAWN: Save state and spawn a new Claude session to continue
    """

    TERMINATE = "terminate"
    PAUSE = "pause"
    SPAWN = "spawn"


@dataclass
class HandoffResult:
    """Result from handling a handoff signal.

    Attributes:
        behavior: The behavior that was applied
        continuation_prompt: The continuation prompt from the signal
        spawned_process: Popen object if spawn behavior was used
    """

    behavior: HandoffBehavior
    continuation_prompt: str | None
    spawned_process: subprocess.Popen[str] | None = None


class HandoffHandler:
    """Handle context handoff signals.

    Provides configurable behavior for when handoff signals are detected
    in loop action output.

    Example:
        handler = HandoffHandler(HandoffBehavior.PAUSE)
        result = handler.handle("fix-types", "Continue from iteration 5")
        # result.behavior == HandoffBehavior.PAUSE
        # State should be saved by caller
    """

    def __init__(self, behavior: HandoffBehavior = HandoffBehavior.PAUSE) -> None:
        """Initialize handler with behavior.

        Args:
            behavior: How to handle handoff signals (default: pause)
        """
        self.behavior = behavior

    def handle(self, loop_name: str, continuation: str | None) -> HandoffResult:
        """Handle a detected handoff signal.

        For PAUSE and SPAWN behaviors, the caller (executor) is responsible
        for saving state with the continuation prompt.

        Args:
            loop_name: Name of the loop for spawn commands
            continuation: Continuation prompt from the signal

        Returns:
            HandoffResult with behavior taken and any spawned process
        """
        if self.behavior == HandoffBehavior.TERMINATE:
            return HandoffResult(self.behavior, continuation)

        if self.behavior == HandoffBehavior.PAUSE:
            # State saving handled by executor
            return HandoffResult(self.behavior, continuation)

        if self.behavior == HandoffBehavior.SPAWN:
            process = self._spawn_continuation(loop_name, continuation)
            return HandoffResult(self.behavior, continuation, process)

        # Should never reach here due to enum exhaustiveness,
        # but satisfy type checker
        return HandoffResult(self.behavior, continuation)

    def _spawn_continuation(
        self, loop_name: str, continuation: str | None
    ) -> subprocess.Popen[str]:
        """Spawn new Claude session to continue loop.

        Creates a new Claude CLI process with a prompt instructing it
        to resume the loop execution.

        Args:
            loop_name: Name of the loop to resume
            continuation: Continuation context from handoff

        Returns:
            Popen object for the spawned process
        """
        prompt_parts = [f"Continue loop execution. Run: ll-loop resume {loop_name}"]
        if continuation:
            prompt_parts.append(f"\n\n{continuation}")
        prompt = "".join(prompt_parts)

        cmd = ["claude", "-p", prompt]
        return subprocess.Popen(
            cmd,
            text=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
