---
id: ENH-1129
type: ENH
priority: P3
status: open
parent: ENH-1111
size: Medium
---

# ENH-1129: Implement scratch-pad-redirect.sh PreToolUse Hook

## Summary

Create `hooks/scripts/scratch-pad-redirect.sh`, register it in `hooks/hooks.json` as a second PreToolUse entry (matcher `Bash|Read`), and add `TestScratchPadRedirect` in `scripts/tests/test_hooks_integration.py`. This is the core deliverable of ENH-1111.

## Parent Issue

Decomposed from ENH-1111: Scratch-Pad Enforcement via PreToolUse Hook

## Prerequisite

Requires ENH-1128 (schema extension) to be merged so `ll_config_value` can resolve the four new `scratch_pad` properties.

## Motivation

The scratch-pad convention in CLAUDE.md is a soft rule — the model forgets it in long loop runs, flooding context with test output and file contents. A PreToolUse hook enforces it automatically by rewriting Bash commands to tee+tail and denying large Read calls with a Bash scratch suggestion.

## Expected Behavior

- Hook is a no-op when `scratch_pad.enabled` is `false` (default)
- When `automation_contexts_only: true` (default), hook skips unless `permission_mode == "bypassPermissions"` (the signal from `ll-auto`/`ll-parallel`/`ll-loop` via `subprocess_utils.py:97-105`)
- **Bash rewrite**: if `tool_name == "Bash"` and first token of command matches `command_allowlist`, rewrite `command` to `<original> > .loops/tmp/scratch/<name>.txt 2>&1; tail -<tail_lines> .loops/tmp/scratch/<name>.txt`; emit `hookSpecificOutput.permissionDecision=allow` + `updatedInput.command=<new>` + `additionalContext` naming scratch path
- **Read deny**: if `tool_name == "Read"` and target file matches `file_extension_filters` and `wc -l` exceeds `threshold_lines`, return `permissionDecision=deny` with `permissionDecisionReason` suggesting the equivalent `Bash cat > .loops/tmp/scratch/<name>.txt` command

## Acceptance Criteria

- `hooks/scripts/scratch-pad-redirect.sh` created following `check-duplicate-issue-id.sh:1-129` pattern (stdin via `INPUT=$(cat)`, parse with `jq -r`, `allow_response()` helper, source `lib/common.sh`)
- Single-pass `jq @tsv` for `tool_name`, `tool_input.command`, `tool_input.file_path`, `permission_mode` (per `context-monitor.sh:45-47` pattern)
- Hook registered in `hooks/hooks.json` as a second PreToolUse entry with matcher `Bash|Read`, 5s timeout; does not disturb the existing `Write|Edit` entry at lines 29-41
- `mkdir -p .loops/tmp/scratch` before emitting rewritten Bash command
- Unit tests in `TestScratchPadRedirect` class in `scripts/tests/test_hooks_integration.py`:
  - (a) disabled → no-op (allow unchanged)
  - (b) enabled, non-automation → no-op
  - (c) enabled + automation + Bash under threshold → allow unchanged
  - (d) enabled + automation + Bash over threshold → `updatedInput` rewrites to tee+tail
  - (e) enabled + automation + Read over threshold → deny with `additionalContext`
  - (f) `command_allowlist` — non-matching Bash (e.g. `git status`) → allow unchanged
- Integration test: simulated 500-line `pytest` invocation in automation context leaves only `tail_lines` lines + scratch path in hook result

## Files to Create

- `hooks/scripts/scratch-pad-redirect.sh`

## Files to Modify

- `hooks/hooks.json` — add second PreToolUse entry (matcher `Bash|Read`, timeout 5s)
- `scripts/tests/test_hooks_integration.py` — add `TestScratchPadRedirect` class

## Reference Files (read only)

- `hooks/scripts/check-duplicate-issue-id.sh:1-129` — PreToolUse structural template
- `hooks/scripts/context-monitor.sh:17,45-47` — single-pass `jq @tsv` pattern
- `hooks/scripts/lib/common.sh:182-234` — `ll_resolve_config` / `ll_feature_enabled` / `ll_config_value`
- `docs/claude-code/hooks-reference.md:807-828` — `updatedInput` / `additionalContext` contract
- `docs/claude-code/hooks-reference.md:395,712-751` — `permission_mode`, Bash/Read `tool_input` schemas
- `scripts/little_loops/subprocess_utils.py:97-105` — confirms `--dangerously-skip-permissions` source
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:87` — loop that Reads `.loops/tmp/` files (behavioral interaction: deny-with-hint is expected, not a bug)
- `scripts/little_loops/loops/dead-code-cleanup.yaml:84` — same
- `scripts/little_loops/loops/test-coverage-improvement.yaml:94,165` — same

## Open Decisions

- **Automation detection**: use `permission_mode == "bypassPermissions"` (no CLI changes) vs exporting `LL_AUTOMATION=1` from `subprocess_utils.py`. Recommendation: `permission_mode` is simpler.

## Session Log
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fc25386-a9f0-4e75-8434-c659db481895.jsonl`
