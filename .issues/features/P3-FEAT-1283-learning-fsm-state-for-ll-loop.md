---
id: FEAT-1283
type: FEAT
priority: P3
captured_at: "2026-04-25T18:06:01Z"
discovered_date: "2026-04-25"
discovered_by: capture-issue
depends_on: [FEAT-1282]
blocked_by: [FEAT-1286, ENH-1115, FEAT-1287]
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

## Use Case

A developer kicks off `ll-auto` on an issue that requires integrating with the Anthropic SDK's streaming API. Without a learning gate, the loop's planning agent fabricates the shape of streaming events and iterates on broken implementations until time or retries run out. With a `learning` state declared in the loop config and `"Anthropic SDK streaming events"` listed as a target, the loop first queries the learning-tests registry (ENH-1282); on a miss it runs `/ll:explore-api`, writes the proven record, then advances to `planning` with verified API knowledge. The next loop run on a different issue that touches the same SDK skips re-exploration entirely because the registry already has a current proven record. If a target is later refuted (e.g., SDK behavior changed), the loop halts and emits a push notification rather than silently producing slop.

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

## Acceptance Criteria

- A loop with `type: learning` and a proven target advances to `on_pass` without re-running explore-api
- A loop with an unproven target automatically invokes `/ll:explore-api`, writes the registry record, then advances
- A loop with a refuted target halts, transitions to a `blocked` state, and emits a `PushNotification`
- After `max_retries` exhaustion on stale/missing targets, the loop transitions to `blocked` rather than looping indefinitely
- Loop YAML schema validation rejects `type: learning` states missing required fields (`targets`, `on_pass`, `on_fail`)

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

`enhancement`, `autonomy`, `fsm`, `learning-tests`, `learning-testing`, `captured`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- No `scripts/little_loops/fsm/learning_state.py` exists ✓
- No `scripts/little_loops/learning_tests.py` module ✓
- No `type: learning` state type in FSM schema ✓
- Feature not yet implemented ✓

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-11T21:32:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/521f9c4d-aa09-4ad1-88fe-93826dacaa4a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-05T02:27:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d743dae1-3278-4abd-a763-b23632abd3cb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-02T02:07:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04ed7039-9c6c-4ed5-8bb4-0babdee81a7b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`

- `/ll:verify-issues` - 2026-04-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf03929d-b936-46f6-9fc6-0edf5cab2290.jsonl`
- `/ll:capture-issue` — 2026-04-25T18:06:01Z — `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/771faa3d-a5a9-41eb-a550-7a0938c98004.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, 2026-05-01): Cross-reference with FEAT-1308 (loop YAML `from:` template inheritance). The example in this issue declares states as a YAML list (`states: - name: ...`); FEAT-1308's `from:` deep-merge mechanism requires the mapping form (`states.<name>: ...`). Pin the canonical states schema to the mapping form before either issue ships. Update the example in this issue to the mapping form during implementation: `states.learning: { type: learning, targets: [...], on_pass: planning, on_fail: learning, max_retries: 2 }`.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): `LearningStateHandler` is a Python module (`scripts/little_loops/fsm/learning_state.py`) and MUST use direct Python import — `from little_loops.learning_tests import read_record` — not shell out to the `ll-learning-tests` CLI. The CLI (FEAT-1286) exists specifically for non-Python callers (skills, Bash evaluators, FSM shell-type evaluators). Using the CLI from within the Python handler adds unnecessary subprocess overhead and goes against the intended interface split.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): `LearningStateHandler` is a Python-native FSM state handler — it is NOT a hook intent under FEAT-1116's hook-intent abstraction layer. FEAT-1116's intent system targets `PreToolUse`, `PostToolUse`, `PreCompact`, and `SessionStart` hooks. The learning state runs within the FSM loop engine (not as a hook), so it does not need a hook adapter and should not use FEAT-1116's `LLHookIntentExtension` protocol. The direct-Python-import constraint (note above) also applies here.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): `type: learning` states are exempt from ENH-1115's throttle `hard_max`. ENH-1115's per-state tool-call counter applies a hard-stop at `hard_max` (default 9) for all states. A learning state with N targets legitimately calls `ll:explore-api` N times in a single visit — this would incorrectly trip the throttle. ENH-1115's implementation MUST check `state_config.type == "learning"` before firing `hard_max`; `warn_max` warnings still apply. This issue does not need to implement the exemption (ENH-1115 owns it), but `LearningStateConfig` should document `max_retries` as its own internal gate to distinguish it from the throttle gate: throttle counts tool-call *volume*, learning counts target-resolution *attempts*.
