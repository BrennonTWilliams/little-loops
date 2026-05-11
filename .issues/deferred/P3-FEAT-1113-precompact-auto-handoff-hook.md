---
id: FEAT-1113
type: FEAT
priority: P3
status: deferred
discovered_date: 2026-04-15
discovered_by: capture-issue
blocked_by: [FEAT-1112]

confidence_score: 95
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
size: Very Large
relates_to: ['ENH-152', 'ENH-495', 'FEAT-150']
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

## Acceptance Criteria

- Hook fires on PreCompact and produces `.ll/ll-continue-prompt.md` ≤2KB
- Priority-tier dropping tested with synthetic large inputs
- No duplicate handoff when user already ran `/ll:handoff` in same session (idempotency marker)
- Integration test verifies continuation prompt is picked up by SessionStart hook on next run
- CLAUDE.md / handoff docs updated

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:207` — imports `read_continuation_prompt`; calls it after detecting `CONTEXT_HANDOFF_PATTERN` in stdout (note: PreCompact hook does NOT emit this signal, so automation pickup happens via `/ll:resume` next session, not here — but verify no assumptions break) [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py:715` — same `read_continuation_prompt` consumer as `issue_manager.py` [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py` — imports `HandoffHandler`; manages `handoff_handler` instance and `_pending_handoff` state; reads `ll-continue-prompt.md` indirectly [Agent 1 finding]
- `scripts/little_loops/fsm/persistence.py` — declares `continuation_prompt` field on `LoopState` (serialized); verify field name matches prompt content written by new hook [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — reads `state.continuation_prompt` for display/resume; sets `LL_HANDOFF_THRESHOLD` env var consumed by `context-monitor.sh` [Agent 1 finding]
- `skills/manage-issue/SKILL.md:295-304` — reads `$(pwd)/.ll/ll-continue-prompt.md` on `--resume`; writes `ll-continue-prompt.md` on manual handoff — will coexist with auto-written file; verify idempotency logic covers this case [Agent 1 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json:524-602` — `context_monitor` section has `"additionalProperties": false`; any new `precompact_handoff.*` config key must be added as a new top-level section (cannot be added under `context_monitor`) [Agent 2 finding]
- `skills/configure/areas.md:867` — hook audit display table lists `[Plugin] PreCompact * precompact-state.sh 5s`; must add row for `precompact-handoff.sh` when registered [Agent 1 + 2 finding]
- `templates/generic.json` (and all 8 other `templates/*.json`) — have `"context_monitor": {"enabled": true}` block; add `"precompact_handoff": {"enabled": true}` block if feature is opt-in [Agent 2 finding]

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

## References

- Inspiration: context-mode PreCompact snapshots
- Related (completed): ENH-152 persistent handoff reminder, FEAT-150 continuation prompt integration, ENH-495 structured handoff, BUG-819 missed handoff silently continues
- Depends on: FEAT-1112 unified session store (for efficient state reconstruction; fallback path available without it — see Integration Map)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-18_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Outcome Risk Factors
- **Timing-sensitive tests**: `test_hooks_integration.py:434,489,531` rely on `ll-continue-prompt.md` mtime comparisons; a fresh PreCompact write could falsely satisfy idempotency checks in those tests — review before committing.
- **Template sprawl**: Whether the feature is opt-in (feature flag) vs. always-on determines if all 9 `templates/*.json` and `config-schema.json` need updating. Decide this first to bound scope.
- **Bash size-capping logic**: Priority-tier dropping under `set -euo pipefail` is brittle; write the `TestPrecompactHandoff` test for size-pressure behavior before implementing the script body.

## Deferral Rationale

_2026-04-18_: Deferred after discovering that headless mode (ll-loop, ll-auto, ll-parallel) already handles handoff automatically via the FSM signal-detection path (`fsm/executor.py:1084`, `subprocess_utils.py:31`). The original issue assumed all modes lacked automatic handoff, but this only applies to interactive sessions. Sub-issues FEAT-1156, FEAT-1157, FEAT-1158 marked `wont_do`. If re-opened, scope to interactive-session gap only.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-18T19:00:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91b72715-a97b-45f0-886e-3a458fc6988e.jsonl`
- `hook:posttooluse-git-mv` - 2026-04-18T18:52:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/142cccc0-40c0-4e81-9bc5-c7b696233355.jsonl`
- `/ll:wire-issue` - 2026-04-18T18:47:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03a2b1c7-5059-4611-867d-d0ffd754d04b.jsonl`
- `/ll:refine-issue` - 2026-04-18T18:40:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/39dbbbf8-ebcc-4b8e-9adf-55fc86c3a89d.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03a2b1c7-5059-4611-867d-d0ffd754d04b.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/142cccc0-40c0-4e81-9bc5-c7b696233355.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-18
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1156: PreCompact Handoff Hook — Core Implementation
- FEAT-1157: PreCompact Handoff Hook — Integration Tests
- FEAT-1158: PreCompact Handoff Hook — Docs & Configuration
