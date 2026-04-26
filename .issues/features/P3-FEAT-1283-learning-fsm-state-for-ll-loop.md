---
id: FEAT-1283
type: FEAT
priority: P3
captured_at: "2026-04-25T18:06:01Z"
discovered_date: "2026-04-25"
discovered_by: capture-issue
depends_on: [FEAT-1282]
blocked_by: [FEAT-1286]
---

# FEAT-1283: `learning` FSM State for ll-loop

## Summary

Add a `learning` state to FSM loop configurations that runs learning test scripts and only advances when all targeted assertions pass. Autonomous loops cannot proceed to `planning` or `implementing` until external system behavior is deterministically proven, eliminating assumption leakage in fully automated runs.

## Current Behavior

FSM loops (`ll-loop`) move from an initial state directly into `planning` or `implementing` with no gate on unproven external system assumptions. If a loop targets an issue involving an unfamiliar SDK or API, the agent hallucinates behavior and may iterate indefinitely on a faulty premise without any deterministic signal that the premise is wrong.

## Expected Behavior

A loop config can declare a `learning` state:

```yaml
states:
  - name: learning
    type: learning
    targets:
      - "Anthropic SDK streaming"
      - "GitHub API rate limits"
    on_pass: planning
    on_fail: learning  # retry, or surface for human input
  - name: planning
    ...
```

When the loop enters `learning`:
1. Queries the learning test registry (ENH-1282) for each target
2. If all targets have up-to-date proven records → advance to `on_pass` state
3. If any target is missing or stale → execute `/ll:explore-api` for that target, capture results, retry
4. If a target is refuted → transition to a `blocked` state and surface the failure for human input

## Motivation

The FSM loop is little-loops' core autonomous execution engine. Without a learning state, fully automated runs (ll-auto, ll-loop) are subject to the same assumption leakage that causes slop code in interactive sessions. The `learning` state is the architectural enforcement of "prove it before you build it" — it turns the registry (ENH-1282) from a passive reference into an active gate. Harness-first methodology means the loop cannot accidentally skip the proof phase.

## Proposed Solution

**New FSM state type** — `type: learning` in loop YAML config:
- Add `LearningState` handler to `scripts/little_loops/fsm/` (or wherever FSM state types live)
- On entry: iterate targets, call `learning_tests.read_record(target)` for each
- If record missing or stale: invoke `ll:explore-api` as a sub-skill call within the loop
- Parse results, update registry, re-evaluate
- Emit structured event: `LLEvent` with `learning_complete` or `learning_blocked` type

**Retry policy** — configurable `max_retries` per target (default: 2); after exhaustion, transition to `blocked`

**Human escalation** — when a target is `refuted` or max retries hit, emit a `PushNotification` and pause the loop awaiting human confirmation before proceeding

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/` — add `learning_state.py` handler
- `scripts/little_loops/loop_runner.py` (or equivalent) — register `LearningState` as a valid state type
- Loop YAML schema — add `learning` as valid state type with `targets`, `on_pass`, `on_fail`, `max_retries`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/learning_tests.py` (ENH-1282) — called by `LearningState` to query/write records
- `ll-loop` CLI entrypoint — no changes needed if state dispatch is already generic

### Similar Patterns
- Existing FSM state handlers (e.g., `verifying` state) — model `LearningState` after these

### Tests
- `scripts/tests/test_learning_state.py` — new test file
- Test: target with existing proven record → advance immediately
- Test: target missing → trigger explore-api → write record → advance
- Test: target refuted → transition to blocked

### Documentation
- `docs/ARCHITECTURE.md` — document `learning` state in FSM section
- Loop config reference docs — add `type: learning` examples

### Configuration
- Loop YAML schema — `targets: list[str]`, `on_pass: str`, `on_fail: str`, `max_retries: int` (default 2)

## Implementation Steps

1. Define `LearningState` dataclass and handler in `scripts/little_loops/fsm/learning_state.py`
2. Register new state type in FSM dispatch table
3. Wire `learning_tests.read_record()` call on entry; wire `ll:explore-api` invocation on miss/stale
4. Implement retry loop with `max_retries` and `blocked` escalation
5. Add `PushNotification` on block/refute
6. Write tests in `scripts/tests/test_learning_state.py`
7. Update docs and loop YAML schema reference

## Success Metrics

- A loop with `type: learning` and a proven target advances without re-running explore-api
- A loop with an unproven target automatically invokes explore-api, writes the record, then advances
- A loop with a refuted target halts and emits a push notification

## Scope Boundaries

- Out of scope: parallel execution of multiple learning targets (sequential is sufficient for v1)
- Out of scope: learning state triggering full issue implementation (it only proves assumptions)
- Out of scope: UI for monitoring learning state progress (loop events/logs are sufficient)

## API/Interface

```yaml
# Loop config example
states:
  - name: learning
    type: learning
    targets:
      - "Anthropic SDK streaming events"
    on_pass: planning
    on_fail: learning
    max_retries: 2
```

```python
# scripts/little_loops/fsm/learning_state.py
@dataclass
class LearningStateConfig:
    targets: list[str]
    on_pass: str
    on_fail: str
    max_retries: int = 2

class LearningStateHandler:
    def enter(self, config: LearningStateConfig, context: LoopContext) -> str: ...
```

## Impact

- **Priority**: P3 — High value for autonomous reliability, but only useful after ENH-1282 ships; not blocking current loop usage
- **Effort**: Medium — New FSM state type; pattern exists for other state types to follow
- **Risk**: Low-Medium — Additive new state type; existing loops unaffected unless they opt in
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM loop architecture context |
| `docs/deterministic-backpressure-learning-tests.md` | Philosophy for why the learning gate matters |

## Labels

`enhancement`, `autonomy`, `fsm`, `learning-tests`, `captured`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- No `scripts/little_loops/fsm/learning_state.py` exists ✓
- No `scripts/little_loops/learning_tests.py` module ✓
- No `type: learning` state type in FSM schema ✓
- Feature not yet implemented ✓

## Session Log
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`

- `/ll:verify-issues` - 2026-04-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf03929d-b936-46f6-9fc6-0edf5cab2290.jsonl`
- `/ll:capture-issue` — 2026-04-25T18:06:01Z — `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/771faa3d-a5a9-41eb-a550-7a0938c98004.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3
