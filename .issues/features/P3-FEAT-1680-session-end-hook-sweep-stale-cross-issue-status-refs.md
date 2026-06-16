---
id: FEAT-1680
title: Session-end hook to sweep stale cross-issue status references
type: FEAT
priority: P3
status: done
discovered_date: 2026-05-24
captured_at: '2026-05-24T17:21:20Z'
completed_at: '2026-06-01T14:13:54Z'
discovered_by: capture-issue
labels:
- hooks
- automation
- issue-management
parent: EPIC-1707
relates_to: [EPIC-2196]
decision_needed: false
confidence_score: 98
outcome_confidence: 91
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 23
score_change_surface: 25
---

# FEAT-1680: Session-end hook to sweep stale cross-issue status references

## Summary

Add a `Stop` hook that fires at the end of every Claude Code session. It collects
all issue IDs currently marked `status: done`, greps open issue files for prose
that still asserts those IDs are `open` or `in_progress`, and reports (or
auto-fixes) the stale references in one batched pass — after editing is complete,
so it doesn't interrupt mid-session work.

## Current Behavior

When an issue is marked `done`, prose in other open issue files (blocker notes,
concerns sections, session logs) may still reference that ID as `open`,
`in_progress`, or describe it as an active blocker. There is no automated
mechanism to detect or clean up these stale references. Engineers must manually
audit issue files after marking work done, which is easy to forget and causes
Claude Code to treat completed work as active in subsequent sessions.

## Expected Behavior

A `Stop` hook fires at the end of every Claude Code session. It collects all
issue IDs with `status: done`, greps open issue files for patterns like
`"<ID> is (still )?(open|in_progress|active)"` and `"blocked by .*<ID>"`
(where the blocker is already done), and prints a concise report (file path,
line number, matched phrase) for each stale reference found. If
`hooks.stale_ref_fix: auto` is set in `ll-config.json`, stale phrases are
rewritten automatically. The hook exits 0 in all cases and completes in under
2s on repos with ~400 issue files when no matches are found.

## Motivation

When an issue is marked `done`, prose in other issue files (blockers notes,
concerns sections, session logs) often still says "X is still open" or "blocked
by X". These stale phrases confuse Claude in future sessions, causing it to treat
done work as active. Manual cleanup is easy to forget. A session-end hook catches
the drift automatically without slowing down the session itself.

## Use Case

Engineer marks FEAT-1112 `done` mid-session. At session end the hook runs,
finds ENH-1114 saying "FEAT-1112 is still `open`", flags it in the terminal
summary. Engineer can approve an auto-fix or address it manually before the next
session starts.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The correct implementation architecture follows the **Python dispatch pattern** already used by `session_start` and `pre_compact` hooks. All Python-backed hooks use a 2-line bash adapter that pipes to `python -m little_loops.hooks <intent>`; a direct `python script.py` invocation is non-standard in this codebase.

1. **Add dispatch entry** in `scripts/little_loops/hooks/__init__.py:_dispatch_table()`:
   ```python
   from . import sweep_stale_refs
   built_ins["session_end"] = sweep_stale_refs.handle
   ```
   Model after how `"session_start": session_start.handle` is registered in the same function.

2. **Create adapter script** `hooks/adapters/claude-code/session-end.sh` (2-liner pattern from `hooks/adapters/claude-code/session-start.sh`):
   ```bash
   #!/usr/bin/env bash
   INPUT=$(cat)
   echo "$INPUT" | python -m little_loops.hooks session_end
   exit $?
   ```

3. **Create handler module** `scripts/little_loops/hooks/sweep_stale_refs.py` with `handle(event: LLHookEvent) -> LLHookResult`:
   - Wrap entire body in `try/except Exception: return LLHookResult(exit_code=0)` (graceful degradation pattern from `pre_compact.handle()`)
   - Collect done IDs: `done_issues = find_issues(config, status_filter={"done"})` → `done_ids = {i.issue_id for i in done_issues}` (from `issue_parser.py:find_issues()`)
   - Collect open files: `open_issues = find_issues(config)` — default call skips done/cancelled/deferred automatically
   - For each open file, apply compiled regex excluding code-fence regions (model after `anchor_sweep.py:_sweep_file()` which uses `_CODE_FENCE` from `text_utils.py` via `_in_fence()`)
   - Stale ref regex: `re.compile(r'\b(ENH|BUG|FEAT|EPIC)-(\d+)\b')` to find ID mentions, then check surrounding context against stale-phrase patterns
   - Read `hooks.stale_ref_fix` from `BRConfig` (from `config/core.py:BRConfig`); when `"auto"`, call `atomic_write(path, new_content)` from `file_utils.py`
   - Return `LLHookResult(exit_code=0)` always; report findings via `result.feedback` (written to stderr, visible in Claude Code session output)

4. **Update `config-schema.json`** — add `stale_ref_fix` to the `hooks` properties object (currently `additionalProperties: false` at line 1139, so the new key MUST be added here or validation will reject it):
   ```json
   "stale_ref_fix": {
     "type": "string",
     "enum": ["report", "auto"],
     "default": "report",
     "description": "..."
   }
   ```

5. **Wire in `hooks/hooks.json`** Stop section — append a new entry to the `"Stop"` array. No `matcher` field (Stop events don't support matchers — confirmed by inspecting existing Stop entries):
   ```json
   {
     "hooks": [
       {
         "type": "command",
         "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/session-end.sh",
         "timeout": 15,
         "statusMessage": "Sweeping stale cross-issue status references..."
       }
     ]
   }
   ```

6. **Add unit tests** to `scripts/tests/test_sweep_stale_refs.py`. Model after `test_hook_session_start.py` and `test_hook_post_tool_use.py`:
   - `_event()` factory helper returning `LLHookEvent(host="claude-code", intent="session_end", payload={})`
   - `_write_config(tmp_path, stale_ref_fix="report"|"auto")` helper
   - `in_tmp` fixture using `monkeypatch.chdir(tmp_path)`
   - Test classes: `TestSweepStaleRefsBaseline` (no issues dir), `TestSweepStaleRefsDetection` (single + multi-file), `TestSweepStaleRefsAutoFix`, `TestSweepStaleRefsGracefulDegradation`

7. **Verification**: `python -m pytest scripts/tests/test_sweep_stale_refs.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/hooks/__init__.py` module docstring — the docstring bullet list enumerates each built-in intent by name; add a `session_end` bullet alongside the existing five
9. Update `scripts/tests/test_hook_intents.py` — in `test_dispatch_table_merges_hook_intent_registry`, add `assert "session_end" in table`; also add `test_dispatch_session_end_happy_path` subprocess test (follow `test_dispatch_pre_tool_use_happy_path`: assert `returncode == 0`, no stdout/stderr)
10. Update `scripts/tests/test_hooks_integration.py` — add integration test class (e.g. `TestSessionEndSweep`) following `TestSessionStartValidation` pattern: write a shell fixture pointing at `hooks/adapters/claude-code/session-end.sh`, run via `subprocess.run(input="{}", ...)`, assert `returncode == 0`
11. Update `scripts/tests/test_config_schema.py` — add `test_stale_ref_fix_in_schema` following `test_analytics_in_schema` pattern; assert `stale_ref_fix` present in `hooks["properties"]` with `type == "string"` and `enum == ["report", "auto"]`
12. Update `docs/reference/API.md` — add `session_end` to the built-in intent list in `### LLHookIntentExtension`; add `session-end.sh` to the adapter file list in `### main_hooks`
13. Update `docs/reference/HOST_COMPATIBILITY.md` — reconcile `stop` row in the hook intent parity matrix to reflect `session_end` as the Python dispatch intent name
14. Update `docs/reference/EVENT-SCHEMA.md` — add `session_end` entry to `#### Per-intent payload notes`
15. Update `docs/ARCHITECTURE.md` — add `session-end.sh` to the `hooks/adapters/claude-code/` directory tree block
16. Update `docs/development/TROUBLESHOOTING.md` — add `chmod +x hooks/adapters/claude-code/session-end.sh` to the "Hook not executing" chmod block
17. Update `docs/claude-code/write-a-hook.md` — add `session-end.sh` to the adapter file list in the "Adapter flow" section

## Integration Map

### Files to Modify
- `hooks/hooks.json` — append entry to `"Stop"` array (no `matcher` field; use `bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/session-end.sh`, `timeout: 15`)
- `scripts/little_loops/hooks/__init__.py` — add `"session_end": sweep_stale_refs.handle` to `_dispatch_table()` built-ins dict; update `_USAGE` string
- `config-schema.json` — add `stale_ref_fix: {type: string, enum: ["report","auto"]}` to `hooks.properties`; required because `hooks` has `additionalProperties: false` (line 1139)

### New Files
- `scripts/little_loops/hooks/sweep_stale_refs.py` — new hook handler; public API is `handle(event: LLHookEvent) -> LLHookResult`
- `hooks/adapters/claude-code/session-end.sh` — 2-line adapter (pipes stdin to `python -m little_loops.hooks session_end`); model after `hooks/adapters/claude-code/session-start.sh`
- `scripts/tests/test_sweep_stale_refs.py` — unit tests

### Dependent Files (Callers/Importers)
- `scripts/little_loops/hooks/__init__.py:_dispatch_table()` — invokes `sweep_stale_refs.handle`; add import and entry
- `scripts/little_loops/issue_parser.py:find_issues()` — used to collect done IDs (`status_filter={"done"}`) and open file list (default call)
- `scripts/little_loops/frontmatter.py:parse_frontmatter()` — reads `status:` with `STATUS_SYNONYMS` coercion already applied
- `scripts/little_loops/text_utils.py:_CODE_FENCE` — regex for code-fence span detection; import to exclude fence regions from grep
- `scripts/little_loops/file_utils.py:atomic_write()` — safe file write for auto-fix mode
- `scripts/little_loops/config/core.py:BRConfig` — read `hooks.stale_ref_fix` setting

### Similar Patterns
- `scripts/little_loops/hooks/session_start.py:handle()` — canonical hook handler structure (LLHookEvent → LLHookResult, config loading, feedback pattern)
- `scripts/little_loops/hooks/pre_compact.py:handle()` — canonical graceful-degradation pattern (`try/except Exception: return LLHookResult(exit_code=0)`)
- `scripts/little_loops/issues/anchor_sweep.py:_sweep_file()` — file scanning with code-fence exclusion (`_in_fence()` + `atomic_write()` for safe rewrite)
- `hooks/adapters/claude-code/session-start.sh` — 2-line adapter template
- `scripts/little_loops/hooks/post_tool_use.py:handle()` — config-gated feature pattern (`feature_enabled(config, "analytics.enabled")`)

### Tests
- `scripts/tests/test_sweep_stale_refs.py` (new) — unit tests covering: no-match fast path, single stale ref detection, multiple files, auto-fix mode, graceful degradation on missing issues dir or broken config
- `scripts/tests/test_hook_session_start.py` — reference for `_event()` factory + `in_tmp` fixture pattern
- `scripts/tests/test_hook_post_tool_use.py` — reference for config-gated feature test class structure

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_intents.py` — update `test_dispatch_table_merges_hook_intent_registry` to add `assert "session_end" in table`; add `test_dispatch_session_end_happy_path` subprocess test following the `test_dispatch_pre_tool_use_happy_path` pattern (`returncode == 0`, no stdout/stderr)
- `scripts/tests/test_hooks_integration.py` — add new integration test class for `session-end.sh` adapter following the `TestSessionStartValidation` / `TestContextHandoffSentinel` pattern (subprocess invocation of the adapter, assert `returncode == 0`)
- `scripts/tests/test_config_schema.py` — add `test_stale_ref_fix_in_schema` following the `test_analytics_in_schema` pattern; assert `stale_ref_fix` key exists in `hooks.properties` with `type == "string"` and `enum == ["report", "auto"]`; also confirms `additionalProperties: false` is preserved on the `hooks` block

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### LLHookIntentExtension` behavior bullets explicitly enumerate built-in intents (`pre_compact`, `session_start`, `user_prompt_submit`, `post_tool_use`, `pre_tool_use`); add `session_end`; also update `### main_hooks` adapter integration bullet that lists `precompact.sh`, `session-start.sh` — add `session-end.sh`
- `docs/reference/HOST_COMPATIBILITY.md` — `## Hook intents` parity matrix has a `stop` row; clarify/update this row to reflect that `session_end` is the Python dispatch intent name for the Claude Code `Stop` event
- `docs/reference/EVENT-SCHEMA.md` — `#### Per-intent payload notes` section has bullets for `pre_compact` and `session_start` only; add `session_end` bullet describing handler reads (done IDs from `find_issues`, `hooks.stale_ref_fix` from `BRConfig`) and outputs (findings in `result.feedback`, always exits 0)
- `docs/ARCHITECTURE.md` — `## Directory Structure` tree explicitly lists `hooks/adapters/claude-code/precompact.sh` and `session-start.sh`; add `session-end.sh` entry
- `docs/development/TROUBLESHOOTING.md` — `chmod +x` block in "Hook not executing" section lists each adapter script; add `chmod +x hooks/adapters/claude-code/session-end.sh`
- `docs/claude-code/write-a-hook.md` — "Adapter flow" bullet names `precompact.sh`, `session-start.sh`; add `session-end.sh`

### Configuration
- `ll-config.json` — optional `hooks.stale_ref_fix: "report" | "auto"` knob (must also be added to `config-schema.json`)

## API / Interface

```json
// hooks/hooks.json — append to "Stop" array
// Note: Stop entries have NO "matcher" field (confirmed: both existing Stop entries omit it)
{
  "hooks": [
    {
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/session-end.sh",
      "timeout": 15,
      "statusMessage": "Sweeping stale cross-issue status references..."
    }
  ]
}
```

```bash
# hooks/adapters/claude-code/session-end.sh (2-line adapter pattern)
#!/usr/bin/env bash
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks session_end
exit $?
```

```python
# scripts/little_loops/hooks/sweep_stale_refs.py
# Public interface: handle(event: LLHookEvent) -> LLHookResult
# Exits 0 always (findings are advisory, not blocking)
# Feedback string (stderr) lists stale refs; empty string = no findings
```

```python
# scripts/little_loops/hooks/__init__.py — _dispatch_table() addition
from . import sweep_stale_refs
built_ins["session_end"] = sweep_stale_refs.handle
```

Optional config knob in `ll-config.json` (requires `config-schema.json` update):
```json
"hooks": {
  "stale_ref_fix": "report"   // "report" | "auto"
}
```

The Stop hook wire format payload received by the adapter (Claude Code injects):
```json
{
  "session_id": "...",
  "transcript_path": "...",
  "cwd": "...",
  "permission_mode": "...",
  "hook_event_name": "Stop",
  "stop_hook_active": true
}
```

## Acceptance Criteria

- [ ] Hook handler exists at `scripts/little_loops/hooks/sweep_stale_refs.py` with `handle(event: LLHookEvent) -> LLHookResult`
- [ ] Adapter script exists at `hooks/adapters/claude-code/session-end.sh`
- [ ] `"session_end"` intent registered in `_dispatch_table()` in `scripts/little_loops/hooks/__init__.py`
- [ ] Registered in `hooks/hooks.json` under `Stop` event (no `matcher` field)
- [ ] `config-schema.json` updated to add `stale_ref_fix` to `hooks.properties` (required: `additionalProperties: false` blocks unknown keys)
- [ ] Given a done issue ID, correctly identifies files with stale `is open` / `in_progress` prose referencing that ID
- [ ] Grep skips code-fence regions (avoid false positives on code examples referencing issue IDs)
- [ ] Outputs file path + line number + matched text per finding (via `result.feedback`)
- [ ] Exits 0 in all cases (never blocks session end)
- [ ] Completes in < 2s on a repo with ~400 issue files when no matches found
- [ ] Unit tests in `scripts/tests/test_sweep_stale_refs.py`

## Impact

- **Priority**: P3 — improves issue hygiene and prevents context confusion in future sessions; non-blocking quality improvement
- **Effort**: Small — ~100-line Python handler, 2-line adapter script, `hooks/hooks.json` + `config-schema.json` + dispatch-table registration, unit tests; reuses `find_issues()`, `parse_frontmatter()`, `_CODE_FENCE`, `atomic_write()`
- **Risk**: Low — hook exits 0 always; auto-fix mode requires explicit opt-in via config; grep-only path is purely advisory
- **Breaking Change**: No

## Out of Scope

- Fixing `blocked_by:` frontmatter fields (separate concern; `ll-deps` handles
  dependency validation)
- Real-time (PostToolUse) triggering — deferred due to interleaving complexity
- Structured reference markers (Approach B from brainstorm) — separate ENH if
  convention is adopted later
- Wiring for non-Claude-Code hosts (opencode, codex) — adapter script is Claude-Code-specific;
  other host adapters can be added independently

---

**Open** | Created: 2026-05-24 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-01T14:00:42 - `97825a43-1502-449e-a519-9fff2717e285.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `e6c6100d-8d0a-4a4d-8316-2fe6eef235c0.jsonl`
- `/ll:wire-issue` - 2026-06-01T13:55:59 - `78af0d26-ea86-4156-b799-4668c991ef85.jsonl`
- `/ll:refine-issue` - 2026-06-01T13:49:17 - `424ba3b0-46e9-434c-b57f-a44b4cda057b.jsonl`
- `/ll:refine-issue` - 2026-06-01T00:00:00
- `/ll:verify-issues` - 2026-05-31T05:40:07 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-24T17:28:21 - `20c144e8-2658-4919-b9a3-e1bfd4e0786b.jsonl`

- `/ll:capture-issue` - 2026-05-24T17:21:20Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a638383a-aa90-4ed6-80c0-1913cf58a71c.jsonl`
