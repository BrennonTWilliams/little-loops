---
id: FEAT-960
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-05
discovered_by: issue-size-review
parent_issue: FEAT-769
blocked_by: [FEAT-959]
---

# FEAT-960: OpenCode Shell Hooks Path Abstraction

## Summary

Update all shell hook scripts to support `.opencode/` config and state paths via `${LL_STATE_DIR:-.claude}` environment variable substitution, and inject `LL_STATE_DIR=".opencode"` from Python CLI entry points when OpenCode context is detected.

## Parent Issue

Decomposed from FEAT-769: Add OpenCode Plugin Compatibility

## Current Behavior

Shell hooks hardcode `.claude/` paths throughout:
- `hooks/scripts/lib/common.sh:186-190` — `ll_resolve_config()` hardcodes `.claude/ll-config.json`
- `hooks/scripts/session-start.sh:16,65-72` — independent `CONFIG_FILE=".claude/ll-config.json"` (shell + embedded Python)
- `hooks/scripts/session-start.sh:13` — deletes `.claude/ll-context-state.json` by hardcoded path
- `hooks/scripts/session-cleanup.sh:14,20` — independent hardcoded `.claude/` paths (does NOT source `lib/common.sh`)
- `hooks/scripts/context-monitor.sh:181,238,309` — 3 hardcoded `.claude/` state paths
- `hooks/scripts/precompact-state.sh:28,66` — `STATE_DIR=".claude"` constant

## Expected Behavior

- All shell scripts use `${LL_STATE_DIR:-.claude}` so setting `LL_STATE_DIR=".opencode"` redirects all state I/O
- `lib/common.sh:ll_resolve_config()` probes `.opencode/ll-config.json` first, falls back to `.claude/ll-config.json`
- Python CLI entry points inject `LL_STATE_DIR=".opencode"` when OpenCode context is detected
- Existing Claude Code behavior unchanged when `LL_STATE_DIR` is unset

## Acceptance Criteria

- `precompact-state.sh:28` uses `STATE_DIR="${LL_STATE_DIR:-.claude}"` (covers all 3 derived paths in that file)
- `context-monitor.sh:181,238,309` use `${LL_STATE_DIR:-.claude}` instead of hardcoded `.claude`
- `session-cleanup.sh:14,20` use `${LL_STATE_DIR:-.claude}` (independent of `lib/common.sh` fix)
- `session-start.sh:13` uses `${LL_STATE_DIR:-.claude}`
- `lib/common.sh:ll_resolve_config()` probes `.opencode/ll-config.json` first
- `session-start.sh:16` shell + `:65-72` embedded Python also probe `.opencode/` first
- `session-cleanup.sh:20` `CONFIG_FILE` patched independently (does NOT source `lib/common.sh`)
- `cli/auto.py`, `cli/parallel.py`, `cli/loop/run.py`, `cli/sprint/run.py` inject `LL_STATE_DIR` when OpenCode detected
- `subprocess_utils.py:28` (`CONTINUATION_PROMPT_PATH`) probes `.opencode/ll-continue-prompt.md` first
- Hook integration tests cover `.opencode/` config path variant (`test_hooks_integration.py`)

## Proposed Solution

### `${LL_STATE_DIR:-.claude}` substitution (shell scripts)

The `LL_HANDOFF_THRESHOLD` / `LL_CONTEXT_LIMIT` pattern (`auto.py:71,76`) is the exact model. Apply `${LL_STATE_DIR:-.claude}` to:

- `precompact-state.sh:28` — `STATE_DIR="${LL_STATE_DIR:-.claude}"` (single change covers all derived paths)
- `context-monitor.sh:181,238,309` — 3 direct substitutions
- `session-start.sh:13` — 1 substitution
- `session-cleanup.sh:14,20` — 2 substitutions (independent from `lib/common.sh`)

### `lib/common.sh:ll_resolve_config()` (config probing)

Extend from 2-location to 3-location fallback:
`.opencode/ll-config.json` → `.claude/ll-config.json` → bare root

### `session-start.sh` (config probing)

Update both the shell layer (`:16`) and embedded Python (`:65-72`) to probe `.opencode/` first. Model after existing two-path probe at lines 15-18.

### `session-cleanup.sh` (independent patch)

`session-cleanup.sh:20` has its own `CONFIG_FILE=".claude/ll-config.json"` and does NOT source `lib/common.sh`. Patch independently to add `.opencode/` probe.

### Python CLI `LL_STATE_DIR` injection

At the 4 existing `LL_HANDOFF_THRESHOLD` injection points, add parallel injection:

```python
if opencode_detected:
    os.environ["LL_STATE_DIR"] = ".opencode"
```

Detection signal: presence of `opencode.json` in project root, or `OPENCODE_SESSION` env var set.

Injection points:
- `cli/auto.py:71`
- `cli/parallel.py:165`
- `cli/loop/run.py:70`
- `cli/sprint/run.py:103`

Also update `subprocess_utils.py:28` to probe `.opencode/ll-continue-prompt.md` first.

## Integration Map

### Files to Modify
- `hooks/scripts/lib/common.sh:186-190` — `ll_resolve_config()` three-location probe
- `hooks/scripts/session-start.sh:13,16,65-72` — `${LL_STATE_DIR}` + config probe
- `hooks/scripts/session-cleanup.sh:14,20` — independent patch
- `hooks/scripts/context-monitor.sh:181,238,309` — `${LL_STATE_DIR}` substitution
- `hooks/scripts/precompact-state.sh:28,66` — `STATE_DIR="${LL_STATE_DIR:-.claude}"`
- `scripts/little_loops/cli/auto.py:71` — `LL_STATE_DIR` injection
- `scripts/little_loops/cli/parallel.py:165` — `LL_STATE_DIR` injection
- `scripts/little_loops/cli/loop/run.py:70` — `LL_STATE_DIR` injection
- `scripts/little_loops/cli/sprint/run.py:103` — `LL_STATE_DIR` injection
- `scripts/little_loops/subprocess_utils.py:28` — continuation prompt path probe

### Files to Modify (Tests)
- `scripts/tests/test_hooks_integration.py:33,104` — add `.opencode/` fixture variants

## Impact

- **Priority**: P4 — Enables hook-level OpenCode support
- **Effort**: Medium — Many files but mechanical substitution pattern; `LL_STATE_DIR` model is pre-designed
- **Risk**: Low — `${LL_STATE_DIR:-.claude}` default preserves all existing behavior when env var is unset
- **Breaking Change**: No

## Notes

**KEY INSIGHT**: `session-cleanup.sh` does NOT source `lib/common.sh` — it has its own independent `CONFIG_FILE=".claude/ll-config.json"`. Patching `ll_resolve_config()` alone will miss this script.

**OpenCode detection heuristic**: Check for `opencode.json` in project root OR `OPENCODE_SESSION` env var. Design decision should be consistent across all 4 CLI entry points.

## Verification Notes

**Verdict**: OUTDATED — The "Current Behavior" section is incorrect throughout. All `.claude/` path references in shell scripts have already been migrated to `.ll/`:

- `precompact-state.sh:28` — `STATE_DIR=".ll"` (not `.claude` as stated); `PRECOMPACT_STATE_FILE="${STATE_DIR}/ll-precompact-state.json"` at line 29; `CONTINUE_PROMPT=".ll/ll-continue-prompt.md"` at line 66
- `session-start.sh:13,16` — already uses `.ll/ll-context-state.json` and `.ll/ll-config.json` (not `.claude/`)
- `session-cleanup.sh:14,20` — already uses `.ll/.ll-lock`, `.ll/ll-context-state.json`, `.ll/ll-config.json`
- `context-monitor.sh` — no `.claude/ll` paths found; already uses `.ll/` paths
- `lib/common.sh:ll_resolve_config()` — already probes `.ll/ll-config.json` first (not `.claude/`)
- `cli/auto.py`: `LL_HANDOFF_THRESHOLD` injection is at line **77** (not 71 as stated)

The core feature requirement (adding `${LL_STATE_DIR:-.ll}` parameterization so OpenCode can redirect paths) still stands. The "Expected Behavior" and acceptance criteria remain valid. Only the "Current Behavior" description and line references are wrong.

— Verified 2026-04-11

## Session Log
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:issue-size-review` - 2026-04-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e591ecf6-7232-42fc-b4c4-903ec2858064.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P4
