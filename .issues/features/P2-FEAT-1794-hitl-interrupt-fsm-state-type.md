---
id: FEAT-1794
type: FEAT
title: HITL interrupt FSM state type (action_type human_approval)
priority: P2
status: open
captured_at: '2026-05-29T20:37:23Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
  - captured
  - fsm
  - harness
  - hitl
  - loops
relates_to: [FEAT-1545, FEAT-1613]
---

# FEAT-1794: HITL interrupt FSM state type (`action_type: human_approval`)

## Summary

Add a first-class human-in-the-loop interrupt to the FSM runner: a new
`action_type: human_approval` (or equivalent state shape) that pauses a
running harness, surfaces a question/context to the operator out-of-band,
waits for a yes/no/edit response, and routes via `on_yes` / `on_no` /
`on_edit`. This is the analogue of DeerFlow's `interrupt()` and
`ask_clarification` patterns and is the missing primitive that prevents
our harness from collaborating with a human inside the loop.

## Current Behavior

The harness pipeline today (`check_concrete` → `check_mcp` → `check_skill`
→ `check_semantic` → `check_invariants`) is fully autonomous. When an
evaluation fails, the only options are:
- `on_no: execute` — retry the same input
- `on_no: advance` / `done` — skip / give up

There is no way for a long-running loop (e.g., `ll-auto` over 30 issues,
a multi-hour `harness-optimize` run) to ask "the diff looks runaway —
keep going or abort?", or to surface a planner output for human review
before paying for the implement step. The operator either babysits the
terminal (defeats the point) or trusts the LLM judge in isolation
(violates our MR-1 anti-self-eval rule for meta-loops).

## Expected Behavior

A state with `action_type: human_approval` should:

1. Render a prompt (the state's `prompt:` field) plus any captured
   context (e.g., `${captured.execute.output}`) to a notification
   channel — minimally the terminal/TUI, ideally also `PushNotification`
   or an IM adapter (Slack/Telegram per the IM-gateway adjacency).
2. Block FSM execution while waiting for a response.
3. Accept at least three verdicts:
   - `approve` → take `on_yes`
   - `reject` → take `on_no`
   - `edit` → take `on_edit`, with the edited text captured for the next
     state to consume via `${captured.<state>.edit}`
4. Honor a `timeout:` field — on timeout, take `on_timeout` (default to
   `on_no` if unspecified). This is critical for unattended `ll-auto`
   runs that must not deadlock if the human is away.
5. Emit a `LLEvent` so the operator can be paged via the existing event
   bus instead of polling.

Example shape (TBD on exact field names):

```yaml
check_human:
  action_type: human_approval
  prompt: >
    The execute step modified 240 lines. Threshold is 50.
    Diff summary: ${captured.check_invariants.output}
    Approve to continue, reject to retry execute, edit to adjust the diff.
  timeout: 1800   # 30 min unattended fallback
  on_yes: advance
  on_no: execute
  on_edit: re_execute
  on_timeout: advance
```

## Use Case

**Who**: A developer or operator running long-lived little-loops automation (e.g.,
`ll-auto` over 30+ issues, multi-hour `harness-optimize` runs).

**Context**: During an unattended or semi-attended FSM run, an evaluation step
detects a condition that warrants human judgment — a diff exceeding a safety
threshold, a planner output that looks questionable, or a meta-loop's
`check_semantic` result that needs independent verification per MR-1.

**Goal**: Pause the harness, surface the relevant context and a yes/no/edit
question to the operator, then route the FSM based on the response — without
requiring the operator to babysit the terminal or trusting the LLM judge alone.

**Outcome**: The operator receives a notification (terminal, push, or IM), reviews
the context, responds with approve/reject/edit, and the FSM resumes on the
appropriate transition path. If the operator is away, a configurable timeout
falls back to a safe default (typically `on_no`) so unattended runs never
deadlock.

## Motivation

- Closes a confirmed gap surfaced by the DeerFlow comparison in
  `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`: DeerFlow's clarification
  loop + plan review + tool-call approval pause execution at strategic
  checkpoints; ours has zero such primitives.
- Strengthens MR-1 compliance — a `human_approval` state IS a non-LLM
  evaluator, so it can pair with `check_semantic` in meta-loops without
  triggering the rule.
- Unlocks workflows that today require either a separate hitl-* loop
  (FEAT-1545, FEAT-1613) or babysitting: mid-`harness-optimize`
  review, gated `ll-auto` runs, dangerous-diff confirmations.
- As models improve and loops get more ambitious, the value of a single
  well-placed human checkpoint goes up, not down.

## Acceptance Criteria

- [ ] FSM runner recognizes `action_type: human_approval` and dispatches to the HITL handler
- [ ] Prompt text plus captured context (e.g., `${captured.execute.output}`) is rendered to the notification channel
- [ ] FSM execution blocks while waiting for a human response (no CPU spin, no premature advance)
- [ ] Three verdicts are accepted: `approve` (→ `on_yes`), `reject` (→ `on_no`), `edit` (→ `on_edit` with edited text captured as `${captured.<state>.edit}`)
- [ ] `timeout:` field is honored; on timeout, takes `on_timeout` (defaults to `on_no` if `on_timeout` unspecified)
- [ ] An `LLEvent` is emitted on state entry so the operator can be paged via the event bus rather than polling
- [ ] `ll-loop validate` warns when a `human_approval` state has no `timeout:` AND the loop is referenced by unattended automation (ll-auto, ll-sprint)
- [ ] Headless/non-interactive contexts (e.g., `LL_HOST_CLI=codex`) take a safe default without deadlocking

## Proposed Solution

TBD — requires investigation of:
- Notification surface: PushNotification vs PushNotification + IM
  adapter chain. The existing host_runner / hook adapter layer is the
  natural place to plug this in.
- Wait semantics: blocking poll on a file/socket vs the existing event
  bus subscribe. The runner already journals events; a `human_response`
  event type may be the cleanest signal.
- Headless mode: `LL_HOST_CLI=codex` / non-interactive contexts need a
  safe default (probably `on_timeout: on_no` with a short timeout and a
  loud log).
- Schema rules: `ll-loop validate` should warn if a `human_approval`
  state has no `timeout:` AND the loop is referenced by ll-auto /
  ll-sprint (where unattended deadlock is a real risk).

## API/Interface

New FSM state schema (`action_type: human_approval`):

```yaml
# In loop YAML definitions
check_human:
  action_type: human_approval
  prompt: "string — rendered to operator; supports ${captured.<state>.<field>} interpolation"
  timeout: 1800          # seconds; optional but warned if absent for unattended contexts
  on_yes: advance        # transition when operator approves
  on_no: execute         # transition when operator rejects
  on_edit: re_execute    # transition when operator edits; edit captured at ${captured.<state>.edit}
  on_timeout: advance    # fallback transition; defaults to on_no if unspecified
```

New LLEvent types:

```python
@dataclass
class HumanApprovalRequest(LLEvent):
    """Emitted when a human_approval state is entered."""
    loop_name: str
    state_name: str
    prompt: str
    timeout: int
    captured_context: dict


@dataclass
class HumanResponse(LLEvent):
    """Emitted when the operator responds to a human_approval request."""
    loop_name: str
    state_name: str
    verdict: Literal["approve", "reject", "edit"]
    edited_text: str | None  # populated for edit verdict
```

Validator rules: `ll-loop validate` SHALL warn (not error) when `action_type:
human_approval` is present without `timeout:` AND the loop is referenced by
unattended automation config (ll-auto, ll-sprint). This is a safety gate, not a
hard block — the loop author can suppress it with `timeout: 0` to explicitly
accept the default.

## Integration Map

### Files to Modify
- `scripts/little_loops/loop_runner.py` (executor dispatch on
  `action_type`) — TBD line range
- `scripts/little_loops/loop_validator.py` — add `human_approval`
  to known action types; add a warning for missing `timeout`
- `scripts/little_loops/loops_schema.py` (or equivalent) — schema entry
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add a new "HITL phase"
  section between `check_skill` and `check_semantic`
- `skills/create-loop/loop-types.md` — wizard question to include the
  phase
- `templates/feat-sections.json` — N/A

### Dependent Files (Callers/Importers)
- TBD — grep for `action_type` dispatch sites

### Similar Patterns
- `action_type: mcp_tool` was a recent addition — same shape of work
- Existing `PushNotification` tool is the cleanest reference for the
  notification side

### Tests
- `scripts/tests/test_loop_runner.py` — new test class
- `scripts/tests/test_loop_validator.py` — schema/timeout validation

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (phase chain table,
  decision guide, troubleshooting)
- `skills/create-loop/reference.md` (FSM field reference)

### Configuration
- `.ll/ll-config.json` — optional `hitl.default_timeout` and
  `hitl.notification_channel` keys (defer if not needed for v1)

## Implementation Steps

1. Define the `human_approval` action schema and add it to the
   validator with a warning for missing `timeout`.
2. Implement the runner dispatch: render prompt → notify → block on
   response → route. Start with terminal-only notification.
3. Add a `human_response` LLEvent type and wire the runner to consume
   from the event bus, so an out-of-band tool (CLI helper or future
   IM adapter) can resolve the wait.
4. Add documentation + a small example loop under `loops/examples/`.
5. Write tests covering approve / reject / edit / timeout paths.
6. Decide v2 scope: PushNotification integration, IM adapter, multi-user
   approval quorum.

## Impact

- **Priority**: P2 — Highest-leverage gap from the DeerFlow comparison;
  enables a class of workflows (gated automation, mid-loop review) that
  are awkward or impossible today.
- **Effort**: Medium — new dispatch path, schema entry, validator
  changes, docs, tests. Notification surface scope determines size.
- **Risk**: Medium — unattended contexts can deadlock if `timeout:`
  semantics aren't conservative by default.
- **Breaking Change**: No — new opt-in state type.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Currently lists zero HITL primitives; this issue adds one |
| `.claude/CLAUDE.md` § Loop Authoring | Meta-loop MR-1 rule — `human_approval` qualifies as a non-LLM evaluator |
| `docs/ARCHITECTURE.md` | Event-bus + host_runner abstraction this hooks into |

## Labels

`captured`, `fsm`, `harness`, `hitl`, `loops`

## Status

**Open** | Created: 2026-05-29 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-05-29T21:13:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b9fd7ee-19a7-49f3-85a1-70addaba91a5.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`
