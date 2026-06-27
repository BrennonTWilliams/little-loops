---
id: ENH-2341
type: ENH
priority: P2
status: open
discovered_date: 2026-06-27
captured_at: "2026-06-27T05:17:49Z"
discovered_by: capture-issue
decision_needed: false
---

# ENH-2341: Add Rubric-Gated Compaction Timing to pre_compact Hook

## Summary

Replace the current token-threshold-only trigger for `pre_compact` with a structural rubric that gates compaction on whether the current reasoning unit is genuinely closed and reducible — not on a blind token counter. Each rubric condition requires verbatim evidence from the trajectory; absence of evidence defaults to "no, don't compact yet."

## Current Behavior

`pre_compact.py` fires whenever the host's token threshold is reached, regardless of where the conversation is in its reasoning. This means compaction can interrupt mid-derivation (before a sub-task resolves), re-summarizing the same dead-end content into every summary window rather than waiting for a clean closure point.

## Expected Behavior

Before compacting, the hook evaluates a lightweight structural rubric over the recent trajectory:
1. **Closed reasoning unit** — the current sub-task has a definite resolution (not mid-derivation)
2. **Reducible to N facts** — the relevant content can be faithfully expressed in 3–5 cite-able facts
3. **Progress made** — something actually changed since the last compact
4. **Not stuck** — the agent is not in a repetitive loop on the same problem

Each condition requires a verbatim quote from the trajectory as evidence. If any condition lacks evidence it defaults to `no`, and compaction is deferred until the next check. Compaction still fires at the hard token ceiling regardless.

## Success Metrics

- Token cost per compaction window reduced by 30–70% vs. threshold-only baseline (per SELFCOMPACT research)
- Downstream task quality improves +5–18 points when rubric gates compaction
- Hard-ceiling bypass rate does not increase (rubric must not cause excessive deferral)
- All 4 rubric conditions independently testable in unit tests with clear pass/fail signal

## Motivation

SELFCOMPACT (research: `docs/research/05-26-2026-batch/`) shows that **the rubric — not the act of compacting — is where the quality gain comes from**. Fixed-interval / fixed-threshold compaction fails by firing blind: qualitative traces show it re-summarizing a dead-end shortlist into every summary window, while rubric-gated compaction waits for the lead to be corrected first. The result: 30–70% lower token cost and +5–18 points on downstream tasks, training-free.

This directly complements the existing `LCM-*` research line and the `continuation-prompt-template.md` handoff path. The rubric value is largest for weaker/open hosts (relevant to ll's multi-host story) but applies to Claude Code as well.

## Proposed Solution

Add a rubric evaluation step inside `scripts/little_loops/hooks/pre_compact.py` (the Python handler invoked by the Claude Code adapter) before deciding whether to emit the compaction payload:

```python
# scripts/little_loops/hooks/pre_compact.py

def should_compact(trajectory_excerpt: str, config: dict) -> tuple[bool, str]:
    """
    Evaluate the SELFCOMPACT rubric over the recent trajectory.
    Returns (compact_now, reason).
    Each condition requires verbatim evidence; absence → False.
    """
    rubric = {
        "closed_unit": _find_evidence(trajectory_excerpt, CLOSED_UNIT_SIGNALS),
        "reducible":   _find_evidence(trajectory_excerpt, REDUCIBLE_SIGNALS),
        "progress":    _find_evidence(trajectory_excerpt, PROGRESS_SIGNALS),
        "not_stuck":   not _find_evidence(trajectory_excerpt, STUCK_SIGNALS),
    }
    passed = all(rubric.values())
    reason = ", ".join(k for k, v in rubric.items() if not v) or "all conditions met"
    return passed, reason
```

The rubric runs as a probe appended to the hook context (not a substitution), so the KV cache is reused and the check is near-free. The existing hard-ceiling logic stays as a fallback.

**Key signals to define** (derived from trajectory text):
- **Closed unit**: phrases like "done", "completed", "fixed", resolved tool calls, explicit task summary
- **Reducible**: short recent window, few open threads, no pending tool calls
- **Progress**: diff between current and last compact checkpoint is non-empty
- **Stuck**: identical consecutive outputs, same error repeated ≥2 times

The rubric config (thresholds, signal lists) lives in `ll-config.json` under `hooks.pre_compact.rubric` so it can be tuned per-project.

## Implementation Steps

1. Add `should_compact()` rubric function to `pre_compact.py` with signal lists for each condition
2. Wire it into the main `pre_compact` handler before emitting the compaction payload
3. Add `hooks.pre_compact.rubric` config schema to `config-schema.json` with defaults
4. Add config read path in `pre_compact.py` via `resolve_config_path`
5. Add hard-ceiling bypass: if token count exceeds `rubric.hard_ceiling_pct` (default 95%) of context, compact regardless
6. Write tests in `scripts/tests/test_pre_compact.py` covering: rubric pass, rubric fail (each condition), hard-ceiling bypass, evidence-absent → no-compact
7. Update `hooks/prompts/continuation-prompt-template.md` to note the rubric timing policy

## Integration Map

### Files to Modify
- `scripts/little_loops/hooks/pre_compact.py` — add `should_compact()` rubric function and wire into main handler
- `config-schema.json` — add `hooks.pre_compact.rubric` schema with signal-list and threshold defaults

### Dependent Files (Callers/Importers)
- `hooks/adapters/claude-code/hooks.json` — invokes `pre_compact.py` as the Claude Code adapter
- Any opencode/codex adapter hooks that delegate to the same Python handler

### Similar Patterns
- `scripts/little_loops/hooks/session_start.py` — sibling hook handler; follow the same `resolve_config_path` pattern for config reads

### Tests
- `scripts/tests/test_pre_compact.py` — new test file (rubric pass, rubric fail per condition, hard-ceiling bypass, evidence-absent → no-compact)

### Documentation
- `hooks/prompts/continuation-prompt-template.md` — add a note about rubric timing policy (Implementation Step 7)

### Configuration
- `.ll/ll-config.json` — `hooks.pre_compact.rubric` block with `hard_ceiling_pct`, signal lists, and enabled flag

## Scope Boundaries

**In scope:**
- `should_compact()` rubric function in `pre_compact.py` with the four conditions above
- Config schema for `hooks.pre_compact.rubric` (signal lists, `hard_ceiling_pct`)
- Hard-ceiling bypass (compact regardless at ≥ `hard_ceiling_pct` of context, default 95%)
- Unit tests covering all rubric branches

**Out of scope:**
- Changing the hard token ceiling mechanism or compaction payload format
- ML-based or learned compaction decisions
- Storing full trajectory history across sessions
- Modifying how other hooks invoke or respond to compaction events

## Impact

- **Priority**: P2 — High leverage for token efficiency and post-compaction quality; not blocking, but multiplies value of the multi-host story for weaker/open hosts
- **Effort**: Medium — New `should_compact()` function + signal definitions + config schema + tests; implementation surface is well-scoped to `pre_compact.py`
- **Risk**: Low — Hard-ceiling bypass preserves existing behavior as permanent fallback; rubric is additive and never prevents compaction permanently
- **Breaking Change**: No — Defaults to existing threshold-only behavior when rubric config is absent; opt-in via `hooks.pre_compact.rubric.enabled`

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/05-26-2026-batch/SYNTHESIS-and-recommendations.md` | Source recommendation #1; SELFCOMPACT findings |
| `scripts/little_loops/hooks/pre_compact.py` | Primary implementation surface |
| `hooks/prompts/continuation-prompt-template.md` | Handoff template that pairs with this |
| `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | Structural-state gating context |

## Labels

`hooks`, `compaction`, `pre-compact`, `captured`

## Status

**Open** | Created: 2026-06-27 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-06-27T05:22:30 - `b1f554bc-7cd6-42a8-af86-2e0e2a418a25.jsonl`
- `/ll:capture-issue` - 2026-06-27T05:17:49Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd21288e-7370-4e7e-8040-6f118e73e291.jsonl`
