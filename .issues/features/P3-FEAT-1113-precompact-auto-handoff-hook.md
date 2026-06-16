---
id: FEAT-1113
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-15
discovered_by: capture-issue
blocked_by:
- FEAT-1112
confidence_score: 90
outcome_confidence: 55
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 14
score_change_surface: 10
size: Very Large
decision_needed: true
relates_to:
- ENH-152
- ENH-495
- FEAT-150
---

# FEAT-1113: PreCompact Auto-Handoff Hook

## Summary

Trigger an implicit, priority-tiered handoff snapshot (≤2KB) automatically on Claude Code's PreCompact event, so interactive sessions don't lose active files, tasks, and decisions when the context window compacts.

**Deferred**: Headless mode (ll-loop, ll-auto, ll-parallel) already has automatic handoff via the FSM signal-detection path — `context-monitor.sh` emits a reminder at threshold, Claude invokes `/ll:handoff`, and the FSM executor's `signal_detector` catches `CONTEXT_HANDOFF: Ready for fresh session` and handles it without user intervention. The remaining gap is **interactive sessions only**, where users must remember to run `/ll:handoff` manually. This is lower priority than originally scoped.

## Motivation

`/ll:handoff` is a manual step in **interactive** sessions. In headless mode (ll-loop, ll-auto), handoff is already semi-automatic: `context-monitor.sh` fires PostToolUse at threshold, emits a reminder back to Claude, Claude invokes `/ll:handoff`, and the FSM executor detects the `CONTEXT_HANDOFF: Ready for fresh session` signal and handles state preservation automatically.

The remaining failure modes are interactive-session-only: BUG-982 (handoff reminder silenced by stale prompt), and users simply forgetting to run `/ll:handoff` before session end. A PreCompact hook would serve as a guaranteed safety net for these cases.

Context-mode (github.com/mksglu/context-mode) runs a PreCompact hook that builds a priority-tiered XML snapshot — active files, tasks, decisions — capped at 2KB, dropping lower-priority metadata if space is tight. This turns handoff from a skill you must remember into a guarantee for interactive sessions.

## Current Behavior

- **Interactive sessions**: `/ll:handoff` is user-invoked or recommended by `context_monitor` at threshold; missed handoffs are the failure mode this issue targets
- **Headless mode (ll-loop, ll-auto, ll-parallel)**: `context-monitor.sh` emits a threshold reminder → Claude invokes `/ll:handoff` → FSM executor (`executor.py:1084 _handle_handoff`) detects `CONTEXT_HANDOFF: Ready for fresh session` signal and handles state preservation automatically — handoff is already semi-automatic here
- Missed handoffs silently continue as "success" (BUG-819, completed)
- Structured handoff ENH-495 landed but still runs on explicit invocation
- Claude Code exposes a PreCompact hook type we don't currently use

## Expected Behavior

- New `hooks/scripts/precompact-handoff.sh` registered as PreCompact in `hooks/hooks.json`
- Hook writes a tiered snapshot to `.ll/ll-continue-prompt.md` with sections ordered:
  1. Active issue + loop state (always kept)
  2. Files edited this session (always kept)
  3. Open decisions / blockers (kept if space)
  4. Recent tool-event summary (dropped first under size pressure)
- Total output capped at 2KB; priorities dropped LIFO until under cap
- Integrates with FEAT-1112 session store to pull file/loop/issue state without re-parsing
- Works alongside existing `/ll:handoff` skill — skill becomes a manual override that produces the richer version

## Use Case

**Who**: Developer running an interactive Claude Code session

**Context**: During a long interactive session, the context window approaches the compact threshold; the user has not manually invoked `/ll:handoff`

**Goal**: Preserve active issue state, edited files, and open decisions without a manual step

**Outcome**: `.ll/ll-continue-prompt.md` is written automatically at PreCompact time; the next session starts with full context when the user invokes `/ll:resume`

## Acceptance Criteria

- Hook fires on PreCompact and produces `.ll/ll-continue-prompt.md` ≤2KB
- Priority-tier dropping tested with synthetic large inputs
- No duplicate handoff when user already ran `/ll:handoff` in same session (idempotency marker)
- Integration test verifies continuation prompt is picked up by SessionStart hook on next run
- CLAUDE.md / handoff docs updated

## API/Interface

No Python API changes. The feature exposes a shell hook:

- **Hook**: `hooks/scripts/precompact-handoff.sh` — invoked by Claude Code on PreCompact event
- **Input**: stdin JSON (PreCompact event payload from Claude Code host)
- **Output**: `.ll/ll-continue-prompt.md` (≤2KB, structured schema — see Integration Map § Output Schema)

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `hooks/hooks.json:89-100` — PreCompact hook already registered pointing to `precompact-state.sh`; either extend that script or add a second entry in the array (multiple hooks per event type are supported)
- `hooks/scripts/precompact-state.sh` — current PreCompact script; **critical**: it writes `.ll/ll-precompact-state.json` which `context-monitor.sh:check_compaction()` (lines 176–206) reads to detect compaction boundary and reset token estimates — this write must be preserved in any refactor

### New File
- `hooks/scripts/precompact-handoff.sh` — new script to create, following the structure of `precompact-state.sh` (stdin JSON → jq extraction → build content → atomic write)

### Reusable Utilities (hooks/scripts/lib/common.sh)
- `acquire_lock` / `release_lock` / `atomic_write_json` — all state writes must use these
- `ll_config_value` — read config keys (e.g., timeout, feature flags)
- `ll_feature_enabled` — feature flag guard at script top
- `to_epoch` / `get_mtime` — timestamp comparison for idempotency

### Idempotency (Already Handled)
- `hooks/scripts/context-monitor.sh:334-348` — already checks if `ll-continue-prompt.md` mtime > `threshold_crossed_at` epoch; writing the file automatically satisfies this and suppresses future handoff reminders in that session
- Pattern: store `compacted_at` in `.ll/ll-precompact-state.json` and compare against existing prompt mtime to skip re-write if prompt was already written post-threshold

### Consumers of ll-continue-prompt.md
- `commands/resume.md:28-42` — locates the file at `$(pwd)/.ll/ll-continue-prompt.md`; validates freshness against `continuation.prompt_expiry_hours`; handles both structured schema (detects `## Intent` + `## Next Steps`) and legacy prose schema
- `scripts/little_loops/subprocess_utils.py:31-58` — `read_continuation_prompt(repo_path)` used by ll-auto and ll-parallel to load continuation after detecting `CONTEXT_HANDOFF_PATTERN` in Claude's stdout (note: PreCompact hook writes the file but does NOT emit this signal to stdout — automation pickup happens on next session start via `/ll:resume`, not via signal detection)
- `hooks/scripts/context-monitor.sh:334-348` — reads mtime to detect completed handoff

### Output Schema to Follow
- `commands/handoff.md:134-158` — defines the structured `ll-continue-prompt.md` format with frontmatter (`session_date`, `session_branch`, `issues_in_progress`) and sections: `## Intent`, `## File Modifications`, `## Decisions Made`, `## Next Steps`
- `hooks/prompts/continuation-prompt-template.md` — legacy template for reference (has `## Context`, `## Completed Work`, `## Current State`, `## Key File References`, `## Critical Context`)

### State Sources (FEAT-1112 Fallback)
Since FEAT-1112 (session store) is not yet implemented, gather state without it:
- **Files edited**: `git diff --name-only HEAD` for current session changes
- **Active issues**: `ll-issues list --status in_progress` or scan `.issues/` frontmatter
- **Loop state**: read `.ll/loops/` JSON files for active loop context

### Tests
- `scripts/tests/test_hooks_integration.py` — covers `ll-continue-prompt` and `PreCompact` references; add new test for precompact-handoff output here
- `scripts/tests/test_handoff_handler.py` — handoff handler unit tests (model for testing continuation prompt content)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_utils.py:136` — `TestReadContinuationPrompt` tests `read_continuation_prompt()` against `.ll/ll-continue-prompt.md`; the new hook writes this file, so run these tests to verify schema compatibility [Agent 1 + 3 finding]
- `scripts/tests/test_hooks_integration.py:531` — `test_fresh_state_with_handoff_file_sets_handoff_complete_false` is timing-sensitive; if `precompact-handoff.sh` writes `ll-continue-prompt.md` before `threshold_crossed_at` is set, this test's mtime assumptions may fail — review carefully [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py:434,489` — `test_reminder_rate_limited_second_call` and `test_state_contains_last_reminder_at_after_exit2` assert reminder behavior; a fresh `ll-continue-prompt.md` mtime will flip `handoff_complete=true` and silence further reminders — verify this is the intended behavior in tests [Agent 3 finding]
- `scripts/tests/test_hooks_integration.py` — new `TestPrecompactHandoff` class to write, modeled after `TestPrecompactState` (line 1468); must cover: (a) file produced ≤2KB, (b) priority-tier dropping under size pressure, (c) idempotency skip when prompt already fresh, (d) schema validates for `/ll:resume` (has frontmatter + `## Intent` + `## Next Steps`) [Agent 3 finding]
- `scripts/tests/test_issue_manager.py` — patches `read_continuation_prompt`; verify no new assumptions break [Agent 1 finding]
- `scripts/tests/test_worker_pool.py:2202` — patches `read_continuation_prompt` in worker pool handoff tests [Agent 1 finding]
- `scripts/tests/test_cli_loop_lifecycle.py:665,715` — tests `continuation_prompt` display and `handoff_threshold` env var; low risk but verify [Agent 1 finding]
- `scripts/tests/test_hook_intents.py:520` — `TestHooksMainModule.test_dispatch_table_merges_hook_intent_registry` calls `_dispatch_table()` and asserts named intents present; add `assert "pre_compact_handoff" in table` when Python intent added; also add `test_dispatch_pre_compact_handoff_empty_stdin` subprocess-level test modeled after line 396 [Agent 2 + 3 finding]
- `scripts/tests/test_claude_code_adapter.py:47` — `test_hooks_json_has_post_tool_use` tests `hooks/hooks.json` structure; add parallel `test_hooks_json_has_pre_compact_handoff` asserting the new PreCompact array entry exists [Agent 3 finding]
- `scripts/tests/test_codex_adapter.py:86` — `test_pre_compact_writes_state_file` tests Codex PreCompact adapter end-to-end; add parallel test for the new Codex adapter entry once `hooks/adapters/codex/hooks.json` is updated [Agent 3 finding]
- `scripts/tests/test_opencode_adapter.py` — tests OpenCode adapter `session.compacted` → `pre_compact` dispatch; add test for the extended dispatch once `Intent` type (line 19) is widened and `"session.compacted"` handler (line 64) is updated [Agent 1 + 3 finding]

### Documentation
- `docs/guides/SESSION_HANDOFF.md` — primary handoff guide; needs update to describe automatic PreCompact trigger
- `docs/ARCHITECTURE.md:92` — PreCompact hook section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md:753` — `chmod +x` list names hook scripts individually; add `precompact-handoff.sh` entry [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md:939-942` — manual test invocation block for `precompact-state.sh`; add parallel entry for `precompact-handoff.sh` [Agent 2 finding]
- `docs/development/TROUBLESHOOTING.md:972` — timeout list names scripts explicitly; add `precompact-handoff.sh` entry [Agent 2 finding]
- `docs/ARCHITECTURE.md:85-98` — directory listing of `hooks/scripts/` enumerates every script by name; add `precompact-handoff.sh` [Agent 2 finding]
- `docs/ARCHITECTURE.md:888-955` — "Context Monitor and Session Continuation" flow diagram describes handoff as PostToolUse-only; update to show PreCompact as additional trigger path [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `context_monitor` config table; add row if `precompact_handoff.enabled` feature flag is introduced [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md:80,546` — per-intent payload notes enumerate `pre_compact` by name; if `pre_compact_handoff` is registered as a Python intent, add a parallel per-intent block here [Agent 2 finding]
- `docs/reference/API.md:7218` — hardcoded built-ins list in the extension-shadowing note; must be extended with the new intent name if Python intent approach is used [Agent 2 finding]
- `docs/reference/API.md:6585` — adapter integration list names `precompact.sh` explicitly; add `precompact-handoff.sh` if a new bash adapter script is registered [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:221` — documents `pre_compact` with ✓ across hosts; if the new handler is added to Claude Code before other hosts, a new row with per-host marks is needed [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:66,285` — summary table (line 66) and `## PreCompact` section (line 285) describe only the state-preservation handler; a second PreCompact action requires a new table row and addendum to the `## PreCompact` section [Agent 2 finding]
- `hooks/adapters/codex/README.md` — documents Codex adapter for precompact; add entry for new Codex PreCompact behavior once adapter is updated [Agent 1 finding]
- `hooks/adapters/opencode/README.md` — documents OpenCode adapter for precompact; add entry for new OpenCode PreCompact behavior [Agent 1 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:207` — imports `read_continuation_prompt`; calls it after detecting `CONTEXT_HANDOFF_PATTERN` in stdout (note: PreCompact hook does NOT emit this signal, so automation pickup happens via `/ll:resume` next session, not here — but verify no assumptions break) [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py:715` — same `read_continuation_prompt` consumer as `issue_manager.py` [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py` — imports `HandoffHandler`; manages `handoff_handler` instance and `_pending_handoff` state; reads `ll-continue-prompt.md` indirectly [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py` — declares `continuation_prompt` field on `LoopState` (serialized); verify field name matches prompt content written by new hook [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — reads `state.continuation_prompt` for display/resume; sets `LL_HANDOFF_THRESHOLD` env var consumed by `context-monitor.sh` [Agent 1 finding]
- `skills/manage-issue/SKILL.md:295-304` — reads `$(pwd)/.ll/ll-continue-prompt.md` on `--resume`; writes `ll-continue-prompt.md` on manual handoff — will coexist with auto-written file; verify idempotency logic covers this case [Agent 1 finding]
- `hooks/adapters/codex/pre-compact.sh` — Codex's PreCompact adapter; same single-dispatch limitation as `hooks/adapters/claude-code/precompact.sh`; if Python intent `pre_compact_handoff` is added, a second dispatch invocation or new Codex adapter script is required; must be updated for host parity [Agent 1 + 2 finding]
- `hooks/adapters/opencode/index.ts` — TypeScript adapter; `Intent` type alias (line 19) and `"session.compacted"` handler (lines 64–72) hardcode `pre_compact` only; extending to a second PreCompact behavior requires updating both the `Intent` type union and the handler body [Agent 1 + 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:524-602` — `context_monitor` section has `"additionalProperties": false`; any new `precompact_handoff.*` config key must be added as a new top-level section (cannot be added under `context_monitor`) [Agent 2 finding]
- `skills/configure/areas.md:867` — hook audit display table lists `[Plugin] PreCompact * precompact-state.sh 5s`; must add row for `precompact-handoff.sh` when registered [Agent 1 + 2 finding]
- `templates/generic.json` (and all 8 other `templates/*.json`) — have `"context_monitor": {"enabled": true}` block; add `"precompact_handoff": {"enabled": true}` block if feature is opt-in [Agent 2 finding]
- `hooks/adapters/codex/hooks.json:16-27` — Codex hook registration; add second `"PreCompact"` entry if a new Codex adapter script is created (mirrors `hooks/hooks.json` changes) [Agent 1 finding]
- `scripts/little_loops/hooks/__init__.py` `_USAGE` literal (line 48–52) — hardcoded string listing all intent names; must be manually updated if `pre_compact_handoff` is added as a Python intent; no test asserts this string, so it is safe to update freely [Agent 2 finding]
- `scripts/little_loops/hooks/__init__.py` module docstring (lines 13–27) — bullet list explicitly enumerates all intents; add new bullet for `pre_compact_handoff → little_loops.hooks.pre_compact_handoff` [Agent 2 finding]

### Architecture Update — June 2026 Research

_Added by `/ll:refine-issue` — stale references corrected based on current codebase state:_

- **Stale line number**: `hooks/hooks.json:89-100` → now at **lines 165–177**; registered command is `bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/precompact.sh` (not `precompact-state.sh` directly)
- **`hooks/adapters/claude-code/precompact.sh`** — thin adapter; pipes stdin to `python -m little_loops.hooks pre_compact`; the PreCompact dispatch path is now Python-first
- **`scripts/little_loops/hooks/pre_compact.py`** — Python port of `precompact-state.sh` (FEAT-1449); `handle()` is the active PreCompact handler; `precompact-state.sh` still exists on disk but is no longer the registered entry point
- **`scripts/little_loops/hooks/__init__.py:_dispatch_table()`** — if `precompact-handoff` is implemented as a Python handler, register a new `pre_compact_handoff` intent here alongside `pre_compact`
- **`scripts/tests/test_pre_compact.py`** — unit tests for `pre_compact.handle()` using `monkeypatch.chdir`; model new Python handoff handler tests here rather than in `test_hooks_integration.py` if the Python approach is chosen

**Implementation fork for FEAT-1156**: The bash-script approach (`hooks/scripts/precompact-handoff.sh` as a second PreCompact array entry) remains valid. A Python handler in `scripts/little_loops/hooks/pre_compact_handoff.py` registered in `_dispatch_table()` would be architecturally consistent — `precompact-state.sh` was ported to `pre_compact.py` under FEAT-1449 and the Python path is now the established pattern. FEAT-1156 currently specifies the bash approach; decide which to follow before starting implementation.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Implement `hooks/scripts/precompact-handoff.sh`**: Follow the `precompact-state.sh` structure — read stdin JSON, extract `transcript_path`, check `jq` availability, source `lib/common.sh`. Build tiered content sections in order: active issue + loop state → files edited this session → open decisions/blockers → recent tool-event summary. Cap at 2KB using `wc -c` on assembled content, dropping sections LIFO until under cap. Write atomically to `.ll/ll-continue-prompt.md` using `acquire_lock`/`atomic_write_json` pattern from `lib/common.sh:8-54`. Exit with `exit 2` to surface stderr message to user.

2. **Add idempotency guard**: Before writing, check if `.ll/ll-continue-prompt.md` already exists AND its mtime is newer than the session start time (read from `.ll/ll-precompact-state.json:compacted_at` or session-start timestamp). If prompt is already fresh, skip write and exit 0.

3. **Register in `hooks/hooks.json:89-100`**: Either extend the existing `precompact-state.sh` entry or add a second hook object in the `"PreCompact"` array. Do NOT remove the `precompact-state.sh` entry — `context-monitor.sh:check_compaction()` depends on `.ll/ll-precompact-state.json` being written.

4. **Write integration tests** following patterns in `scripts/tests/test_hooks_integration.py`: test that (a) hook produces `ll-continue-prompt.md` ≤ 2KB, (b) priority tiers drop correctly with synthetic large input, (c) idempotency prevents double-write, (d) prompt is readable by `/ll:resume` (schema validation).

5. **Update docs**: `docs/guides/SESSION_HANDOFF.md` to note automatic PreCompact trigger; `docs/ARCHITECTURE.md:92` PreCompact section.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Update `skills/configure/areas.md:867`** — add a second row in the hook audit table for `precompact-handoff.sh` alongside the existing `precompact-state.sh` PreCompact entry
7. **Update `docs/development/TROUBLESHOOTING.md:753,939-942,972`** — add `precompact-handoff.sh` to the chmod list, manual test block, and timeout list
8. **Update `docs/ARCHITECTURE.md:85-98,888-955`** — add `precompact-handoff.sh` to the scripts directory listing; update the context-monitor flow diagram to show PreCompact as a second handoff trigger path
9. **Update `config-schema.json`** — if a `precompact_handoff.enabled` feature flag is introduced, add a new top-level section (cannot go under `context_monitor` due to `additionalProperties: false`)
10. **Update all `templates/*.json`** — if the feature is opt-in via config, add `"precompact_handoff": {"enabled": true}` to all 9 template files alongside `context_monitor`
11. **Review timing-sensitive tests** in `scripts/tests/test_hooks_integration.py:434,489,531` — verify that a freshly written `ll-continue-prompt.md` (from the new hook) doesn't falsely satisfy idempotency checks in the context-monitor mtime comparison within tests
12. **Update `hooks/adapters/codex/pre-compact.sh` and `hooks/adapters/codex/hooks.json:16-27`** — add a second PreCompact dispatch (new bash script entry or second Python intent invocation) for Codex host parity; update `test_codex_adapter.py` to assert the new entry
13. **Update `hooks/adapters/opencode/index.ts`** — extend `Intent` type alias (line 19) and `"session.compacted"` handler (line 64) to also invoke the new PreCompact handoff behavior; update `test_opencode_adapter.py`
14. **Update `scripts/little_loops/hooks/__init__.py`** (if Python intent approach) — add `pre_compact_handoff` to `_dispatch_table()` built-ins dict, extend `_USAGE` literal (line 48–52), and add bullet to module docstring (lines 13–27)
15. **Update `docs/reference/EVENT-SCHEMA.md:80,546`, `docs/reference/API.md:7218,6585`, `docs/reference/HOST_COMPATIBILITY.md:221`** — add per-intent payload block, extend built-ins list and adapter integration list, add per-host coverage row
16. **Update `docs/guides/BUILTIN_HOOKS_GUIDE.md:66,285`** — add new summary table row and subsection for the PreCompact handoff behavior alongside the existing state-preservation entry

## References

- Inspiration: context-mode PreCompact snapshots
- Related (completed): ENH-152 persistent handoff reminder, FEAT-150 continuation prompt integration, ENH-495 structured handoff, BUG-819 missed handoff silently continues
- Depends on: FEAT-1112 unified session store (for efficient state reconstruction; fallback path available without it — see Integration Map)

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-16 (prior: 2026-04-18 → 95/100 readiness, 56/100 outcome)_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 55/100 → LOW

### Outcome Risk Factors
- **Open decision — bash vs Python approach**: June 2026 architecture update explicitly flags this unresolved decision; "decide which to follow before starting implementation" — this must be resolved in FEAT-1156 before coding starts.
- **Timing-sensitive tests**: `test_hooks_integration.py:434,489,531` rely on `ll-continue-prompt.md` mtime comparisons; a fresh PreCompact write could falsely satisfy idempotency checks in those tests — review before committing.
- **Feature-flag opt-in vs always-on**: Determines whether all 9 `templates/*.json` and `config-schema.json` need updating; resolve before scoping FEAT-1158.
- **Very large change surface**: 16 steps across 3 host adapters, Python dispatch, 9 templates, 15+ docs, 8+ test additions — implement via child issues FEAT-1156/1157/1158.

## Deferral Rationale

_2026-04-18_: Deferred after discovering that headless mode (ll-loop, ll-auto, ll-parallel) already handles handoff automatically via the FSM signal-detection path (`fsm/executor.py:1084`, `subprocess_utils.py:31`). The original issue assumed all modes lacked automatic handoff, but this only applies to interactive sessions. Sub-issues FEAT-1156, FEAT-1157, FEAT-1158 marked `wont_do`. If re-opened, scope to interactive-session gap only.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-16T23:18:07 - `7610fcbf-3024-48de-879f-3565c425d173.jsonl`
- `/ll:confidence-check` - 2026-06-16T23:30:00Z - `f1cfd32d-9915-4da3-89f1-643c1c09bfb4.jsonl`
- `/ll:wire-issue` - 2026-06-16T23:05:09 - `6bc84bfa-fc14-45b4-b36b-142a14cd7862.jsonl`
- `/ll:refine-issue` - 2026-06-16T22:54:43 - `7e4f8e86-755c-43c1-9f4f-339908ce5b14.jsonl`
- `/ll:format-issue` - 2026-06-16T22:47:52 - `0b38eeca-4742-48bd-a340-8119ef1ef216.jsonl`
- `hook:posttooluse-git-mv` - 2026-04-18T19:00:24 - `91b72715-a97b-45f0-886e-3a458fc6988e.jsonl`
- `hook:posttooluse-git-mv` - 2026-04-18T18:52:08 - `142cccc0-40c0-4e81-9bc5-c7b696233355.jsonl`
- `/ll:wire-issue` - 2026-04-18T18:47:29 - `03a2b1c7-5059-4611-867d-d0ffd754d04b.jsonl`
- `/ll:refine-issue` - 2026-04-18T18:40:29 - `39dbbbf8-ebcc-4b8e-9adf-55fc86c3a89d.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `03a2b1c7-5059-4611-867d-d0ffd754d04b.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `142cccc0-40c0-4e81-9bc5-c7b696233355.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-18
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1156: PreCompact Handoff Hook — Core Implementation
- FEAT-1157: PreCompact Handoff Hook — Integration Tests
- FEAT-1158: PreCompact Handoff Hook — Docs & Configuration
