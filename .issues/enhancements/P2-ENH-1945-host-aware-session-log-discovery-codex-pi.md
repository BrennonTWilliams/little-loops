---
id: ENH-1945
title: Make session log discovery host-aware for Codex/OpenCode/Pi backfill
type: ENH
priority: P2
status: open
discovered_date: 2026-06-04
captured_at: "2026-06-04T19:18:32Z"
discovered_by: capture-issue
parent: EPIC-1707
decision_needed: true
labels:
  - enh
  - captured
  - multi-host
---

# ENH-1945: Make session log discovery host-aware for Codex/OpenCode/Pi backfill

## Summary

`get_project_folder()` in `scripts/little_loops/user_messages.py:355-381` hardcodes `~/.claude/projects/<encoded-path>/` as the only session log source. This makes `ll-session backfill`, auto-backfill on `session_start`, and `session_log.get_current_session_jsonl()` Claude-Code-only operations. Codex and OpenCode sessions write live events via hooks but get no historical backfill, LCM summarization, or correction mining. Pi has no adapter at all yet. The `transcript_path` is already in Codex hook payloads — it just isn't consumed.

## Current Behavior

- `get_project_folder(cwd)` always probes `~/.claude/projects/<encoded-cwd>/` and returns `None` if that directory doesn't exist.
- Three critical paths depend on it:
  1. `ll-session backfill` (`cli/session.py:304`) — discovers JSONL files to seed `message_events`, `tool_events`, and `sessions`.
  2. `session_start._run_backfill()` (`hooks/session_start.py:132`) — ENH-1830 background daemon that auto-backfills at session start.
  3. `session_log.get_current_session_jsonl()` (`session_log.py:75`) — resolves the active session's JSONL path.
- For Codex projects (no `~/.claude/projects/` directory), all three paths fail silently: backfill does nothing, `sessions.jsonl_path` stays NULL, and the LCM summary DAG has no `message_events` to compact.
- Codex hook payloads include `transcript_path` (absolute path to the session JSONL) — see `hooks/adapters/codex/README.md:67` — but no code path consumes it.
- Pi has no adapter at all (FEAT-992 is deferred).

## Expected Behavior

- `get_project_folder()` (or a new host-aware wrapper) probes the correct session log directory for the active host: `~/.claude/projects/` for Claude Code, the Codex session directory for Codex, the OpenCode session directory for OpenCode, and a future Pi directory for Pi.
- `ll-session backfill` accepts a `--host` flag or auto-detects the host from `LL_HOOK_HOST` / project config.
- `session_start._run_backfill()` uses the `transcript_path` from the hook payload when available, falling back to host-aware directory probing.
- `session_log.get_current_session_jsonl()` resolves paths correctly for non-Claude-Code hosts.
- All downstream consumers (LCM DAG, correction mining, project-context snapshot) work for all hosts that have adapters.

## Motivation

This is the root-cause gap preventing EPIC-1707's consumer layer from working for non-Claude-Code hosts. Without it, Codex and Pi sessions are invisible to history.db beyond live hook writes (which don't cover backfill, summarization, or correction mining). The `## Success Metrics` in EPIC-1707 (measurable reduction in repeated corrections) cannot be achieved for non-Claude-Code hosts until this is fixed. The `transcript_path` data is already flowing in hook payloads — the gap is purely on the consumer side.

## Proposed Solution

### Option A: Host-aware `get_project_folder()` (Recommended)

Add a `host` parameter to `get_project_folder(cwd, host=None)` that branches on host type:

```python
def get_project_folder(cwd: Path | None = None, host: str | None = None) -> Path | None:
    if host is None:
        host = os.environ.get("LL_HOOK_HOST", "claude")
    if host == "claude":
        return _get_claude_project_folder(cwd)
    elif host in ("codex", "opencode"):
        # Probe the host's session directory pattern
        return _get_codex_project_folder(cwd)
    elif host == "pi":
        return _get_pi_project_folder(cwd)
    return None
```

Each host-specific helper mirrors the Claude Code path-encoding convention for its own session directory layout.

### Option B: New `resolve_session_dir()` wrapper

Create a new function that wraps `get_project_folder()` for the "given a CWD, find session JSONL files" use case, leaving `get_project_folder()` as-is for backward compatibility. All three call sites switch to the new function.

**Recommendation**: Option A — fewer new functions, direct fix at the root, and the `host` parameter is backward-compatible (defaults to `"claude"`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Host parameter pattern**: `_config_candidates(project_root, *, host: str | None, state_dir: str | None)` at `config/core.py:74` is the best model for `get_project_folder(cwd, *, host: str | None)`. It uses keyword-only `host` parameter, defaults `None` to preserve backward compatibility, and branches on string equality (`host == "codex"`).
- **Host naming alignment**: The `host` parameter should accept the `_HOST_RUNNER_REGISTRY` key names (`"claude-code"`, `"codex"`, `"opencode"`, `"pi"`) to match `resolve_host().name`. For backward compatibility, `host=None` should default to `"claude-code"`. Use `os.environ.get("LL_HOOK_HOST", "claude-code")` as the auto-detection fallback, matching the dispatcher at `hooks/__init__.py:125`.
- **Codex session directory layout**: Codex provides `transcript_path` in hook payloads (absolute path to session JSONL) — this is the primary mechanism for `session_start` and `session_log`. For CLI tools (`ll-session backfill`, `ll-logs discover`) where no hook payload exists, the Codex session directory must be probed directly. Research suggests Codex stores sessions under `~/.codex/` with `CODEX_HOME` env override (per FEAT-957), but the exact layout needs verification during implementation. A `CODEX_PROJECTS_DIR` constant (like the `CODEX_CONFIG_DIR = ".codex"` at `config/core.py:41`) could centralize the path prefix.
- **`transcript_path` consumption precedent**: `pre_compact.handle()` at `hooks/pre_compact.py:55` already reads `transcript_path = payload.get("transcript_path") or ""`. Step 3 of implementation should follow this exact pattern instead of probing the directory — when the payload has `transcript_path`, use it directly (no directory probing needed for that session).
- **`del event` blocker**: `session_start.handle()` at line 80 explicitly discards the event with `del event` and the comment "SessionStart consumes no payload fields today." This line must be removed or guarded so `_run_backfill()` can read `event.payload.transcript_path`.

## Integration Map

### Files to Modify

- `scripts/little_loops/user_messages.py` — `get_project_folder()`: add host parameter + host-specific probing
- `scripts/little_loops/cli/session.py` — `backfill` command: accept `--host` flag or auto-detect
- `scripts/little_loops/hooks/session_start.py` — `_run_backfill()`: consume `transcript_path` from payload
- `scripts/little_loops/session_log.py` — `get_current_session_jsonl()`: use host-aware path resolution

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/logs.py:244,254` — `ll-logs discover` calls `get_project_folder()`; also `discover_all_projects()` at line 140 hardcodes `~/.claude/projects/` iteration
- `scripts/little_loops/cli/messages.py:173` — `ll-messages extract` calls `get_project_folder()`
- `scripts/little_loops/user_messages.py:14-16` — internal `extract_user_messages()` docstring references
- `scripts/little_loops/session_store.py:1503,1535` — `backfill()` defaults `jsonl_files=None`, guard skips JSONL entirely when None; full backfill (no `--since`) also fails for non-Claude-Code hosts
- `scripts/little_loops/session_store.py:1323` — `_compact_session_conn()` queries `message_events` (LCM DAG leaf nodes); empty when backfill didn't run
- `scripts/little_loops/session_store.py:1099` — `mine_corrections_from_messages()` scans `message_events`; no corrections mined for non-Claude-Code hosts
- `scripts/little_loops/history_reader.py:933` — `project_digest()` consumes session data from multiple tables; all empty for non-Claude-Code hosts

### Similar Patterns

- `resolve_host()` in `host_runner.py:751` already provides host detection — reuse its logic
- `_config_candidates()` in `config/core.py:74` — accepts `host: str | None` parameter and branches on `host == "codex"`; the closest existing pattern for adding a `host` parameter to `get_project_folder()`; docstring at line 88 explicitly notes "Future hosts (e.g. FEAT-992 Pi) add a new branch here"
- `pre_compact.handle()` at `hooks/pre_compact.py:55` — already consumes `transcript_path` from Codex hook payloads (`transcript_path = payload.get("transcript_path") or ""`); proves the data flows through the adapter and dispatcher correctly; the only missing link is `session_start.handle()` consuming it
- `hooks/adapters/codex/` adapter scripts set `export LL_HOOK_HOST=codex` — the Python dispatcher at `hooks/__init__.py:125` reads this as `os.environ.get("LL_HOOK_HOST", "claude-code")`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Verified**: All line numbers in the issue match actual code (355-381, 304, 132, 75, 244, 254, 173)
- **Additional hardcoding**: `discover_all_projects()` at `cli/logs.py:140` also hardcodes `~/.claude/projects/` iteration — `ll-logs discover` is also Claude-Code-only
- **Full-backfill gap**: `backfill()` in `session_store.py:1503` defaults `jsonl_files=None`, and the guard at line 1535 (`if jsonl_files:`) skips JSONL backfill entirely when `None`. So even full backfill (no `--since`) produces zero `message_events`/`sessions` for non-Claude-Code hosts
- **Host naming inconsistency**: `_HOST_RUNNER_REGISTRY` keys use `"claude-code"` (with hyphen) while `LL_HOOK_HOST` uses `"claude"` for the default and `"codex"` for Codex. The `get_project_folder()` host parameter should use the `host_runner.py` registry names (`"claude-code"`, `"codex"`, `"opencode"`, `"pi"`) for consistency with `resolve_host().name`
- **Failure table**: 16 distinct call sites fail silently for non-Claude-Code hosts — including LCM summary DAG leaf nodes (`_compact_session_conn()` at `session_store.py:1323` queries `message_events` which is empty), correction mining (`mine_corrections_from_messages()` at `session_store.py:1099`), and project digest (all SECTION_PROVIDERS consuming session data)

### Tests

- `scripts/tests/test_user_messages.py` — add test for `get_project_folder()` with `host="codex"` param
- `scripts/tests/test_session_store.py` — add backfill tests with non-Claude-Code session directories
- `scripts/tests/test_session_log.py` — test JSONL path resolution for Codex

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — document host-specific session directories
- `docs/reference/API.md` — update `get_project_folder()` signature docs

### Configuration

- N/A (host detection is automatic via env/config)

## Implementation Steps

1. Add `host` parameter to `get_project_folder(cwd, *, host: str | None = None)` following the `_config_candidates()` pattern at `config/core.py:74`. Implement host-specific helpers for `"codex"` and `"opencode"` session directories. Use `os.environ.get("LL_HOOK_HOST", "claude-code")` for auto-detection when `host=None`. Add a `CODEX_PROJECTS_DIR` constant alongside `CODEX_CONFIG_DIR` at `config/core.py:41`.
2. Update `ll-session backfill` at `cli/session.py:290` to accept `--host` flag (default auto-detect from `LL_HOOK_HOST` env / `orchestration.host_cli` config). Also fix full-backfill mode (line 319): pass discovered `jsonl_files` to `backfill()` so JSONL backfill works even without `--since`.
3. Update `session_start._run_backfill()` at `hooks/session_start.py:127` to consume `transcript_path` from the hook payload when available, following the exact pattern at `pre_compact.py:55` (`transcript_path = payload.get("transcript_path") or ""`). Remove or guard `del event` at line 80 so the payload is accessible. When `transcript_path` is present, backfill that specific file directly rather than probing the directory.
4. Update `session_log.get_current_session_jsonl()` at `session_log.py:63` to resolve paths for non-Claude-Code hosts. Pass host context through to `get_project_folder()`.
5. Update `ll-logs discover` at `cli/logs.py:408` and `discover_all_projects()` at line 126 to scan host-specific session directories (not just `~/.claude/projects/`). Update `ll-messages extract` at `cli/messages.py:173` to pass host context.
6. Add tests for each call site with mocked Codex/OpenCode session directories. Model after `test_host_runner.py` patterns: `isolated_env` fixture (line 40), `resolve_host(env={...})` explicit-env testing (line 54), `shutil.which` mocking (line 77). For `get_project_folder()` tests, extend `test_user_messages.py` with `host="codex"` and `host="opencode"` cases.
7. Verify end-to-end: run backfill in a Codex project, confirm `message_events` / `sessions` / LCM DAG all populate correctly. Use `ll-session backfill --host codex` to test manual backfill, and verify `session_start` auto-backfill daemon via `test_hook_session_start.py` with a Codex payload including `transcript_path`.

## Impact

- **Priority**: P2 — Blocks the multi-host value proposition of EPIC-1707; Codex sessions are partially blind without it. Not P1 because live hook writes still work and Claude Code is unaffected.
- **Effort**: Medium — `get_project_folder()` is a single function with 3 call sites; host detection already exists in `resolve_host()`. Main effort is testing across host directory layouts.
- **Risk**: Low — Additive change; `host` parameter defaults to `"claude"` so existing callers are unaffected. Graceful fallback to `None` preserves existing degrade-to-noop behavior.
- **Breaking Change**: No

## Success Metrics

- `ll-session backfill` succeeds in a Codex project and populates `message_events` with non-zero rows.
- `session_start` auto-backfill daemon populates sessions for Codex without manual intervention.
- LCM summary DAG produces summary nodes for Codex sessions.
- `ll-history-context` returns corrections mined from Codex session history.

## Scope Boundaries

- **In scope**: Making `get_project_folder()` host-aware; updating the 3 call sites; testing with Codex and OpenCode session directories.
- **Out of scope**: Building a Pi adapter (FEAT-992); changing the session log format or JSONL parsing; cross-project aggregation; host-agnostic session directory for Pi (deferred until Pi adapter exists).

## Labels

`enh`, `captured`, `multi-host`

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:refine-issue` - 2026-06-04T23:12:24 - `51a4f1e1-9f20-480f-843f-156ec1efd738.jsonl`

- `/ll:capture-issue` - 2026-06-04T19:18:32Z - `15020717-6ee7-4d89-bd61-d70602429425.jsonl`

---

**Open** | Created: 2026-06-04 | Priority: P2
