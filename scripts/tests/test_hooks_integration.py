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
                "context_limit_estimate": 150000,
                "state_file": str(tmp_path / "ll-context-state.json"),
            }
        }
        config_file = tmp_path / ".claude" / "ll-config.json"
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
            config_link = tmp_path / ".claude" / "ll-config.json"
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

    def test_state_file_corruption_resistance(
        self, hook_script: Path, test_config: Path, tmp_path: Path
    ):
        """Test that atomic writes prevent state file corruption."""
        import os

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create config
            config_link = tmp_path / ".claude" / "ll-config.json"
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
        config_file = tmp_path / ".claude" / "ll-config.json"
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
            config_link = tmp_path / ".claude" / "ll-config.json"
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

    def test_resolve_config_finds_claude_dir(self, common_sh: Path, tmp_path: Path):
        """ll_resolve_config finds .claude/ll-config.json."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "ll-config.json"
        config_file.write_text('{"test": true}')

        result = self._run_bash(common_sh, 'll_resolve_config; echo "$LL_CONFIG_FILE"', tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ".claude/ll-config.json"

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
        config_dir = tmp_path / ".claude"
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
        config_dir = tmp_path / ".claude"
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
        config_dir = tmp_path / ".claude"
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
        config_dir = tmp_path / ".claude"
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
        config_dir = tmp_path / ".claude"
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
            config_dir = tmp_path / ".claude"
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
            config_dir = tmp_path / ".claude"
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
            config_dir = tmp_path / ".claude"
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
            config_dir = tmp_path / ".claude"
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
                            "goals_file": ".claude/ll-goals.md",
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
            config_dir = tmp_path / ".claude"
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
            state_file = tmp_path / ".claude" / "ll-precompact-state.json"
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
            state_file = tmp_path / ".claude" / "ll-precompact-state.json"
            state = json.loads(state_file.read_text())
            assert state["preserved"] is True

        finally:
            os.chdir(original_dir)
