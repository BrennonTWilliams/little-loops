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

Implement `hooks/scripts/precompact-handoff.sh` with priority-tiered snapshot logic, size-capping, and idempotency, then register it as a second PreCompact hook in `hooks/hooks.json`.

## Current Behavior

No automatic handoff snapshot is written before context compaction. Users must manually run `/ll:handoff` to generate `.ll/ll-continue-prompt.md`. If a PreCompact event fires without a prior manual handoff, session continuity state (active issues, file edits, open decisions) is lost.

## Expected Behavior

`hooks/scripts/precompact-handoff.sh` fires automatically on every PreCompact event and writes `.ll/ll-continue-prompt.md` (≤2KB, priority-tiered) before context is compacted. An idempotency guard skips the write when the snapshot is already fresh relative to `compacted_at` in `ll-precompact-state.json`.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Motivation

`/ll:handoff` today is a manual step. Claude Code's PreCompact event fires before context compaction; hooking into it ensures a continuity snapshot is always written before state is lost. This is the core deliverable of FEAT-1113.

## Use Case

**Who**: Developer using little-loops with Claude Code's automatic context compaction enabled.

**Context**: Working on a long session that triggers a PreCompact event, with active issues in progress and file edits staged.

**Goal**: Ensure session continuity is preserved automatically — without remembering to run `/ll:handoff` manually before each potential compaction.

**Outcome**: After compaction, `/ll:resume` restores the session from `.ll/ll-continue-prompt.md`, which was automatically written by the PreCompact hook.

## Acceptance Criteria

- `hooks/scripts/precompact-handoff.sh` exists and is executable
- Hook fires on PreCompact and produces `.ll/ll-continue-prompt.md` ≤2KB
- Priority tiers drop LIFO under size pressure (tool-event summary dropped first, then decisions, etc.)
- Idempotency: skips write if `ll-continue-prompt.md` mtime is newer than `compacted_at` from `.ll/ll-precompact-state.json`
- `hooks/hooks.json` registers the new script as a second PreCompact entry (existing `precompact-state.sh` entry preserved)
- Schema of written file passes `/ll:resume` compatibility: frontmatter with `session_date`, `session_branch`, `issues_in_progress` + sections `## Intent`, `## File Modifications`, `## Decisions Made`, `## Next Steps`

## Implementation

### New File: `hooks/scripts/precompact-handoff.sh`

Follow `precompact-state.sh` structure:
- Read stdin JSON, extract `transcript_path` via jq
- Source `hooks/scripts/lib/common.sh`
- Check `ll_feature_enabled` guard
- Build tiered content sections:
  1. Active issue + loop state (always kept) — from `ll-issues list --status in_progress` + `.ll/loops/` JSON files
  2. Files edited this session (always kept) — from `git diff --name-only HEAD`
  3. Open decisions / blockers (kept if space)
  4. Recent tool-event summary (dropped first under size pressure)
- Cap at 2KB with `wc -c`; drop sections LIFO until under cap
- Write atomically using `acquire_lock` / `atomic_write_json` from `lib/common.sh`
- Exit 2 with message to surface errors to user

### Idempotency Guard

Before writing, compare `.ll/ll-continue-prompt.md` mtime against `compacted_at` from `.ll/ll-precompact-state.json`. If prompt is already fresh (mtime > compacted_at), skip write and exit 0.

### Registration: `hooks/hooks.json:89-100`

Add a second object to the PreCompact array. Do NOT remove the existing `precompact-state.sh` entry — `context-monitor.sh:check_compaction()` (lines 176–206) depends on `.ll/ll-precompact-state.json` being written.

### Output Schema

Follow `commands/handoff.md:134-158` structured schema. The `commands/resume.md:28-42` consumer validates `## Intent` + `## Next Steps` presence. The legacy `hooks/prompts/continuation-prompt-template.md` is for reference only.

### State Sources (FEAT-1112 Fallback)

FEAT-1112 (session store) is not yet implemented; gather state without it:
- **Files edited**: `git diff --name-only HEAD`
- **Active issues**: `ll-issues list --status in_progress` or frontmatter scan of `.issues/`
- **Loop state**: read `.ll/loops/` JSON files

## Files to Modify

- `hooks/hooks.json:89-100` — add second PreCompact entry
- `hooks/scripts/precompact-state.sh` — read-only reference for structure (do not modify)
- `hooks/scripts/lib/common.sh` — import only (`acquire_lock`, `release_lock`, `atomic_write_json`, `ll_config_value`, `ll_feature_enabled`, `to_epoch`, `get_mtime`)

## New Files

- `hooks/scripts/precompact-handoff.sh`

## References

- Related tests: FEAT-1157
- Docs/config updates: FEAT-1158
- Depends on: FEAT-1112 (fallback available without it)
- Consumers of `ll-continue-prompt.md`: `commands/resume.md:28-42`, `scripts/little_loops/subprocess_utils.py:31-58`, `hooks/scripts/context-monitor.sh:334-348`

## Integration Map

### Files to Modify
- `hooks/hooks.json:89-100` — add second PreCompact entry
- `scripts/little_loops/hooks/__init__.py` — add dispatch entry + update `_USAGE` string [Wiring pass]
- `scripts/little_loops/cli/doctor.py` — update PreCompact feature description to reflect second hook [Wiring pass]

### New Files
- `hooks/scripts/precompact-handoff.sh` — core hook implementation

### Dependent Files (Callers/Importers)
- `commands/resume.md:28-42` — consumer of `.ll/ll-continue-prompt.md`
- `scripts/little_loops/subprocess_utils.py:31-58` — consumer of `.ll/ll-continue-prompt.md`
- `hooks/scripts/context-monitor.sh:334-348` — consumer of `.ll/ll-continue-prompt.md`

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/context-monitor.sh:50-80` — `check_handoff()` function reads `ll-continue-prompt.md` for `handoff_pending` state (second read point not listed above)
- `scripts/little_loops/issue_manager.py:290,462-464` — calls `detect_context_handoff()` and `read_continuation_prompt()` (indirect `ll-continue-prompt.md` consumer)
- `scripts/little_loops/parallel/worker_pool.py:797,939-943` — same pattern as `issue_manager.py`; reads handoff state in parallel worker execution

### Similar Patterns
- `hooks/scripts/precompact-state.sh` — reference for stdin JSON → jq → feature guard structure
- `hooks/scripts/lib/common.sh` — shared utilities: `acquire_lock`, `release_lock`, `atomic_write_json`, `ll_config_value`, `ll_feature_enabled`, `to_epoch`, `get_mtime`

### Tests
- FEAT-1157 covers test additions for this hook

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_intents.py` — `TestHooksMainModule.test_dispatch_table_merges_hook_intent_registry` needs `assert "pre_compact_handoff" in table`; new `test_dispatch_pre_compact_handoff_happy_path` test needed (parallel to the existing `test_dispatch_pre_compact_happy_path` at line ~273)

### Documentation
- FEAT-1158 covers docs/config updates for this hook

### Configuration
- N/A — no new config keys; hook registered via `hooks/hooks.json` entry only

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Architecture change (FEAT-1116 has shipped):** The issue was written before FEAT-1116 (Hook-Intent Abstraction Layer) landed. That migration is complete — live PreCompact execution goes through `hooks/adapters/claude-code/precompact.sh` → `python -m little_loops.hooks pre_compact` → `scripts/little_loops/hooks/pre_compact.py`. The Scope Boundary notes' "once FEAT-1116 lands, port to Python" condition is now satisfied. The implementation MUST follow the Python handler + thin adapter pattern, not `hooks/scripts/precompact-handoff.sh`.

**Corrected files to create/modify:**
- `scripts/little_loops/hooks/pre_compact_handoff.py` — new Python handler (replaces planned `hooks/scripts/precompact-handoff.sh`)
- `hooks/adapters/claude-code/precompact-handoff.sh` — new thin Claude Code adapter (model after `hooks/adapters/claude-code/precompact.sh`: 2 lines — reads stdin, pipes to `python -m little_loops.hooks pre_compact_handoff`)
- `scripts/little_loops/hooks/__init__.py` — add `"pre_compact_handoff": pre_compact_handoff.handle` to `_dispatch_table()` (line ~70)
- `hooks/hooks.json:165-177` — actual PreCompact section (issue's `:89-100` is stale); add second entry in the array

**Reference implementation:**
- `scripts/little_loops/hooks/pre_compact.py` — canonical Python handler to model after (`handle(event: LLHookEvent) -> LLHookResult` with `acquire_lock` + `atomic_write_json`)
- `hooks/adapters/claude-code/precompact.sh` — thin adapter pattern: `INPUT=$(cat)` + `echo "$INPUT" | python -m little_loops.hooks <intent>`
- `scripts/little_loops/hooks/types.py` — `LLHookEvent`, `LLHookResult` dataclass contracts

**Python utilities (replaces shell lib/common.sh equivalents):**
- `scripts/little_loops/file_utils.py` — `acquire_lock(path, timeout=3.0)` context manager; `atomic_write_json(path, data)` with round-trip validation
- No `ll_feature_enabled` gate needed: `pre_compact.py` runs unconditionally (same for this handler)

**Corrected line numbers for dependent consumers:**
- `hooks/hooks.json:165-177` (not `:89-100`) — current PreCompact array
- `commands/resume.md:28-56` (not `:28-42`) — schema detection (checks for `## Intent` + `## Next Steps` presence)
- `scripts/little_loops/subprocess_utils.py:57-95` (not `:31-58`) — `detect_context_handoff()` and `read_continuation_prompt()`; checks file presence/non-emptiness only, content not parsed
- `hooks/scripts/context-monitor.sh:370-407` (not `:334-348`) — mtime-vs-threshold idempotency check

**`ll-issues list` constraint (BUG-1799):** `--status` accepts a single value only. Use `ll-issues list --status in_progress`. For multi-status needs, use the frontmatter awk pattern from `skills/capture-issue/SKILL.md:168-179`.

**Tests to model after:**
- `scripts/tests/test_pre_compact.py` — unit tests for `pre_compact.handle()` (direct Python handler logic)
- `scripts/tests/test_hooks_integration.py` — integration tests including `TestPrecompactState` for subprocess/adapter layer

**Novel logic (no existing pattern):** The LIFO-under-2KB section-dropping algorithm has no prior implementation. Python equivalent: build sections as a list in priority order, join, check `len(content.encode()) <= 2048`, pop from tail until under cap.

## Implementation Steps

1. Create `hooks/scripts/precompact-handoff.sh` following `precompact-state.sh` structure (stdin JSON → jq → feature guard → common.sh import)
2. Implement priority-tiered content builder: active issues + loop state (always kept), file edits (always kept), decisions/blockers (kept if space), tool-event summary (dropped first under size pressure)
3. Add idempotency guard: compare `.ll/ll-continue-prompt.md` mtime vs `compacted_at` from `ll-precompact-state.json`; skip write if already fresh
4. Add 2KB size cap with LIFO section dropping; use `wc -c` to measure; write atomically via `acquire_lock` / `atomic_write_json`
5. Register as second PreCompact hook in `hooks/hooks.json`, preserving the existing `precompact-state.sh` entry
6. Validate output passes `/ll:resume` compatibility (frontmatter schema + required `## Intent` and `## Next Steps` headers)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/hooks/__init__.py` — add `pre_compact_handoff` to the `_USAGE` constant (lines 48–52) and to the module-level docstring intents list; without this the CLI help text is stale
7. Update `hooks/hooks.json` with ordering constraint: the new `precompact-handoff.sh` entry MUST be second in the `"PreCompact"` array — `precompact.sh` writes `compacted_at` to `ll-precompact-state.json`, which the new handler reads for its idempotency guard; reversing the order breaks the guard on first run
8. Update `scripts/tests/test_hook_intents.py` — add `assert "pre_compact_handoff" in table` to `test_dispatch_table_merges_hook_intent_registry`; add `test_dispatch_pre_compact_handoff_happy_path` parallel to existing `test_dispatch_pre_compact_happy_path`
9. Update `scripts/little_loops/cli/doctor.py` — update the PreCompact feature description string to reflect the second hook (e.g., "PreCompact state capture + handoff snapshot" or add a second feature row)

### Codebase Research Findings

_Added by `/ll:refine-issue` — Python-first steps (FEAT-1116 has shipped):_

1. Create `scripts/little_loops/hooks/pre_compact_handoff.py` following `pre_compact.py`'s structure:
   - `handle(event: LLHookEvent) -> LLHookResult` signature from `scripts/little_loops/hooks/types.py`
   - Read `compacted_at` from `.ll/ll-precompact-state.json` (written by `pre_compact.handle()`)
   - Idempotency: compare `Path(".ll/ll-continue-prompt.md").stat().st_mtime` vs `compacted_at` epoch; return `LLHookResult(exit_code=0)` if already fresh
   - Build tiered sections in priority order: (1) active issues via `subprocess` call to `ll-issues list --status in_progress` + `.ll/loops/` JSON reads; (2) files via `git diff --name-only HEAD`; (3) decisions/blockers; (4) tool-event summary
   - LIFO 2KB cap: join sections, while `len(content.encode()) > 2048`, pop last section
   - Write via `acquire_lock(lock_path, timeout=3.0)` + `atomic_write_json(prompt_path, content)` from `scripts/little_loops/file_utils.py`
   - Return `LLHookResult(exit_code=2, feedback="Handoff snapshot written.")` on success, `LLHookResult(exit_code=0)` on skip/error
2. Register in `scripts/little_loops/hooks/__init__.py` `_dispatch_table()` (~line 70): add `"pre_compact_handoff": pre_compact_handoff.handle`
3. Create `hooks/adapters/claude-code/precompact-handoff.sh` following `hooks/adapters/claude-code/precompact.sh` exactly: `INPUT=$(cat)` + `echo "$INPUT" | python -m little_loops.hooks pre_compact_handoff; exit $?`
4. Add second entry to `hooks/hooks.json` inside the `"PreCompact": [...]` array (after the existing entry at lines 165–177): `{"matcher": "*", "hooks": [{"type": "command", "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/precompact-handoff.sh", "timeout": 5, "statusMessage": "Writing session handoff..."}]}`
5. Add unit tests in `scripts/tests/test_pre_compact_handoff.py` following `scripts/tests/test_pre_compact.py` pattern; add integration test to `scripts/tests/test_hooks_integration.py` following `TestPrecompactState`

## Impact

- **Priority**: P3 — Convenience/reliability improvement; compaction is occasional and manual workaround (`/ll:handoff`) exists
- **Effort**: Medium — New shell script with atomic writes, size-capping logic, idempotency guard, and hook registration
- **Risk**: Low — Additive hook; existing `precompact-state.sh` entry is preserved; worst case is no snapshot on hook failure
- **Breaking Change**: No

## Labels

`hooks`, `precompact`, `automation`, `shell-script`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-1116 (hook-intent abstraction layer) is migrating PreCompact hooks from `hooks/scripts/` shell scripts to Python core handlers with thin per-host adapters. This issue adds a new shell script in the legacy layer FEAT-1116 is retiring. Implement `precompact-handoff.sh` as specified here for the MVP, but scope it to be replaced by — or restructured as — the Python core handler + Claude Code adapter pattern once FEAT-1116's PreCompact migration scaffolding is in place.

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `hooks/scripts/precompact-handoff.sh` does not exist ✓
- `hooks/hooks.json` has no second PreCompact entry for handoff ✓
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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): The State Sources section specifies git diff/ll-issues/loops-JSON as the fallback approach — but does not acknowledge FEAT-1262's `.ll/ll-session-events.jsonl` as the richer primary source. If `.ll/ll-session-events.jsonl` is present and non-empty (i.e., FEAT-1262 has been shipping and running), prefer it as the primary source for the files-edited and decisions sections of the snapshot. Fall back to `git diff --name-only HEAD` and `ll-issues list` only when the JSONL is absent. FEAT-1264 (which formally integrates the event log) depends on this issue; this note ensures the fallback/primary distinction is documented in the implementation contract so FEAT-1264 doesn't need to re-explain the fallback semantics.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-11): This issue implements `precompact-handoff.sh` as a full-logic shell script. FEAT-1116 (Hook-Intent Abstraction Layer) will migrate PreCompact hooks to Python core handlers with thin per-host shell adapters. Implement the shell script as specified here for the MVP, but treat it as temporary: once FEAT-1116's PreCompact migration scaffolding lands, port the snapshot logic to a Python intent handler (e.g., `scripts/little_loops/hooks/pre_compact_handoff.py`) and replace `precompact-handoff.sh` with a thin Claude Code adapter that delegates to the Python handler. Do not embed new business logic in the shell script beyond what is required for the initial implementation.
