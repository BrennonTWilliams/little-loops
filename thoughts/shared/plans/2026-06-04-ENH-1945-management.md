# ENH-1945: Host-Aware Session Log Discovery - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-1945-host-aware-session-log-discovery-codex-pi.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve
- **Score**: confidence=100, complexity=14

## Historical Effort
No prior sessions implementing this issue.

## Current State Analysis

### Key Discoveries
- `get_project_folder()` at `user_messages.py:355-381` — hardcodes `~/.claude/projects/`, no host parameter. Returns `None` gracefully when directory missing.
- `_config_candidates(project_root, *, host, state_dir)` at `config/core.py:74` — exact precedent pattern for host-aware parameter addition. Uses keyword-only `host: str | None`, string-equality branching, docstring extension-point convention.
- `CODEX_CONFIG_DIR = ".codex"` at `config/core.py:41` — only host-specific constant; need `CODEX_PROJECTS_DIR` alongside it.
- `session_start.handle()` line 80: `del event` explicitly discards the `LLHookEvent` — blocks `_run_backfill()` from reading `transcript_path` from Codex payloads.
- `_run_backfill()` at line 127 calls `get_project_folder(cwd)` — no host context passed.
- `session_log.get_current_session_jsonl()` at line 63 calls `get_project_folder(cwd)` — no host context.
- `append_session_log_entry()` at line 86 auto-detects session JSONL via `get_current_session_jsonl()` — 7 transitive callers benefit from fix.
- `cli/session.py:304-307` — `ll-session backfill --since` calls `get_project_folder()`, hardcodes "No Claude project folder found" error.
- `cli/session.py:319` — full backfill (no `--since`) calls `backfill(args.db)` with `jsonl_files=None`, skipping JSONL entirely (secondary gap).
- `cli/logs.py:126` — `discover_all_projects()` hardcodes `~/.claude/projects/` directly (doesn't even use `get_project_folder()`).
- `cli/logs.py:244-247` — `ll-logs extract` calls `get_project_folder()`, Claude-Code-specific error messages.
- `cli/messages.py:173-177` — `ll-messages extract` calls `get_project_folder()`, Claude-Code-specific error messages.
- `pre_compact.py:55` — precedent for consuming `transcript_path` from hook payload: `payload.get("transcript_path") or ""`.
- `host_runner.py:751` — `resolve_host()` detection chain (binary probe + env vars); NOT suitable for session discovery (raises on failure).
- `hooks/__init__.py:125` — dispatcher defaults `LL_HOOK_HOST` to `"claude-code"`.
- `_HOST_RUNNER_REGISTRY` keys: `"claude-code"`, `"codex"`, `"opencode"`, `"pi"`.
- `_PROBE_ORDER` at `host_runner.py:736-740`: only `claude-code`, `codex`, `pi` — `opencode` absent.
- `OpenCodeRunner` at `host_runner.py:589-590` raises `HostNotConfigured` on all `build_*` methods.
- `config-schema.json:1173` — `hooks.host.enum` values `["claude-code", "opencode", "codex"]`; `host_cli` at line 1312 adds `"pi"`.

### Failure Table (16 call sites silent-fail for non-Claude-Code hosts)
- LCM DAG `_compact_session_conn()` at `session_store.py:1323` — empty `message_events`
- Correction mining `mine_corrections_from_messages()` at `session_store.py:1099` — no data
- Project digest `project_digest()` at `history_reader.py:933` — all SECTION_PROVIDERS empty
- FSM loop session logging at `fsm/executor.py:1089` — no session JSONL path
- Issue lifecycle logging at `issue_lifecycle.py:25` — no session log entries
- All other transitive importers of `append_session_log_entry`

## Desired End State

- `get_project_folder(cwd, *, host=None)` probes correct session directory per host
- `ll-session backfill` supports `--host` flag, populates `message_events`/`sessions` for Codex
- `session_start._run_backfill()` consumes `transcript_path` from hook payload directly
- `session_log.get_current_session_jsonl()` resolves paths for non-Claude-Code hosts
- `ll-logs discover` / `ll-messages extract` scan host-specific directories
- All error messages host-agnostic
- Pi gets a stub branch (directories probed, no adapter yet per FEAT-992)

### How to Verify
- `ll-session backfill --host codex` succeeds with mock Codex session directory
- `session_start` auto-backfill populates Codex sessions when `transcript_path` in payload
- `ll-history-context ENH-1945` returns corrections mined from Codex history (end-to-end)
- All existing Claude Code tests pass unchanged

## What We're NOT Doing
- Not building a Pi adapter (FEAT-992, deferred)
- Not changing session log format or JSONL parsing
- Not cross-project aggregation
- Not adding `opencode` to `_PROBE_ORDER` (out of scope — session discovery ≠ command execution)
- Not fixing `resolve_host()` for OpenCode (out of scope — it's correct to raise for command execution)

## Solution Approach

**Selected**: Option A — Host-aware `get_project_folder()` with keyword-only `host` parameter.

Follow the `_config_candidates()` precedent at `config/core.py:74` exactly:
- `*, host: str | None = None` keyword-only parameter
- String-equality branching per host
- Docstring extension-point convention
- `os.environ.get("LL_HOOK_HOST", "claude-code")` auto-detection

**Host detection chain for `--host` CLI flag**:
1. Explicit `--host` flag value
2. `LL_HOOK_HOST` env var
3. `orchestration.host_cli` config key
4. Default: `"claude-code"`

Do NOT use `resolve_host()` for CLI auto-detection — it raises `HostNotConfigured` when no binary is on PATH, which is inappropriate for filesystem path probing.

## Code Reuse & Integration
- **Reuse**: `_config_candidates()` pattern (`config/core.py:74`) — template for `get_project_folder()` host parameter
- **Reuse**: `resolve_config_path()` env detection (`config/core.py:99`) — `os.environ.get("LL_HOOK_HOST")` pattern
- **Reuse**: `pre_compact.handle()` transcript_path consumption (`hooks/pre_compact.py:55`) — `payload.get("transcript_path") or ""`
- **Reuse**: `backfill()` silent skip pattern (`session_store.py:1638`) — `if not directory.is_dir(): continue`
- **Extend**: `CODEX_CONFIG_DIR` constant → add `CODEX_PROJECTS_DIR`
- **New**: `get_project_folder()` host parameter (no existing pattern to extend — this IS the pattern)

## Implementation Phases

### Phase 0: Write Tests — Red *(TDD mode)*

#### Overview
Write tests encoding acceptance criteria. Tests must FAIL against current codebase (current `get_project_folder()` has no host parameter).

#### Test Files
1. **`scripts/tests/test_user_messages.py`** — Add `TestGetProjectFolderHostAware` class:
   - `test_host_claude_code_defaults_to_claude_projects` — host=None → probes `~/.claude/projects/`
   - `test_host_codex_probes_codex_directory` — host="codex" → probes `~/.codex/projects/`
   - `test_host_opencode_probes_opencode_directory` — host="opencode" → probes appropriate dir
   - `test_host_auto_detect_from_env` — `LL_HOOK_HOST=codex` → probes Codex dir
   - `test_returns_none_when_dir_missing` — nonexistent dir → None

2. **`scripts/tests/test_hook_session_start.py`** — Add Codex payload tests:
   - `test_run_backfill_consumes_transcript_path` — Codex payload with `transcript_path` → backfill uses it directly
   - `test_run_backfill_falls_back_when_no_transcript_path` — no `transcript_path` in payload → probes directory
   - `_codex_event()` helper — creates `LLHookEvent(host="codex", payload={"transcript_path": "..."})`

3. **`scripts/tests/test_session_log.py`** — Add host-aware path resolution:
   - `test_get_current_session_jsonl_codex` — resolves JSONL from Codex session dir
   - `test_append_session_log_entry_auto_detects_host` — auto-detection works for Codex

4. **`scripts/tests/test_ll_session.py`** — Add `--host codex` CLI tests:
   - `test_backfill_host_codex` — `ll-session backfill --host codex` with mock Codex dir
   - `test_backfill_host_auto_detect` — auto-detection from `LL_HOOK_HOST`

#### Red Validation
Run: `python -m pytest scripts/tests/test_user_messages.py scripts/tests/test_hook_session_start.py scripts/tests/test_session_log.py scripts/tests/test_ll_session.py -v -k "host or codex or HostAware"`
- **Expected**: Non-zero exit with `FAILED` markers (assertion failures against current code)
- **Invalid**: ImportError/SyntaxError/ERROR — fix test code before proceeding

#### Success Criteria
- [ ] Tests fail with assertion errors (not import/syntax errors)
- [ ] Test output contains `FAILED` (not just `ERROR`)

---

### Phase 1: Add `host` parameter to `get_project_folder()`

#### Overview
Modify `get_project_folder()` to accept a keyword-only `host` parameter and branch on host type. This is the root fix — all downstream consumers benefit automatically.

#### Changes Required

**File**: `scripts/little_loops/user_messages.py` (line 355)
**Changes**: Add `host` parameter + host-specific helpers

```python
# Add after existing imports
from little_loops.config.core import CODEX_CONFIG_DIR

# New constant (or added to config/core.py)
_CODEX_PROJECTS_DIR = ".codex/projects"

def get_project_folder(cwd: Path | None = None, *, host: str | None = None) -> Path | None:
    """Map current directory to the host's session-log project folder.

    Converts the working directory into the host-specific encoded path and
    probes the host's session directory for matching JSONL files.

    Args:
        cwd: Working directory to map. If None, uses current directory.
        host: Host identifier (``"claude-code"``, ``"codex"``, ``"opencode"``,
            ``"pi"``). If None, auto-detects from ``LL_HOOK_HOST`` env var
            (default ``"claude-code"``).

    Returns:
        Path to the host's project session folder, or None if not found.

    Future hosts (e.g. FEAT-992 Pi) add a new branch here rather than a
    new code path elsewhere.
    """
    if cwd is None:
        cwd = Path.cwd()
    if host is None:
        host = os.environ.get("LL_HOOK_HOST", "claude-code")

    path_str = str(cwd.resolve())
    encoded_path = path_str.replace("/", "-")

    if host == "claude-code":
        return _get_claude_project_folder(encoded_path)
    elif host == "codex":
        return _get_codex_project_folder(encoded_path)
    elif host == "opencode":
        return _get_opencode_project_folder(encoded_path)
    elif host == "pi":
        return _get_pi_project_folder(encoded_path)
    return None


def _get_claude_project_folder(encoded_path: str) -> Path | None:
    project_folder = Path.home() / ".claude" / "projects" / encoded_path
    return project_folder if project_folder.exists() else None


def _get_codex_project_folder(encoded_path: str) -> Path | None:
    project_folder = Path.home() / ".codex" / "projects" / encoded_path
    return project_folder if project_folder.exists() else None


def _get_opencode_project_folder(encoded_path: str) -> Path | None:
    project_folder = Path.home() / ".opencode" / "projects" / encoded_path
    return project_folder if project_folder.exists() else None


def _get_pi_project_folder(encoded_path: str) -> Path | None:
    project_folder = Path.home() / ".pi" / "projects" / encoded_path
    return project_folder if project_folder.exists() else None
```

**File**: `scripts/little_loops/config/core.py` (line 41)
**Changes**: Add `CODEX_PROJECTS_DIR` constant (if needed after verification; the helper functions above have paths inline following the simplicity of the existing `CODEX_CONFIG_DIR` constant usage)

#### Success Criteria
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v -k "host or codex or HostAware"`
- [ ] Lint passes: `ruff check scripts/little_loops/user_messages.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/user_messages.py`
- [ ] Existing Claude Code tests unchanged: `python -m pytest scripts/tests/ -v -k "get_project_folder"`

---

### Phase 2: Update `session_start._run_backfill()` for `transcript_path`

#### Overview
Remove `del event` blocker, consume `transcript_path` from hook payload when available (following `pre_compact.py:55` pattern), pass host context.

#### Changes Required

**File**: `scripts/little_loops/hooks/session_start.py` (lines 75-139)

**Change 1** (line 80): Remove or guard `del event`
```python
# BEFORE:
    del event  # SessionStart consumes no payload fields today; ...

# AFTER: Remove the line entirely. The event object is now consumed by _run_backfill.
```

**Change 2** (lines 127-137): Update `_run_backfill()` to consume payload
```python
def _run_backfill() -> None:
    try:
        from little_loops.session_store import backfill_incremental
        from little_loops.user_messages import get_project_folder

        payload = event.payload or {}
        transcript_path = payload.get("transcript_path") or ""

        if transcript_path:
            # Use transcript_path directly (Codex/OpenCode hook path)
            jsonl_path = Path(transcript_path)
            if jsonl_path.is_file():
                jsonl_files = [jsonl_path]
            else:
                jsonl_files = []
        else:
            # Fall back to directory probing (Claude Code path)
            project_folder = get_project_folder(cwd)
            if project_folder is not None:
                jsonl_files = list(project_folder.glob("*.jsonl"))
            else:
                jsonl_files = []

        if jsonl_files:
            backfill_incremental(_db_path, jsonl_files=jsonl_files)
    except Exception:
        logger.warning("session_start: backfill_incremental failed", exc_info=True)
```

#### Success Criteria
- [ ] Tests pass: `python -m pytest scripts/tests/test_hook_session_start.py -v -k "codex or transcript_path or run_backfill"`
- [ ] Lint, types pass
- [ ] Existing Claude Code session_start tests unchanged

---

### Phase 3: Update `session_log.get_current_session_jsonl()`

#### Overview
Pass host context through to `get_project_folder()` so session JSONL resolution works for non-Claude-Code hosts.

#### Changes Required

**File**: `scripts/little_loops/session_log.py` (line 63)

```python
def get_current_session_jsonl(cwd: Path | None = None) -> Path | None:
    """Resolve the active session's JSONL file path.

    Finds the most recently modified .jsonl file in the host's
    session directory, excluding agent session files.

    Args:
        cwd: Working directory to map. If None, uses current directory.

    Returns:
        Path to the most recent JSONL file, or None if not found.
    """
    project_folder = get_project_folder(cwd)  # host auto-detects from LL_HOOK_HOST
    if project_folder is None:
        return None

    jsonl_files = [f for f in project_folder.glob("*.jsonl") if not f.name.startswith("agent-")]
    if not jsonl_files:
        return None

    return max(jsonl_files, key=lambda f: f.stat().st_mtime)
```

Note: No signature change needed — `get_project_folder()` auto-detects host from `LL_HOOK_HOST`. This is the beauty of fixing at the root.

#### Success Criteria
- [ ] Tests pass: `python -m pytest scripts/tests/test_session_log.py -v`
- [ ] Lint, types pass

---

### Phase 4: Update CLI tools (`ll-session backfill`, `ll-logs`, `ll-messages`)

#### Overview
Add `--host` flag to `ll-session backfill`. Update error messages to be host-agnostic. Update `ll-logs discover` and `ll-messages extract` for host-aware directory probing.

#### Changes Required

**File**: `scripts/little_loops/cli/session.py` (lines 290-328)

**Change 1**: Add `--host` argument to parser (near the backfill subparser setup)
```python
backfill_parser.add_argument(
    "--host",
    choices=["claude-code", "codex", "opencode", "pi"],
    default=None,
    help="Host to discover session logs for (default: auto-detect from LL_HOOK_HOST env)",
)
```

**Change 2**: Update backfill logic to pass host
```python
project_folder = get_project_folder(host=args.host)
if project_folder is None:
    logger.error("No session project folder found; cannot discover JSONL files.")
    return 1
```

**Change 3** (line 319): Fix full backfill gap — discover JSONL files even without `--since`
```python
# BEFORE:
counts = backfill(args.db)

# AFTER:
project_folder = get_project_folder(host=args.host)
jsonl_files = list(project_folder.glob("*.jsonl")) if project_folder else None
counts = backfill(args.db, jsonl_files=jsonl_files)
```

**File**: `scripts/little_loops/cli/logs.py` (lines 126, 244-247)
- Update `discover_all_projects()` to probe host-specific directories
- Update error messages to remove "Claude project folder" wording

**File**: `scripts/little_loops/cli/messages.py` (lines 173-177)
- Update error messages to be host-agnostic

#### Success Criteria
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_session.py scripts/tests/test_ll_logs.py scripts/tests/test_cli.py -v -k "host or codex or discover or backfill"`
- [ ] Lint, types pass
- [ ] All existing CLI tests unchanged

---

### Phase 5: Update `ll-logs discover_all_projects()`

#### Overview
`discover_all_projects()` at `cli/logs.py:126` hardcodes `~/.claude/projects/` directly. Make it host-aware.

#### Changes Required

**File**: `scripts/little_loops/cli/logs.py` (line 126)

Add a `host` parameter and iterate the correct host directory. Follow same pattern as `get_project_folder()` — branch on host, iterate the corresponding directory.

#### Success Criteria
- [ ] Tests pass for Codex/OpenCode project discovery
- [ ] Lint, types pass

---

### Phase 6: Update Error Messages to be Host-Agnostic

#### Overview
Replace all "Claude project folder" references with host-agnostic wording.

#### Files
- `cli/session.py:306` — "No Claude project folder found" → "No session project folder found"
- `cli/logs.py:246-247` — "No Claude project folder found for: ..." → host-aware wording
- `cli/messages.py:176-177` — same pattern

#### Success Criteria
- [ ] Grep for "Claude project folder" in scripts/ returns zero results (outside docstrings referencing legacy behavior)
- [ ] Lint, types pass

---

### Phase 7: Documentation Updates

#### Overview
Update docs to reflect host-aware session discovery.

#### Files
- `docs/reference/HOST_COMPATIBILITY.md` — document host-specific session directories
- `docs/reference/API.md` — update `get_project_folder()` signature docs
- `docs/reference/CLI.md` — document `--host` flag for `ll-session backfill`
- `docs/reference/EVENT-SCHEMA.md:81` — qualify "session_start reads no payload keys"
- `docs/ARCHITECTURE.md` — note backfill/session_start host-awareness
- `.claude/CLAUDE.md:65` — add `--host` to `ll-session` subcommand listing

#### Success Criteria
- [ ] Documentation accurately reflects new behavior
- [ ] No broken links: `python -m little_loops.cli.check_links` if available

---

### Phase 8: End-to-End Verification

#### Overview
Run full test suite, verify all hosts work end-to-end.

#### Automated Verification
- [ ] Full test suite: `python -m pytest scripts/tests/ -v`
- [ ] Lint: `ruff check scripts/`
- [ ] Types: `python -m mypy scripts/little_loops/`
- [ ] No regressions in existing functionality

#### Manual Verification
- [ ] `ll-session backfill --host codex` works with mock Codex session directory
- [ ] `session_start` auto-backfill works with Codex payload including `transcript_path`
- [ ] LCM DAG produces summary nodes for Codex sessions
- [ ] `ll-history-context` returns corrections from Codex sessions

## Testing Strategy

### Unit Tests
- `get_project_folder()` with each host value
- `_run_backfill()` with `transcript_path` in payload
- `get_current_session_jsonl()` with Codex session dir
- Error message content validation

### Integration Tests
- `ll-session backfill --host codex` end-to-end
- `ll-logs discover` with mock Codex directories
- `session_start` hook dispatch with Codex payload

## References
- Original issue: `.issues/enhancements/P2-ENH-1945-host-aware-session-log-discovery-codex-pi.md`
- Pattern: `_config_candidates()` at `config/core.py:74`
- Pattern: `pre_compact.handle()` at `hooks/pre_compact.py:55`
- Pattern: `resolve_config_path()` at `config/core.py:99`
- Host registry: `_HOST_RUNNER_REGISTRY` at `host_runner.py:727`
