---
id: ENH-1111
type: ENH
priority: P3
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
related: [FEAT-1116]
---

# ENH-1111: Scratch-Pad Enforcement via PreToolUse Hook

## Summary

Enforce the `/tmp/ll-scratch` convention from `.claude/CLAUDE.md` automatically via a PreToolUse hook, so large Bash/Read outputs are redirected to scratch files instead of relying on the model to remember the convention.

## Motivation

`.claude/CLAUDE.md` currently documents a scratch-pad convention: "Before reading a file, check its size... if > 200 lines, use Bash to cat to `/tmp/ll-scratch/`." This is a soft rule — the model regularly forgets it in long loop runs, flooding context with test output, file contents, and scan results.

Context-mode (github.com/mksglu/context-mode) enforces equivalent behavior via a PreToolUse hook that intercepts tool calls, runs the command in a subprocess, and returns a summary + index pointer instead of raw output. They report ~98% context reduction on typical workloads.

## Current Behavior

- Convention lives only in `CLAUDE.md:131-137` as prose guidance
- No mechanism enforces the ≥200-line threshold
- Long ll-auto / ll-parallel runs routinely hit compaction because large outputs leak into context
- Related completed work: ENH-498 added observation masking for ll-auto/parallel, but only masks, doesn't redirect

## Expected Behavior

- New PreToolUse hook (`hooks/scripts/scratch-pad-redirect.sh` or similar) inspects Bash commands that read files (`cat`, `pytest`, `mypy`, `ruff`) and large Read calls
- When expected output exceeds a threshold (default 200 lines / configurable), the hook rewrites the command to pipe through `tee /tmp/ll-scratch/<name>.txt | tail -N` and returns the tail + scratch path
- Read tool calls on files >N lines get redirected to a `Bash cat > scratch` equivalent with a pointer returned
- Threshold, enabled/disabled, and file-extension filters live under `scratch_pad:` in `.ll/ll-config.json`

## Acceptance Criteria

- New hook registered in `hooks/hooks.json` as PreToolUse
- Config section in `.ll/ll-config.json` and `config-schema.json`
- Hook is a no-op when disabled (default: enabled in automation contexts only — ll-auto / ll-parallel / ll-loop)
- Unit tests in `scripts/tests/` cover threshold logic and command rewriting
- Integration test proves a 500-line `pytest` run leaves only a tail + scratch path in tool result
- CLAUDE.md scratch-pad section updated to describe automatic enforcement

## References

- Inspiration: context-mode sandbox tools (`ctx_execute`, `ctx_batch_execute`)
- Related completed: ENH-498 observation masking in ll-auto/parallel
- Related: ENH-1114 (intent parameter), FEAT-1116 (hook-intent abstraction)
