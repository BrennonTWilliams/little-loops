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
confidence_score: 91
outcome_confidence: 72
score_complexity: 15
score_test_coverage: 17
score_ambiguity: 20
score_change_surface: 20
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
- **Idempotency guard**: compare `Path(".ll/ll-continue-prompt.md").stat().st_mtime` vs `compacted_at` epoch; return `LLHookResult(exit_code=0)` if already fresh
- **Tiered section builder** (priority order):
  1. Active issues + loop state (always kept) — `subprocess` call to `ll-issues list --status in_progress` + `.ll/loops/` JSON reads
  2. Files edited this session (always kept) — `subprocess` call to `git diff --name-only HEAD`
  3. Open decisions / blockers (kept if space)
  4. Recent tool-event summary (dropped first under size pressure)
- **LIFO 2KB cap**: `while len(content.encode()) > 2048: sections.pop()` then join
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
- **Loop state**: read `.ll/loops/` JSON files

When FEAT-1262's `.ll/ll-session-events.jsonl` is present, prefer it as the primary source for
files-edited and decisions sections (FEAT-1264 formalizes this). Fall back to the above when absent.

### Output Schema

Follow `commands/handoff.md` structured schema. The consumer `commands/resume.md:28-56` validates
`## Intent` + `## Next Steps` presence.

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
- `commands/resume.md:28-56` — consumer of `.ll/ll-continue-prompt.md`
- `scripts/little_loops/subprocess_utils.py:57-95` — `detect_context_handoff()` and `read_continuation_prompt()`; checks file presence/non-emptiness only
- `hooks/scripts/context-monitor.sh:370-407` — mtime-vs-threshold idempotency check

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-monitor.sh:50-80` — `check_handoff()` function reads `ll-continue-prompt.md` for `handoff_pending` state
- `scripts/little_loops/issue_manager.py:290,462-464` — calls `detect_context_handoff()` and `read_continuation_prompt()` (indirect `ll-continue-prompt.md` consumer)
- `scripts/little_loops/parallel/worker_pool.py:797,939-943` — same pattern as `issue_manager.py`; reads handoff state in parallel worker execution

### Similar Patterns
- `scripts/little_loops/hooks/pre_compact.py` — canonical Python handler to model after (`handle(event: LLHookEvent) -> LLHookResult`, `acquire_lock` + `atomic_write_json`, try/except wrapper)
- `hooks/adapters/claude-code/precompact.sh` — thin adapter pattern: `INPUT=$(cat)` + `echo "$INPUT" | python -m little_loops.hooks <intent>`
- `scripts/little_loops/file_utils.py` — `acquire_lock`, `atomic_write` (text files), `atomic_write_json` (JSON files)

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
   - Idempotency guard: read `compacted_at` from `.ll/ll-precompact-state.json`, compare against `ll-continue-prompt.md` mtime; return `exit_code=0` if already fresh
   - Build tiered sections in priority order: active issues via `ll-issues list --status in_progress` + `.ll/loops/` JSON reads; files via `git diff --name-only HEAD`; decisions/blockers; tool-event summary
   - LIFO 2KB cap: `while len(content.encode()) > 2048: sections.pop()`
   - Write via `acquire_lock(lock_path, timeout=3.0)` + `atomic_write(prompt_path, content)` with `TimeoutError` best-effort fallback
   - Wrap entire body in `try/except Exception: return LLHookResult(exit_code=0)`
2. Register in `scripts/little_loops/hooks/__init__.py`: add `pre_compact_handoff` to the lazy import block in `_dispatch_table()`, add to `built_ins` dict, add to `_USAGE` string
3. Create `hooks/adapters/claude-code/precompact-handoff.sh` (3-line thin adapter: `#!/usr/bin/env bash`, `INPUT=$(cat)`, `echo "$INPUT" | python -m little_loops.hooks pre_compact_handoff; exit $?`)
4. Add second PreCompact entry in `hooks/hooks.json` after the existing entry — ordering required (existing entry writes `compacted_at` first)
5. Write tests in `scripts/tests/test_pre_compact_handoff.py` modeled after `scripts/tests/test_pre_compact.py`: cover LIFO algorithm in isolation, idempotency guard (fresh vs stale prompt), subprocess fanout graceful degradation (each of the three sources fails independently), and result contract (exit 2 + feedback on write, exit 0 on skip). Add `assert "pre_compact_handoff" in table` to `test_dispatch_table_merges_hook_intent_registry` and add `test_dispatch_pre_compact_handoff_happy_path` to `scripts/tests/test_hook_intents.py`

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

**Verdict**: VALID — Verified 2026-04-23

- `scripts/little_loops/hooks/pre_compact_handoff.py` does not exist ✓
- `hooks/adapters/claude-code/precompact-handoff.sh` does not exist ✓
- No second PreCompact entry for handoff in `hooks/hooks.json` ✓
- Feature not yet implemented ✓

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-16_

**Readiness Score**: 91/100 → PROCEED
**Outcome Confidence**: 72/100 → LOW

### Outcome Risk Factors
- **Novel per-site complexity** — The LIFO 2KB section-dropping algorithm has no existing Python implementation to model. Design and test this piece in isolation (a small pure-function `_build_content(sections, max_bytes)`) before integrating with the hook handler.
- **Multi-source subprocess fanout** — The handler spawns `ll-issues list --status in_progress` + reads `.ll/loops/` JSON + calls `git diff --name-only HEAD`. Each subprocess has its own failure mode; ensure all three have graceful degradation (empty section on error, not a crash).
- **Tests are co-deliverables** — `test_pre_compact_handoff.py` and the `test_hook_intents.py` assertions (`pre_compact_handoff in table`) are tracked in FEAT-1157, not co-located here. Implement tests first so the LIFO algorithm and idempotency guard are exercised before hook registration.

## Session Log
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
