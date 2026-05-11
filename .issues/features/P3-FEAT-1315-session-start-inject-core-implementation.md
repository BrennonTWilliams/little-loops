---
id: FEAT-1315
type: FEAT
priority: P3
status: open
discovered_date: 2026-05-01
discovered_by: issue-size-review
blocked_by: [FEAT-1156, FEAT-1116]
parent: FEAT-1263

decision_needed: false
confidence_score: 90
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
size: Very Large
relates_to: ['FEAT-1156', 'FEAT-1264', 'FEAT-1262', 'FEAT-1316']
---

# FEAT-1315: SessionStart Inject — Core Hook Implementation

## Summary

Implement `hooks/scripts/session-start-inject.sh` (the SessionStart hook script), register it in `hooks/hooks.json`, add sentinel cleanup to `hooks/scripts/session-cleanup.sh`, add `.ll/ll-session-injected` to `.gitignore`, update `commands/resume.md` for sentinel compatibility, and add the `TestSessionStartInject` test class.

## Parent Issue

Decomposed from FEAT-1263: SessionStart Context Injector (`session-start-inject.sh`)

## Motivation

The current resume flow is passive: `ll-continue-prompt.md` is a file Claude *can* read, not a directive Claude *receives*. After compaction, Claude typically asks the user to re-explain what they were doing. A SessionStart hook that outputs `additionalContext` makes context restoration authoritative — Claude receives a structured brief at session start, not a file reference.

## Acceptance Criteria

- `hooks/scripts/session-start-inject.sh` exists and is executable
- Hook fires on SessionStart and reads `.ll/ll-continue-prompt.md` if it exists
- Freshness check: only inject if prompt mtime is within `continuation.prompt_expiry_hours` (from `ll-config.json`; default 24h)
- Output format: valid `additionalContext` JSON envelope as required by the Claude Code SessionStart hook protocol (`hookSpecificOutput.hookEventName + additionalContext`)
- Injected content includes a `<continue_from>` directive plus the `## Intent`, `## Next Steps`, and `## File Modifications` sections from the prompt
- Hook marks the prompt as consumed (writes `.ll/ll-session-injected` sentinel) to prevent re-injection within the same session
- `hooks/hooks.json` registers the script as a second SessionStart entry
- `hooks/scripts/session-cleanup.sh` clears `.ll/ll-session-injected` in its Stop hook cleanup block
- `.gitignore` includes `.ll/ll-session-injected` under the `# little-loops context/sync state files` section
- `commands/resume.md` Validate Prompt step checks for sentinel and notes "context already injected at session start" if present
- `TestSessionStartInject` class added to `scripts/tests/test_hooks_integration.py` with 6 test cases

## Implementation

### New File: `hooks/scripts/session-start-inject.sh`

Standard hook preamble (matches `user-prompt-check.sh`, `context-monitor.sh`, `precompact-state.sh`):

```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source // ""')
ll_resolve_config
```

Logic sequence:
1. `if ! ll_feature_enabled "continuation.enabled"; then exit 0; fi`
2. Check `.ll/ll-session-injected` sentinel does not exist (idempotency guard)
3. Freshness check using `get_mtime` and `ll_config_value "continuation.prompt_expiry_hours" "24"`:
   ```bash
   EXPIRY_HOURS=$(ll_config_value "continuation.prompt_expiry_hours" "24")
   FILE_MTIME=$(get_mtime ".ll/ll-continue-prompt.md")
   NOW_EPOCH=$(date +%s)
   EXPIRY_SECONDS=$((EXPIRY_HOURS * 3600))
   if [ "$FILE_MTIME" -le 0 ] || [ $((NOW_EPOCH - FILE_MTIME)) -ge "$EXPIRY_SECONDS" ]; then
       exit 0
   fi
   ```
4. Parse `## Intent`, `## File Modifications`, `## Next Steps` sections from the prompt using inline awk (keeps hook lightweight, no Python spawn):
   `awk '/^## Intent$/,/^## /'` pattern
5. Build output via `jq -nc --arg ctx "$CTX" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'` (mirrors `hooks/scripts/scratch-pad-redirect.sh:87-89`)
6. Write `.ll/ll-session-injected` sentinel with ISO-8601 timestamp
7. On any failure, `exit 0` silently — must not block session start

### Registration: `hooks/hooks.json`

Add second sibling entry to SessionStart array (after `hooks.json:4-16`):

```json
{
  "matcher": "*",
  "hooks": [
    {
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-start-inject.sh",
      "timeout": 5,
      "statusMessage": "Restoring session context..."
    }
  ]
}
```

Use `"*"` matcher; freshness/sentinel checks already gate injection.

### `hooks/scripts/session-cleanup.sh` — Sentinel Cleanup

Add `rm -f .ll/ll-session-injected 2>/dev/null || true` to the Stop hook cleanup block so the sentinel is cleared between sessions. Without this, injection is permanently blocked after the first session.

### `.gitignore`

Add `.ll/ll-session-injected` under the `# little-loops context/sync state files` section (around line 84–92).

### `commands/resume.md` Compatibility

In step 2 (Validate Prompt, currently lines 43-50): if `.ll/ll-session-injected` exists and is newer than the prompt, prepend "context already injected at session start" to the resume display rather than re-displaying the full prompt.

### Tests: `TestSessionStartInject`

Add to `scripts/tests/test_hooks_integration.py` after `TestPrecompactState` (~line 1467), before `TestScratchPadRedirect` (line 1545). Model `_write_config`/`_run` helpers from `TestScratchPadRedirect`; use `input=json.dumps({"source":"compact"})` + `json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]` assertion chain:

1. Fresh prompt → injects `additionalContext` with `<continue_from>` directive
2. Stale prompt (mtime > expiry) → no output, exits 0
3. Missing prompt file → no output, exits 0
4. Sentinel present → no output (idempotency)
5. Malformed prompt → exits 0 (failure-safe)
6. Compact-source and non-compact-source: document the decided behavior in a script comment; test both

## Files to Modify

- `hooks/hooks.json:4-16` — add second entry to SessionStart array
- `hooks/scripts/session-cleanup.sh` — add sentinel `rm -f` to Stop cleanup block
- `.gitignore` — add `.ll/ll-session-injected` (~line 84-92)
- `commands/resume.md:43-50` — extend Validate Prompt step with sentinel check
- `scripts/tests/test_hooks_integration.py` — add `TestSessionStartInject` class at line 1543 (between `TestPrecompactState` end and `TestScratchPadRedirect` start)

## New Files

- `hooks/scripts/session-start-inject.sh`
- `.ll/ll-session-injected` (runtime artifact, gitignored)

## Hook Library Anchors (`hooks/scripts/lib/common.sh`)

| Function | Line | Usage |
|----------|------|-------|
| `ll_resolve_config` | 184 | Sets `$LL_CONFIG_FILE`; call before `ll_config_value`/`ll_feature_enabled` |
| `ll_feature_enabled` | 198 | `if ! ll_feature_enabled "continuation.enabled"; then exit 0; fi` |
| `ll_config_value` | 218 | `EXPIRY_HOURS=$(ll_config_value "continuation.prompt_expiry_hours" "24")` |
| `get_mtime` | 134 | `MTIME=$(get_mtime ".ll/ll-continue-prompt.md")` — returns `"0"` if missing |

## Codebase Research Findings

_Added by `/ll:refine-issue` — verified against the codebase on 2026-05-01:_

### Verified Anchors

All file paths and line references in this issue have been verified against the current codebase:

- `hooks/scripts/lib/common.sh` — `get_mtime` line 134, `ll_resolve_config` line 184, `ll_feature_enabled` line 198, `ll_config_value` line 218 (all confirmed)
- `hooks/hooks.json:4-16` — SessionStart array with single existing entry; insertion point for the new sibling is after line 15 (confirmed)
- `hooks/scripts/scratch-pad-redirect.sh:87-89` — canonical `jq -nc` `additionalContext` envelope (confirmed)
- `commands/resume.md:43-50` — Validate Prompt step (confirmed; bullets at lines 47–50)
- `scripts/tests/test_hooks_integration.py` — `TestPrecompactState` starts at line 1468; `TestScratchPadRedirect` starts at line 1545; insertion point for `TestSessionStartInject` is between them (confirmed)
- `.gitignore` — `# little-loops context/sync state files` section at lines 83–93 (confirmed; `.ll/ll-continue-prompt.md` already listed at line 87)

### Sibling Hook, Not Replacement

There is already a `hooks/scripts/session-start.sh` registered as the existing SessionStart entry (currently the sole hook in `hooks.json:5-15`). Its purpose is config resolution / local-overlay merge / feature validation, and it does **not** consume stdin or use `lib/common.sh`. The new `session-start-inject.sh` is a **sibling**, registered as a second array entry, and uses the standard `lib/common.sh` preamble (matching `user-prompt-check.sh`, `context-monitor.sh`, `precompact-state.sh`). Do not modify `session-start.sh`.

### Precedent for mtime/freshness Check

The closest existing pattern is in `hooks/scripts/context-monitor.sh:334-347` (inside `main()`), which already reads `.ll/ll-continue-prompt.md` mtime via `get_mtime` and compares against another epoch using integer arithmetic. Use the same shape for the expiry check.

### New Patterns Introduced by This Issue

The following patterns are **new to the repo** — there is no prior example to copy from, so they must be implemented as specified:

- **`additionalContext` emission for SessionStart**: `scratch-pad-redirect.sh:87-89` is currently the only hook emitting a `hookSpecificOutput`/`additionalContext` envelope, and it uses `hookEventName:"PreToolUse"`. This will be the first SessionStart emitter. The protocol shape is documented at `docs/claude-code/hooks-reference.md:594-600`.
- **Sentinel write**: No hook currently writes a marker file for idempotency. The closest analog is `context-monitor.sh:266` (which deletes `.ll/ll-precompact-state.json` after handling). Use `echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .ll/ll-session-injected 2>/dev/null || true`.
- **Markdown section parsing in shell**: No existing awk/sed-based markdown extractor in `hooks/scripts/`. The `awk '/^## Intent$/,/^## /'` range-address pattern in the spec is a clean POSIX form.

### Source Section Reference

The shape of `## Intent`, `## Next Steps`, `## File Modifications` headings is defined by `hooks/prompts/continuation-prompt-template.md` (the producer template owned by FEAT-1156/FEAT-1264). Section names must match that template exactly so the awk range pattern matches.

### Test Pattern References

- **Class to model**: `TestScratchPadRedirect` (`scripts/tests/test_hooks_integration.py:1545`) — copy `_write_config` (line 1553) and `_run` (line 1569) helpers; the JSON assertion chain `json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]` appears at line 1643 onward.
- **Time-based test pattern**: `TestContextMonitor.test_reminder_fires_again_after_cooldown_expires` (`scripts/tests/test_hooks_integration.py:621`) — shows how to pre-age a state file before invoking the hook (use `os.utime(path, (past, past))`); apply the same approach for the stale-prompt test case.
- **`os.chdir(tmp_path)` framing**: every test method in this file uses a `try/finally` `os.chdir` frame (see `test_concurrent_updates:38`); the new tests must follow the same pattern because the hook resolves paths relative to CWD.

### `session-cleanup.sh` Insertion Point (Specific)

The `cleanup()` function spans lines 12–46, but the natural insertion point is line 14, where `.ll/.ll-lock` and `.ll/ll-context-state.json` are removed together. Either consolidate into one line (`rm -f .ll/.ll-lock .ll/ll-context-state.json .ll/ll-session-injected 2>/dev/null || true`) or add an adjacent `rm -f .ll/ll-session-injected 2>/dev/null || true` line — the script's `2>/dev/null || true` discipline (cleanup must never fail) is mandatory.

### Source Field Decision (test case 6)

The spec extracts `SOURCE=$(echo "$INPUT" | jq -r '.source // ""')` but does not branch on it. Per Acceptance Criteria test case 6 ("document the decided behavior in a script comment; test both"), the implementer chooses one of:
1. **Inject for all sources** (recommended — simplest, freshness check already gates noise)
> **Selected:** Option 1: Inject for all sources — all 8 existing hooks use `"*"` matcher without source branching; freshness check + sentinel already gate injection; parent FEAT-1263 explicitly designed for this approach.
2. **Inject only when `source == "compact"`** (narrower — but `resume`/`startup`/`clear` sources also benefit from continuation context)
3. **Inject for all except `clear`** (compromise)

Document the chosen behavior as a header comment in `session-start-inject.sh` and exercise both branches in the test class.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-01.

**Selected**: Option 1: Inject for all sources

**Reasoning**: Every existing hook in the codebase uses `"*"` matcher without branching on the `source` field — no existing hook reads the `source` field from stdin at all. The freshness check (`get_mtime` vs `prompt_expiry_hours`) and the `.ll/ll-session-injected` sentinel already prevent stale or duplicate injection, making source-based filtering redundant. The parent FEAT-1263 completed-issue design (`hooks-reference.md:572`) explicitly documented `"*"` matcher + freshness/sentinel as sufficient.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1: Inject all | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option 3: All except clear | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |
| Option 2: Compact-only | 1/3 | 2/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option 1: All 8 hook scripts use `"*"` matcher; `context-monitor.sh:334-347` shows mtime/expiry as the established gate; `scratch-pad-redirect.sh:87-89` reusable as `additionalContext` envelope; parent FEAT-1263 completed-issue explicitly chose `"*"` with freshness gates (`hooks/scripts/lib/common.sh:134,198,218` all directly reusable)
- Option 2: Zero existing hooks read `source` field; issue itself notes resume/startup/clear also benefit from continuation context (reuse score 1/3); significantly narrows feature utility
- Option 3: Early-exit-by-field pattern exists in `scratch-pad-redirect.sh:42-44`; but parent FEAT-1263 explicitly argued freshness check is sufficient gate without source branching (reuse score 2/3)

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
No direct callers or importers — `session-start-inject.sh` is invoked exclusively by the Claude Code hook runner via `hooks/hooks.json`. The `lib/common.sh` library functions (`ll_resolve_config`, `ll_feature_enabled`, `ll_config_value`, `get_mtime`) are already defined at their documented anchors and require no modification.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hooks_integration.py` — add `TestSessionStartInject` class between `TestPrecompactState` (ends line 1542) and `TestScratchPadRedirect` (starts line 1545); copy `_write_config` (line 1553) and `_run` (line 1569) helper pattern from `TestScratchPadRedirect`; assertion chain: `json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]`
- No existing tests will break: `TestSessionStartValidation` tests `session-start.sh` (not modified); `session-cleanup.sh` has zero existing test coverage; `commands/resume.md` has zero existing test coverage; `TestDetectConfigGaps` uses synthetic `hooks.json` in `tmp_path` and does not assert on entry count

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — **no change needed**: both `continuation.enabled` (line 488, boolean, default `true`) and `continuation.prompt_expiry_hours` (line 520, integer, default 24, min 1, max 168) are already defined correctly under the `continuation` object at line 484

### Template Dependency

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/prompts/continuation-prompt-template.md` — **do not modify** (owned by FEAT-1156/FEAT-1264): current template uses legacy section headings (`## Context`, `## Current State`, etc.) and does **not** produce `## Intent`, `## Next Steps`, or `## File Modifications` — the three headings `session-start-inject.sh` parses via awk range patterns. The hook will safely emit empty `additionalContext` (not fail) until FEAT-1156/FEAT-1264 ship the updated template. This is the structural reason for `blocked_by: [FEAT-1156, FEAT-1116]`.

## Scope Boundary

This issue implements the hook and all functional wiring. Documentation updates for the newly-shipped behavior are tracked in FEAT-1316. FEAT-1316 should be worked after this issue ships.

This issue does NOT modify how `ll-continue-prompt.md` is produced (FEAT-1156 and FEAT-1264 own that).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-01_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Multi-subsystem span** (10/25 complexity): 6 files across shell, JSON, markdown, and Python — run `jq . hooks/hooks.json` after editing to catch syntax errors early
- **Untested modification surfaces**: `session-cleanup.sh` sentinel `rm -f` and `commands/resume.md` sentinel check have zero automated test coverage — smoke-test both paths manually after implementation
- **Source-field decision still open** (`decision_needed: true`): choose one of the 3 documented options (inject-all / compact-only / all-except-clear) before writing test case 6; document the chosen behavior as a script header comment

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-05T02:27:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d743dae1-3278-4abd-a763-b23632abd3cb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:decide-issue` - 2026-05-02T03:06:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a6ed7bfa-f06a-46a2-b3b0-31a947ceaf0a.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9dc6be6f-9ae9-42eb-8b36-2a19186357ee.jsonl`
- `/ll:refine-issue` - 2026-05-02T02:58:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/af0b6a0d-8f6c-4311-b5e4-babea0309bc4.jsonl`
- `/ll:wire-issue` - 2026-05-02T02:51:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9bfc87dc-2252-4640-b95c-d480acced029.jsonl`
- `/ll:refine-issue` - 2026-05-02T02:46:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f78dca6-c355-4116-98b4-8735e5ca4fc8.jsonl`
- `/ll:issue-size-review` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29f10429-7b81-4ece-9545-cd5da490acdd.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9bfc87dc-2252-4640-b95c-d480acced029.jsonl`

## Blocks

- FEAT-1317
- FEAT-1318
- FEAT-1319

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): Add `FEAT-1262` to this issue's `related` frontmatter. The quality of the injected `additionalContext` depends on the FEAT-1262 → FEAT-1264 pipeline: FEAT-1262 (`session-capture.sh`) produces `.ll/ll-session-events.jsonl`; FEAT-1264 uses it to build a richer `ll-continue-prompt.md`; this hook injects that richer prompt. When FEAT-1262 has not yet shipped, the injected context is accurate but lower-fidelity. Document this degradation in the implementation as a known behavior, not a bug.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): `session-start-inject.sh` is an interim shell implementation. FEAT-1116 (Hook-Intent Abstraction Layer) will migrate SessionStart hooks from `hooks/scripts/` shell scripts to Python core handlers (`scripts/little_loops/hooks/session_start.py`) with thin per-host adapters. Implement `session-start-inject.sh` as specified here for the MVP, but scope it to be replaced by — or restructured as — the Python core handler + Claude Code adapter pattern once FEAT-1116's SessionStart migration scaffolding is in place. This matches the approach taken by FEAT-1156 (`precompact-handoff.sh`). When FEAT-1116 lands, open a follow-up to port the inject logic to `scripts/little_loops/hooks/pre_compact.py` (or the equivalent intent module for SessionStart) and replace `session-start-inject.sh` with a thin `hooks/adapters/claude-code/session-start-inject.sh` wrapper.
