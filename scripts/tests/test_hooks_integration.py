"""Integration tests for hooks system robustness.

Tests concurrent access, special character handling, and race conditions.
"""

import itertools
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# ENH-2529: consolidate per-test temp dirs under one module-scoped parent to cut
# macOS launchservicesd/mds re-indexing churn during full-suite runs. Each test
# still gets a fresh, unique directory; only the parent dir consolidates.
_TMP_COUNTER = itertools.count()


@pytest.fixture(scope="module")
def _module_tmp_parent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One temp parent per module instead of one top-level dir per test."""
    return tmp_path_factory.mktemp("hooks_integration")


@pytest.fixture
def tmp_path(_module_tmp_parent: Path, request: pytest.FixtureRequest) -> Path:
    """Override built-in tmp_path: unique fresh subdir of the module parent."""
    name = re.sub(r"\W", "_", request.node.name)[:30]
    path = _module_tmp_parent / f"{name}_{next(_TMP_COUNTER)}"
    path.mkdir()
    return path


class TestContextMonitor:
    """Test context-monitor.sh under concurrent access."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to context-monitor.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/context-monitor.sh"

    @pytest.fixture
    def test_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> Path:
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

    def test_concurrent_updates(self, hook_script: Path, test_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Simulate concurrent PostToolUse hooks updating state file."""
        # Change to temp directory for test

        monkeypatch.chdir(tmp_path)

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

        # Run 4 hooks concurrently
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(run_hook, "Read") for _ in range(4)]
            results = [f.result() for f in as_completed(futures)]

        # Verify all completed
        assert len(results) == 4

        # Read final state
        state_file = tmp_path / "ll-context-state.json"
        assert state_file.exists(), "State file should exist"

        state = json.loads(state_file.read_text())

        # Verify state is valid JSON
        assert isinstance(state, dict)
        assert "estimated_tokens" in state
        assert "tool_calls" in state

        # Verify no token count loss (should be 4 calls * ~1000 tokens each)
        # Allow some variance due to estimation
        assert state["tool_calls"] == 4, f"Expected 4 tool calls, got {state['tool_calls']}"
        assert state["estimated_tokens"] > 2000, "Token count seems too low"


    def test_transcript_baseline_used_when_jsonl_present(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Test that JSONL transcript token counts are used as the baseline."""

        monkeypatch.chdir(tmp_path)

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


    def test_transcript_baseline_falls_back_when_absent(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Test that pure heuristics are used when transcript_path is absent."""

        monkeypatch.chdir(tmp_path)

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


    def test_state_file_corruption_resistance(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Test that atomic writes prevent state file corruption."""

        monkeypatch.chdir(tmp_path)

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


    def test_env_var_overrides_config_threshold(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """LL_HANDOFF_THRESHOLD env var overrides config auto_handoff_threshold."""
        import os

        monkeypatch.chdir(tmp_path)

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


    def test_env_var_overrides_context_limit(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """LL_CONTEXT_LIMIT env var overrides config context_limit_estimate."""
        import os

        monkeypatch.chdir(tmp_path)

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


    def test_known_model_auto_detection(self, hook_script: Path, test_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Known model in JSONL triggers auto-detection of 200K context limit.

        Uses baseline of 180K tokens. At 200K limit: 90% → triggers handoff (exit 2).
        At 1M limit: 18% → no trigger (exit 0). The exit code proves which limit was used.
        """

        monkeypatch.chdir(tmp_path)

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


    def test_1m_model_suffix_auto_detection(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """[1m]-suffixed model triggers auto-detection of 1M context limit.

        Uses baseline of 700K tokens. At 1M limit: 70% → no trigger (exit 0).
        At 200K limit: 350% → would trigger (exit 2). Exit code proves 1M was used.
        State file confirms context_limit == 1000000.
        """
        import json as _json

        monkeypatch.chdir(tmp_path)

        config_link = tmp_path / ".ll" / "ll-config.json"
        config_link.parent.mkdir(exist_ok=True)
        config_link.write_text(test_config.read_text())

        transcript_file = tmp_path / "transcript.jsonl"
        assistant_entry = {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-8[1m]",
                "usage": {
                    "input_tokens": 700000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 0,
                },
            },
        }
        transcript_file.write_text(_json.dumps(assistant_entry) + "\n")

        input_data = {
            "tool_name": "Read",
            "tool_response": {"content": "x\n"},
            "transcript_path": str(transcript_file),
        }
        result = subprocess.run(
            [str(hook_script)],
            input=_json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=6,
        )

        # exit 0 = no handoff. 700K / 1M = 70% < 80% threshold.
        # If denominator were 200K, 700K / 200K = 350% → would trigger (exit 2).
        assert result.returncode == 0, (
            f"Expected exit 0 (auto-detected 1M limit), got {result.returncode}. "
            f"stderr: {result.stderr}"
        )
        # Confirm context_limit == 1000000 in state file
        # test_config fixture sets state_file to tmp_path / "ll-context-state.json"
        state_file = tmp_path / "ll-context-state.json"
        assert state_file.exists(), "State file should be written by hook"
        state = _json.loads(state_file.read_text())
        assert state.get("context_limit") == 1000000, (
            f"Expected context_limit=1000000 in state, got {state.get('context_limit')}. "
            f"Full state: {state}"
        )


    def test_unknown_model_config_fallback(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Unknown model falls back to context_limit_estimate from config.

        Uses baseline of 45K tokens with config limit 50K. At 50K: 90% → triggers (exit 2).
        At 200K auto-detected: 22.5% → no trigger (exit 0). Exit code proves fallback was used.
        """

        monkeypatch.chdir(tmp_path)

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


    def test_reminder_rate_limited_second_call(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Second call above threshold within 60s exits 0 silently (rate-limited).

        First call should produce exit 2 with stderr. Second call within 60s should
        produce exit 0 with no stderr — the cooldown suppresses the reminder.
        """
        import os

        monkeypatch.chdir(tmp_path)

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


    def test_state_contains_last_reminder_at_after_exit2(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """State file contains last_reminder_at timestamp after exit 2 fires."""
        import os

        monkeypatch.chdir(tmp_path)

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


    def test_fresh_state_with_handoff_file_sets_handoff_complete_false(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Fresh state initializes handoff_complete=false even when ll-continue-prompt.md exists.

        The continue-prompt file persists across sessions and must NOT suppress reminders in a
        new session. The post-threshold mtime check in main() handles marking complete mid-session.
        """

        monkeypatch.chdir(tmp_path)

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


    def test_fresh_state_without_handoff_file_sets_handoff_complete_false(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Fresh state initializes handoff_complete=false when ll-continue-prompt.md is absent."""

        monkeypatch.chdir(tmp_path)

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


    def test_reminder_fires_again_after_cooldown_expires(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Reminder fires again (exit 2) when last_reminder_at is more than 60s ago."""
        import os
        from datetime import UTC, datetime, timedelta

        monkeypatch.chdir(tmp_path)

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


    def test_detected_model_cached_in_state(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Detected model from transcript should be cached in state file."""

        monkeypatch.chdir(tmp_path)

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


    def test_large_tool_response_completes_within_timeout(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Hook should complete within 5s even with large tool_response and transcript."""
        import time

        monkeypatch.chdir(tmp_path)

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


    def test_result_token_count_used_when_present(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """When result_token_count > 0 in state, context-monitor uses it instead of heuristics."""

        monkeypatch.chdir(tmp_path)

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


    def test_result_token_count_zero_falls_back_to_heuristics(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """When result_token_count is 0 in state, context-monitor falls back to heuristics."""

        monkeypatch.chdir(tmp_path)

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


    def test_1m_model_limit_resolution(self, hook_script: Path, test_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Transcript baseline exceeding 200k auto-upgrades context limit to 1M.

        Uses baseline of 250K tokens on claude-opus-4-8 (maps to 200k by model name).
        250k > 200k triggers auto-upgrade to 1M. 250k / 1M = 25% -> no handoff (exit 0).
        Verifies state context_limit is written as 1000000.
        """

        monkeypatch.chdir(tmp_path)

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


    def test_sentinel_1000000_honored_as_explicit_override(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Explicit context_limit_estimate: 1000000 in config is honored (not treated as sentinel).

        Unknown model with 900k baseline and config limit 1000000. 900k / 1M = 90% -> trigger (exit 2).
        If 1000000 were still ignored: limit falls to 200k, 900k clamped -> exit 0.
        """

        monkeypatch.chdir(tmp_path)

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


    def test_impossible_baseline_clamped(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Impossible token count (> 1.05x limit) is clamped to prior estimate, no spurious trigger.

        Pre-write state with result_token_count=1517046 (> 200k limit x 1.05 = 210k).
        Clamp falls back to CURRENT_TOKENS (1000) -> exit 0. Without clamp: 758% -> exit 2.
        """

        monkeypatch.chdir(tmp_path)

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


    def test_transcript_baseline_refreshed_on_new_turn(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Baseline re-reads JSONL when mtime advances (new turn); cached otherwise.

        Regression test for BUG-2145: baseline was read once and cached for the entire
        session, causing estimates to diverge by 70K+ tokens on long sessions.
        """
        import os

        monkeypatch.chdir(tmp_path)

        config_link = tmp_path / ".ll" / "ll-config.json"
        config_link.parent.mkdir(exist_ok=True)
        config_link.write_text(test_config.read_text())

        transcript_file = tmp_path / "transcript.jsonl"
        state_file = tmp_path / "ll-context-state.json"

        def write_transcript(input_tokens: int) -> None:
            entry = {
                "type": "assistant",
                "message": {
                    "usage": {
                        "input_tokens": input_tokens,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "output_tokens": 0,
                    }
                },
            }
            transcript_file.write_text(json.dumps(entry) + "\n")

        def run_hook() -> dict:
            input_data = {
                "tool_name": "Read",
                "tool_response": {"content": "output\n"},
                "transcript_path": str(transcript_file),
            }
            result = subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=6,
            )
            assert result.returncode in (0, 2), f"Unexpected exit code: {result.returncode}"
            return json.loads(state_file.read_text())

        # Turn 1: initial JSONL with 50K tokens
        write_transcript(50000)
        state = run_hook()
        assert state["transcript_baseline_tokens"] == 50000, (
            f"Expected 50000 baseline on first call, got {state['transcript_baseline_tokens']}"
        )
        mtime_after_turn1 = state.get("last_baseline_mtime", "0")
        assert mtime_after_turn1 != "0", "last_baseline_mtime should be set after first read"

        # Same turn: run hook again without touching the transcript (mtime unchanged)
        # Baseline must be served from cache, not re-read
        state2 = run_hook()
        assert state2["transcript_baseline_tokens"] == 50000, (
            f"Baseline should be cached mid-turn, got {state2['transcript_baseline_tokens']}"
        )
        assert state2.get("last_baseline_mtime") == mtime_after_turn1, (
            "last_baseline_mtime should not change when mtime is unchanged"
        )

        # New turn: update the transcript, then force its mtime strictly forward
        # via os.utime so the hook treats this as a new turn. Avoids a real ~1s
        # sleep just to cross the filesystem mtime-resolution boundary.
        write_transcript(120000)
        bumped = os.stat(transcript_file).st_mtime + 10
        os.utime(transcript_file, (bumped, bumped))

        state3 = run_hook()
        assert state3["transcript_baseline_tokens"] == 120000, (
            f"Expected refreshed baseline 120000 on new turn, got {state3['transcript_baseline_tokens']}"
        )
        mtime_after_turn2 = state3.get("last_baseline_mtime", "0")
        assert mtime_after_turn2 != mtime_after_turn1, (
            "last_baseline_mtime should advance after new turn"
        )


    def test_system_prompt_baseline_not_added_when_transcript_available(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Regression test for BUG-2146: SYSTEM_PROMPT_BASELINE must not be added when
        TRANSCRIPT_BASELINE > 0.

        The transcript already includes the system prompt via cache_read_input_tokens;
        adding SYSTEM_PROMPT_BASELINE (10000) on top double-counts it on the first call.
        """

        monkeypatch.chdir(tmp_path)

        config_link = tmp_path / ".ll" / "ll-config.json"
        config_link.parent.mkdir(exist_ok=True)
        config_link.write_text(test_config.read_text())

        transcript_baseline = 50000
        transcript_file = tmp_path / "transcript.jsonl"
        assistant_entry = {
            "type": "assistant",
            "message": {
                "usage": {
                    "input_tokens": transcript_baseline,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 0,
                }
            },
        }
        transcript_file.write_text(json.dumps(assistant_entry) + "\n")

        # First tool call of the session (CURRENT_CALLS == 0)
        input_data = {
            "tool_name": "Read",
            "tool_response": {"content": "x"},
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

        assert state["transcript_baseline_tokens"] == transcript_baseline

        # SYSTEM_PROMPT_BASELINE is 10000. When transcript is present, it must NOT be
        # added. The estimate should be baseline + small per-turn amounts, not +10K.
        # A threshold of 5000 above baseline safely excludes the 10K overcounting.
        assert state["estimated_tokens"] < transcript_baseline + 5000, (
            f"SYSTEM_PROMPT_BASELINE (10000) was incorrectly added on first call "
            f"when transcript baseline was already available. "
            f"Got estimated_tokens={state['estimated_tokens']}, "
            f"expected < {transcript_baseline + 5000}"
        )



class TestUserPromptCheck:
    """Test user-prompt-check.sh special character handling."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to user-prompt-check.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/user-prompt-check.sh"

    @pytest.fixture
    def test_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> Path:
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
    , monkeypatch: pytest.MonkeyPatch):
        """Verify special characters don't cause shell injection or template corruption."""

        monkeypatch.chdir(tmp_path)

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
    , monkeypatch: pytest.MonkeyPatch):
        """Regression test: prompt optimization must not silently fail when CLAUDE_PLUGIN_ROOT is set.

        The bug: HOOK_PROMPT_FILE used CLAUDE_PLUGIN_ROOT which resolves to
        $CLAUDE_PLUGIN_ROOT/prompts/ — a path that doesn't exist.
        Fix: always use SCRIPT_DIR/../prompts/ instead.
        """
        import os

        monkeypatch.chdir(tmp_path)

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
    , monkeypatch: pytest.MonkeyPatch):
        """Session log entry is appended even when transcript path contains single quotes.

        Paths with single quotes used to break shell interpolation into the Python
        snippet; passing via env vars keeps them safe. The hook detects a Write
        marking an issue file `status: done` in frontmatter and appends a session
        log entry.
        """

        # Issue file lives in its category dir (frontmatter status flips in place
        # under the new model — no move to completed/).
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P3-BUG-870-test.md"
        issue_file.write_text(
            "---\nstatus: done\ndiscovered_date: 2026-01-01\n---\n# Test\n\n## Session Log\n"
        )

        transcript_dir = tmp_path / "transcripts"
        transcript_dir.mkdir(exist_ok=True)
        transcript_file = transcript_dir / transcript_name
        transcript_file.write_text("")

        monkeypatch.chdir(tmp_path)

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

    def test_hook_exits_zero_when_ll_issues_fails(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Hook exits 0 even when ll-issues exits non-zero.

        The extract-from-completed call added in ENH-2152 runs in a background
        subshell and must not affect the hook exit code even when ll-issues fails.
        """
        import os
        import stat

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        issue_file = bugs_dir / "P3-BUG-999-test.md"
        issue_file.write_text(
            "---\nstatus: done\ndiscovered_date: 2026-01-01\n---\n# Test\n\n## Session Log\n"
        )

        transcript_dir = tmp_path / "transcripts"
        transcript_dir.mkdir(exist_ok=True)
        transcript_file = transcript_dir / "session.jsonl"
        transcript_file.write_text("")

        # Stub ll-issues that exits immediately with code 1 (simulates unavailability)
        fake_bin = tmp_path / "fake_bin"
        fake_bin.mkdir()
        fake_ll_issues = fake_bin / "ll-issues"
        fake_ll_issues.write_text("#!/bin/bash\nexit 1\n")
        fake_ll_issues.chmod(fake_ll_issues.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)

        env = dict(os.environ)
        env["PATH"] = str(fake_bin) + ":" + os.environ.get("PATH", "")
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=self._make_input(str(issue_file), str(transcript_file)),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        assert result.returncode == 0, (
            f"Hook exited non-zero when ll-issues fails: {result.returncode}\n{result.stderr}"
        )


class TestDuplicateIssueId:
    """Test check-duplicate-issue-id.sh race condition handling."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to check-duplicate-issue-id.sh."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/check-duplicate-issue-id.sh"

    def test_concurrent_duplicate_detection(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test duplicate check with concurrent Write attempts."""

        monkeypatch.chdir(tmp_path)

        # Create .issues directory
        issues_dir = tmp_path / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)

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
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(attempt_create, "001", i) for i in range(4)]
            results = [f.result() for f in as_completed(futures)]

        # All should be denied (duplicate of existing)
        denied_count = sum(1 for r in results if "deny" in r.stdout.lower())
        assert denied_count >= 3, f"Expected at least 3 denials, got {denied_count}"

        # Try to create new issue BUG-002 concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(attempt_create, "002", i) for i in range(3)]
            results = [f.result() for f in as_completed(futures)]

        # At least one should be allowed (first one)
        # Some may be allowed if they run before the file is created
        allowed_count = sum(1 for r in results if "allow" in r.stdout.lower())
        assert allowed_count >= 1, "At least one should be allowed"


    def test_config_fallback_to_root_ll_config(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that script reads issues.base_dir from ll-config.json when .claude/ config absent."""

        monkeypatch.chdir(tmp_path)

        # Config at root ll-config.json only (no .ll/ll-config.json)
        custom_base = "myissues"
        config = {"issues": {"base_dir": custom_base}}
        (tmp_path / "ll-config.json").write_text(json.dumps(config))

        # Create custom issues directory
        issues_dir = tmp_path / custom_base / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)

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


    def test_null_byte_in_filename(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that null-terminated find handles unusual filenames correctly."""

        monkeypatch.chdir(tmp_path)

        # Create .issues directory with various filenames
        issues_dir = tmp_path / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)

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


    def test_cross_type_integer_collision(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that write is denied when same integer is used with a different type prefix."""

        monkeypatch.chdir(tmp_path)

        # Create .issues directory with bugs and features subdirs
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        features_dir = tmp_path / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)

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

    def test_unique_issue_not_deleted(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A newly written file with a unique integer ID is left intact."""

        monkeypatch.chdir(tmp_path)

        issues_dir = tmp_path / ".issues" / "bugs"
        issues_dir.mkdir(parents=True, exist_ok=True)

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

    def test_duplicate_file_deleted_and_exit2(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A newly written file whose integer ID already exists is deleted; hook exits 2."""

        monkeypatch.chdir(tmp_path)

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)

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

    def test_cross_type_duplicate_deleted(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A newly written file whose integer collides with a different-type file is deleted."""

        monkeypatch.chdir(tmp_path)

        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True, exist_ok=True)
        features_dir = tmp_path / ".issues" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)

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

    def test_non_issue_file_ignored(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Files outside the issues directory are ignored without error."""

        monkeypatch.chdir(tmp_path)

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

    def test_non_write_tool_ignored(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Non-Write tool events (e.g., Bash) are ignored immediately."""

        monkeypatch.chdir(tmp_path)

        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hi"}}),
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0, f"Expected exit 0 for non-Write tool: {result.stderr}"


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

    def test_warns_sync_without_github(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Warns when sync.enabled is true but sync.github is empty."""

        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
        (config_dir / "ll-config.json").write_text(json.dumps({"sync": {"enabled": True}}))

        result = subprocess.run(
            [str(hook_script)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert "sync.enabled is true but sync.github is not configured" in result.stderr

    def test_warns_documents_without_categories(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Warns when documents.enabled is true but no categories."""

        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
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

    def test_no_warnings_when_properly_configured(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """No warnings when enabled features have required sub-configuration."""

        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)

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

    def test_no_warnings_when_features_disabled(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """No warnings when features are disabled."""

        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
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

    def test_warns_design_tokens_enabled_without_path(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Warns when design_tokens.enabled is true but the path does not exist."""

        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(exist_ok=True)
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


class TestPrecompactState:
    """Test precompact adapter (Python handler via Claude Code wrapper)."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to the Claude Code precompact adapter (FEAT-1455)."""
        return Path(__file__).parent.parent.parent / "hooks/adapters/claude-code/precompact.sh"

    def test_atomic_write_with_missing_directory(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test that state is written even if thoughts directory doesn't exist."""

        monkeypatch.chdir(tmp_path)

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


    def test_concurrent_precompact_writes(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Test concurrent precompact hook invocations."""

        monkeypatch.chdir(tmp_path)

        def run_hook(i: int) -> subprocess.CompletedProcess:
            input_data = {"transcript_path": f"/tmp/transcript-{i}.jsonl"}
            return subprocess.run(
                [str(hook_script)],
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                timeout=5,
            )

        # Run 4 hooks concurrently
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(run_hook, i) for i in range(4)]
            results = [f.result() for f in as_completed(futures)]

        # All should succeed with exit 2 (PreCompact: non-blocking, shows stderr)
        assert all(r.returncode == 2 for r in results)

        # State file should have valid JSON (last write wins)
        state_file = tmp_path / ".ll" / "ll-precompact-state.json"
        state = json.loads(state_file.read_text())
        assert state["preserved"] is True



class TestPrecompactHandoff:
    """Integration tests for precompact-handoff.sh shell adapter.

    Exercises the shell → dispatcher → pre_compact_handoff.handle() path.
    Unit-level handler logic is covered by test_pre_compact_handoff.py.
    """

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to the Claude Code precompact-handoff adapter."""
        return (
            Path(__file__).parent.parent.parent / "hooks/adapters/claude-code/precompact-handoff.sh"
        )

    def test_produces_prompt_file_within_2kb(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """(a) Hook writes ll-continue-prompt.md ≤ 2KB and exits 2."""
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 2
        prompt_file = tmp_path / ".ll" / "ll-continue-prompt.md"
        assert prompt_file.exists()
        assert len(prompt_file.read_bytes()) <= 2048

    def test_priority_tier_dropping_under_size_pressure(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """(b) Output stays ≤ 2KB even with a large in-progress issues list."""
        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (ll_dir / "ll-session-events.jsonl").write_text('{"type": "tool_use"}\n' * 200)
        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 2
        prompt_file = tmp_path / ".ll" / "ll-continue-prompt.md"
        assert prompt_file.exists()
        assert len(prompt_file.read_bytes()) <= 2048

    def test_idempotency_skips_when_prompt_is_fresh(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """(c) Exit 0 (no write) when ll-continue-prompt.md mtime > compacted_at."""

        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)

        past_ts = "2000-01-01T00:00:00"
        (ll_dir / "ll-precompact-state.json").write_text(
            json.dumps({"compacted_at": past_ts, "preserved": True, "recent_plan_files": []})
        )

        prompt_file = ll_dir / "ll-continue-prompt.md"
        prompt_file.write_text("---\nsession_date: today\n---\n## Intent\n\n## Next Steps\n")

        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_schema_has_required_resume_sections(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """(d) Produced file has YAML frontmatter, ## Intent, and ## Next Steps."""
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 2
        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "session_date:" in content
        assert "## Intent" in content
        assert "## Next Steps" in content

    def test_event_log_deduplicated_file_edits(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """(e) Event log with duplicate file events → single entry in ll-continue-prompt.md."""

        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        events = [
            {
                "ts": "2026-06-17T10:00:00Z",
                "type": "file",
                "op": "Write",
                "subject": "scripts/bar.py",
                "status": "",
            },
            {
                "ts": "2026-06-17T10:01:00Z",
                "type": "file",
                "op": "Write",
                "subject": "scripts/bar.py",
                "status": "",
            },
        ]
        (ll_dir / "ll-session-events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )

        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 2
        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert content.count("scripts/bar.py") == 1

    def test_event_log_unresolved_error_in_output(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """(f) Unresolved error event → subject appears in Unresolved Errors section."""

        monkeypatch.chdir(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        events = [
            {
                "ts": "2026-06-17T10:00:00Z",
                "type": "error",
                "op": "run",
                "subject": "mypy-type-error",
                "status": "",
            },
        ]
        (ll_dir / "ll-session-events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )

        result = subprocess.run(
            [str(hook_script)],
            input=json.dumps({}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 2
        content = (tmp_path / ".ll" / "ll-continue-prompt.md").read_text(encoding="utf-8")
        assert "mypy-type-error" in content


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

    def test_disabled_noop(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """When scratch_pad.enabled is false, hook allows unchanged."""
        monkeypatch.chdir(tmp_path)
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

    def test_non_automation_noop(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """When permission_mode is not bypassPermissions, hook is a no-op."""
        monkeypatch.chdir(tmp_path)
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

    def test_bash_rewritten(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Allowlisted Bash command in automation context is rewritten to tee+tail."""
        monkeypatch.chdir(tmp_path)
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

    def test_bash_non_allowlist_allow(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Non-allowlisted Bash command (e.g. git status) is allowed unchanged."""
        monkeypatch.chdir(tmp_path)
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

    def test_read_over_threshold_allowed(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Read is never intercepted, even for a large filtered-extension file (BUG-2357).

        Denying a Read leaves the Edit/Write "file has been read" precondition
        unsatisfied, edit-locking the file for the rest of the session. The hook
        must allow all Reads; only Bash output (which is uncapped) is redirected.
        """
        monkeypatch.chdir(tmp_path)
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
        assert hso["permissionDecision"] == "allow"
        assert "updatedInput" not in hso

    def test_read_small_file_allow(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Small file Read is allowed unchanged."""
        monkeypatch.chdir(tmp_path)
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

    def test_read_unfiltered_extension_allow(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Read of large file with non-filtered extension is allowed."""
        monkeypatch.chdir(tmp_path)
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

    def test_python_dash_m_pytest_rewritten(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """`python -m pytest ...` is unwrapped to `pytest` and redirected (BUG-2407)."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path, enabled=True)
        result = self._run(
            hook_script,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "python -m pytest scripts/tests/"},
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
        assert "python -m pytest scripts/tests/" in new_cmd

    def test_python3_dash_m_mypy_rewritten(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """`python3 -m mypy ...` is unwrapped to `mypy` and redirected (BUG-2407)."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path, enabled=True)
        result = self._run(
            hook_script,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "python3 -m mypy scripts/little_loops/"},
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

    def test_python_dash_m_non_allowlisted_module_allow(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """`python -m <module not in allowlist>` is allowed unchanged."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path, enabled=True)
        result = self._run(
            hook_script,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "python -m http.server 8000"},
                "permission_mode": "bypassPermissions",
            },
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert "updatedInput" not in output["hookSpecificOutput"]


class TestScratchPadRedirectBug2420:
    """BUG-2420: don't double-wrap output-managing commands; group-wrap bare
    compound commands so one redirect captures every segment; recreate the
    scratch dir at execution time (belt-and-suspenders for the cleanup race)."""

    @pytest.fixture
    def hook_script(self) -> Path:
        return Path(__file__).parent.parent.parent / "hooks/scripts/scratch-pad-redirect.sh"

    def _write_config(self, tmp_path: Path) -> None:
        config = {
            "scratch_pad": {
                "enabled": True,
                "threshold_lines": 200,
                "automation_contexts_only": True,
                "tail_lines": 20,
                "command_allowlist": ["cat", "pytest", "mypy", "ruff", "ls", "grep", "find"],
                "file_extension_filters": [".log", ".txt"],
            }
        }
        config_dir = tmp_path / ".ll"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "ll-config.json").write_text(json.dumps(config))

    def _run(self, hook_script: Path, command: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(hook_script)],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "permission_mode": "bypassPermissions",
                }
            ),
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_already_redirecting_command_passthrough(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A command that already manages its own output (`>`) is passed through
        unchanged — appending a second redirect would bind to the trailing
        segment and misroute the real output (defect 1)."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path)
        result = self._run(hook_script, "pytest a.py > out.txt 2>&1; tail -20 out.txt")
        assert result.returncode == 0
        hso = json.loads(result.stdout)["hookSpecificOutput"]
        assert hso["permissionDecision"] == "allow"
        assert "updatedInput" not in hso, (
            "a command already managing its own output must not be re-wrapped"
        )

    def test_tee_command_passthrough(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A command piping to `tee` already manages its output → passthrough."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path)
        result = self._run(hook_script, "pytest a.py | tee out.txt")
        assert result.returncode == 0
        hso = json.loads(result.stdout)["hookSpecificOutput"]
        assert "updatedInput" not in hso

    def test_compound_command_group_wrapped(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A bare compound command (`;` between segments) is group-wrapped so a
        single redirect captures every segment, not just the trailing one."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path)
        result = self._run(hook_script, "pytest a.py; pytest b.py")
        assert result.returncode == 0
        hso = json.loads(result.stdout)["hookSpecificOutput"]
        assert "updatedInput" in hso
        new_cmd = hso["updatedInput"]["command"]
        # Subshell group wraps the whole compound command...
        assert "( pytest a.py; pytest b.py )" in new_cmd
        # ...and exactly one output redirect targets the scratch file.
        assert new_cmd.count("> .loops/tmp/scratch/") == 1

    def test_rewrite_recreates_scratch_dir(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """The rewritten command recreates the scratch dir so it exists at
        execution time even if a prior sweep removed it (defect 2 belt-and-suspenders)."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path)
        result = self._run(hook_script, "pytest scripts/tests/")
        assert result.returncode == 0
        hso = json.loads(result.stdout)["hookSpecificOutput"]
        assert "updatedInput" in hso
        assert "mkdir -p .loops/tmp/scratch" in hso["updatedInput"]["command"]

    def test_compound_command_execution_captures_all_segments(
        self, hook_script: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch):
        """Execution-level: running the rewritten compound command lands BOTH
        segments' output in the scratch file, not just the trailing one."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path)
        (tmp_path / "alpha.txt").write_text("a")
        (tmp_path / "beta.txt").write_text("b")
        result = self._run(hook_script, "ls alpha.txt; ls beta.txt")
        new_cmd = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["command"]
        # Execute the rewritten command exactly as the harness would.
        subprocess.run(
            ["bash", "-c", new_cmd], cwd=tmp_path, capture_output=True, text=True, timeout=10
        )
        scratch_files = list((tmp_path / ".loops/tmp/scratch").glob("*.txt"))
        assert scratch_files, "scratch file was not created"
        contents = scratch_files[0].read_text()
        assert "alpha.txt" in contents and "beta.txt" in contents, (
            f"both segments' output must be captured; got: {contents!r}"
        )

    def test_rewrite_preserves_nonzero_exit_code(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Execution-level: the wrapped command's FAILING exit status must survive.

        A bare `( CMD ) > file 2>&1; tail file` returns `tail`'s status (≈0),
        masking a failing pytest/mypy ("Exit code 0 but 5 failures reported").
        The rewrite must re-raise the real status while still tailing the summary.
        """
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path)
        # `grep` (allowlisted) with no match exits 1 but still writes nothing
        # to stdout; a preceding `ls` of a missing path guarantees non-zero.
        result = self._run(hook_script, "ls /definitely-nonexistent-path-xyz")
        new_cmd = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["command"]
        proc = subprocess.run(
            ["bash", "-c", new_cmd], cwd=tmp_path, capture_output=True, text=True, timeout=10
        )
        # The failing command's non-zero status must propagate, not `tail`'s 0.
        assert proc.returncode != 0, (
            f"non-zero exit of the wrapped command must be preserved; got {proc.returncode}"
        )
        # ...and the tail summary must still have been captured to scratch.
        scratch_files = list((tmp_path / ".loops/tmp/scratch").glob("*.txt"))
        assert scratch_files, "scratch file was not created"
        assert scratch_files[0].read_text().strip(), "tail summary must still be captured"

    def test_rewrite_preserves_zero_exit_code(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A succeeding wrapped command must still report exit 0 (no false failure)."""
        monkeypatch.chdir(tmp_path)
        self._write_config(tmp_path)
        (tmp_path / "present.txt").write_text("x")
        result = self._run(hook_script, "ls present.txt")
        new_cmd = json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]["command"]
        proc = subprocess.run(
            ["bash", "-c", new_cmd], cwd=tmp_path, capture_output=True, text=True, timeout=10
        )
        assert proc.returncode == 0, (
            f"a succeeding command must report exit 0; got {proc.returncode}"
        )


class TestScratchCleanupSessionEnd:
    """BUG-2420: scratch cleanup moved off the racing `Stop` hook onto a
    dedicated, correctly-wired `SessionEnd` binding."""

    REPO_ROOT = Path(__file__).parent.parent.parent

    def test_session_cleanup_no_longer_removes_scratch(self):
        """session-cleanup.sh (a Stop handler) must NOT delete the scratch dir —
        that raced auto-backgrounded commands still writing to it. Explanatory
        comments may still reference the path; only executable lines are checked."""
        text = (self.REPO_ROOT / "hooks/scripts/session-cleanup.sh").read_text()
        code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        offending = [ln for ln in code_lines if ".loops/tmp/scratch" in ln]
        assert not offending, (
            "session-cleanup.sh (Stop) must not remove the scratch dir; scratch "
            f"cleanup belongs on SessionEnd. Offending lines: {offending!r}"
        )

    def test_scratch_cleanup_script_prunes_scratch(self):
        """A dedicated scratch-cleanup.sh exists and prunes .loops/tmp/scratch.

        Must NOT be a blind `rm -rf` of the whole directory — that path is
        shared by every concurrent session in the repo, so an unconditional
        delete wipes out files other still-running sessions are actively
        writing (the cross-process collision this cleanup now guards against).
        """
        script = self.REPO_ROOT / "hooks/scripts/scratch-cleanup.sh"
        assert script.is_file(), "hooks/scripts/scratch-cleanup.sh must exist"
        text = script.read_text()
        assert ".loops/tmp/scratch" in text
        assert "kill -0" in text, "cleanup must check PID liveness before deleting a scratch file"
        code_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        offending = [ln for ln in code_lines if "rm -rf" in ln and "scratch" in ln]
        assert not offending, f"must not blindly rm -rf the shared scratch dir: {offending!r}"

    def test_scratch_cleanup_never_fails_when_dir_absent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """scratch-cleanup.sh must exit 0 even when the scratch dir is absent."""

        script = self.REPO_ROOT / "hooks/scripts/scratch-cleanup.sh"
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(script)], input="{}", capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 0

    def test_scratch_cleanup_preserves_file_without_pid_suffix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """BUG-2525: a scratch file written without the -<pid> suffix convention
        (e.g. user-typed `> .loops/tmp/scratch/test-results.txt`) must survive
        the SessionEnd sweep — the cleanup only owns files its sibling
        scratch-pad-redirect.sh created, identified by the PID-suffix shape."""

        script = self.REPO_ROOT / "hooks/scripts/scratch-cleanup.sh"
        monkeypatch.chdir(tmp_path)
        scratch = tmp_path / ".loops/tmp/scratch"
        scratch.mkdir(parents=True)
        user_file = scratch / "test-results.txt"
        user_file.write_text("data the user redirected and expected to read back")
        result = subprocess.run(
            [str(script)], input="{}", capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 0
        assert user_file.exists(), "user-typed scratch file (no -<pid> suffix) must survive cleanup"
        assert scratch.exists(), "scratch dir must survive while a user-typed file remains"

    def test_scratch_cleanup_preserves_file_owned_by_live_process(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A scratch file whose owning PID is still alive must survive cleanup.

        Regression test for the cross-process collision: a concurrent
        session's SessionEnd must not delete another live session's
        in-progress scratch-pad-redirected output.
        """
        import os

        script = self.REPO_ROOT / "hooks/scripts/scratch-cleanup.sh"
        monkeypatch.chdir(tmp_path)
        scratch = tmp_path / ".loops/tmp/scratch"
        scratch.mkdir(parents=True)
        live_pid = os.getpid()  # the test process itself is definitely alive
        owned = scratch / f"pytest-{live_pid}.txt"
        owned.write_text("still writing")
        result = subprocess.run(
            [str(script)], input="{}", capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 0
        assert owned.exists(), "file owned by a live PID must not be deleted"
        assert scratch.exists(), "dir must survive while a live-owned file remains"

    def test_scratch_cleanup_removes_file_owned_by_dead_process(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """A scratch file whose owning PID is no longer alive is pruned."""

        script = self.REPO_ROOT / "hooks/scripts/scratch-cleanup.sh"
        monkeypatch.chdir(tmp_path)
        scratch = tmp_path / ".loops/tmp/scratch"
        scratch.mkdir(parents=True)
        # PID 2**31-1 is not a valid/alive process on any real system.
        dead = scratch / "pytest-2147483647.txt"
        dead.write_text("stale")
        result = subprocess.run(
            [str(script)], input="{}", capture_output=True, text=True, timeout=5
        )
        assert result.returncode == 0
        assert not dead.exists(), "file owned by a dead PID must be pruned"
        assert not scratch.exists(), "dir should be removed once empty"

    def test_hooks_json_registers_session_end_scratch_cleanup(self):
        """hooks/hooks.json registers a SessionEnd block bound to scratch-cleanup.sh."""
        data = json.loads((self.REPO_ROOT / "hooks/hooks.json").read_text())
        assert "SessionEnd" in data["hooks"], "hooks.json is missing a SessionEnd key"
        commands = [
            hook.get("command", "")
            for group in data["hooks"]["SessionEnd"]
            for hook in group.get("hooks", [])
        ]
        assert any("scratch-cleanup.sh" in c for c in commands), (
            f"SessionEnd must bind scratch-cleanup.sh; got {commands!r}"
        )


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

    def test_sentinel_written_above_threshold(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sentinel file is written when estimated_tokens >= sentinel_threshold."""

        monkeypatch.chdir(tmp_path)
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


    def test_sentinel_not_written_below_threshold(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sentinel file is NOT written when token usage is below threshold."""

        monkeypatch.chdir(tmp_path)
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


    def test_sentinel_not_written_when_handoff_complete(
        self, hook_script: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Sentinel is skipped when handoff_complete=true (session already handed off)."""

        monkeypatch.chdir(tmp_path)
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


    def test_sentinel_survives_session_cleanup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sentinel file is NOT deleted by session-cleanup.sh (intentionally excluded)."""
        cleanup_script = Path(__file__).parent.parent.parent / "hooks/scripts/session-cleanup.sh"

        monkeypatch.chdir(tmp_path)
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


    def test_result_token_count_preferred_over_estimated(
        self, hook_script: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """result_token_count (accurate) is preferred over estimated_tokens (heuristic)."""

        monkeypatch.chdir(tmp_path)
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
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Worktree with live PID marker must not be removed by session-cleanup.sh."""
        import os

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir(exist_ok=True)
        worker_dir = self._make_worktree(tmp_path)
        (worker_dir / f".ll-session-{os.getpid()}").write_text("")

        subprocess.run([str(cleanup_script)], capture_output=True, text=True, timeout=15)

        assert worker_dir.exists(), (
            "Worktree with live PID marker should not be removed by session-cleanup.sh"
        )

    def test_session_cleanup_removes_worktree_with_dead_pid_marker(
        self, cleanup_script: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Worktree with dead PID marker must be removed by session-cleanup.sh."""

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir(exist_ok=True)
        worker_dir = self._make_worktree(tmp_path)
        (worker_dir / ".ll-session-99999").write_text("")

        subprocess.run([str(cleanup_script)], capture_output=True, text=True, timeout=15)

        assert not worker_dir.exists(), (
            "Worktree with dead PID marker should be removed by session-cleanup.sh"
        )

    def test_session_cleanup_removes_worktree_with_no_marker(
        self, cleanup_script: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Orphaned worktree (no .ll-session-* marker) must be removed by session-cleanup.sh."""

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".ll").mkdir(exist_ok=True)
        worker_dir = self._make_worktree(tmp_path)
        # No marker — simulates an orphan from an interrupted run

        subprocess.run([str(cleanup_script)], capture_output=True, text=True, timeout=15)

        assert not worker_dir.exists(), (
            "Orphaned worktree with no session marker should be removed by session-cleanup.sh"
        )


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

    def test_non_issue_file_exits_0(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> None:
        """Non-issue file path exits 0 immediately without touching git."""

        self._init_git_repo(tmp_path)
        plain_file = tmp_path / "README.md"
        plain_file.write_text("hello")
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=self._make_input(str(plain_file)),
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        git_log = subprocess.run(
            ["git", "log", "--oneline"], cwd=str(tmp_path), capture_output=True, text=True
        )
        assert git_log.stdout.strip() == "", "Expected no commits for non-issue file"

    def test_disabled_exits_0_without_git_commit(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> None:
        """auto_commit absent (default false) → hook exits 0 without committing."""

        self._init_git_repo(tmp_path)
        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_file = issues_dir / "P3-ENH-1844-test.md"
        issue_file.write_text("---\nstatus: open\n---\n")
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=self._make_input(str(issue_file)),
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        git_log = subprocess.run(
            ["git", "log", "--oneline"], cwd=str(tmp_path), capture_output=True, text=True
        )
        assert git_log.stdout.strip() == "", "Expected no commits when auto_commit disabled"

    def test_enabled_clean_tree_commits_issue_file(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> None:
        """auto_commit: true + clean working tree → git add + git commit run."""

        self._init_git_repo(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
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
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_file = issues_dir / "P3-ENH-1844-test.md"
        issue_file.write_text("---\nstatus: open\n---\n")
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=self._make_input(str(issue_file)),
            capture_output=True,
            text=True,
            timeout=10,
        )

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

    def test_custom_prefix_in_commit_message(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> None:
        """Custom auto_commit_prefix appears in commit message."""

        self._init_git_repo(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
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
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_file = issues_dir / "P2-BUG-999-my-bug.md"
        issue_file.write_text("---\nstatus: open\n---\n")
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=self._make_input(str(issue_file)),
            capture_output=True,
            text=True,
            timeout=10,
        )

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
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Dirty working tree → hook skips commit and prints warning to stderr."""

        self._init_git_repo(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
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
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_file = issues_dir / "P3-ENH-1844-test.md"
        issue_file.write_text("---\nstatus: open\n---\n")

        # Create a dirty file (other staged/unstaged change)
        dirty_file = tmp_path / "dirty.txt"
        dirty_file.write_text("dirty")
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=self._make_input(str(issue_file)),
            capture_output=True,
            text=True,
            timeout=10,
        )

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

    def test_edit_tool_uses_update_verb(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> None:
        """Edit tool calls produce 'update' verb in commit message."""

        self._init_git_repo(tmp_path)
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        config_file = ll_dir / "ll-config.json"
        config_file.write_text(json.dumps({"issues": {"auto_commit": True}}))

        issues_dir = tmp_path / ".issues" / "enhancements"
        issues_dir.mkdir(parents=True, exist_ok=True)
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
        monkeypatch.chdir(tmp_path)
        result = subprocess.run(
            [str(hook_script)],
            input=self._make_input(str(issue_file), tool_name="Edit"),
            capture_output=True,
            text=True,
            timeout=10,
        )

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

    def test_adapter_exits_zero(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> None:
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


class TestSessionCapture:
    """Test session-capture.sh PostToolUse hook (FEAT-1262)."""

    @pytest.fixture
    def hook_script(self) -> Path:
        """Path to session-capture.sh (tested directly — no adapter wrapper)."""
        return Path(__file__).parent.parent.parent / "hooks/scripts/session-capture.sh"

    @pytest.fixture
    def test_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> Path:
        """Config file with session_capture.enabled: true."""
        config = {"session_capture": {"enabled": True}}
        config_file = tmp_path / ".ll" / "ll-config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(config))
        return config_file

    def _make_input(
        self,
        tool_name: str,
        tool_input: dict,
        tool_response: dict | None = None,
    ) -> str:
        """Build JSON stdin for the hook simulating a PostToolUse invocation."""
        data: dict = {"tool_name": tool_name, "tool_input": tool_input}
        if tool_response is not None:
            data["tool_response"] = tool_response
        return json.dumps(data)

    def _run_hook(
        self,
        hook_script: Path,
        stdin: str,
        cwd: Path,
        env: dict | None = None,
    ) -> subprocess.CompletedProcess:
        import os

        run_env = dict(os.environ) if env is None else env
        return subprocess.run(
            [str(hook_script)],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cwd),
            env=run_env,
        )

    def _read_events(self, tmp_path: Path) -> list[dict]:
        """Read all events from the JSONL file, returning parsed dicts."""
        events_file = tmp_path / ".ll" / "ll-session-events.jsonl"
        if not events_file.exists():
            return []
        lines = [ln for ln in events_file.read_text().splitlines() if ln.strip()]
        return [json.loads(ln) for ln in lines]

    def test_file_event_captured(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Write tool invocation produces a type=file event record."""
        monkeypatch.chdir(tmp_path)
        stdin = self._make_input(
            "Write",
            {"file_path": "scripts/foo.py"},
        )
        result = self._run_hook(hook_script, stdin, tmp_path)

        assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
        events = self._read_events(tmp_path)
        assert len(events) == 1, f"Expected 1 event, got {len(events)}: {events}"
        ev = events[0]
        assert ev["type"] == "file"
        assert ev["op"] == "Write"
        assert ev["subject"] == "scripts/foo.py"
        assert "ts" in ev
        assert "status" in ev

    def test_task_event_captured(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """TaskCreate tool invocation produces a type=task event record."""
        monkeypatch.chdir(tmp_path)
        stdin = self._make_input(
            "TaskCreate",
            {"id": "task-123", "content": "implement foo", "status": "in_progress"},
        )
        result = self._run_hook(hook_script, stdin, tmp_path)

        assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
        events = self._read_events(tmp_path)
        assert len(events) == 1
        ev = events[0]
        assert ev["type"] == "task"
        assert ev["op"] == "TaskCreate"
        assert "ts" in ev

    def test_git_event_captured(self, hook_script: Path, test_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> None:
        """Bash invocation with git produces a type=git event record."""
        monkeypatch.chdir(tmp_path)
        stdin = self._make_input(
            "Bash",
            {"command": "git commit -m 'fix: test'"},
            tool_response={"exit_code": 0},
        )
        result = self._run_hook(hook_script, stdin, tmp_path)

        assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
        events = self._read_events(tmp_path)
        assert len(events) == 1
        ev = events[0]
        assert ev["type"] == "git"
        assert ev["op"] == "commit"
        assert "ts" in ev

    def test_error_event_captured(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Bash invocation with non-zero exit produces a type=error event record."""
        monkeypatch.chdir(tmp_path)
        stdin = self._make_input(
            "Bash",
            {"command": "pytest scripts/tests/"},
            tool_response={"exit_code": 1},
        )
        result = self._run_hook(hook_script, stdin, tmp_path)

        assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
        events = self._read_events(tmp_path)
        assert len(events) == 1
        ev = events[0]
        assert ev["type"] == "error"
        assert ev["op"] == "bash_error"
        assert ev["status"] == "1"
        assert "pytest" in ev["subject"]
        assert "ts" in ev

    def test_exits_zero_when_feature_disabled(self, hook_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch)-> None:
        """Hook exits 0 and produces no record when session_capture.enabled is false (default)."""
        monkeypatch.chdir(tmp_path)
        # No test_config fixture — feature defaults to disabled
        stdin = self._make_input("Write", {"file_path": "scripts/foo.py"})
        result = self._run_hook(hook_script, stdin, tmp_path)

        assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
        events = self._read_events(tmp_path)
        assert len(events) == 0, "No events should be written when feature is disabled"

    def test_exits_zero_on_malformed_stdin(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Hook exits 0 and produces no record when stdin is malformed JSON."""
        monkeypatch.chdir(tmp_path)
        result = self._run_hook(hook_script, "not valid json {{{{", tmp_path)

        assert result.returncode == 0, f"Hook exited non-zero on bad stdin: {result.stderr}"

    def test_unknown_tool_produces_no_record(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """Unknown tool names produce no event record."""
        monkeypatch.chdir(tmp_path)
        stdin = self._make_input("SomeUnknownTool", {"data": "value"})
        result = self._run_hook(hook_script, stdin, tmp_path)

        assert result.returncode == 0, f"Hook exited non-zero: {result.stderr}"
        events = self._read_events(tmp_path)
        assert len(events) == 0, "Unknown tools should produce no event record"

    def test_concurrent_writes_no_corruption(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """4 concurrent hook invocations produce 4 valid, uncorrupted JSONL lines."""

        monkeypatch.chdir(tmp_path)

        def run_one(i: int) -> subprocess.CompletedProcess:
            stdin = self._make_input(
                "Write",
                {"file_path": f"scripts/file_{i}.py"},
            )
            return self._run_hook(hook_script, stdin, tmp_path)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(run_one, i) for i in range(4)]
            results = [f.result() for f in as_completed(futures)]

        assert all(r.returncode == 0 for r in results), "All hook invocations must exit 0"

        events = self._read_events(tmp_path)
        assert len(events) == 4, f"Expected 4 events, got {len(events)}"
        for ev in events:
            assert ev["type"] == "file"
            assert ev["op"] == "Write"
            assert "ts" in ev

    def test_file_subject_strips_leading_dot_slash(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    , monkeypatch: pytest.MonkeyPatch) -> None:
        """File subject has leading ./ stripped per subject-normalization rule."""
        monkeypatch.chdir(tmp_path)
        stdin = self._make_input("Read", {"file_path": "./scripts/foo.py"})
        result = self._run_hook(hook_script, stdin, tmp_path)

        assert result.returncode == 0
        events = self._read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["subject"] == "scripts/foo.py"
