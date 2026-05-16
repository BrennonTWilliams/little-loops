---
id: FEAT-789
type: FEAT
priority: P3
status: active
discovered_date: 2026-03-16
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
---

# FEAT-789: Create context-health-monitor FSM Loop

## Summary

Add a `loops/context-health-monitor.yaml` FSM loop that monitors context health using scratch file accumulation and session log size as observable proxies for context pressure, then applies targeted strategies (scratch compaction, output archival) when pressure is detected. Builds on the existing `hooks/scripts/context-monitor.sh` and `.claude/ll-context-state.json` infrastructure.

## Current Behavior

No `context-health-monitor` loop exists. Developers must manually inspect `.loops/tmp/` for large scratch files and remove or summarize them by hand. The existing `hooks/scripts/context-monitor.sh` tracks token estimates in `.claude/ll-context-state.json` but takes no remediation action — it only observes. There is no automated mechanism to compact scratch files or archive stale outputs before they inflate context pressure.

## Context

During a design session, three FSM loop ideas were derived from the [Agent-Skills-for-Context-Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering) repo's `context-optimization` skill, which describes a threshold-driven cycle: measure utilization → identify dominant component → apply lever → verify quality → repeat. The context-optimization skill notes that tool outputs can represent up to 83.9% of typical agent context usage and recommends activating optimization at 70-80% utilization.

The key adaptation for little-loops: Claude Code's context window is not directly observable from a shell, but `.loops/tmp/` file sizes and session log accumulation serve as reliable external proxies. The existing `context-monitor.sh` hook already tracks token estimates in `.claude/ll-context-state.json`; this loop complements it by cleaning up the artifacts that cause the accumulation.

## Use Case

**Who**: A developer running long ll-loop sessions or multi-issue sprints.

**Context**: After several loop iterations, `.loops/tmp/` fills with large test output files, intermediate analysis results, and stale scratch data. These files don't directly fill the context window, but they get read into it by prompt states that naively `cat` large files. The loop addresses this before it becomes a problem.

**Goal**: Run the loop proactively (before a sprint, or as a periodic maintenance task) to compact scratch files, archive stale outputs, and keep context-consuming artifacts lean.

**Outcome**: Scratch files are summarized to their essential findings, stale outputs are archived, and the session can proceed with a leaner context footprint.

## Expected Behavior

The loop runs through these states:

```
assess_context → self_assess → route → [compact_scratch | archive_outputs] → verify → assess_context
                                    ↘ done (CONTEXT_HEALTHY)
```

1. **assess_context** (shell): Measure `.loops/tmp/` sizes, list large files, sample recent session log sizes — no LLM tokens spent.
2. **self_assess** (prompt): LLM evaluates the snapshot and emits one of: `PRESSURE_SCRATCH`, `PRESSURE_OUTPUTS`, `CONTEXT_HEALTHY`.
3. **route** (evaluate): Routes to remediation or `done` based on the tag.
4. **compact_scratch** (prompt): For each file >100KB, summarize to essential findings and overwrite. Delete clearly stale files.
5. **archive_outputs** (prompt): Move files older than 3 days to `.loops/archive/`. Delete zero-byte or duplicate files.
6. **verify** (shell): Re-measure after remediation and loop back to `assess_context`.
7. **done** (terminal): Context is healthy.

## Implementation Steps

1. Create `loops/context-health-monitor.yaml` with the state machine described above.
2. Shell states: `assess_context` and `verify` — use `du`, `find`, `wc -l` against `.loops/tmp/`.
3. Prompt states: `self_assess`, `compact_scratch`, `archive_outputs` — LLM only where judgment is needed (which files are still needed vs. stale).
4. Read `.claude/ll-context-state.json` in `assess_context` to incorporate the existing token estimate as an additional signal (if the file exists).
5. `context` block: configure thresholds (`scratch_size_kb_warn: 500`, `log_age_days_warn: 7`, `scratch_dir: .loops/tmp`).
6. Set `max_iterations: 10`, `timeout: 3600` (no `on_handoff` — this is a maintenance loop, not a work loop).

## API/Interface

New file: `loops/context-health-monitor.yaml`

Invoked via:
```bash
ll-loop run context-health-monitor
```

No changes to existing hooks or scripts required. Optionally reads `.claude/ll-context-state.json` (already written by `context-monitor.sh`) for additional signal.

## Motivation

- **Existing infrastructure**: `hooks/scripts/context-monitor.sh` and `.claude/ll-context-state.json` track token estimates but don't act on scratch accumulation. This loop is the action complement to the hook's observation.
- **Gap**: There is currently no way to proactively clean context-consuming artifacts before they cause handoff warnings or mid-session degradation.
- **Composability**: Other loops (`project-dev-pipeline`, `issue-refinement`) could invoke this as a pre-flight step via subprocess once it exists.

## Acceptance Criteria

- [x] `loops/context-health-monitor.yaml` passes `ll-loop validate context-health-monitor`
- [x] `assess_context` state reads `.claude/ll-context-state.json` if it exists and includes its `estimated_tokens` value in the snapshot
- [x] Loop terminates at `done` when `CONTEXT_HEALTHY` is diagnosed
- [x] `compact_scratch` state reduces file sizes without deleting files referenced in active issues
- [x] `archive_outputs` state moves files to `.loops/archive/` (not deletes) so nothing is permanently lost
- [x] Loop runs to completion in < 10 minutes on a typical `.loops/tmp/` state

## Integration Map

### Files to Create
- `loops/context-health-monitor.yaml` — the FSM loop definition

### Files to Read (no changes)
- `hooks/scripts/context-monitor.sh` — writes `.claude/ll-context-state.json` with fields: `session_start`, `estimated_tokens`, `tool_calls`, `threshold_crossed_at`, `handoff_complete`, `breakdown` (dict by tool name), `last_compaction`; file only exists during an active session — `assess_context` must handle absence gracefully
- `.claude/ll-context-state.json` — may not exist; use `jq -r '.estimated_tokens // "n/a"' .claude/ll-context-state.json 2>/dev/null || echo "n/a"` pattern

### Similar Patterns
- `loops/docs-sync.yaml` — shell measure → prompt fix → verify → loop back pattern; uses `exit_code` evaluate with `on_yes`/`on_no` pointing to same next state to capture output
- `loops/backlog-flow-optimizer.yaml` — `context:` block with configurable thresholds (`target_active_max: 20`); `output_contains` route chain where each `on_no` falls to next route state; prompt states emit tag on its own line captured for downstream routing
- `loops/worktree-health.yaml` — `output_numeric` + `eq`/`gt` operator for file size/count thresholds; `maintain: true` / `backoff: 300` for monitor mode

### Configuration
- No schema changes required
- No `ll-config.json` changes required (thresholds live in loop `context:` block)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**YAML schema reference (all fields are from live loops):**

```yaml
name: context-health-monitor
description: |
  Monitor context health via scratch file accumulation and session log size.
  Compact scratch files and archive stale outputs when pressure is detected.
initial: assess_context
context:
  scratch_size_kb_warn: 500
  log_age_days_warn: 7
  scratch_dir: .loops/tmp
max_iterations: 10
timeout: 3600

states:
  assess_context:
    action_type: shell
    action: |
      echo "=== Scratch Dir ==="
      SCRATCH_SIZE=$(du -sk ${context.scratch_dir} 2>/dev/null | awk '{print $1}' || echo 0)
      FILE_COUNT=$(find ${context.scratch_dir} -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')
      echo "scratch_kb: $SCRATCH_SIZE"
      echo "file_count: $FILE_COUNT"
      # Include token estimate if available
      TOKENS=$(jq -r '.estimated_tokens // "n/a"' .claude/ll-context-state.json 2>/dev/null || echo "n/a")
      echo "estimated_tokens: $TOKENS"
      find ${context.scratch_dir} -maxdepth 1 -type f -size +100k 2>/dev/null | sort -k5 -rn || true
    capture: snapshot
    next: self_assess

  self_assess:
    action_type: prompt
    timeout: 120
    action: |
      Evaluate this context health snapshot and emit a diagnosis tag:

      ${captured.snapshot.output}

      Thresholds: scratch_size_warn=${context.scratch_size_kb_warn}KB

      Emit exactly one of:
      PRESSURE_SCRATCH
      PRESSURE_OUTPUTS
      CONTEXT_HEALTHY
    capture: diagnosis
    next: route

  route:
    evaluate:
      type: output_contains
      source: "${captured.diagnosis.output}"
      pattern: "CONTEXT_HEALTHY"
    on_yes: done
    on_no: route_scratch

  route_scratch:
    evaluate:
      type: output_contains
      source: "${captured.diagnosis.output}"
      pattern: "PRESSURE_SCRATCH"
    on_yes: compact_scratch
    on_no: archive_outputs

  compact_scratch:
    action_type: prompt
    timeout: 300
    action: |
      Compact large scratch files in ${context.scratch_dir}. For each file >100KB,
      summarize to essential findings and overwrite. Delete clearly stale files.
      Do NOT delete files referenced in active issues.
    next: verify

  archive_outputs:
    action_type: prompt
    timeout: 300
    action: |
      Archive stale outputs from ${context.scratch_dir}. Move files older than
      ${context.log_age_days_warn} days to .loops/archive/. Delete zero-byte files.
    next: verify

  verify:
    action_type: shell
    action: |
      SCRATCH_SIZE=$(du -sk ${context.scratch_dir} 2>/dev/null | awk '{print $1}' || echo 0)
      echo "post_remediation_kb: $SCRATCH_SIZE"
    next: assess_context

  done:
    terminal: true
```

**Key pattern**: `context:` block values referenced as `${context.<key>}` inside state fields. `captured.<name>.output` interpolated in prompt actions.

---

### Second Pass: YAML Corrections (2026-03-20)

_Added by `/ll:refine-issue` — engine analysis and real-loop cross-validation revealed three bugs in the proposed YAML above:_

**1. `assess_context` — file-listing sort is broken**

```yaml
# BROKEN — `sort -k5 -rn` expects 5+ whitespace-delimited fields per line,
# but `find` without -ls outputs just file paths (one field):
find ${context.scratch_dir} -maxdepth 1 -type f -size +100k 2>/dev/null | sort -k5 -rn || true

# CORRECT — pipe through `du -sk` first to get "size path" pairs:
find ${context.scratch_dir} -maxdepth 1 -type f -size +100k -exec du -sk {} \; 2>/dev/null | sort -rn || true
```

Confirmed by `executor.py`: FSM interpolates `${context.scratch_dir}` → `.loops/tmp` before bash runs the command, so the variable substitution itself is fine — the bug is only in the sort.

**2. `compact_scratch` — LLM has no file list**

```yaml
# BROKEN — LLM is told to "compact files >100KB" but has no data about which files exist:
action: |
  Compact large scratch files in ${context.scratch_dir}. For each file >100KB, ...

# CORRECT — pass the measured snapshot so LLM acts on real data:
action: |
  Here is the current scratch directory snapshot:
  ${captured.snapshot.output}

  Compact large scratch files in ${context.scratch_dir}. For each file >100KB listed above,
  summarize to essential findings and overwrite. Delete clearly stale files.
  Do NOT delete files referenced in active issues.
```

Pattern confirmed by `backlog-flow-optimizer.yaml:44` — `diagnose` always includes `${captured.metrics.output}` before the prompt instructions.

**3. `archive_outputs` — same missing-context issue**

```yaml
# CORRECT form:
action: |
  Here is the current scratch directory snapshot:
  ${captured.snapshot.output}

  Archive stale outputs from ${context.scratch_dir}. Move files older than
  ${context.log_age_days_warn} days to .loops/archive/. Delete zero-byte files.
```

**4. Engine behavior confirmations (no changes needed)**

- `${context.scratch_dir}` in shell `action:` ✓ — engine interpolates before handing to `bash -c`
- `capture: snapshot` on shell state ✓ — captures stdout regardless of exit code (executor.py:737-743)
- `evaluate:` with no `action:` ✓ — pure routing states are valid (route, route_scratch)
- `source: "${captured.diagnosis.output}"` ✓ — matches pattern in backlog-flow-optimizer.yaml
- `terminal: true` minimal state ✓ — confirmed in every loop file
- `max_iterations: 10` prevents infinite `verify → assess_context` cycle ✓

## Impact

- **Priority**: P3 — Useful maintenance loop; not blocking
- **Effort**: Small — single YAML file, no code changes
- **Risk**: Low — additive, no changes to existing loop engine or hooks
- **Breaking Change**: No

## Labels

`loop`, `context`, `maintenance`, `fsm`

---

## Status

- [x] Completed 2026-03-20

## Verification Notes

_Verified by `/ll:verify-issues` on 2026-03-19 — **VALID**_

- `loops/context-health-monitor.yaml` does not exist — feature is not yet implemented ✓
- `hooks/scripts/context-monitor.sh` exists at `hooks/scripts/context-monitor.sh` ✓
- `.claude/ll-context-state.json` exists ✓
- All documented JSON fields (`session_start`, `estimated_tokens`, `tool_calls`, `threshold_crossed_at`, `handoff_complete`, `breakdown`, `last_compaction`) confirmed accurate against `context-monitor.sh` ✓
- Similar loop patterns confirmed: `backlog-flow-optimizer.yaml` has `context:` block + `output_contains`; `worktree-health.yaml` has `maintain: true`, `backoff: 300`, `output_numeric` ✓
- No dependency references to validate

## Resolution

Implemented 2026-03-20. Created `loops/context-health-monitor.yaml` with the 8-state FSM described in the issue, applying all three corrections from the Second Pass review:
- Fixed `assess_context` sort (uses `-exec du -sk {} \;` piped to `sort -rn`)
- Added `${captured.snapshot.output}` to `compact_scratch` and `archive_outputs` prompts
- Added `on_error:` to routing states following `backlog-flow-optimizer.yaml` pattern

Also updated `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` to include `context-health-monitor`.

`ll-loop validate context-health-monitor` passes. All 3779 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-03-20T20:00:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d09ee0f3-cb43-4c99-8bef-98547284f6a2.jsonl`
- `/ll:ready-issue` - 2026-03-21T00:54:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aff8f7bc-86de-4a43-b435-accb0774eb8b.jsonl`
- `/ll:refine-issue` - 2026-03-21T00:51:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/24f32447-0c48-4116-8565-f064477c3067.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:11:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:refine-issue` - 2026-03-16T23:24:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f41b047-87a9-4dc6-bd79-b70fcba93e87.jsonl`
- `/ll:format-issue` - 2026-03-16T23:15:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03ef4a48-cdf1-402c-a6f3-262d76f4c071.jsonl`
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f7bf6f5-8d0a-49aa-a2dc-02169a6d3f97.jsonl`
