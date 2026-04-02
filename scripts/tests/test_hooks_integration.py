"""Integration tests for hooks system robustness.

Tests concurrent access, special character handling, and race conditions.
"""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest


class TestContextMonitor:
    """Test context-monitor.sh under concurrent access."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to context-monitor.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/context-monitor.sh"

    @pytest.fixture
    def test_config(self, tmp_path: Path) -> Path:
        """Create a test config file."""
        config = {
            "context_monitor": {
                "enabled": True,
                "auto_handoff_threshold": 80,
                "context_limit_estimate": 1000000,
                "state_file": str(tmp_path / "ll-context-state.json"),
            }
        }
        config_file = tmp_path / ".ll" / "ll-config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(config, indent=2))
        return config_file

    def test_concurrent_updates(self, hook_script: Path, test_config: Path, tmp_path: Path):
        """Simulate concurrent PostToolUse hooks updating state file."""
        # Change to temp directory for test
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create config symlink in temp dir
            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            def run_hook(tool_name: str) -> subprocess.CompletedProcess:
                """Run hook with tool information."""
                input_data = {
                    "tool_name": tool_name,
                    "tool_response": {"content": "test output\n" * 100},
                }
                result = subprocess.run(
                    [str(hook_script)],
                    input=json.dumps(input_data),
                    capture_output=True,
                    text=True,
                    timeout=6,
                )
                return result

            # Run 10 hooks concurrently
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(run_hook, "Read") for _ in range(10)]
                results = [f.result() for f in as_completed(futures)]

            # Verify all completed
            assert len(results) == 10

            # Read final state
            state_file = tmp_path / "ll-context-state.json"
            assert state_file.exists(), "State file should exist"

            state = json.loads(state_file.read_text())

            # Verify state is valid JSON
            assert isinstance(state, dict)
            assert "estimated_tokens" in state
            assert "tool_calls" in state

            # Verify no token count loss (should be 10 calls * ~1000 tokens each)
            # Allow some variance due to estimation
            assert state["tool_calls"] == 10, f"Expected 10 tool calls, got {state['tool_calls']}"
            assert state["estimated_tokens"] > 5000, "Token count seems too low"

        finally:
            os.chdir(original_dir)

    def test_transcript_baseline_used_when_jsonl_present(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Test that JSONL transcript token counts are used as the baseline."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # Create a JSONL transcript with a single assistant entry containing usage data
            transcript_file = tmp_path / "transcript.jsonl"
            assistant_entry = {
                "type": "assistant",
                "message": {
                    "usage": {
                        "input_tokens": 50000,
                        "cache_creation_input_tokens": 10000,
                        "cache_read_input_tokens": 5000,
                        "output_tokens": 2000,
                    }
                },
            }
            transcript_file.write_text(json.dumps(assistant_entry) + "\n")

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "small output\n"},
                "transcript_path": str(transcript_file),
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            assert result.returncode == 0

            state_file = tmp_path / "ll-context-state.json"
            assert state_file.exists()
            state = json.loads(state_file.read_text())

            # transcript_baseline_tokens should be the sum of all usage fields
            expected_baseline = 50000 + 10000 + 5000 + 2000  # 67000
            assert state["transcript_baseline_tokens"] == expected_baseline

            # estimated_tokens should be baseline + current-turn delta (not a full heuristic accumulation)
            assert state["estimated_tokens"] > expected_baseline

        finally:
            os.chdir(original_dir)

    def test_transcript_baseline_falls_back_when_absent(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Test that pure heuristics are used when transcript_path is absent."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # No transcript_path in input
            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "output\n" * 100},
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            assert result.returncode == 0

            state_file = tmp_path / "ll-context-state.json"
            state = json.loads(state_file.read_text())

            # Baseline should be 0 (no transcript available)
            assert state["transcript_baseline_tokens"] == 0
            # Heuristic estimate should still be non-zero
            assert state["estimated_tokens"] > 0

        finally:
            os.chdir(original_dir)

    def test_state_file_corruption_resistance(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Test that atomic writes prevent state file corruption."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create config
            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # Run hook multiple times
            for i in range(5):
                input_data = {
                    "tool_name": "Read",
                    "tool_response": {"content": f"output {i}\n" * 50},
                }
                subprocess.run(
                    [str(hook_script)],
                    input=json.dumps(input_data),
                    capture_output=True,
                    text=True,
                    timeout=6,
                )

            # Verify state is valid JSON
            state_file = tmp_path / "ll-context-state.json"
            state = json.loads(state_file.read_text())
            assert state["tool_calls"] == 5

        finally:
            os.chdir(original_dir)

    def test_env_var_overrides_config_threshold(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """LL_HANDOFF_THRESHOLD env var overrides config auto_handoff_threshold."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "x" * 500},
            }
            env = os.environ.copy()
            env["LL_HANDOFF_THRESHOLD"] = "1"  # trigger immediately

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
                env=env,
            )

            # Hook triggers handoff (exit 2) because LL_HANDOFF_THRESHOLD=1 means any context
            # usage exceeds threshold. Config threshold is 80, so without the env var the hook
            # would exit 0. The fact that it triggered confirms env var was used.
            assert result.returncode == 2
            assert "handoff" in result.stderr.lower() or "context" in result.stderr.lower()

        finally:
            os.chdir(original_dir)

    def test_env_var_overrides_context_limit(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """LL_CONTEXT_LIMIT env var overrides config context_limit_estimate."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # Generate enough output tokens (~150) to exceed 80% of a tiny 50000-token window
            # (threshold = 40000 tokens). With LL_CONTEXT_LIMIT=50000 and LL_HANDOFF_THRESHOLD=1
            # any context usage triggers handoff, confirming the env var was used.
            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "x" * 500},
            }
            env = os.environ.copy()
            env["LL_CONTEXT_LIMIT"] = "50000"
            env["LL_HANDOFF_THRESHOLD"] = "1"  # trigger immediately

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
                env=env,
            )

            # Hook should trigger (exit 2) confirming LL_CONTEXT_LIMIT was consumed
            assert result.returncode == 2
            assert "handoff" in result.stderr.lower() or "context" in result.stderr.lower()

        finally:
            os.chdir(original_dir)

    def test_known_model_auto_detection(self, hook_script: Path, test_config: Path, tmp_path: Path):
        """Known model in JSONL triggers auto-detection of 200K context limit.

        Uses baseline of 180K tokens. At 200K limit: 90% → triggers handoff (exit 2).
        At 1M limit: 18% → no trigger (exit 0). The exit code proves which limit was used.
        """
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())  # context_limit_estimate = 1000000

            transcript_file = tmp_path / "transcript.jsonl"
            assistant_entry = {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "usage": {
                        "input_tokens": 180000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "output_tokens": 0,
                    },
                },
            }
            transcript_file.write_text(json.dumps(assistant_entry) + "\n")

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "x\n"},
                "transcript_path": str(transcript_file),
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            # exit 2 = handoff triggered. 180K / 200K = 90% > 80% threshold.
            # If denominator were 1M, 180K / 1M = 18% → no trigger (exit 0).
            assert result.returncode == 2, (
                f"Expected exit 2 (auto-detected 200K limit), got {result.returncode}. "
                f"stderr: {result.stderr}"
            )
            # Confirm denominator is 200000 in the handoff message
            assert "200000" in result.stderr, (
                f"Expected '200000' in stderr to confirm auto-detected limit. stderr: {result.stderr}"
            )

        finally:
            os.chdir(original_dir)

    def test_unknown_model_config_fallback(self, hook_script: Path, tmp_path: Path):
        """Unknown model falls back to context_limit_estimate from config.

        Uses baseline of 45K tokens with config limit 50K. At 50K: 90% → triggers (exit 2).
        At 200K auto-detected: 22.5% → no trigger (exit 0). Exit code proves fallback was used.
        """
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create config with explicit non-default context_limit_estimate
            config = {
                "context_monitor": {
                    "enabled": True,
                    "auto_handoff_threshold": 80,
                    "context_limit_estimate": 50000,
                    "state_file": str(tmp_path / "ll-context-state.json"),
                }
            }
            config_file = tmp_path / ".ll" / "ll-config.json"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(json.dumps(config, indent=2))

            transcript_file = tmp_path / "transcript.jsonl"
            assistant_entry = {
                "type": "assistant",
                "message": {
                    "model": "claude-custom-model-xyz",  # unknown model
                    "usage": {
                        "input_tokens": 45000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "output_tokens": 0,
                    },
                },
            }
            transcript_file.write_text(json.dumps(assistant_entry) + "\n")

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "x\n"},
                "transcript_path": str(transcript_file),
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            # exit 2 = handoff triggered. 45K / 50K = 90% > 80% threshold.
            # If denominator were 200K (auto-detected), 45K / 200K = 22.5% → no trigger.
            assert result.returncode == 2, (
                f"Expected exit 2 (config fallback 50K limit), got {result.returncode}. "
                f"stderr: {result.stderr}"
            )
            # Confirm denominator is 50000 in the handoff message
            assert "50000" in result.stderr, (
                f"Expected '50000' in stderr to confirm config fallback limit. stderr: {result.stderr}"
            )

        finally:
            os.chdir(original_dir)

    def test_reminder_rate_limited_second_call(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Second call above threshold within 60s exits 0 silently (rate-limited).

        First call should produce exit 2 with stderr. Second call within 60s should
        produce exit 0 with no stderr — the cooldown suppresses the reminder.
        """
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "x" * 500},
            }
            env = os.environ.copy()
            env["LL_HANDOFF_THRESHOLD"] = "1"  # trigger immediately

            def run_hook() -> subprocess.CompletedProcess:
                return subprocess.run(
                    [str(hook_script)],
                    input=json.dumps(input_data),
                    capture_output=True,
                    text=True,
                    timeout=6,
                    env=env,
                )

            # First call: should trigger reminder (exit 2)
            first = run_hook()
            assert first.returncode == 2, (
                f"Expected first call to exit 2 (trigger reminder), got {first.returncode}. "
                f"stderr: {first.stderr}"
            )

            # Second call: within 60s cooldown — should be silent (exit 0)
            second = run_hook()
            assert second.returncode == 0, (
                f"Expected second call within 60s to exit 0 (rate-limited), got {second.returncode}. "
                f"stderr: {second.stderr}"
            )
            assert second.stderr == "", (
                f"Expected no stderr on rate-limited call, got: {second.stderr!r}"
            )

        finally:
            os.chdir(original_dir)

    def test_state_contains_last_reminder_at_after_exit2(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """State file contains last_reminder_at timestamp after exit 2 fires."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "x" * 500},
            }
            env = os.environ.copy()
            env["LL_HANDOFF_THRESHOLD"] = "1"

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
                env=env,
            )
            assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"

            state_file = tmp_path / "ll-context-state.json"
            state = json.loads(state_file.read_text())
            assert "last_reminder_at" in state, (
                f"Expected 'last_reminder_at' in state after exit 2, got keys: {list(state.keys())}"
            )
            assert state["last_reminder_at"] is not None
            assert state["last_reminder_at"] != ""

        finally:
            os.chdir(original_dir)

    def test_fresh_state_with_handoff_file_sets_handoff_complete_true(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Fresh state initializes handoff_complete=true when ll-continue-prompt.md exists."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # Create the handoff file (simulates a prior-session handoff)
            (tmp_path / ".ll" / "ll-continue-prompt.md").write_text("Continue from here.")

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "output\n" * 10},
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            assert result.returncode == 0, (
                f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
            )

            state_file = tmp_path / "ll-context-state.json"
            assert state_file.exists()
            state = json.loads(state_file.read_text())
            assert state["handoff_complete"] is True, (
                f"Expected handoff_complete=true when handoff file exists, got: {state['handoff_complete']}"
            )

        finally:
            os.chdir(original_dir)

    def test_fresh_state_without_handoff_file_sets_handoff_complete_false(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Fresh state initializes handoff_complete=false when ll-continue-prompt.md is absent."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # No handoff file exists

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "output\n" * 10},
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            assert result.returncode == 0, (
                f"Expected exit 0, got {result.returncode}. stderr: {result.stderr}"
            )

            state_file = tmp_path / "ll-context-state.json"
            assert state_file.exists()
            state = json.loads(state_file.read_text())
            assert state["handoff_complete"] is False, (
                f"Expected handoff_complete=false when no handoff file, got: {state['handoff_complete']}"
            )

        finally:
            os.chdir(original_dir)

    def test_reminder_fires_again_after_cooldown_expires(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Reminder fires again (exit 2) when last_reminder_at is more than 60s ago."""
        import os
        from datetime import UTC, datetime, timedelta

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # Pre-write state with last_reminder_at 2 minutes ago
            old_ts = (datetime.now(UTC) - timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
            state_file = tmp_path / "ll-context-state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "session_start": old_ts,
                        "estimated_tokens": 0,
                        "tool_calls": 5,
                        "threshold_crossed_at": old_ts,
                        "handoff_complete": False,
                        "last_reminder_at": old_ts,
                        "breakdown": {},
                    }
                )
            )

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "x" * 500},
            }
            env = os.environ.copy()
            env["LL_HANDOFF_THRESHOLD"] = "1"
            env["LL_CONTEXT_LIMIT"] = "1000"  # tiny limit ensures threshold is crossed

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
                env=env,
            )

            # Cooldown expired (120s > 60s) — should fire again
            assert result.returncode == 2, (
                f"Expected exit 2 after cooldown expires (120s > 60s), got {result.returncode}. "
                f"stderr: {result.stderr}"
            )

        finally:
            os.chdir(original_dir)

    def test_detected_model_cached_in_state(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Detected model from transcript should be cached in state file."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # Create transcript with a known model
            transcript_file = tmp_path / "transcript.jsonl"
            assistant_entry = {
                "type": "assistant",
                "message": {
                    "model": "claude-sonnet-4-6",
                    "usage": {
                        "input_tokens": 1000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "output_tokens": 100,
                    },
                },
            }
            transcript_file.write_text(json.dumps(assistant_entry) + "\n")

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "small output\n"},
                "transcript_path": str(transcript_file),
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            assert result.returncode == 0

            state_file = tmp_path / "ll-context-state.json"
            state = json.loads(state_file.read_text())

            # Model should be cached in state for future calls
            assert "detected_model" in state, (
                f"State should contain 'detected_model' field. State keys: {list(state.keys())}"
            )
            assert state["detected_model"] == "claude-sonnet-4-6"

        finally:
            os.chdir(original_dir)

    def test_large_tool_response_completes_within_timeout(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Hook should complete within 5s even with large tool_response and transcript."""
        import os
        import time

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # Create a transcript with 200 entries to simulate a mid-session state
            transcript_file = tmp_path / "transcript.jsonl"
            entries = []
            for i in range(200):
                entry = {
                    "type": "assistant" if i % 2 == 0 else "user",
                    "message": {
                        "model": "claude-sonnet-4-6",
                        "content": f"Response {i} " + "x" * 200,
                        "usage": {
                            "input_tokens": 1000 + i * 10,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 100,
                        },
                    },
                }
                entries.append(json.dumps(entry))
            transcript_file.write_text("\n".join(entries) + "\n")

            # Large tool_response simulating a 2000-line file read
            large_content = "Line of code with some typical content here\n" * 2000
            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": large_content},
                "transcript_path": str(transcript_file),
            }

            start = time.monotonic()
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
            )
            elapsed = time.monotonic() - start

            assert result.returncode in (0, 2), (
                f"Hook failed with exit code {result.returncode}. "
                f"stderr: {result.stderr}"
            )
            assert elapsed < 5.0, (
                f"Hook took {elapsed:.2f}s, exceeding 5s timeout. "
                f"stderr: {result.stderr}"
            )

        finally:
            os.chdir(original_dir)


class TestUserPromptCheck:
    """Test user-prompt-check.sh special character handling."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to user-prompt-check.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/user-prompt-check.sh"

    @pytest.fixture
    def test_config(self, tmp_path: Path) -> Path:
        """Create test config with prompt optimization disabled."""
        config = {"prompt_optimization": {"enabled": False}}
        config_file = tmp_path / ".ll" / "ll-config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(config, indent=2))
        return config_file

    @pytest.mark.parametrize(
        "prompt",
        [
            "Simple prompt with $VAR",
            "Prompt with & ampersand",
            "Prompt with \\ backslash",
            "Prompt with / forward slash",
            "Prompt with {{template}} syntax",
            "Prompt with }}} extra braces",
            "Multi\nline\nprompt",
            "Prompt with `backticks` and $(subshell)",
            "Prompt with ; semicolon && and ||",
            "Prompt with \"quotes\" and 'apostrophes'",
        ],
    )
    def test_special_characters_no_injection(
        self, hook_script: Path, test_config: Path, tmp_path: Path, prompt: str
    ):
        """Verify special characters don't cause shell injection or template corruption."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create config
            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            input_data = {"prompt": prompt}

            # Run hook
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Should exit cleanly with 0 (skip or optimization context added)
            assert result.returncode == 0, f"Unexpected exit code: {result.returncode}"

            # No errors on stderr (optimization output goes to stdout)
            if result.returncode == 0:
                # Skipped - no error output expected
                pass

        finally:
            os.chdir(original_dir)

    @pytest.fixture
    def enabled_config(self, tmp_path: Path) -> Path:
        """Create test config with prompt optimization enabled."""
        config = {"prompt_optimization": {"enabled": True, "mode": "quick", "confirm": "true"}}
        config_file = tmp_path / ".ll" / "ll-config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(config, indent=2))
        return config_file

    def test_optimization_template_injected_when_claude_plugin_root_set(
        self, hook_script: Path, enabled_config: Path, tmp_path: Path
    ):
        """Regression test: prompt optimization must not silently fail when CLAUDE_PLUGIN_ROOT is set.

        The bug: HOOK_PROMPT_FILE used CLAUDE_PLUGIN_ROOT which resolves to
        $CLAUDE_PLUGIN_ROOT/prompts/ — a path that doesn't exist.
        Fix: always use SCRIPT_DIR/../prompts/ instead.
        """
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(enabled_config.read_text())

            input_data = {
                "prompt": "This is a qualifying prompt that is longer than ten characters"
            }

            # Set CLAUDE_PLUGIN_ROOT to the project root (not hooks/ dir) to reproduce the bug.
            # With the bug: path resolves to $CLAUDE_PLUGIN_ROOT/prompts/ (no such dir) → empty output.
            # After fix: path uses SCRIPT_DIR/../prompts/ → template injected → non-empty output.
            project_root = str(hook_script.parent.parent.parent)
            env = os.environ.copy()
            env["CLAUDE_PLUGIN_ROOT"] = project_root

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )

            assert result.returncode == 0, (
                f"Hook exited non-zero: {result.returncode}\n{result.stderr}"
            )
            assert result.stdout.strip(), (
                "Prompt optimization produced no output — template was not injected. "
                "HOOK_PROMPT_FILE path is likely wrong when CLAUDE_PLUGIN_ROOT is set."
            )
        finally:
            os.chdir(original_dir)


class TestIssueCompletionLog:
    """Test issue-completion-log.sh path injection safety."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to issue-completion-log.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/issue-completion-log.sh"

    def _make_input(self, dest_path: str, transcript_path: str) -> str:
        """Build JSON stdin for the hook simulating a git mv to completed/."""
        return json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": f"git mv .issues/bugs/P3-BUG-870.md {dest_path}"},
                "transcript_path": transcript_path,
            }
        )

    @pytest.mark.parametrize(
        "transcript_name",
        [
            "normal-transcript.jsonl",
            "O'Brien-transcript.jsonl",
            "it's-fixed.jsonl",
        ],
    )
    def test_single_quote_in_transcript_path_appends_log(
        self, hook_script: Path, tmp_path: Path, transcript_name: str
    ):
        """Session log entry is appended even when transcript path contains single quotes.

        Before the fix, shell interpolation of $TRANSCRIPT_PATH into a Python string
        literal caused a SyntaxError for paths with single quotes. The error was
        swallowed by || true so returncode stayed 0 but no entry was written.
        """
        import os

        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        issue_file = completed_dir / "P3-BUG-870-test.md"
        issue_file.write_text("---\ndiscovered_date: 2026-01-01\n---\n# Test\n\n## Session Log\n")

        transcript_dir = tmp_path / "transcripts"
        transcript_dir.mkdir()
        transcript_file = transcript_dir / transcript_name
        transcript_file.write_text("")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(issue_file), str(transcript_file)),
                capture_output=True,
                text=True,
                timeout=10,
            )

            assert result.returncode == 0, (
                f"Hook exited non-zero: {result.returncode}\n{result.stderr}"
            )
            content = issue_file.read_text()
            assert "hook:posttooluse-git-mv" in content, (
                f"Session log entry not appended for transcript path {transcript_name!r}. "
                "Likely a Python SyntaxError was silently swallowed."
            )
        finally:
            os.chdir(original_dir)


class TestDuplicateIssueId:
    """Test check-duplicate-issue-id.sh race condition handling."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to check-duplicate-issue-id.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/check-duplicate-issue-id.sh"

    def test_concurrent_duplicate_detection(self, hook_script: Path, tmp_path: Path):
        """Test duplicate check with concurrent Write attempts."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create .issues directory
            issues_dir = tmp_path / ".issues" / "bugs"
            issues_dir.mkdir(parents=True)

            # Create one existing issue
            existing = issues_dir / "P2-BUG-001-existing.md"
            existing.write_text("# Existing issue")

            def attempt_create(issue_id: str, file_num: int) -> subprocess.CompletedProcess:
                """Attempt to create an issue file."""
                input_data = {
                    "tool_name": "Write",
                    "tool_input": {
                        "file_path": str(issues_dir / f"P2-BUG-{issue_id}-test-{file_num}.md")
                    },
                }
                result = subprocess.run(
                    [str(hook_script)],
                    input=json.dumps(input_data),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return result

            # Try to create duplicate BUG-001 from multiple threads
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(attempt_create, "001", i) for i in range(5)]
                results = [f.result() for f in as_completed(futures)]

            # All should be denied (duplicate of existing)
            denied_count = sum(1 for r in results if "deny" in r.stdout.lower())
            assert denied_count >= 4, f"Expected at least 4 denials, got {denied_count}"

            # Try to create new issue BUG-002 concurrently
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(attempt_create, "002", i) for i in range(3)]
                results = [f.result() for f in as_completed(futures)]

            # At least one should be allowed (first one)
            # Some may be allowed if they run before the file is created
            allowed_count = sum(1 for r in results if "allow" in r.stdout.lower())
            assert allowed_count >= 1, "At least one should be allowed"

        finally:
            os.chdir(original_dir)

    def test_config_fallback_to_root_ll_config(self, hook_script: Path, tmp_path: Path):
        """Test that script reads issues.base_dir from ll-config.json when .claude/ config absent."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Config at root ll-config.json only (no .ll/ll-config.json)
            custom_base = "myissues"
            config = {"issues": {"base_dir": custom_base}}
            (tmp_path / "ll-config.json").write_text(json.dumps(config))

            # Create custom issues directory
            issues_dir = tmp_path / custom_base / "bugs"
            issues_dir.mkdir(parents=True)

            # Create an existing issue in the custom directory
            (issues_dir / "P2-BUG-010-existing.md").write_text("# Existing issue")

            # Try to create a duplicate — should be denied (custom base_dir was read)
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": str(issues_dir / "P2-BUG-010-duplicate.md")},
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert "deny" in result.stdout.lower(), (
                f"Expected deny when duplicate exists in custom base_dir '{custom_base}'. "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )

        finally:
            os.chdir(original_dir)

    def test_null_byte_in_filename(self, hook_script: Path, tmp_path: Path):
        """Test that null-terminated find handles unusual filenames correctly."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create .issues directory with various filenames
            issues_dir = tmp_path / ".issues" / "bugs"
            issues_dir.mkdir(parents=True)

            # Create issues with spaces and special chars in names
            (issues_dir / "P2-BUG-001-has spaces.md").write_text("test")
            (issues_dir / "P2-BUG-002-has'quote.md").write_text("test")

            # Try to create duplicate
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": str(issues_dir / "P2-BUG-001-another.md")},
            }

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Should detect duplicate despite spaces in existing filename
            assert "deny" in result.stdout.lower(), "Should deny duplicate"

        finally:
            os.chdir(original_dir)


class TestSharedConfigFunctions:
    """Test ll_resolve_config, ll_feature_enabled, ll_config_value from common.sh."""

    @pytest.fixture
    def common_sh(self) -> Path:
        """Path to common.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/lib/common.sh"

    def _run_bash(self, common_sh: Path, script: str, cwd: Path) -> subprocess.CompletedProcess:
        """Run a bash snippet that sources common.sh."""
        full_script = f'source "{common_sh}"\n{script}'
        return subprocess.run(
            ["bash", "-e", "-c", full_script],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(cwd),
        )

    def test_resolve_config_finds_ll_dir(self, common_sh: Path, tmp_path: Path):
        """ll_resolve_config finds .ll/ll-config.json."""
        config_dir = tmp_path / ".ll"
        config_dir.mkdir()
        config_file = config_dir / "ll-config.json"
        config_file.write_text('{"test": true}')

        result = self._run_bash(common_sh, 'll_resolve_config; echo "$LL_CONFIG_FILE"', tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ".ll/ll-config.json"

    def test_resolve_config_finds_root_fallback(self, common_sh: Path, tmp_path: Path):
        """ll_resolve_config falls back to ll-config.json."""
        config_file = tmp_path / "ll-config.json"
        config_file.write_text('{"test": true}')

        result = self._run_bash(common_sh, 'll_resolve_config; echo "$LL_CONFIG_FILE"', tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "ll-config.json"

    def test_resolve_config_empty_when_missing(self, common_sh: Path, tmp_path: Path):
        """ll_resolve_config sets empty string when no config found."""
        result = self._run_bash(common_sh, 'll_resolve_config; echo "[$LL_CONFIG_FILE]"', tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "[]"

    def test_feature_enabled_returns_true(self, common_sh: Path, tmp_path: Path):
        """ll_feature_enabled returns 0 when feature is enabled."""
        config_dir = tmp_path / ".ll"
        config_dir.mkdir()
        (config_dir / "ll-config.json").write_text('{"context_monitor": {"enabled": true}}')

        result = self._run_bash(
            common_sh,
            'set +e; ll_resolve_config; ll_feature_enabled "context_monitor.enabled"; echo $?',
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "0"

    def test_feature_enabled_returns_false(self, common_sh: Path, tmp_path: Path):
        """ll_feature_enabled returns 1 when feature is disabled."""
        config_dir = tmp_path / ".ll"
        config_dir.mkdir()
        (config_dir / "ll-config.json").write_text('{"context_monitor": {"enabled": false}}')

        result = self._run_bash(
            common_sh,
            'set +e; ll_resolve_config; ll_feature_enabled "context_monitor.enabled"; echo $?',
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_feature_enabled_missing_key(self, common_sh: Path, tmp_path: Path):
        """ll_feature_enabled returns 1 when key is missing."""
        config_dir = tmp_path / ".ll"
        config_dir.mkdir()
        (config_dir / "ll-config.json").write_text("{}")

        result = self._run_bash(
            common_sh,
            'set +e; ll_resolve_config; ll_feature_enabled "sync.enabled"; echo $?',
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_feature_enabled_no_config(self, common_sh: Path, tmp_path: Path):
        """ll_feature_enabled returns 1 when no config file exists."""
        result = self._run_bash(
            common_sh,
            'set +e; ll_resolve_config; ll_feature_enabled "sync.enabled"; echo $?',
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "1"

    def test_config_value_reads_string(self, common_sh: Path, tmp_path: Path):
        """ll_config_value reads a string value."""
        config_dir = tmp_path / ".ll"
        config_dir.mkdir()
        (config_dir / "ll-config.json").write_text('{"prompt_optimization": {"mode": "thorough"}}')

        result = self._run_bash(
            common_sh,
            'll_resolve_config; ll_config_value "prompt_optimization.mode" "quick"',
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "thorough"

    def test_config_value_uses_default(self, common_sh: Path, tmp_path: Path):
        """ll_config_value returns default when key is missing."""
        config_dir = tmp_path / ".ll"
        config_dir.mkdir()
        (config_dir / "ll-config.json").write_text("{}")

        result = self._run_bash(
            common_sh,
            'll_resolve_config; ll_config_value "prompt_optimization.mode" "quick"',
            tmp_path,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "quick"


class TestSessionStartValidation:
    """Test validate_enabled_features in session-start.sh."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to session-start.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/session-start.sh"

    def test_warns_sync_without_github(self, hook_script: Path, tmp_path: Path):
        """Warns when sync.enabled is true but sync.github is empty."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            config_dir = tmp_path / ".ll"
            config_dir.mkdir()
            (config_dir / "ll-config.json").write_text(json.dumps({"sync": {"enabled": True}}))

            result = subprocess.run(
                [str(hook_script)],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert "sync.enabled is true but sync.github is not configured" in result.stderr
        finally:
            os.chdir(original_dir)

    def test_warns_documents_without_categories(self, hook_script: Path, tmp_path: Path):
        """Warns when documents.enabled is true but no categories."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            config_dir = tmp_path / ".ll"
            config_dir.mkdir()
            (config_dir / "ll-config.json").write_text(json.dumps({"documents": {"enabled": True}}))

            result = subprocess.run(
                [str(hook_script)],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert (
                "documents.enabled is true but no document categories configured" in result.stderr
            )
        finally:
            os.chdir(original_dir)

    def test_warns_product_without_goals(self, hook_script: Path, tmp_path: Path):
        """Warns when product.enabled is true but goals file missing."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            config_dir = tmp_path / ".ll"
            config_dir.mkdir()
            (config_dir / "ll-config.json").write_text(json.dumps({"product": {"enabled": True}}))

            result = subprocess.run(
                [str(hook_script)],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert "product.enabled is true but goals file not found" in result.stderr
        finally:
            os.chdir(original_dir)

    def test_no_warnings_when_properly_configured(self, hook_script: Path, tmp_path: Path):
        """No warnings when enabled features have required sub-configuration."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            config_dir = tmp_path / ".ll"
            config_dir.mkdir()

            # Create goals file for product
            (config_dir / "ll-goals.md").write_text("# Goals\n")

            (config_dir / "ll-config.json").write_text(
                json.dumps(
                    {
                        "sync": {
                            "enabled": True,
                            "github": {"label_mapping": {"BUG": "bug"}},
                        },
                        "documents": {
                            "enabled": True,
                            "categories": {"arch": {"files": ["docs/ARCH.md"]}},
                        },
                        "product": {
                            "enabled": True,
                            "goals_file": ".ll/ll-goals.md",
                        },
                    }
                )
            )

            result = subprocess.run(
                [str(hook_script)],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert "Warning:" not in result.stderr
        finally:
            os.chdir(original_dir)

    def test_no_warnings_when_features_disabled(self, hook_script: Path, tmp_path: Path):
        """No warnings when features are disabled."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            config_dir = tmp_path / ".ll"
            config_dir.mkdir()
            (config_dir / "ll-config.json").write_text(
                json.dumps(
                    {
                        "sync": {"enabled": False},
                        "documents": {"enabled": False},
                        "product": {"enabled": False},
                    }
                )
            )

            result = subprocess.run(
                [str(hook_script)],
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert "Warning:" not in result.stderr
        finally:
            os.chdir(original_dir)


class TestPrecompactState:
    """Test precompact-state.sh file operations."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to precompact-state.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/precompact-state.sh"

    def test_atomic_write_with_missing_directory(self, hook_script: Path, tmp_path: Path):
        """Test that state is written even if thoughts directory doesn't exist."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Don't create thoughts/shared/plans - test graceful handling
            input_data = {"transcript_path": "/tmp/transcript.jsonl"}

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Should succeed with exit 2 (PreCompact: non-blocking, shows stderr to user)
            assert result.returncode == 2

            # State file should exist with valid JSON
            state_file = tmp_path / ".ll" / "ll-precompact-state.json"
            assert state_file.exists()

            state = json.loads(state_file.read_text())
            assert state["preserved"] is True
            assert "recent_plan_files" in state
            assert state["recent_plan_files"] == []  # Empty since dir doesn't exist

        finally:
            os.chdir(original_dir)

    def test_concurrent_precompact_writes(self, hook_script: Path, tmp_path: Path):
        """Test concurrent precompact hook invocations."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            def run_hook(i: int) -> subprocess.CompletedProcess:
                input_data = {"transcript_path": f"/tmp/transcript-{i}.jsonl"}
                return subprocess.run(
                    [str(hook_script)],
                    input=json.dumps(input_data),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

            # Run 5 hooks concurrently
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(run_hook, i) for i in range(5)]
                results = [f.result() for f in as_completed(futures)]

            # All should succeed with exit 2 (PreCompact: non-blocking, shows stderr)
            assert all(r.returncode == 2 for r in results)

            # State file should have valid JSON (last write wins)
            state_file = tmp_path / ".ll" / "ll-precompact-state.json"
            state = json.loads(state_file.read_text())
            assert state["preserved"] is True

        finally:
            os.chdir(original_dir)


class TestContextMonitorLockTimeout:
    """Test that context-monitor.sh uses correct lock timeout value."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to context-monitor.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/context-monitor.sh"

    def test_lock_timeout_leaves_adequate_margin(self, hook_script: Path):
        """context-monitor.sh lock timeout must be 3s to leave ~2s margin within 5s hook timeout.

        The PostToolUse hook timeout is 5s. Using a 4s lock timeout leaves only 1s for
        post-acquisition operations, which is insufficient under I/O load. The timeout
        must be 3s to match precompact-state.sh and check-duplicate-issue-id.sh.
        """
        content = hook_script.read_text()
        assert 'acquire_lock "$STATE_LOCK" 3' in content, (
            "context-monitor.sh must use a 3s lock timeout (not 4s) to leave ~2s margin "
            "within the 5s PostToolUse hook timeout"
        )
