---
id: FEAT-789
type: FEAT
priority: P3
discovered_date: 2026-03-16
discovered_by: capture-issue
---

# FEAT-789: Create context-health-monitor FSM Loop

## Summary

Add a `loops/context-health-monitor.yaml` FSM loop that monitors context health using scratch file accumulation and session log size as observable proxies for context pressure, then applies targeted strategies (scratch compaction, output archival) when pressure is detected. Builds on the existing `hooks/scripts/context-monitor.sh` and `.claude/ll-context-state.json` infrastructure.

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

- [ ] `loops/context-health-monitor.yaml` passes `ll-loop validate context-health-monitor`
- [ ] `assess_context` state reads `.claude/ll-context-state.json` if it exists and includes its `estimated_tokens` value in the snapshot
- [ ] Loop terminates at `done` when `CONTEXT_HEALTHY` is diagnosed
- [ ] `compact_scratch` state reduces file sizes without deleting files referenced in active issues
- [ ] `archive_outputs` state moves files to `.loops/archive/` (not deletes) so nothing is permanently lost
- [ ] Loop runs to completion in < 10 minutes on a typical `.loops/tmp/` state

## Integration Map

### Files to Create
- `loops/context-health-monitor.yaml` — the FSM loop definition

### Files to Read (no changes)
- `hooks/scripts/context-monitor.sh` — reference for what `.claude/ll-context-state.json` contains
- `.claude/ll-context-state.json` — token estimate state written by the hook

### Similar Patterns
- `loops/docs-sync.yaml` — shell measure → prompt fix → verify → loop back pattern
- `loops/backlog-flow-optimizer.yaml` — `context:` block with configurable thresholds, diagnose→route→act pattern

### Configuration
- No schema changes required
- No `ll-config.json` changes required (thresholds live in loop `context:` block)

## Impact

- **Priority**: P3 — Useful maintenance loop; not blocking
- **Effort**: Small — single YAML file, no code changes
- **Risk**: Low — additive, no changes to existing loop engine or hooks
- **Breaking Change**: No

## Labels

`loop`, `context`, `maintenance`, `fsm`

---

## Status

- [ ] Not started

## Session Log
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
