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
            config_link.write_text(
                test_config.read_text()
            )  # no context_limit_estimate -> auto-detect

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

    def test_fresh_state_with_handoff_file_sets_handoff_complete_false(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Fresh state initializes handoff_complete=false even when ll-continue-prompt.md exists.

        The continue-prompt file persists across sessions and must NOT suppress reminders in a
        new session. The post-threshold mtime check in main() handles marking complete mid-session.
        """
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
            assert state["handoff_complete"] is False, (
                f"Expected handoff_complete=false on fresh state even when handoff file exists, "
                f"got: {state['handoff_complete']}"
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
                f"Hook failed with exit code {result.returncode}. stderr: {result.stderr}"
            )
            assert elapsed < 5.0, (
                f"Hook took {elapsed:.2f}s, exceeding 5s timeout. stderr: {result.stderr}"
            )

        finally:
            os.chdir(original_dir)

    def test_result_token_count_used_when_present(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """When result_token_count > 0 in state, context-monitor uses it instead of heuristics."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            # Pre-write state with result_token_count (simulating on_usage closure write)
            state_file = tmp_path / "ll-context-state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "estimated_tokens": 1000,
                        "tool_calls": 5,
                        "result_token_count": 80000,
                        "breakdown": {},
                    }
                )
            )

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "x" * 100},
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            assert result.returncode == 0, f"Hook failed: {result.stderr}"

            state = json.loads(state_file.read_text())
            # With result_token_count=80000, estimated_tokens should reflect that value
            # (plus per-turn overhead), not the heuristic path from 1000.
            assert state["estimated_tokens"] >= 80000, (
                f"estimated_tokens {state['estimated_tokens']} should be >= 80000 "
                f"(result_token_count path). Full state: {state}"
            )

        finally:
            os.chdir(original_dir)

    def test_result_token_count_zero_falls_back_to_heuristics(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """When result_token_count is 0 in state, context-monitor falls back to heuristics."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            state_file = tmp_path / "ll-context-state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "estimated_tokens": 5000,
                        "tool_calls": 3,
                        "result_token_count": 0,
                        "breakdown": {},
                    }
                )
            )

            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "small output"},
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            assert result.returncode == 0, f"Hook failed: {result.stderr}"

            state = json.loads(state_file.read_text())
            # Falls back to heuristics: estimated_tokens stays near 5000 (heuristic delta is small)
            assert state["estimated_tokens"] < 80000, (
                f"estimated_tokens {state['estimated_tokens']} should stay near heuristic baseline. "
                f"Full state: {state}"
            )

        finally:
            os.chdir(original_dir)

    def test_1m_model_limit_resolution(self, hook_script: Path, test_config: Path, tmp_path: Path):
        """Transcript baseline exceeding 200k auto-upgrades context limit to 1M.

        Uses baseline of 250K tokens on claude-opus-4-8 (maps to 200k by model name).
        250k > 200k triggers auto-upgrade to 1M. 250k / 1M = 25% -> no handoff (exit 0).
        Verifies state context_limit is written as 1000000.
        """
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            transcript_file = tmp_path / "transcript.jsonl"
            assistant_entry = {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-8",
                    "usage": {
                        "input_tokens": 250000,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "output_tokens": 0,
                    },
                },
            }
            transcript_file.write_text(json.dumps(assistant_entry) + "\n")

            state_file = tmp_path / "ll-context-state.json"
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

            # exit 0 = no trigger. 250k / 1M = 25% < 80% threshold.
            assert result.returncode == 0, (
                f"Expected exit 0 (auto-upgraded to 1M limit), got {result.returncode}. "
                f"stderr: {result.stderr}"
            )
            if state_file.exists():
                state = json.loads(state_file.read_text())
                assert state.get("context_limit") == 1000000, (
                    f"Expected context_limit=1000000 in state. Full state: {state}"
                )

        finally:
            os.chdir(original_dir)

    def test_sentinel_1000000_honored_as_explicit_override(self, hook_script: Path, tmp_path: Path):
        """Explicit context_limit_estimate: 1000000 in config is honored (not treated as sentinel).

        Unknown model with 900k baseline and config limit 1000000. 900k / 1M = 90% -> trigger (exit 2).
        If 1000000 were still ignored: limit falls to 200k, 900k clamped -> exit 0.
        """
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

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

            transcript_file = tmp_path / "transcript.jsonl"
            assistant_entry = {
                "type": "assistant",
                "message": {
                    "model": "claude-custom-model-xyz",
                    "usage": {
                        "input_tokens": 900000,
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

            # exit 2 = handoff triggered. 900k / 1M = 90% > 80% threshold.
            assert result.returncode == 2, (
                f"Expected exit 2 (1000000 honored as 1M limit), got {result.returncode}. "
                f"stderr: {result.stderr}"
            )
            assert "1000000" in result.stderr, (
                f"Expected '1000000' in stderr to confirm explicit 1M limit. stderr: {result.stderr}"
            )

        finally:
            os.chdir(original_dir)

    def test_impossible_baseline_clamped(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Impossible token count (> 1.05x limit) is clamped to prior estimate, no spurious trigger.

        Pre-write state with result_token_count=1517046 (> 200k limit x 1.05 = 210k).
        Clamp falls back to CURRENT_TOKENS (1000) -> exit 0. Without clamp: 758% -> exit 2.
        """
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            config_link = tmp_path / ".ll" / "ll-config.json"
            config_link.parent.mkdir(exist_ok=True)
            config_link.write_text(test_config.read_text())

            state_file = tmp_path / "ll-context-state.json"
            state_file.write_text(
                json.dumps(
                    {
                        "estimated_tokens": 1000,
                        "tool_calls": 5,
                        "result_token_count": 1517046,
                        "breakdown": {},
                    }
                )
            )

            input_data = {
                "tool_name": "Write",
                "tool_response": {"content": ""},
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )

            assert result.returncode != 2, (
                f"Expected no handoff trigger (clamped), got exit 2. stderr: {result.stderr}"
            )
            state = json.loads(state_file.read_text())
            assert state["estimated_tokens"] <= 200000, (
                f"estimated_tokens {state['estimated_tokens']} should be <= 200000 after clamp. "
                f"Full state: {state}"
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
        """Build JSON stdin for the hook simulating a PostToolUse Write of status: done."""
        return json.dumps(
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": dest_path,
                    "content": (
                        "---\n"
                        "status: done\n"
                        "discovered_date: 2026-01-01\n"
                        "---\n\n"
                        "# BUG-870: Test\n\n## Session Log\n"
                    ),
                },
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

        Paths with single quotes used to break shell interpolation into the Python
        snippet; passing via env vars keeps them safe. The hook detects a Write
        marking an issue file `status: done` in frontmatter and appends a session
        log entry.
        """
        import os

        # Issue file lives in its category dir (frontmatter status flips in place
        # under the new model — no move to completed/).
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        issue_file = bugs_dir / "P3-BUG-870-test.md"
        issue_file.write_text(
            "---\nstatus: done\ndiscovered_date: 2026-01-01\n---\n# Test\n\n## Session Log\n"
        )

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
            assert "hook:posttooluse-status-done" in content, (
                f"Session log entry not appended for transcript path {transcript_name!r}. "
                "Likely a Python SyntaxError was silently swallowed."
            )
            assert transcript_name in content, (
                f"Transcript path {transcript_name!r} missing from session log entry."
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

    def test_cross_type_integer_collision(self, hook_script: Path, tmp_path: Path):
        """Test that write is denied when same integer is used with a different type prefix."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create .issues directory with bugs and features subdirs
            bugs_dir = tmp_path / ".issues" / "bugs"
            bugs_dir.mkdir(parents=True)
            features_dir = tmp_path / ".issues" / "features"
            features_dir.mkdir(parents=True)

            # Create existing BUG-007
            (bugs_dir / "P2-BUG-007-existing.md").write_text("# Existing bug")

            # Try to create FEAT-007 — should be denied (cross-type integer collision)
            input_data = {
                "tool_name": "Write",
                "tool_input": {"file_path": str(features_dir / "P2-FEAT-007-new-feature.md")},
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert "deny" in result.stdout.lower(), (
                f"Expected deny for FEAT-007 when BUG-007 exists (cross-type collision). "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )

            # ENH-007 should also be denied
            input_data["tool_input"]["file_path"] = str(
                tmp_path / ".issues" / "enhancements" / "P3-ENH-007-enhancement.md"
            )
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert "deny" in result.stdout.lower(), (
                f"Expected deny for ENH-007 when BUG-007 exists (cross-type collision). "
                f"stdout={result.stdout!r} stderr={result.stderr!r}"
            )

        finally:
            os.chdir(original_dir)


class TestDuplicateIssueIdPost:
    """Test check-duplicate-issue-id-post.sh PostToolUse reactive deletion."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to check-duplicate-issue-id-post.sh."""
        return (
            Path(__file__).parent.parent.parent / "hooks/scripts/check-duplicate-issue-id-post.sh"
        )

    def _make_input(self, file_path: str) -> str:
        """Build JSON stdin simulating a PostToolUse Write event."""
        return json.dumps({"tool_name": "Write", "tool_input": {"file_path": file_path}})

    def test_unique_issue_not_deleted(self, hook_script: Path, tmp_path: Path):
        """A newly written file with a unique integer ID is left intact."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            issues_dir = tmp_path / ".issues" / "bugs"
            issues_dir.mkdir(parents=True)

            new_file = issues_dir / "P2-BUG-042-first-issue.md"
            new_file.write_text("# First issue")

            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(new_file)),
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0, (
                f"Expected exit 0, got {result.returncode}: {result.stderr}"
            )
            assert new_file.exists(), "Unique issue file should not be deleted"
        finally:
            os.chdir(original_dir)

    def test_duplicate_file_deleted_and_exit2(self, hook_script: Path, tmp_path: Path):
        """A newly written file whose integer ID already exists is deleted; hook exits 2."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            bugs_dir = tmp_path / ".issues" / "bugs"
            bugs_dir.mkdir(parents=True)

            # Pre-existing issue
            existing = bugs_dir / "P2-BUG-007-original.md"
            existing.write_text("# Original")

            # Duplicate written by a concurrent Write tool call
            duplicate = bugs_dir / "P2-BUG-007-duplicate.md"
            duplicate.write_text("# Duplicate")

            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(duplicate)),
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
            assert not duplicate.exists(), "Duplicate file should be deleted"
            assert existing.exists(), "Original file should remain"
            assert "007" in result.stderr, f"Feedback should mention integer: {result.stderr}"
        finally:
            os.chdir(original_dir)

    def test_cross_type_duplicate_deleted(self, hook_script: Path, tmp_path: Path):
        """A newly written file whose integer collides with a different-type file is deleted."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            bugs_dir = tmp_path / ".issues" / "bugs"
            bugs_dir.mkdir(parents=True)
            features_dir = tmp_path / ".issues" / "features"
            features_dir.mkdir(parents=True)

            # Pre-existing BUG-007
            existing = bugs_dir / "P2-BUG-007-original.md"
            existing.write_text("# Original bug")

            # FEAT-007 just written — cross-type collision
            duplicate = features_dir / "P2-FEAT-007-new-feature.md"
            duplicate.write_text("# New feature")

            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(duplicate)),
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
            assert not duplicate.exists(), "Cross-type duplicate should be deleted"
            assert existing.exists(), "Original bug file should remain"
        finally:
            os.chdir(original_dir)

    def test_non_issue_file_ignored(self, hook_script: Path, tmp_path: Path):
        """Files outside the issues directory are ignored without error."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # File not in .issues/
            other_file = tmp_path / "README.md"
            other_file.write_text("# Not an issue")

            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(other_file)),
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0, f"Expected exit 0 for non-issue file: {result.stderr}"
            assert other_file.exists(), "Non-issue file should not be touched"
        finally:
            os.chdir(original_dir)

    def test_non_write_tool_ignored(self, hook_script: Path, tmp_path: Path):
        """Non-Write tool events (e.g., Bash) are ignored immediately."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hi"}}),
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert result.returncode == 0, f"Expected exit 0 for non-Write tool: {result.stderr}"
        finally:
            os.chdir(original_dir)


class TestSharedConfigFunctionsBashSmoke:
    """Smoke check that bash callers can still source common.sh after the FEAT-1454 port.

    The Python-direct equivalents of ``ll_resolve_config`` / ``ll_feature_enabled``
    now live in ``little_loops.config.core`` and ``little_loops.config.features``
    and are exhaustively tested in ``test_config.py:TestResolveConfigPath`` and
    ``TestFeatureEnabledHelper``. The exhaustive bash-source coverage was dropped
    along with the ``_run_bash`` / ``source common.sh`` harness; we only verify the
    bash primitives are still defined for the bash hook scripts not yet migrated.
    """

    def test_common_sh_still_defines_bash_primitives(self) -> None:
        common_sh = Path(__file__).parent.parent.parent / "hooks/scripts/lib/common.sh"
        for fn in (
            "acquire_lock",
            "release_lock",
            "atomic_write_json",
            "ll_resolve_config",
            "ll_feature_enabled",
            "ll_config_value",
        ):
            result = subprocess.run(
                ["bash", "-c", f'source "{common_sh}" && declare -f {fn} >/dev/null'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0, f"bash function {fn!r} missing from common.sh"


class TestSessionStartValidation:
    """Test feature-flag validation in the SessionStart Claude Code adapter (FEAT-1450)."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to the Claude Code session-start adapter."""
        return Path(__file__).parent.parent.parent / "hooks/adapters/claude-code/session-start.sh"

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
                input="{}",
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
                input="{}",
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert (
                "documents.enabled is true but no document categories configured" in result.stderr
            )
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
                        "design_tokens": {"enabled": False},
                    }
                )
            )

            result = subprocess.run(
                [str(hook_script)],
                input="{}",
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
                        "design_tokens": {"enabled": False},
                    }
                )
            )

            result = subprocess.run(
                [str(hook_script)],
                input="{}",
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert "Warning:" not in result.stderr
        finally:
            os.chdir(original_dir)

    def test_warns_design_tokens_enabled_without_path(self, hook_script: Path, tmp_path: Path):
        """Warns when design_tokens.enabled is true but the path does not exist."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            config_dir = tmp_path / ".ll"
            config_dir.mkdir()
            (config_dir / "ll-config.json").write_text(
                json.dumps({"design_tokens": {"enabled": True}})
            )

            result = subprocess.run(
                [str(hook_script)],
                input="{}",
                capture_output=True,
                text=True,
                timeout=5,
            )

            assert "design_tokens.enabled is true but path" in result.stderr
            assert "does not exist" in result.stderr
        finally:
            os.chdir(original_dir)


class TestPrecompactState:
    """Test precompact adapter (Python handler via Claude Code wrapper)."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to the Claude Code precompact adapter (FEAT-1455)."""
        return Path(__file__).parent.parent.parent / "hooks/adapters/claude-code/precompact.sh"

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


class TestScratchPadRedirect:
    """Test scratch-pad-redirect.sh PreToolUse hook (ENH-1129)."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to scratch-pad-redirect.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/scratch-pad-redirect.sh"

    def _write_config(self, tmp_path: Path, enabled: bool = True, **overrides) -> None:
        """Write ll-config.json with scratch_pad block."""
        scratch_pad = {
            "enabled": enabled,
            "threshold_lines": 200,
            "automation_contexts_only": True,
            "tail_lines": 20,
            "command_allowlist": ["cat", "pytest", "mypy", "ruff", "ls", "grep", "find"],
            "file_extension_filters": [".log", ".txt", ".json", ".md", ".py", ".ts", ".tsx", ".js"],
        }
        scratch_pad.update(overrides)
        config = {"scratch_pad": scratch_pad}
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "ll-config.json").write_text(json.dumps(config))

    def _run(self, hook_script: Path, input_data: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(hook_script)],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_disabled_noop(self, hook_script: Path, tmp_path: Path):
        """When scratch_pad.enabled is false, hook allows unchanged."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            self._write_config(tmp_path, enabled=False)
            result = self._run(
                hook_script,
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest scripts/tests/"},
                    "permission_mode": "bypassPermissions",
                },
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
            assert "updatedInput" not in output["hookSpecificOutput"]
        finally:
            os.chdir(original_dir)

    def test_non_automation_noop(self, hook_script: Path, tmp_path: Path):
        """When permission_mode is not bypassPermissions, hook is a no-op."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            self._write_config(tmp_path, enabled=True)
            result = self._run(
                hook_script,
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest scripts/tests/"},
                    # no permission_mode
                },
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
            assert "updatedInput" not in output["hookSpecificOutput"]
        finally:
            os.chdir(original_dir)

    def test_bash_rewritten(self, hook_script: Path, tmp_path: Path):
        """Allowlisted Bash command in automation context is rewritten to tee+tail."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            self._write_config(tmp_path, enabled=True)
            result = self._run(
                hook_script,
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "pytest scripts/tests/"},
                    "permission_mode": "bypassPermissions",
                },
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            hso = output["hookSpecificOutput"]
            assert hso["permissionDecision"] == "allow"
            assert "updatedInput" in hso
            new_cmd = hso["updatedInput"]["command"]
            assert ".loops/tmp/scratch/" in new_cmd
            assert "tail -20" in new_cmd
            assert "pytest scripts/tests/" in new_cmd
            assert "additionalContext" in hso
            assert ".loops/tmp/scratch/" in hso["additionalContext"]
        finally:
            os.chdir(original_dir)

    def test_bash_non_allowlist_allow(self, hook_script: Path, tmp_path: Path):
        """Non-allowlisted Bash command (e.g. git status) is allowed unchanged."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            self._write_config(tmp_path, enabled=True)
            result = self._run(
                hook_script,
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "git status"},
                    "permission_mode": "bypassPermissions",
                },
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
            assert "updatedInput" not in output["hookSpecificOutput"]
        finally:
            os.chdir(original_dir)

    def test_read_denied_over_threshold(self, hook_script: Path, tmp_path: Path):
        """Read of a large filtered-extension file is denied with actionable hint."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            self._write_config(tmp_path, enabled=True)
            big_file = tmp_path / "big.txt"
            big_file.write_text("line\n" * 500)
            result = self._run(
                hook_script,
                {
                    "tool_name": "Read",
                    "tool_input": {"file_path": str(big_file)},
                    "permission_mode": "bypassPermissions",
                },
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            hso = output["hookSpecificOutput"]
            assert hso["permissionDecision"] == "deny"
            reason = hso["permissionDecisionReason"]
            assert "cat" in reason
            assert ".loops/tmp/scratch/" in reason
            assert "tail" in reason
        finally:
            os.chdir(original_dir)

    def test_read_small_file_allow(self, hook_script: Path, tmp_path: Path):
        """Small file Read is allowed unchanged."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            self._write_config(tmp_path, enabled=True)
            small_file = tmp_path / "small.py"
            small_file.write_text("x = 1\n" * 10)
            result = self._run(
                hook_script,
                {
                    "tool_name": "Read",
                    "tool_input": {"file_path": str(small_file)},
                    "permission_mode": "bypassPermissions",
                },
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
        finally:
            os.chdir(original_dir)

    def test_read_unfiltered_extension_allow(self, hook_script: Path, tmp_path: Path):
        """Read of large file with non-filtered extension is allowed."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            self._write_config(tmp_path, enabled=True)
            big_file = tmp_path / "big.yaml"
            big_file.write_text("line\n" * 500)
            result = self._run(
                hook_script,
                {
                    "tool_name": "Read",
                    "tool_input": {"file_path": str(big_file)},
                    "permission_mode": "bypassPermissions",
                },
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
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


class TestContextHandoffSentinel:
    """Test context-handoff-sentinel.sh Stop hook file operations (BUG-1377 Option G)."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to context-handoff-sentinel.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/context-handoff-sentinel.sh"

    def test_sentinel_written_above_threshold(self, hook_script: Path, tmp_path: Path) -> None:
        """Sentinel file is written when estimated_tokens >= sentinel_threshold."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".ll").mkdir(exist_ok=True)

            # Write state with high usage (75% of 200000 = 150000 tokens)
            state = {
                "estimated_tokens": 150000,
                "result_token_count": 0,
                "handoff_complete": False,
                "context_limit": 200000,
            }
            (tmp_path / ".ll" / "ll-context-state.json").write_text(json.dumps(state))

            # Minimal ll-config.json for ll_resolve_config / ll_feature_enabled
            (tmp_path / ".ll").mkdir(exist_ok=True)
            (tmp_path / ".ll" / "ll-config.json").write_text(
                json.dumps({"context_monitor": {"enabled": True, "sentinel_threshold": 50}})
            )

            result = subprocess.run(
                [str(hook_script)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            assert result.returncode == 0
            sentinel_file = tmp_path / ".ll" / "ll-context-handoff-needed"
            assert sentinel_file.exists(), "Sentinel not written despite high usage"
            data = json.loads(sentinel_file.read_text())
            assert data["usage_percent"] >= 50
            assert data["token_count"] == 150000

        finally:
            os.chdir(original_dir)

    def test_sentinel_not_written_below_threshold(self, hook_script: Path, tmp_path: Path) -> None:
        """Sentinel file is NOT written when token usage is below threshold."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".ll").mkdir(exist_ok=True)

            # Write state with low usage (20% of 200000 = 40000 tokens)
            state = {
                "estimated_tokens": 40000,
                "result_token_count": 0,
                "handoff_complete": False,
                "context_limit": 200000,
            }
            (tmp_path / ".ll" / "ll-context-state.json").write_text(json.dumps(state))
            (tmp_path / ".ll" / "ll-config.json").write_text(
                json.dumps({"context_monitor": {"enabled": True, "sentinel_threshold": 50}})
            )

            subprocess.run(
                [str(hook_script)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            sentinel_file = tmp_path / ".ll" / "ll-context-handoff-needed"
            assert not sentinel_file.exists(), "Sentinel written despite low usage"

        finally:
            os.chdir(original_dir)

    def test_sentinel_not_written_when_handoff_complete(
        self, hook_script: Path, tmp_path: Path
    ) -> None:
        """Sentinel is skipped when handoff_complete=true (session already handed off)."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".ll").mkdir(exist_ok=True)

            state = {
                "estimated_tokens": 180000,
                "result_token_count": 0,
                "handoff_complete": True,  # already handed off
                "context_limit": 200000,
            }
            (tmp_path / ".ll" / "ll-context-state.json").write_text(json.dumps(state))
            (tmp_path / ".ll" / "ll-config.json").write_text(
                json.dumps({"context_monitor": {"enabled": True, "sentinel_threshold": 50}})
            )

            subprocess.run(
                [str(hook_script)],
                input="{}",
                capture_output=True,
                text=True,
                timeout=10,
            )

            sentinel_file = tmp_path / ".ll" / "ll-context-handoff-needed"
            assert not sentinel_file.exists(), "Sentinel must not be written after handoff_complete"

        finally:
            os.chdir(original_dir)

    def test_sentinel_survives_session_cleanup(self, tmp_path: Path) -> None:
        """Sentinel file is NOT deleted by session-cleanup.sh (intentionally excluded)."""
        cleanup_script = Path(__file__).parent.parent.parent / "hooks/scripts/session-cleanup.sh"
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".ll").mkdir(exist_ok=True)

            # Write sentinel and state files
            sentinel_file = tmp_path / ".ll" / "ll-context-handoff-needed"
            sentinel_file.write_text('{"usage_percent": 70}')
            (tmp_path / ".ll" / "ll-context-state.json").write_text('{"estimated_tokens": 0}')

            subprocess.run(
                [str(cleanup_script)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # sentinel must survive; state file must be deleted by cleanup
            assert sentinel_file.exists(), "Sentinel was incorrectly deleted by session-cleanup.sh"
            assert not (tmp_path / ".ll" / "ll-context-state.json").exists(), (
                "session-cleanup.sh should delete ll-context-state.json"
            )

        finally:
            os.chdir(original_dir)

    def test_result_token_count_preferred_over_estimated(
        self, hook_script: Path, tmp_path: Path
    ) -> None:
        """result_token_count (accurate) is preferred over estimated_tokens (heuristic)."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".ll").mkdir(exist_ok=True)

            # estimated_tokens is low (heuristic underestimate) but result_token_count is high
            state = {
                "estimated_tokens": 30000,  # below threshold — would not trigger
                "result_token_count": 160000,  # accurate — should trigger at 80%
                "handoff_complete": False,
                "context_limit": 200000,
            }
            (tmp_path / ".ll" / "ll-context-state.json").write_text(json.dumps(state))
            (tmp_path / ".ll" / "ll-config.json").write_text(
                json.dumps({"context_monitor": {"enabled": True, "sentinel_threshold": 50}})
            )

            subprocess.run(
                [str(hook_script)],
                input="{}",
                capture_output=True,
                text=True,
                timeout=10,
            )

            sentinel_file = tmp_path / ".ll" / "ll-context-handoff-needed"
            assert sentinel_file.exists(), (
                "Sentinel must be written when result_token_count is above threshold "
                "even if estimated_tokens is below"
            )
            data = json.loads(sentinel_file.read_text())
            assert data["token_count"] == 160000

        finally:
            os.chdir(original_dir)


class TestSessionCleanupWorktrees:
    """Per-worktree liveness-check in session-cleanup.sh (BUG-1683)."""

    @pytest.fixture
    def cleanup_script(self) -> Path:
        return Path(__file__).parent.parent.parent / "hooks/scripts/session-cleanup.sh"

    def _make_worktree(self, tmp_path: Path) -> Path:
        """Init a git repo in tmp_path and add one worker worktree under .worktrees/."""
        git = ["git", "-c", "user.email=t@t.com", "-c", "user.name=T"]
        subprocess.run([*git, "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            [*git, "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        worker_dir = tmp_path / ".worktrees" / "worker-test-20260524"
        subprocess.run(
            ["git", "worktree", "add", "-b", "parallel/test-20260524", str(worker_dir)],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        return worker_dir

    def test_session_cleanup_skips_worktree_with_live_pid_marker(
        self, cleanup_script: Path, tmp_path: Path
    ) -> None:
        """Worktree with live PID marker must not be removed by session-cleanup.sh."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".ll").mkdir(exist_ok=True)
            worker_dir = self._make_worktree(tmp_path)
            (worker_dir / f".ll-session-{os.getpid()}").write_text("")

            subprocess.run([str(cleanup_script)], capture_output=True, text=True, timeout=15)

            assert worker_dir.exists(), (
                "Worktree with live PID marker should not be removed by session-cleanup.sh"
            )
        finally:
            os.chdir(original_dir)

    def test_session_cleanup_removes_worktree_with_dead_pid_marker(
        self, cleanup_script: Path, tmp_path: Path
    ) -> None:
        """Worktree with dead PID marker must be removed by session-cleanup.sh."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".ll").mkdir(exist_ok=True)
            worker_dir = self._make_worktree(tmp_path)
            (worker_dir / ".ll-session-99999").write_text("")

            subprocess.run([str(cleanup_script)], capture_output=True, text=True, timeout=15)

            assert not worker_dir.exists(), (
                "Worktree with dead PID marker should be removed by session-cleanup.sh"
            )
        finally:
            os.chdir(original_dir)

    def test_session_cleanup_removes_worktree_with_no_marker(
        self, cleanup_script: Path, tmp_path: Path
    ) -> None:
        """Orphaned worktree (no .ll-session-* marker) must be removed by session-cleanup.sh."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / ".ll").mkdir(exist_ok=True)
            worker_dir = self._make_worktree(tmp_path)
            # No marker — simulates an orphan from an interrupted run

            subprocess.run([str(cleanup_script)], capture_output=True, text=True, timeout=15)

            assert not worker_dir.exists(), (
                "Orphaned worktree with no session marker should be removed by session-cleanup.sh"
            )
        finally:
            os.chdir(original_dir)


class TestIssueAutoCommitHook:
    """ENH-1844: issue-auto-commit.sh PostToolUse hook."""

    @pytest.fixture
    def hook_script(self) -> Path:
        return Path(__file__).parent.parent.parent / "hooks/scripts/issue-auto-commit.sh"

    def _make_input(self, file_path: str, tool_name: str = "Write") -> str:
        return json.dumps({"tool_name": tool_name, "tool_input": {"file_path": file_path}})

    def _init_git_repo(self, path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(path),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(path),
            check=True,
            capture_output=True,
        )

    def test_non_issue_file_exits_0(self, hook_script: Path, tmp_path: Path) -> None:
        """Non-issue file path exits 0 immediately without touching git."""
        import os

        self._init_git_repo(tmp_path)
        plain_file = tmp_path / "README.md"
        plain_file.write_text("hello")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(plain_file)),
                capture_output=True,
                text=True,
                timeout=10,
            )
        finally:
            os.chdir(original_dir)

        assert result.returncode == 0
        git_log = subprocess.run(
            ["git", "log", "--oneline"], cwd=str(tmp_path), capture_output=True, text=True
        )
        assert git_log.stdout.strip() == "", "Expected no commits for non-issue file"

    def test_disabled_exits_0_without_git_commit(self, hook_script: Path, tmp_path: Path) -> None:
        """auto_commit absent (default false) → hook exits 0 without committing."""
        import os

        self._init_git_repo(tmp_path)
        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P3-ENH-1844-test.md"
        issue_file.write_text("---\nstatus: open\n---\n")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(issue_file)),
                capture_output=True,
                text=True,
                timeout=10,
            )
        finally:
            os.chdir(original_dir)

        assert result.returncode == 0
        git_log = subprocess.run(
            ["git", "log", "--oneline"], cwd=str(tmp_path), capture_output=True, text=True
        )
        assert git_log.stdout.strip() == "", "Expected no commits when auto_commit disabled"

    def test_enabled_clean_tree_commits_issue_file(self, hook_script: Path, tmp_path: Path) -> None:
        """auto_commit: true + clean working tree → git add + git commit run."""
        import os

        self._init_git_repo(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        config_file = ll_dir / "ll-config.json"
        config_file.write_text(json.dumps({"issues": {"auto_commit": True}}))

        # Seed the repo with an initial commit so git commit works
        subprocess.run(
            ["git", "add", str(config_file)], cwd=str(tmp_path), check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )

        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P3-ENH-1844-test.md"
        issue_file.write_text("---\nstatus: open\n---\n")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(issue_file)),
                capture_output=True,
                text=True,
                timeout=10,
            )
        finally:
            os.chdir(original_dir)

        assert result.returncode == 0, f"Hook failed: {result.stderr}"
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert "chore(issues): capture ENH-1844 test" in git_log.stdout, (
            f"Expected auto-commit message, got: {git_log.stdout!r}"
        )

    def test_custom_prefix_in_commit_message(self, hook_script: Path, tmp_path: Path) -> None:
        """Custom auto_commit_prefix appears in commit message."""
        import os

        self._init_git_repo(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        config_file = ll_dir / "ll-config.json"
        config_file.write_text(
            json.dumps({"issues": {"auto_commit": True, "auto_commit_prefix": "fix(issues)"}})
        )
        subprocess.run(
            ["git", "add", str(config_file)], cwd=str(tmp_path), check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )

        issues_dir = tmp_path / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P2-BUG-999-my-bug.md"
        issue_file.write_text("---\nstatus: open\n---\n")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(issue_file)),
                capture_output=True,
                text=True,
                timeout=10,
            )
        finally:
            os.chdir(original_dir)

        assert result.returncode == 0, f"Hook failed: {result.stderr}"
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert "fix(issues): capture BUG-999 my-bug" in git_log.stdout, (
            f"Expected custom prefix in commit, got: {git_log.stdout!r}"
        )

    def test_dirty_tree_skips_commit_prints_warning(
        self, hook_script: Path, tmp_path: Path
    ) -> None:
        """Dirty working tree → hook skips commit and prints warning to stderr."""
        import os

        self._init_git_repo(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        config_file = ll_dir / "ll-config.json"
        config_file.write_text(json.dumps({"issues": {"auto_commit": True}}))
        subprocess.run(
            ["git", "add", str(config_file)], cwd=str(tmp_path), check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )

        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P3-ENH-1844-test.md"
        issue_file.write_text("---\nstatus: open\n---\n")

        # Create a dirty file (other staged/unstaged change)
        dirty_file = tmp_path / "dirty.txt"
        dirty_file.write_text("dirty")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(issue_file)),
                capture_output=True,
                text=True,
                timeout=10,
            )
        finally:
            os.chdir(original_dir)

        assert result.returncode == 0, f"Hook should exit 0 even on dirty tree: {result.stderr}"
        assert "skipping commit" in result.stderr, (
            f"Expected warning message in stderr, got: {result.stderr!r}"
        )
        git_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        commit_count = len(git_log.stdout.strip().splitlines())
        assert commit_count == 1, f"Expected only init commit, got {commit_count} commits"

    def test_edit_tool_uses_update_verb(self, hook_script: Path, tmp_path: Path) -> None:
        """Edit tool calls produce 'update' verb in commit message."""
        import os

        self._init_git_repo(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        config_file = ll_dir / "ll-config.json"
        config_file.write_text(json.dumps({"issues": {"auto_commit": True}}))

        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P3-ENH-1844-test.md"
        issue_file.write_text("---\nstatus: open\n---\n")

        # Stage and commit initial state
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path),
            check=True,
            capture_output=True,
        )

        # Modify the file so Edit can re-commit it
        issue_file.write_text("---\nstatus: in_progress\n---\n")

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = subprocess.run(
                [str(hook_script)],
                input=self._make_input(str(issue_file), tool_name="Edit"),
                capture_output=True,
                text=True,
                timeout=10,
            )
        finally:
            os.chdir(original_dir)

        assert result.returncode == 0, f"Hook failed: {result.stderr}"
        git_log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert "chore(issues): update ENH-1844 test" in git_log.stdout, (
            f"Expected 'update' verb for Edit, got: {git_log.stdout!r}"
        )


class TestSessionEndSweep:
    """Test session-end.sh adapter exits cleanly with no project config (FEAT-1680)."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to the Claude Code session-end adapter."""
        return Path(__file__).parent.parent.parent / "hooks/adapters/claude-code/session-end.sh"

    def test_adapter_exits_zero(self, hook_script: Path, tmp_path: Path) -> None:
        """session-end.sh exits 0 when run with minimal input and no project config."""
        result = subprocess.run(
            [str(hook_script)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0, (
            f"session-end.sh exited {result.returncode}. stderr: {result.stderr!r}"
        )
