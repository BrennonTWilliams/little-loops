---
id: FEAT-1263
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-22
discovered_by: issue-size-review
blocked_by: [FEAT-1156, FEAT-1116]
parent: FEAT-1159

confidence_score: 88
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
relates_to: ['FEAT-1156', 'FEAT-1264', 'FEAT-1262']
completed_at: 2026-05-10T00:00:00Z
---

# FEAT-1263: SessionStart Context Injector (`session-start-inject.sh`)

## Summary

Implement `hooks/scripts/session-start-inject.sh` as a SessionStart hook that reads `ll-continue-prompt.md` (when fresh) and outputs it as `additionalContext` JSON, injecting the handoff snapshot authoritatively into Claude's context on session resume — without requiring the user to run `/ll:resume`.

## Parent Issue

Decomposed from FEAT-1159: Continuous Session Event Capture with PreCompact Guarantee and SessionStart Injection

## Motivation

The current resume flow is passive: `ll-continue-prompt.md` is a file Claude *can* read, not a directive Claude *receives*. After compaction, Claude typically asks the user to re-explain what they were doing. A SessionStart hook that outputs `additionalContext` makes context restoration authoritative — Claude receives a structured brief at session start, not a file reference.

## Acceptance Criteria

- `hooks/scripts/session-start-inject.sh` exists and is executable
- Hook fires on SessionStart and reads `.ll/ll-continue-prompt.md` if it exists
- Freshness check: only inject if prompt mtime is within `continuation.prompt_expiry_hours` (from `ll-config.json`; default 24h)
- Output format: valid `additionalContext` JSON as required by the Claude Code SessionStart hook protocol
- Injected content includes a `<continue_from>` directive plus the `## Intent`, `## Next Steps`, and `## File Modifications` sections from the prompt
- Hook marks the prompt as consumed (writes a `.ll/ll-session-injected` sentinel) to prevent re-injection within the same session
- Existing `/ll:resume` manual flow continues to work unchanged — if the prompt was already injected, `/ll:resume` is a no-op or notes "already injected"
- `TestSessionStartInject` class added to `scripts/tests/test_hooks_integration.py`
- `hooks/hooks.json` registers the script as a SessionStart entry

## Implementation

### New File: `hooks/scripts/session-start-inject.sh`

- Read stdin JSON, extract `source` field (detect `"compact"` source for priority injection)
- Source `hooks/scripts/lib/common.sh`
- Check `ll_feature_enabled` guard
- Check `.ll/ll-continue-prompt.md` exists and passes freshness check (`get_mtime` vs expiry window)
- Check `.ll/ll-session-injected` sentinel does not exist (idempotency)
- Parse `## Intent`, `## File Modifications`, `## Next Steps` sections from the prompt with awk/grep
- Build `additionalContext` output:
  ```json
  {"additionalContext": "<continue_from>\n## Intent\n...\n## Next Steps\n...\n</continue_from>"}
  ```
- Write `.ll/ll-session-injected` sentinel with timestamp
- On any failure (file missing, parse error), exit 0 silently — must not block session start

### Freshness Check

Use `get_mtime` from `lib/common.sh` on `.ll/ll-continue-prompt.md`. Compare against current time minus `continuation.prompt_expiry_hours` (from `ll_config_value`). Stale prompts are silently skipped.

### Idempotency

`.ll/ll-session-injected` sentinel file (timestamp only). Cleared at session end by `precompact-state.sh` or on next PreCompact event. Do not re-inject if sentinel is present and same-session.

### Registration: `hooks/hooks.json`

Add `session-start-inject.sh` to the SessionStart array.

### Tests: `TestSessionStartInject`

Add to `scripts/tests/test_hooks_integration.py`:
- Fresh prompt → injects `additionalContext` with `<continue_from>` directive
- Stale prompt (mtime > expiry) → no output, exits 0
- Missing prompt file → no output, exits 0
- Sentinel present → no output (idempotency)
- Malformed prompt → exits 0 (failure-safe)
- Compact-source SessionStart injects; non-compact source still injects if prompt is fresh (decide during implementation whether to filter on source)

### `/ll:resume` Compatibility

`commands/resume.md:28-42` reads `ll-continue-prompt.md` directly. This hook does not change that file. If `.ll/ll-session-injected` exists, `/ll:resume` should note "context already injected at session start" rather than re-displaying — update `commands/resume.md` to check the sentinel.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Add `rm -f .ll/ll-session-injected 2>/dev/null || true` to `hooks/scripts/session-cleanup.sh` Stop hook cleanup block — without this, the sentinel persists indefinitely and blocks injection on every subsequent session after the first
2. Add `.ll/ll-session-injected` to `.gitignore` under the `# little-loops context/sync state files` section
3. Update `skills/configure/areas.md` hardcoded hook table (~line 861) to add `session-start-inject.sh` as second SessionStart entry
4. Update `docs/guides/SESSION_HANDOFF.md` in three places: flow diagram, `## Files` table (add sentinel), `### Auto-Detect on Session Start` section (reflect active injection)
5. Update `commands/handoff.md` `### 4. Output Handoff Signal` — change "Run /ll:resume" from required to optional/automatic
6. Update `docs/ARCHITECTURE.md` directory structure listing to include `session-start-inject.sh`
7. Update `docs/reference/CONFIGURATION.md` `### continuation` — clarify `auto_detect_on_session_start` vs new active injection behavior
8. Update `docs/reference/COMMANDS.md` `/ll:resume` description to mention automatic injection path

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis 2026-05-01:_

### Output Format Correction (Critical)

The example JSON in `### New File` above (`{"additionalContext": "..."}`) is **incomplete** per the official Claude Code SessionStart hook protocol. Per `docs/claude-code/hooks-reference.md:594-601`, the correct envelope is:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<continue_from>\n## Intent\n...\n## Next Steps\n...\n</continue_from>"
  }
}
```

Build with `jq -nc --arg ctx "$CTX" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'` (mirrors `hooks/scripts/scratch-pad-redirect.sh:87-89`).

**Alternative path** — per `hooks-reference.md:420`, SessionStart hooks may instead emit plain stdout text (no JSON envelope) which is also added to Claude's context. The existing `hooks/scripts/session-start.sh` uses this simpler approach. Choose JSON envelope here for the explicit `<continue_from>` directive boundary; plain text would lose the structured framing.

### Markdown Section Parsing Approach

The issue specifies "with awk/grep" but **no bash awk/sed section parser exists in the codebase**. Two viable approaches:

1. **Inline awk** (new pattern, self-contained): standard `awk '/^## Intent$/,/^## /'` block extraction — keeps the hook free of Python dependency
2. **Python heredoc** (matches `session-start.sh:25-97` precedent): invoke `python3 <<'PYTHON'` and call `parse_sections()` from `scripts/little_loops/output_parsing.py:118` (already implemented `## HEADER` → dict parser)

Recommend **inline awk** — keeps a single-event SessionStart hook lightweight and avoids spawning a Python interpreter on every session start. The script is short enough that duplicating `parse_sections` logic in awk is cheap.

### Hook Library Anchors (`hooks/scripts/lib/common.sh`)

| Function | Line | Usage |
|----------|------|-------|
| `ll_resolve_config` | 184 | Sets `$LL_CONFIG_FILE`; call before `ll_config_value`/`ll_feature_enabled` |
| `ll_feature_enabled` | 198 | `if ! ll_feature_enabled "continuation.enabled"; then exit 0; fi` |
| `ll_config_value` | 218 | `EXPIRY_HOURS=$(ll_config_value "continuation.prompt_expiry_hours" "24")` |
| `get_mtime` | 134 | `MTIME=$(get_mtime ".ll/ll-continue-prompt.md")` — returns `"0"` if missing |

### Freshness Check Bash Idiom

The TTL pattern is **not yet implemented** in any existing hook (the closest is the rate-limit cooldown in `context-monitor.sh:351-357`). Standard idiom for this hook:

```bash
EXPIRY_HOURS=$(ll_config_value "continuation.prompt_expiry_hours" "24")
FILE_MTIME=$(get_mtime ".ll/ll-continue-prompt.md")
NOW_EPOCH=$(date +%s)
EXPIRY_SECONDS=$((EXPIRY_HOURS * 3600))
if [ "$FILE_MTIME" -le 0 ] || [ $((NOW_EPOCH - FILE_MTIME)) -ge "$EXPIRY_SECONDS" ]; then
    exit 0  # missing or stale — silent skip
fi
```

### Standard Hook Preamble (matches `user-prompt-check.sh`, `context-monitor.sh`, `precompact-state.sh`)

```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
INPUT=$(cat)
SOURCE=$(echo "$INPUT" | jq -r '.source // ""')
ll_resolve_config
```

Note: `hooks/scripts/session-start.sh` is a deliberate exception that does NOT source `common.sh` and does NOT read stdin — but the new hook needs both, so it follows the standard preamble.

### `hooks/hooks.json` Registration Block (`hooks.json:4-16`)

The existing SessionStart array contains one entry; add a second sibling entry with the same shape:

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

Valid SessionStart matcher values: `startup`, `resume`, `clear`, `compact` (`hooks-reference.md:572`). Use `"*"` for all sources; the freshness/sentinel checks already gate injection appropriately.

### Test Class Reference

Model `TestSessionStartInject` after `TestSessionStartValidation` at `scripts/tests/test_hooks_integration.py:1318`. Pattern: `os.chdir(tmp_path)` + `try/finally`, write `.ll/ll-config.json` and `.ll/ll-continue-prompt.md` inline, invoke via `subprocess.run([str(hook_script)], input=json.dumps({"source":"compact"}), capture_output=True, text=True, timeout=5)`. Assert on `result.stdout` parsed as JSON: `output["hookSpecificOutput"]["additionalContext"]`. Reference `TestScratchPadRedirect` at line 1545 for the JSON-stdout assertion idiom.

### Sentinel Pattern Note

Issue specifies a standalone `.ll/ll-session-injected` file. The codebase precedent (`context-monitor.sh:319-349`) embeds the idempotency flag inside an existing `.ll/` JSON state file rather than using a separate sentinel — but a standalone sentinel is acceptable here since it has no other state to colocate with. Sentinel content can be the ISO-8601 injection timestamp (one line).

### Continuation Prompt Producer

`ll-continue-prompt.md` is produced by `commands/handoff.md` (interactive) and will additionally be produced by `precompact-handoff.sh` (FEAT-1156, not yet implemented). `precompact-state.sh:66-69` only flags its existence in the state JSON; it does not author the file.

### Resume Compatibility Update

The line reference `commands/resume.md:28-42` in the issue is approximate. The actual relevant range is `commands/resume.md:23-50` (Locate + Validate steps). Add the sentinel check in step 2 (Validate Prompt, currently lines 43-50): if `.ll/ll-session-injected` exists and is newer than the prompt, prepend "context already injected at session start" to the resume display.

## Files to Modify

- `hooks/hooks.json:4-16` — add second entry to SessionStart array for `session-start-inject.sh` (matches existing entry shape)
- `scripts/tests/test_hooks_integration.py` — add `TestSessionStartInject` class after `TestSessionStartValidation` (line 1318), modeling JSON-stdout assertions on `TestScratchPadRedirect` (line 1545)
- `commands/resume.md:43-50` — extend Validate Prompt step with `.ll/ll-session-injected` sentinel check
- `hooks/scripts/session-cleanup.sh` — add `rm -f .ll/ll-session-injected 2>/dev/null || true` to Stop hook cleanup block so sentinel is cleared between sessions [Agent 2 finding]
- `.gitignore` — add `.ll/ll-session-injected` entry under the `# little-loops context/sync state files` section (around line 84–92) [Agent 2 finding]

## New Files

- `hooks/scripts/session-start-inject.sh`
- `.ll/ll-session-injected` (runtime artifact, gitignored)

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/scripts/session-cleanup.sh` — Stop hook; must clear `.ll/ll-session-injected` so next session can re-inject; currently only removes `.ll/.ll-lock` and `.ll/ll-context-state.json` [Agent 2 finding]
- `hooks/scripts/precompact-state.sh` — PreCompact hook; issue claims it clears sentinel but it does not; sentinel clearing belongs in `session-cleanup.sh` (Stop) instead [Agent 2 finding]
- `hooks/scripts/session-start.sh` — existing SessionStart sibling; clears `ll-context-state.json` at line 13 but does not touch the new sentinel — no change needed, documented for clarity [Agent 2 finding]
- `hooks/scripts/context-monitor.sh` — checks for continuation state and handoff signals; no code change needed but registers as a consumer of `.ll/ll-continue-prompt.md` [Agent 1 finding]
- `scripts/little_loops/subprocess_utils.py` — `read_continuation_prompt()` (lines 47–59) reads the same `.ll/ll-continue-prompt.md`; no change needed but confirms shared file dependency [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — `## Directory Structure` lists `session-start.sh` but will be stale after `session-start-inject.sh` is added; update the directory tree listing [Agent 2 finding]
- `docs/guides/SESSION_HANDOFF.md` — three update locations: (1) `## How It Works` flow diagram omits new automatic injection step; (2) `## Files` table (line 373) is missing `.ll/ll-session-injected` entry; (3) `### Auto-Detect on Session Start` (line 329) describes passive detect, not active injection [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `### continuation` at line 387: `auto_detect_on_session_start` description doesn't reflect that the new hook now performs active injection; clarify the relationship [Agent 2 finding]
- `commands/handoff.md` — `### 4. Output Handoff Signal` at line 189 tells users "Run /ll:resume" as required step 2; after FEAT-1263 this is optional/automatic — update the message [Agent 2 finding]
- `docs/reference/COMMANDS.md` — `## Session Management / /ll:resume` at line 436 omits the automatic injection path [Agent 2 finding]
- `skills/configure/areas.md` — hardcoded hook table at line 861 lists only `session-start.sh` for SessionStart event; second entry will be missing after this feature lands [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hooks_integration.py` — `TestSessionStartInject` new class (6 cases); insert after `TestPrecompactState` (~line 1467), before `TestScratchPadRedirect` (line 1545); model `_write_config`/`_run` helpers from `TestScratchPadRedirect` and use `input=json.dumps({"source":"compact"})` + `json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]` assertion chain [Agent 3 finding]
- No existing tests assert on the live `hooks/hooks.json` SessionStart array contents — adding the second entry will not break any test [Agent 3 finding]
- `scripts/tests/test_subprocess_utils.py` — `TestReadContinuationPrompt` fixture pattern (`temp_repo_with_prompt`, writing `.ll/ll-continue-prompt.md`) is reusable for `TestSessionStartInject` setup [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — `continuation.enabled` and `continuation.prompt_expiry_hours` are **already defined** (lines 484–528, `additionalProperties: false`) — no schema change required [Agent 2 + 3 finding]
- `.gitignore` — add `.ll/ll-session-injected` sentinel; currently only named `.ll/` artifacts are gitignored by individual name, not by wildcard [Agent 2 finding]

## Scope Boundary

This issue owns only the injection side. It does NOT modify how `ll-continue-prompt.md` is produced (FEAT-1156 and FEAT-1264 own that). It works with whatever snapshot format FEAT-1156 produces; FEAT-1264's richer format will automatically benefit injection once that issue lands.

FEAT-1116 risk: `session-start-inject.sh` is a SessionStart shell script in the layer FEAT-1116 is migrating. Implement as specified for unblocked delivery; plan follow-up to migrate to the adapter pattern.

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `hooks/scripts/session-start-inject.sh` does not exist ✓
- No `session-start-inject.sh` entry in `hooks/hooks.json` ✓
- Blocked by FEAT-1156 (`ll-continue-prompt.md` must exist before injection) ✓
- Feature not yet implemented ✓

## References

- Parent: FEAT-1159
- Reads from: FEAT-1156 (`precompact-handoff.sh` → `ll-continue-prompt.md`)
- Richer input when available: FEAT-1264 (event-log-driven snapshot)
- Hook utilities: `hooks/scripts/lib/common.sh` (`get_mtime`, `ll_config_value`, `ll_feature_enabled`)
- Consumer compatibility: `commands/resume.md:28-42`, `scripts/little_loops/subprocess_utils.py:31-58`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-01_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- **FEAT-1156 is open and blocked**: `precompact-handoff.sh` (FEAT-1156) is the producer of `ll-continue-prompt.md`. The hook is implementable and unit-testable in isolation, but functional E2E delivery depends on FEAT-1156 (which was blocked by FEAT-1112+FEAT-1116; FEAT-1112 is now `done`).

### Outcome Risk Factors
- **Doc surface is wide**: 6 documentation touchpoints — easy to miss one; recommend a final doc sweep pass after implementation.
- **Compact-source filtering undecided**: Test case 6 defers the decision to implementation; must be explicitly decided and documented in the script comment.

## Session Log
- `hook:posttooluse-git-mv` - 2026-05-02T02:42:20 - `d66dd1b0-da8a-48e4-b8aa-f0a5ca081782.jsonl`
- `/ll:confidence-check` - 2026-05-01T00:00:00 - `29f10429-7b81-4ece-9545-cd5da490acdd.jsonl`
- `/ll:wire-issue` - 2026-05-02T02:36:40 - `1239fb73-74ff-467e-9e81-2b5a1731b3f1.jsonl`
- `/ll:refine-issue` - 2026-05-02T02:31:16 - `64ddeff9-9667-44e6-b298-8265e21a21fb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:issue-size-review` - 2026-05-01T00:00:00 - `29f10429-7b81-4ece-9545-cd5da490acdd.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-01
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1315: SessionStart Inject — Core Hook Implementation
- FEAT-1316: SessionStart Inject — Documentation Updates
