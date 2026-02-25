---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 90
outcome_confidence: 64
---

# ENH-498: Observation Masking / Scratch Pad Pattern in ll-auto and ll-parallel

## Summary

Tool outputs are typically 80%+ of total agent context tokens in long automation runs. Implement an "observation masking" pattern: large tool outputs (file contents, test results, lint reports) are written to scratch pad files and referenced by path rather than inlined in conversation context. This significantly reduces context bloat in ll-auto and ll-parallel sessions.

## Current Behavior

In ll-auto and ll-parallel, every tool output is inlined in the conversation history. A single issue implementation might read 10–20 files (each potentially 200–1000 lines), run tests, and execute lint — all of which remain in context for subsequent turns. By mid-session, the context is dominated by tool outputs from earlier steps that are no longer needed.

This contributes directly to context degradation in longer runs (related: ENH-499).

## Expected Behavior

Large tool outputs are captured to temporary scratch files (`/tmp/ll-scratch/<session>/<turn>-<tool>.txt`) and replaced in conversation context with a compact reference:

```
[Output saved to scratch/turn-012-file-read.txt — 847 lines]
```

The agent can re-read the scratch file on demand if it needs the full content. Small outputs (< N lines, configurable) are still inlined normally.

## Motivation

Research benchmarks show this pattern reduces context token usage by 50–80% in tool-heavy sessions without degrading task completion quality — agents selectively re-read what they need rather than having everything compete for attention. For ll-auto processing 5–10 issues sequentially, this could be the difference between completing a run and hitting context limits mid-batch.

## Proposed Solution

Option A (preferred — hook-based): Implement as a `PostToolUse` hook that intercepts large tool outputs and writes them to scratch files before they enter context.

Option B (agent-directed): Update the ll-auto system prompt to instruct Claude to write large outputs to files and reference them, using existing Write tool capability.

Option A is preferable because it's automatic and doesn't require Claude to remember the pattern.

### Codebase Research Findings — Critical Constraint

_Added by `/ll:refine-issue` — based on hooks reference analysis:_

**Native tool output cannot be fully replaced by a `PostToolUse` hook.** The `updatedMCPToolOutput` field in hook decision output only applies to MCP tools, not native tools (Read, Bash, Grep, etc.). The available mechanisms for a `PostToolUse` hook on native tools are:

1. **`additionalContext`** (JSON output): Adds a supplemental message to Claude's view alongside the original tool output. Does _not_ remove the large output from context — it augments it. Compact reference appears as extra context.
2. **`decision: "block"` + `reason`** (JSON output): Shows the `reason` text to Claude when the hook decision is "block". Whether this suppresses the original tool response from appearing in context needs validation against live Claude Code behavior.
3. **`exit 2` + stderr**: Surfaces the stderr text to Claude as a non-blocking message. Original output is still present.

**Implication for Option A:** The hook cannot guarantee that the large tool output is _removed_ from context; it can only ensure Claude is _informed_ where the saved content lives. True context reduction may require Option B (agent-directed, where Claude itself chooses to write output to a file rather than having it appear in context at all) or a combination.

**Recommended approach:** Use `additionalContext` JSON output (most principled) to inject the compact reference. Validate whether `decision: "block"` actually suppresses the original output in context. If neither removes the original, reconsider whether Option B is the more effective path for actual token reduction.

## Scope Boundaries

- **In scope**: Intercepting large tool outputs in ll-auto/ll-parallel sessions; scratch file management; configurable size threshold
- **Out of scope**: Changing issue processing logic, modifying how results are reported in git worktrees

## Implementation Steps

1. Determine which hook event is appropriate (`PostToolUse` in `hooks/hooks.json`)
2. Implement a Python hook script: reads tool output size, if > threshold writes to scratch file, returns compact reference
3. Add `scratch_pad_threshold_lines` to ll-config.json schema (default: 200)
4. Implement scratch file cleanup (per-session, cleared at session start)
5. Update ll-auto and ll-parallel system prompts to acknowledge scratch references and re-read as needed
6. Test with a representative issue that reads multiple large files

### Codebase Research Findings — Concrete References

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Register in `hooks/hooks.json:42–53`** — Add a second hook object inside the existing `PostToolUse` array's `hooks` array (alongside the `context-monitor.sh` entry):
   ```json
   {
     "type": "command",
     "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scratch-pad.sh",
     "timeout": 5,
     "statusMessage": "Checking output size..."
   }
   ```

2. **Implement `hooks/scripts/scratch-pad.sh`** (bash, not Python) — follow `context-monitor.sh` structure exactly:
   - `source "${SCRIPT_DIR}/lib/common.sh"` then `INPUT=$(cat)`
   - Gate with `ll_resolve_config` + `ll_feature_enabled "scratch_pad.enabled"` (exit 0 if disabled)
   - Read threshold: `THRESHOLD=$(ll_config_value "scratch_pad.threshold_lines" "200")`; scratch dir: `SCRATCH_DIR=$(ll_config_value "scratch_pad.scratch_dir" "/tmp/ll-scratch")`
   - Extract session ID: `SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')`; tool use ID: `TOOL_USE_ID=$(echo "$INPUT" | jq -r '.tool_use_id // ""')`
   - Reuse per-tool content extraction jq patterns from `context-monitor.sh:50–107` to get line count from `tool_response`
   - If line count ≥ threshold: write content to `${SCRATCH_DIR}/${SESSION_ID}/${TOOL_USE_ID}-${TOOL_NAME}.txt`; output `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"[ll-scratch] Output too large (N lines). Saved to <path> — read this file if you need the full content."}}` to stdout; exit 0
   - **Validate** whether `decision: "block"` instead of `additionalContext` suppresses the original output from Claude's context (test manually before choosing)

3. **Add `"scratch_pad"` to `config-schema.json`** — insert a new top-level object following the `"context_monitor"` block structure (lines 369–441); include `"additionalProperties": false`:
   ```json
   "scratch_pad": {
     "type": "object",
     "properties": {
       "enabled": { "type": "boolean", "default": false },
       "threshold_lines": { "type": "integer", "default": 200 },
       "scratch_dir": { "type": "string", "default": "/tmp/ll-scratch" }
     },
     "additionalProperties": false
   }
   ```
   Also add `"scratch_pad"` default block to `.claude/ll-config.json`.

4. **Scratch file cleanup** — add to `hooks/scripts/session-cleanup.sh` (Stop hook) or `hooks/scripts/session-start.sh`: remove `${SCRATCH_DIR}/${SESSION_ID}/` at session start/end using `SESSION_ID` from stdin.

5. **No system prompt changes needed** — ll-auto (`subprocess_utils.py:88`) and ll-parallel (`worker_pool.py:241`) do not use explicit `--system-prompt` flags; Claude picks up behavior from the project's `.claude/` directory and hook output. The hook's `additionalContext` message itself instructs Claude how to handle scratch references. Optionally add a note in `CLAUDE.md` describing the scratch pad behavior.

6. **Tests in `scripts/tests/test_hooks_integration.py`** — add a new `TestScratchPad` class following `TestContextMonitor` at lines 38–92:
   - `hook_script` fixture points to `hooks/scripts/scratch-pad.sh`
   - `test_config` fixture writes `{"scratch_pad": {"enabled": true, "threshold_lines": 5, "scratch_dir": str(tmp_path / "scratch")}}` to `tmp_path / ".claude" / "ll-config.json"`
   - Test cases: (a) output below threshold → exit 0, no scratch file written; (b) output above threshold → exit 0, scratch file written, stdout contains `additionalContext` JSON; (c) feature disabled → exit 0, no scratch file; (d) concurrent calls don't collide (use `ThreadPoolExecutor`)

## Integration Map

### Files to Modify
- `hooks/hooks.json` — add PostToolUse hook
- `hooks/` — new hook script for observation masking
- `config-schema.json` — add `scratch_pad_threshold_lines` field
- `.claude/ll-config.json` — add default value

### New Files
- `hooks/observation-masking.py` (or `.sh`) — hook implementation

### Tests
- `scripts/tests/` — test hook invocation with mock large output
- Manual: run ll-auto on a file-heavy issue, verify context size reduction

### Documentation
- `docs/ARCHITECTURE.md` — document observation masking pattern
- `docs/guides/` — mention in ll-auto usage guide

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Pattern reference (existing PostToolUse hook):**
- `hooks/scripts/context-monitor.sh` — follow this as the implementation pattern; complete stdin-reading, feature-flag-gating, config-reading, and `exit 2` stderr pattern; per-tool content extraction in `estimate_tokens()` at lines 50–107 (jq patterns for `Read`, `Bash`, `Grep`, `Glob`)
- `hooks/scripts/lib/common.sh` — source in the new hook; provides `ll_resolve_config`, `ll_feature_enabled "scratch_pad.enabled"`, `ll_config_value "scratch_pad.threshold_lines" "200"`, `atomic_write_json`, `acquire_lock`/`release_lock`; no changes needed

**Additional files to modify:**
- `scripts/little_loops/config.py:177` — add `ScratchPadConfig` dataclass following `AutomationConfig` pattern; add `self._scratch_pad = ScratchPadConfig.from_dict(self._raw_config.get("scratch_pad", {}))` in `_parse_config()` around line 434

**Exact hook registration target:**
- `hooks/hooks.json:42–53` — add a second entry inside the existing `PostToolUse` array (alongside the `context-monitor.sh` entry); use `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scratch-pad.sh`, `timeout: 5`

**Prefer `.sh` over `.py`:** All existing hook scripts are bash; Python is used only as an inline heredoc inside `session-start.sh`. Use `hooks/scripts/scratch-pad.sh` for consistency.

**Test file (exact path):**
- `scripts/tests/test_hooks_integration.py` — add a new `TestScratchPad` class following `TestContextMonitor` pattern at lines 38–92; use `subprocess.run([str(hook_script)], input=json.dumps(...), capture_output=True, text=True, timeout=6)` and `os.chdir(tmp_path)` with `finally: os.chdir(original_dir)`

**Dependent callers (ll-auto/ll-parallel launch mechanism):**
- `scripts/little_loops/subprocess_utils.py:88` — ll-auto invokes Claude CLI via `["claude", "--dangerously-skip-permissions", "-p", command]`; no `--system-prompt` flag; hooks are picked up automatically from `.claude/` directory
- `scripts/little_loops/parallel/worker_pool.py:241` — ll-parallel copies `.claude/` into each worktree via `shutil.copytree`; hooks fire in each worktree automatically

**Config schema target:**
- `config-schema.json:369–441` — add `"scratch_pad"` object at top level following the `"context_monitor"` block structure; must include `"additionalProperties": false`

**Session ID for scratch file namespacing:**
- Available in every hook's stdin JSON as `session_id`; extract with `SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // ""')`; also available as `${CLAUDE_SESSION_ID}` in skill substitution contexts

## Impact

- **Priority**: P2 — High; directly improves reliability of long automation runs
- **Effort**: Medium — Hook infrastructure + Python script + config changes
- **Risk**: Medium — Hook failures could break tool output delivery; needs robust error handling and fallback
- **Breaking Change**: No (additive)

## Labels

`enhancement`, `context-engineering`, `ll-auto`, `ll-parallel`, `hooks`, `performance`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P2

## Blocks

- ENH-459

- ENH-491
- FEAT-440
- FEAT-441
- FEAT-503