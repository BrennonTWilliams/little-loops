---
id: FEAT-1156
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: issue-size-review
blocked_by:
- FEAT-1112
parent: FEAT-1113
relates_to:
- ENH-152
- ENH-495
- FEAT-150
- FEAT-1157
- FEAT-1158
decision_needed: false
implementation_order_risk: true
confidence_score: 100
outcome_confidence: 72
score_complexity: 15
score_test_coverage: 17
score_ambiguity: 20
score_change_surface: 20
size: Very Large
---

# FEAT-1156: PreCompact Handoff Hook — Core Implementation

## Summary

Implement `scripts/little_loops/hooks/pre_compact_handoff.py` (Python handler) and
`hooks/adapters/claude-code/precompact-handoff.sh` (thin Claude Code adapter) with priority-tiered
snapshot logic, 2KB size-capping, and idempotency, then register the adapter as a second PreCompact
hook in `hooks/hooks.json`.

## Current Behavior

No automatic handoff snapshot is written before context compaction. Users must manually run
`/ll:handoff` to generate `.ll/ll-continue-prompt.md`. If a PreCompact event fires without a prior
manual handoff, session continuity state (active issues, file edits, open decisions) is lost.

## Expected Behavior

`pre_compact_handoff.handle()` fires automatically on every PreCompact event and writes
`.ll/ll-continue-prompt.md` (≤2KB, priority-tiered) before context is compacted. An idempotency
guard skips the write when the snapshot is already fresh relative to `compacted_at` in
`.ll/ll-precompact-state.json`.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Motivation

`/ll:handoff` today is a manual step. Claude Code's PreCompact event fires before context
compaction; hooking into it ensures a continuity snapshot is always written before state is lost.
This is the core deliverable of FEAT-1113.

## Use Case

**Who**: Developer using little-loops with Claude Code's automatic context compaction enabled.

**Context**: Working on a long session that triggers a PreCompact event, with active issues in
progress and file edits staged.

**Goal**: Ensure session continuity is preserved automatically — without remembering to run
`/ll:handoff` manually before each potential compaction.

**Outcome**: After compaction, `/ll:resume` restores the session from `.ll/ll-continue-prompt.md`,
which was automatically written by the PreCompact hook.

## Acceptance Criteria

- `scripts/little_loops/hooks/pre_compact_handoff.py` exists with a `handle(event: LLHookEvent) -> LLHookResult` function
- `hooks/adapters/claude-code/precompact-handoff.sh` exists and is executable
- Hook fires on PreCompact and produces `.ll/ll-continue-prompt.md` ≤2KB
- Priority tiers drop LIFO under size pressure (tool-event summary dropped first, then decisions, etc.)
- Idempotency: skips write if `.ll/ll-continue-prompt.md` mtime is newer than `compacted_at` from `.ll/ll-precompact-state.json`
- `hooks/hooks.json` registers the new adapter as a second PreCompact entry (existing `precompact.sh` entry preserved and ordered first)
- Schema of written file passes `/ll:resume` compatibility: frontmatter with `session_date`, `session_branch`, `issues_in_progress` + sections `## Intent`, `## File Modifications`, `## Decisions Made`, `## Next Steps`
- `scripts/little_loops/hooks/__init__.py` dispatch table includes `"pre_compact_handoff"`

## Implementation

### New File: `scripts/little_loops/hooks/pre_compact_handoff.py`

Follow `pre_compact.py` structure exactly:

- `handle(event: LLHookEvent) -> LLHookResult` signature from `scripts/little_loops/hooks/types.py`
- Read `compacted_at` from `.ll/ll-precompact-state.json` (written by `pre_compact.handle()`)
- **Idempotency guard**: read `compacted_at` string (format `"%Y-%m-%dT%H:%M:%SZ"`) from `.ll/ll-precompact-state.json`; parse to epoch via `datetime.fromisoformat(compacted_at.replace("Z", "+00:00")).timestamp()`; compare to `Path(".ll/ll-continue-prompt.md").stat().st_mtime`; return `LLHookResult(exit_code=0)` if prompt mtime is newer than compacted epoch (already fresh)
- **Tiered section builder** (priority order):
  1. Active issues + loop state (always kept) — `subprocess` call to `ll-issues list --status in_progress`; loop state from `.loops/runs/` (glob latest run-dir JSON files); gracefully degrade to empty section if `.loops/runs/` does not exist or subprocess fails
  2. Files edited this session (always kept) — `subprocess` call to `git diff --name-only HEAD`
  3. Open decisions / blockers (kept if space)
  4. Recent tool-event summary (dropped first under size pressure)
- **LIFO 2KB cap**: extract into a pure helper `_build_content(sections: list[str], max_bytes: int = 2048) -> str` — `while len("\n\n".join(sections).encode()) > max_bytes: sections.pop()` then return `"\n\n".join(sections)`; test this function in isolation per Confidence Check Note on LIFO complexity
- Write via `acquire_lock(lock_path, timeout=3.0)` + `atomic_write(prompt_path, content)` — use `atomic_write` (text), NOT `atomic_write_json` (JSON), since `.ll/ll-continue-prompt.md` is markdown
- Best-effort fallback: `except TimeoutError: atomic_write(prompt_path, content)` (mirrors `pre_compact.py` lines 96–100)
- Wrap entire body in `try/except Exception: return LLHookResult(exit_code=0)` — failures must not surface
- Return `LLHookResult(exit_code=2, feedback="[ll] Session handoff snapshot written.")` on successful write; `LLHookResult(exit_code=0)` on skip or error

### New File: `hooks/adapters/claude-code/precompact-handoff.sh`

Thin adapter following `hooks/adapters/claude-code/precompact.sh` exactly (3 lines):

```bash
#!/usr/bin/env bash
INPUT=$(cat)
echo "$INPUT" | python -m little_loops.hooks pre_compact_handoff
exit $?
```

### Modify: `scripts/little_loops/hooks/__init__.py`

1. Add `pre_compact_handoff` to the lazy import block in `_dispatch_table()` (alongside `pre_compact`, `session_start`, etc.)
2. Add `"pre_compact_handoff": pre_compact_handoff.handle` to the `built_ins` dict
3. Add `pre_compact_handoff` to the `_USAGE` string (line 51)

### Modify: `hooks/hooks.json` (PreCompact section, lines 165–177)

Add a second object to the `"PreCompact": [...]` array **after** the existing entry:

```json
{
  "matcher": "*",
  "hooks": [
    {
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/precompact-handoff.sh",
      "timeout": 5,
      "statusMessage": "Writing session handoff..."
    }
  ]
}
```

**Ordering constraint**: this entry MUST be second. The existing `precompact.sh` entry writes
`compacted_at` to `.ll/ll-precompact-state.json`; this handler reads that value for its idempotency
guard. Reversing the order breaks the guard on first run.

### State Sources (FEAT-1112 Fallback)

FEAT-1112 (session store) is not yet implemented; gather state without it:

- **Files edited**: `git diff --name-only HEAD`
- **Active issues**: `ll-issues list --status in_progress` (single-value `--status` per BUG-1799)
- **Loop state**: glob `.loops/runs/` for most-recent run-dir JSON files; gracefully skip if directory absent

When FEAT-1262's `.ll/ll-session-events.jsonl` is present, prefer it as the primary source for
files-edited and decisions sections (FEAT-1264 formalizes this). Fall back to the above when absent.

### Output Schema

Follow `commands/handoff.md` structured schema. The consumer `commands/resume.md:56-68` validates
`## Intent` + `## Next Steps` section headings (schema detection by section heading presence, not frontmatter keys).

## Files to Modify

- `scripts/little_loops/hooks/__init__.py` — add `pre_compact_handoff` to dispatch table + `_USAGE` string
- `hooks/hooks.json:165-177` — add second PreCompact entry (after existing entry)

## New Files

- `scripts/little_loops/hooks/pre_compact_handoff.py` — Python handler
- `hooks/adapters/claude-code/precompact-handoff.sh` — thin Claude Code adapter

## References

- Related tests: FEAT-1157
- Docs/config updates: FEAT-1158
- Depends on: `pre_compact.py` (writes `compacted_at` before this handler reads it); FEAT-1112 (fallback available without it)
- Consumers of `ll-continue-prompt.md`: `commands/resume.md:28-56`, `scripts/little_loops/subprocess_utils.py:57-95`, `hooks/scripts/context-monitor.sh:370-407`

## Integration Map

### Files to Modify
- `hooks/hooks.json:165-177` — add second PreCompact entry
- `scripts/little_loops/hooks/__init__.py` — add dispatch entry + update `_USAGE` string

### New Files
- `scripts/little_loops/hooks/pre_compact_handoff.py` — Python handler
- `hooks/adapters/claude-code/precompact-handoff.sh` — thin Claude Code adapter

### Dependent Files (Callers/Importers)
- `commands/resume.md:56-68` — consumer of `.ll/ll-continue-prompt.md`; detects schema by checking for `## Intent` and `## Next Steps` section headings (not frontmatter keys)
- `scripts/little_loops/subprocess_utils.py:59` — `CONTINUATION_PROMPT_PATH = Path(".ll/ll-continue-prompt.md")` constant; all consumers import this path, not a hard-coded string
- `scripts/little_loops/subprocess_utils.py:71,92` — `detect_context_handoff()` and `read_continuation_prompt()`; read `.ll/ll-continue-prompt.md` via `CONTINUATION_PROMPT_PATH`
- `hooks/scripts/context-monitor.sh:370-407` — mtime-vs-threshold idempotency check

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-monitor.sh:50-80` — `check_handoff()` function reads `ll-continue-prompt.md` for `handoff_pending` state
- `scripts/little_loops/issue_manager.py:290,462-464` — calls `detect_context_handoff()` and `read_continuation_prompt()` (indirect `ll-continue-prompt.md` consumer)
- `scripts/little_loops/parallel/worker_pool.py:797,939-943` — same pattern as `issue_manager.py`; reads handoff state in parallel worker execution

### Similar Patterns
- `scripts/little_loops/hooks/pre_compact.py` — canonical Python handler to model after (`handle(event: LLHookEvent) -> LLHookResult`, `acquire_lock` + `atomic_write_json`, try/except wrapper)
- `hooks/adapters/claude-code/precompact.sh` — thin adapter pattern: `INPUT=$(cat)` + `echo "$INPUT" | python -m little_loops.hooks <intent>`
- `scripts/little_loops/file_utils.py` — `acquire_lock`, `atomic_write` (text files), `atomic_write_json` (JSON files)
- `scripts/little_loops/cli/session.py:_run_extract_decisions()` — reference for `["ll-issues", ...]` subprocess call pattern: `capture_output=True, text=True` + `except FileNotFoundError` guard (exact model for the `ll-issues list --status in_progress` call)

_Confirmed by codebase research 2026-06-16:_
- `scripts/little_loops/hooks/__init__.py` dispatch table: `session_end` maps to `sweep_stale_refs.handle` (not a `session_end.py`) — `pre_compact_handoff` should follow the same built_ins pattern. Precedence: `return {**_HOOK_INTENT_REGISTRY, **built_ins}` means built-ins shadow extension-provided handlers on name collision.
- `scripts/little_loops/hooks/pre_compact.py` uses `atomic_write_json` (JSON output) — `pre_compact_handoff.py` must use `atomic_write` (text/markdown) instead.
- All adapters (`session-end.sh`, `post-tool-use.sh`, etc.) confirm the 3-line pattern is universal. `precompact-handoff.sh` differs only in the intent name argument.
- `scripts/little_loops/cli/session.py:_run_extract_decisions()` confirms the `ll-issues` subprocess call pattern: `["ll-issues", "list", "--status", "in_progress"]` with `capture_output=True, text=True, timeout=5` + `except (FileNotFoundError, subprocess.TimeoutExpired): active_issues_text = ""` guard. Same pattern applies to `git diff --name-only HEAD`. No existing Python hook handler calls `ll-issues` via subprocess — this is the first.

### Tests
- FEAT-1157 covers test additions for this handler

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_intents.py` — `TestHooksMainModule.test_dispatch_table_merges_hook_intent_registry` needs `assert "pre_compact_handoff" in table`; new `test_dispatch_pre_compact_handoff_happy_path` test needed (parallel to existing `test_dispatch_pre_compact_happy_path`)

### Documentation
- FEAT-1158 covers docs/config updates for this hook

### Configuration
- N/A — no new config keys; hook registered via `hooks/hooks.json` entry only

## Implementation Steps

1. Create `scripts/little_loops/hooks/pre_compact_handoff.py` following `pre_compact.py` structure:
   - `handle(event: LLHookEvent) -> LLHookResult` signature
   - Idempotency guard: read `compacted_at` from `.ll/ll-precompact-state.json` (format `"%Y-%m-%dT%H:%M:%SZ"`), parse to epoch via `datetime.fromisoformat(compacted_at.replace("Z", "+00:00")).timestamp()`, compare against `prompt_path.stat().st_mtime`; return `exit_code=0` if prompt is already fresh; guard the whole block in `try/except (OSError, json.JSONDecodeError, KeyError, ValueError)` — skip guard on any error and proceed to write
   - Extract LIFO cap as pure helper: `_build_content(sections: list[str], max_bytes: int = 2048) -> str` — `while len("\n\n".join(sections).encode()) > max_bytes: sections.pop()` then return `"\n\n".join(sections)`
   - Build tiered sections in priority order:
     - **Active issues** via subprocess (exact pattern from `session.py:_run_extract_decisions()`):
       ```python
       try:
           r = subprocess.run(["ll-issues", "list", "--status", "in_progress"],
                              capture_output=True, text=True, timeout=5)
           active_issues_text = r.stdout if r.returncode == 0 else ""
       except (FileNotFoundError, subprocess.TimeoutExpired):
           active_issues_text = ""
       ```
     - **Files edited** via subprocess (same guard pattern):
       ```python
       try:
           r = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                              capture_output=True, text=True, timeout=5)
           files_text = r.stdout if r.returncode == 0 else ""
       except (FileNotFoundError, subprocess.TimeoutExpired):
           files_text = ""
       ```
     - **Loop state** via `Path(".loops/runs/").glob("*/")` sorted by mtime — read first `.json` in each run dir; graceful `OSError` degradation
     - **Loop state caveat (confirmed 2026-06-16)**: Standard run-dir files use `.jsonl` extension (`usage.jsonl`, `messages.jsonl`); the `*.json` glob will typically return nothing — the empty-section graceful degradation handles this normally. The loop-state section is best-effort and may be empty in most real runs.
     - **Decisions/blockers** (kept if space after tiers 1–3)
     - **Tool-event summary** (dropped first under size pressure)
   - Apply `_build_content(sections, max_bytes=2048)` to assemble the final markdown
   - Write via `acquire_lock(lock_path, timeout=3.0)` + `atomic_write(prompt_path, content)` with `TimeoutError` best-effort fallback; lock file path: `prompt_path.with_suffix(".md.lock")`
   - Wrap entire body in `try/except Exception: return LLHookResult(exit_code=0)`
2. Register in `scripts/little_loops/hooks/__init__.py`:
   - Lazy import block (`_dispatch_table()` lines 73–80): add `pre_compact_handoff,` alphabetically between `pre_compact` and `pre_tool_use`
   - `built_ins` dict (lines 82–89): add `"pre_compact_handoff": pre_compact_handoff.handle,` after the `"pre_compact"` entry
   - `_USAGE` string (lines 48–52): append `, pre_compact_handoff` to the end of the `" post_tool_use, pre_tool_use, session_end"` line (before the closing `"`)
   - Module docstring (line 14): add `- ``pre_compact_handoff`` → :mod:`little_loops.hooks.pre_compact_handoff`` to the routing list
3. Create `hooks/adapters/claude-code/precompact-handoff.sh` (3-line thin adapter: `#!/usr/bin/env bash`, `INPUT=$(cat)`, `echo "$INPUT" | python -m little_loops.hooks pre_compact_handoff; exit $?`)
4. Add second PreCompact entry in `hooks/hooks.json` after the existing entry — ordering required (existing entry writes `compacted_at` first)
5. Write tests in `scripts/tests/test_pre_compact_handoff.py` modeled after `scripts/tests/test_pre_compact.py`: cover LIFO algorithm in isolation, idempotency guard (fresh vs stale prompt), subprocess fanout graceful degradation (each of the three sources fails independently), and result contract (exit 2 + feedback on write, exit 0 on skip). Add `assert "pre_compact_handoff" in table` to `test_dispatch_table_merges_hook_intent_registry` and add `test_dispatch_pre_compact_handoff_happy_path` to `scripts/tests/test_hook_intents.py`
   - **Exact subprocess test pattern (confirmed 2026-06-16)** — `tmp_path` has no `.ll/ll-precompact-state.json`, so the idempotency guard hits `OSError` → caught → handler proceeds to write (no skip). Assert `returncode == 2`, `"Session handoff snapshot written" in result.stderr`, and `(tmp_path / ".ll" / "ll-continue-prompt.md").is_file()`. Pattern mirrors `test_dispatch_pre_compact_happy_path` (uses `cwd=str(tmp_path)`, `input=json.dumps({})`, `capture_output=True`, `timeout=10`).
   - All test classes use `monkeypatch.chdir(tmp_path)` (in-process tests) or `cwd=str(tmp_path)` (subprocess tests) — never write to the real `.ll/` directory.

## Impact

- **Priority**: P3 — Convenience/reliability improvement; compaction is occasional and manual workaround (`/ll:handoff`) exists
- **Effort**: Medium — New Python handler with subprocess fanout, size-capping logic, idempotency guard, thin adapter, and hook registration
- **Risk**: Low — Additive hook; existing `precompact.sh` entry is preserved; worst case is no snapshot on hook failure
- **Breaking Change**: No

## Labels

`hooks`, `precompact`, `automation`, `python`

---

## Scope Boundary

**FEAT-1116 has shipped.** The implementation follows the Python handler + thin Claude Code adapter
pattern directly (`pre_compact_handoff.py` + `precompact-handoff.sh`). No legacy shell script is
created under `hooks/scripts/`. The "port to Python later" caveat from earlier passes is now moot.

## Verification Notes

**Verdict**: VALID — Re-verified 2026-06-16

- `scripts/little_loops/hooks/pre_compact_handoff.py` does not exist ✓
- `hooks/adapters/claude-code/precompact-handoff.sh` does not exist ✓
- No second PreCompact entry for handoff in `hooks/hooks.json` ✓
- `hooks/hooks.json` PreCompact section line range 165–177 still accurate ✓
- `__init__.py` dispatch table line ranges (73–80 import block, 82–89 built_ins, 48–52 `_USAGE`) confirmed current ✓
- `subprocess_utils.py:59` `CONTINUATION_PROMPT_PATH` confirmed current ✓
- Feature not yet implemented ✓

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-16; updated 2026-06-16_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 72/100 → LOW

### Outcome Risk Factors
- **Novel LIFO algorithm** — `_build_content(sections, max_bytes)` has no existing Python counterpart to model; design and test this pure helper in isolation before integrating with the hook handler
- **Multi-source subprocess fanout** — handler spawns `ll-issues list --status in_progress` + `git diff --name-only HEAD` + `.loops/runs/` glob; each has its own failure mode — ensure all three degrade to empty section (not a crash)
- **Tests are co-deliverables (FEAT-1157)** — `test_pre_compact_handoff.py` and `test_hook_intents.py` assertion (`pre_compact_handoff in table`) are tracked in FEAT-1157; implement tests first so LIFO and idempotency guard are exercised before hook registration

## Session Log
- `/ll:confidence-check` - 2026-06-16T00:00:00 - `b396a3fd-b6f8-4762-9f77-9bf4135b13a5.jsonl`
- `/ll:refine-issue` - 2026-06-17T01:26:06 - `db7c22a7-6029-405e-9991-478990a1bba3.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00 - `16a2efe8-0d23-40b4-8630-87117c17a1bc.jsonl`
- `/ll:refine-issue` - 2026-06-17T01:17:02 - `3da5122d-2e48-40a4-8df4-932869055323.jsonl`
- `/ll:confidence-check` - 2026-06-17T00:00:00 - `0e61485f-3d17-4f44-b005-5b6f95252be2.jsonl`
- `/ll:refine-issue` - 2026-06-17T00:36:33 - `7d311f92-7a9f-475e-a7a0-98b44e638a80.jsonl`
- `/ll:confidence-check` - 2026-06-16T00:00:00 - `74f0a04a-2564-4481-b304-97bcf6561db6.jsonl`
- `/ll:confidence-check` - 2026-06-16T23:55:00 - `bf3fb4d1-54fd-4a5b-a332-5d6f637f776f.jsonl`
- `/ll:confidence-check` - 2026-06-16T23:30:00 - `f7a2c37a-062a-4915-a771-821fa46945ff.jsonl`
- `/ll:wire-issue` - 2026-06-16T23:06:39 - `f1cfd32d-9915-4da3-89f1-643c1c09bfb4.jsonl`
- `/ll:refine-issue` - 2026-06-16T22:58:03 - `7e4f8e86-755c-43c1-9f4f-339908ce5b14.jsonl`
- `/ll:format-issue` - 2026-06-16T22:50:17 - `0bc5f346-83c2-4b32-a3f5-b8981b66367d.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-11T21:32:14 - `521f9c4d-aa09-4ad1-88fe-93826dacaa4a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-22T20:04:15 - `82d256a6-9a99-40f5-8866-377a208de262.jsonl`

## Blocks

- FEAT-1157
- FEAT-1158
- FEAT-1264
- FEAT-1315
