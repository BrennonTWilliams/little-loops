---
id: ENH-1945
title: Make session log discovery host-aware for Codex/OpenCode/Pi backfill
type: ENH
priority: P2
status: open
discovered_date: 2026-06-04
captured_at: '2026-06-04T19:18:32Z'
discovered_by: capture-issue
parent: EPIC-1707
decision_needed: false
labels:
- enh
- captured
- multi-host
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
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

> **Selected:** Option A — direct codebase fit; `_config_candidates()` at `config/core.py:74` is a near-identical precedent with the same `host: str | None` parameter pattern.

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

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-04.

**Selected**: Option A — Host-aware `get_project_folder()`

**Reasoning**: Option A is the established convention in this codebase for adding host awareness. `_config_candidates()` at `config/core.py:74` uses the identical pattern — keyword-only `host: str | None` parameter, string-equality branching (`host == "codex"`), and a docstring that explicitly says "Future hosts add a new branch here rather than a new code path elsewhere." Adding a `host=None` keyword-only parameter is fully backward-compatible with all 6 existing call sites. Option B would require migrating all call sites and updating 23 test patches, creating churn without benefit — and contradicts the project's stated extension-point convention.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: Host-aware `get_project_folder()` | 3/3 | 3/3 | 3/3 | 2/3 | **11/12** |
| Option B: New `resolve_session_dir()` wrapper | 1/3 | 1/3 | 1/3 | 2/3 | 5/12 |

**Key evidence**:
- **Option A**: `_config_candidates(project_root, *, host: str | None, state_dir: str | None)` at `config/core.py:74` is a near-line-for-line precedent — same keyword-only `host` parameter, same string-equality branching, same docstring extension-point convention. `resolve_config_path()` at `config/core.py:99` already demonstrates the `os.environ.get("LL_HOOK_HOST")` auto-detection pattern. All 6 call sites pass only `cwd` and are unaffected by a keyword-only parameter addition.
- **Option B**: No existing pattern of creating a new wrapper solely to avoid modifying a backward-compatible function. `_config_candidates()` was modified to accept `host` rather than wrapped — proving the codebase convention is to add parameters, not wrappers. 23 test patches across 5 files would need mock-target migration. `discover_all_projects()` at `cli/logs.py:126` hardcodes `~/.claude/projects/` and wouldn't benefit from any wrapper — it needs a separate fix either way.

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

- `scripts/little_loops/cli/logs.py:244,254` — `ll-logs discover` calls `get_project_folder()`; also `discover_all_projects()` at line 126 hardcodes `~/.claude/projects/` iteration
- `scripts/little_loops/cli/messages.py:173` — `ll-messages extract` calls `get_project_folder()`
- `scripts/little_loops/user_messages.py:14-16` — internal `extract_user_messages()` docstring references
- `scripts/little_loops/session_store.py:1503,1535` — `backfill()` defaults `jsonl_files=None`, guard skips JSONL entirely when None; full backfill (no `--since`) also fails for non-Claude-Code hosts
- `scripts/little_loops/session_store.py:1323` — `_compact_session_conn()` queries `message_events` (LCM DAG leaf nodes); empty when backfill didn't run
- `scripts/little_loops/session_store.py:1099` — `mine_corrections_from_messages()` scans `message_events`; no corrections mined for non-Claude-Code hosts
- `scripts/little_loops/history_reader.py:933` — `project_digest()` consumes session data from multiple tables; all empty for non-Claude-Code hosts

_Wiring pass added by `/ll:wire-issue` — transitive beneficiaries (use `append_session_log_entry` which defaults `session_jsonl=None` → auto-detects via `get_current_session_jsonl()`):_
- `scripts/little_loops/fsm/executor.py:1089` — calls `get_current_session_jsonl()` for loop session logging; host-awareness enables FSM loops on non-Claude-Code hosts
- `scripts/little_loops/parallel/orchestrator.py:37` — imports `append_session_log_entry`; session log entries from parallel workers will auto-resolve correctly for all hosts
- `scripts/little_loops/issue_lifecycle.py:25` — imports `append_session_log_entry`; issue lifecycle logging works for all hosts
- `scripts/little_loops/cli/issues/append_log.py:23` — imports `append_session_log_entry`; `ll-issues append-log` works for all hosts
- `scripts/little_loops/issue_parser.py:62,577` — uses `parse_session_log`, `count_session_commands` which read session log entries; correct resolution benefits log-aware issue commands for all hosts
- `scripts/little_loops/cli/issues/show.py:232` — uses `count_session_commands`, `parse_session_log`; correct resolution benefits `ll-issues show` for all hosts

### Similar Patterns

- `resolve_host()` in `host_runner.py:751` already provides host detection — reuse its logic
- `_config_candidates()` in `config/core.py:74` — accepts `host: str | None` parameter and branches on `host == "codex"`; the closest existing pattern for adding a `host` parameter to `get_project_folder()`; docstring at line 88 explicitly notes "Future hosts (e.g. FEAT-992 Pi) add a new branch here"
- `pre_compact.handle()` at `hooks/pre_compact.py:55` — already consumes `transcript_path` from Codex hook payloads (`transcript_path = payload.get("transcript_path") or ""`); proves the data flows through the adapter and dispatcher correctly; the only missing link is `session_start.handle()` consuming it
- `hooks/adapters/codex/` adapter scripts set `export LL_HOOK_HOST=codex` — the Python dispatcher at `hooks/__init__.py:125` reads this as `os.environ.get("LL_HOOK_HOST", "claude-code")`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Verified**: All line numbers in the issue match actual code (355-381, 304, 132, 75, 244, 254, 173) at time of prior refinement pass. **2026-06-04 re-verification pass**: `discover_all_projects()` is at line 126 (was 140 in earlier research); all other line numbers confirmed current.
- **Additional hardcoding**: `discover_all_projects()` at `cli/logs.py:126` also hardcodes `~/.claude/projects/` iteration — `ll-logs discover` is also Claude-Code-only
- **Full-backfill gap**: `backfill()` in `session_store.py:1503` defaults `jsonl_files=None`, and the guard at line 1535 (`if jsonl_files:`) skips JSONL backfill entirely when `None`. So even full backfill (no `--since`) produces zero `message_events`/`sessions` for non-Claude-Code hosts
- **Host naming verified consistent**: Re-verification on 2026-06-04 confirmed `_HOST_RUNNER_REGISTRY` keys (`"claude-code"`, `"codex"`, `"opencode"`, `"pi"`), `LL_HOOK_HOST` adapter values (`"codex"`, `"opencode"`), and `resolve_host().name` all use identical string conventions. The dispatcher at `hooks/__init__.py:125` defaults `LL_HOOK_HOST` to `"claude-code"` (not `"claude"`). The earlier concern about a `"claude"`/`"claude-code"` mismatch was unfounded — no such discrepancy exists in the codebase. The `get_project_folder()` host parameter should use these registry names for consistency with `resolve_host().name`.
- **Failure table**: 16 distinct call sites fail silently for non-Claude-Code hosts — including LCM summary DAG leaf nodes (`_compact_session_conn()` at `session_store.py:1323` queries `message_events` which is empty), correction mining (`mine_corrections_from_messages()` at `session_store.py:1099`), and project digest (all SECTION_PROVIDERS consuming session data)
- **2026-06-04 re-verification pass (pass 4)**: All critical line numbers re-verified against current code — no drift since prior passes. `get_project_folder()` at `user_messages.py:355`, `_config_candidates()` at `config/core.py:74`, `del event` at `session_start.py:80`, `_run_backfill()` at `session_start.py:127`, `discover_all_projects()` at `cli/logs.py:126`, `resolve_host()` at `host_runner.py:751`, `append_session_log_entry()` at `session_log.py:86`, `get_current_session_jsonl()` at `session_log.py:63` — all confirmed.
- **OpenCode `HostRunner` is a stub**: `OpenCodeRunner` at `host_runner.py:589-590` raises `HostNotConfigured` on all `build_*` methods. This means `get_project_folder(host="opencode")` can work for session directory probing, but `resolve_host()` with `LL_HOOK_HOST=opencode` cannot execute commands. Implementation step 5 should handle this: `ll-logs discover --host opencode` and `ll-messages extract --host opencode` should probe the OpenCode session directory regardless of whether the runner can exec. The session-discovery layer and the command-execution layer have different host-support thresholds — they should not be coupled.
- **`opencode` absent from `_PROBE_ORDER`**: `_PROBE_ORDER` at `host_runner.py:736-740` lists only `claude-code`, `codex`, `pi`. Binary-probe auto-detection (`shutil.which`) will never resolve `opencode`. For `--host` auto-detection in CLI tools (`ll-session backfill`, `ll-logs discover`, `ll-messages extract`), the detection chain should be: `--host` flag → `LL_HOOK_HOST` env → `orchestration.host_cli` config → default `"claude-code"`. Do not use `resolve_host()` for CLI auto-detection — it would raise `HostNotConfigured` for opencode projects with no host binary on PATH, crashing the CLI instead of gracefully falling back.
- **No existing `--host` CLI flag precedent**: Searched all of `scripts/little_loops/cli/` — zero `add_argument("--host")` calls exist. ENH-1945 establishes the pattern. The closest analog is `ll-doctor` at `cli/doctor.py:140-141` which auto-detects via `resolve_host()` + `apply_host_cli_from_config()` but does not expose a `--host` flag. The new `--host` flag should use `choices=["claude-code", "codex", "opencode", "pi"]` and `default=None` (meaning auto-detect).
- **Existing test mocks confirmed safe**: `patch("little_loops.session_log.get_project_folder", return_value=...)` and similar mocks replace the entire function object — adding `*, host: str | None = None` to the real signature does not affect any existing test. The lambda pattern `monkeypatch.setattr(um, "get_project_folder", lambda *a, **kw: in_tmp)` at `test_hook_session_start.py:333` already uses `*a, **kw` to absorb any future parameters. No test breakage expected from the signature change.

### Tests

- `scripts/tests/test_user_messages.py` — add test for `get_project_folder()` with `host="codex"` param
- `scripts/tests/test_session_store.py` — add backfill tests with non-Claude-Code session directories
- `scripts/tests/test_session_log.py` — test JSONL path resolution for Codex
- `scripts/tests/test_hook_session_start.py` — add `LLHookEvent(host="codex", payload={"transcript_path": ...})` tests; verify `_run_backfill()` consumes `transcript_path` directly
- `scripts/tests/test_ll_session.py` — add `--host codex` flag integration tests with mock Codex session dir
- `scripts/tests/test_ll_logs.py` — add discover/extract tests with `~/.codex/sessions/...` alongside `~/.claude/projects/...`
- `scripts/tests/test_cli.py` — add companion `ll-logs discover` tests with Codex session directories (currently hardcodes `~/.claude/projects/`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_assistant_messages.py` — existing backfill tests are Claude-Code-only; add round-trip test that creates JSONL in Codex session dir, runs `backfill()` with explicit `jsonl_files`, and verifies `message_events` populated
- `scripts/tests/test_hook_intents.py` — already tests `LL_HOOK_HOST` dispatch; add `session_start` intent with `transcript_path` in Codex payload to verify dispatcher-to-handler round-trip
- `scripts/tests/test_codex_adapter.py` — already tests adapter round-trips; verify `session-start.sh` stdin JSON includes `transcript_path` when present in Codex event payload

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — document host-specific session directories
- `docs/reference/API.md` — update `get_project_folder()` signature docs
- `docs/reference/CLI.md` — document new `--host` flag for `ll-session backfill`; broaden `ll-messages`/`ll-logs` descriptions from "Claude Code session logs" to host-agnostic language
- `docs/reference/EVENT-SCHEMA.md:81` — update or qualify the statement "`session_start` — reads no payload keys; operates via `Path.cwd()`" since `_run_backfill()` will now consume `transcript_path` payload field for non-Claude-Code hosts
- `docs/ARCHITECTURE.md:564,600,633,644,1192` — note that backfill/session_start behavior is now host-aware; update `transcript_path` consumption note at line 1192 to include SessionStart

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md:65` — `ll-session` subcommand listing doesn't mention `--host`; add after implementation
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:62-82` — describes `ll-messages` as extracting from "Claude Code session logs"; broaden to host-agnostic
- `docs/guides/EXAMPLES_MINING_GUIDE.md:134` — same "Claude Code" phrasing

### Configuration

- Host detection is automatic via `LL_HOOK_HOST` env var (already set by adapters) and `orchestration.host_cli` config key (`config-schema.json:1312`). No new config keys needed.
- `config-schema.json:1173` — `hooks.host.enum` values `["claude-code", "opencode", "codex"]`; no Pi value yet (deferred until FEAT-992). The `--host` auto-detection should read `hooks.host` as one source alongside `LL_HOOK_HOST` and `orchestration.host_cli`.
- `scripts/little_loops/config/core.py:41` — add `CODEX_PROJECTS_DIR` constant alongside existing `CODEX_CONFIG_DIR` for Codex session directory probing

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:1173` — `hooks.host` key is consumed for `--host` auto-detection (new consumption of existing key; no schema change needed)

### Host Detection Design (added by `/ll:refine-issue` pass 4)

_These design constraints emerged from fresh codebase analysis and constrain the `--host` auto-detection implementation:_

**Do NOT use `resolve_host()` for CLI auto-detection.** `resolve_host()` at `host_runner.py:751` falls through to a binary probe (`shutil.which`) that only covers `claude-code`, `codex`, `pi` — `opencode` is absent from `_PROBE_ORDER` at line 736-740. If `LL_HOOK_HOST` is unset and no host binary is on PATH, `resolve_host()` raises `HostNotConfigured`, crashing the CLI. Session discovery tools should degrade gracefully (fall back to `"claude-code"` default) rather than crashing.

**Recommended detection chain for `--host` CLI flag:**

```
1. Explicit --host flag value (if provided)
2. LL_HOOK_HOST env var (set by adapters)
3. orchestration.host_cli config key (from ll-config.json)
4. Default: "claude-code"
```

This is a simpler chain than `resolve_host()` — it skips the binary probe entirely. The binary probe is appropriate for command execution (where you need a real binary) but not for session directory discovery (where you're just probing a filesystem path). A user on a machine with only Codex installed, running `ll-session backfill`, should get Codex session discovery from `LL_HOOK_HOST=codex` (set by the adapter) — not a crash because `claude` isn't on PATH.

**OpenCode stub caveat:** `OpenCodeRunner` at `host_runner.py:589-590` raises `HostNotConfigured` on all `build_*` methods. Session discovery for `opencode` should work independently — probing the OpenCode session directory does not require the runner to execute commands. The session-discovery layer and the command-execution layer have different host-support thresholds and must not be coupled.

## Implementation Steps

1. Add `host` parameter to `get_project_folder(cwd, *, host: str | None = None)` following the `_config_candidates()` pattern at `config/core.py:74`. Implement host-specific helpers for `"codex"` and `"opencode"` session directories. Use `os.environ.get("LL_HOOK_HOST", "claude-code")` for auto-detection when `host=None`. Add a `CODEX_PROJECTS_DIR` constant alongside `CODEX_CONFIG_DIR` at `config/core.py:41`.
2. Update `ll-session backfill` at `cli/session.py:290` to accept `--host` flag (default auto-detect from `LL_HOOK_HOST` env / `orchestration.host_cli` config). Also fix full-backfill mode (line 319): pass discovered `jsonl_files` to `backfill()` so JSONL backfill works even without `--since`.
3. Update `session_start._run_backfill()` at `hooks/session_start.py:127` to consume `transcript_path` from the hook payload when available, following the exact pattern at `pre_compact.py:55` (`transcript_path = payload.get("transcript_path") or ""`). Remove or guard `del event` at line 80 so the payload is accessible. When `transcript_path` is present, backfill that specific file directly rather than probing the directory.
4. Update `session_log.get_current_session_jsonl()` at `session_log.py:63` to resolve paths for non-Claude-Code hosts. Pass host context through to `get_project_folder()`.
5. Update `ll-logs discover` at `cli/logs.py:408` and `discover_all_projects()` at line 126 to scan host-specific session directories (not just `~/.claude/projects/`). Update `ll-messages extract` at `cli/messages.py:173` to pass host context.
6. Add tests for each call site with mocked Codex/OpenCode session directories. Model after `test_host_runner.py` patterns: `isolated_env` fixture (line 40), `resolve_host(env={...})` explicit-env testing (line 54), `shutil.which` mocking (line 77). For `get_project_folder()` tests, extend `test_user_messages.py` with `host="codex"` and `host="opencode"` cases.
7. Verify end-to-end: run backfill in a Codex project, confirm `message_events` / `sessions` / LCM DAG all populate correctly. Use `ll-session backfill --host codex` to test manual backfill, and verify `session_start` auto-backfill daemon via `test_hook_session_start.py` with a Codex payload including `transcript_path`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update host-specific error messages to be host-generic:
   - `cli/session.py:306` — `"No Claude project folder found; cannot discover JSONL files."` → host-aware wording
   - `cli/logs.py:246-247` — `"No Claude project folder found for: {cwd_path}"` and `"Expected: ~/.claude/projects/..."` → host-aware wording
   - `cli/messages.py:176-177` — same pattern of Claude-Code-specific error messages
9. Update `docs/reference/EVENT-SCHEMA.md:81` — remove or qualify the statement "`session_start` — reads no payload keys; operates via `Path.cwd()`" since `_run_backfill()` will now consume `transcript_path` from the payload for non-Claude-Code hosts.
10. Update `docs/reference/CLI.md:1806-1807` — document the new `--host` flag for `ll-session backfill`; broaden `ll-messages`/`ll-logs` descriptions from "Claude Code session logs" to host-agnostic language.
11. Update `docs/ARCHITECTURE.md:564,600,633,644` — note that backfill/session_start behavior is now host-aware.
12. Update test fixtures for host-aware directory creation:
    - `test_ll_logs.py:33,553` — `_make_project_dir()` hardcodes `~/.claude/projects/`; add Codex/OpenCode directory helpers
    - `test_cli.py:2939,2958` — discover tests create only `~/.claude/projects/`; add companion tests with Codex session dirs
    - `test_hook_session_start.py:31` — `_event()` helper creates `LLHookEvent` with empty payload; add `_codex_event()` variant with `transcript_path`
13. Update `test_ll_session.py:483-499` — `test_since_calls_backfill_incremental` mocks `get_project_folder` on the CLI path; verify mock still works with updated import path or signature.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-04 (re-evaluated 2026-06-04T23:55:00, re-evaluated 2026-06-05T02:45:00)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- Codex session directory layout not fully confirmed — CLI probing paths (`ll-session backfill` without `--since`, `ll-logs discover`) need layout verification during implementation. `transcript_path` eliminates this for `session_start`/`session_log` paths.
- 7 test files need new host-aware test cases; the specific Codex/OpenCode backfill paths are currently untested, and existing `get_project_folder` mocks will need signature updates for the new `host` keyword parameter.

_Note: Prior risk factor about host naming inconsistency removed — re-verification confirmed `_HOST_RUNNER_REGISTRY` keys and `LL_HOOK_HOST` defaults use identical `"claude-code"` convention; no discrepancy exists._

## Session Log
- `/ll:refine-issue` - 2026-06-05T02:31:21 - `f09b04f7-6149-4dd9-8ab2-cba36c640b61.jsonl`
- `/ll:refine-issue` - 2026-06-04T23:50:47 - `849453dc-052d-4d7f-89cc-55354ccfde5a.jsonl`
- `/ll:refine-issue` - 2026-06-04T23:50:31 - `8826ca14-a9b9-4717-b939-4425b44d5d7c.jsonl`
- `/ll:confidence-check` - 2026-06-04T23:55:00 - `2d527f2f-a26e-4fef-a416-cbfeb70ef7af.jsonl`
- `/ll:confidence-check` - 2026-06-04T23:45:00 - `4627729e-f88a-487e-88f9-6298bfd77cbd.jsonl`
- `/ll:decide-issue` - 2026-06-04T23:32:03 - `ab09a645-db24-4bab-bd83-45ebf6d1f4bf.jsonl`
- `/ll:confidence-check` - 2026-06-04T23:30:00 - `e484df0a-bfc4-4607-bd41-973d4785157e.jsonl`
- `/ll:wire-issue` - 2026-06-04T23:21:59 - `d827f3a5-6a61-49a6-9999-a9cdd389d50d.jsonl`
- `/ll:refine-issue` - 2026-06-04T23:12:24 - `51a4f1e1-9f20-480f-843f-156ec1efd738.jsonl`

- `/ll:capture-issue` - 2026-06-04T19:18:32Z - `15020717-6ee7-4d89-bd61-d70602429425.jsonl`
- `/ll:confidence-check` - 2026-06-05T02:45:00 - `d3831c55-0b33-4127-9ff5-55a6e3c393cb.jsonl`

---

**Open** | Created: 2026-06-04 | Priority: P2
