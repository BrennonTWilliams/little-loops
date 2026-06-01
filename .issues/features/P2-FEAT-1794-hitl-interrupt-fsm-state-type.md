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
decision_needed: false
decision: Option A — hardcoded dispatch following the mcp_tool pattern. Simpler single-file executor change, follows existing conventions. Extension-based path (Option B) deferred as future refactor.
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Implementation approach — two options identified:**

**Option A: Hardcoded dispatch (mcp_tool pattern)**
Add `human_approval` as a built-in action type in the executor core, following the exact pattern `action_type: mcp_tool` used:
- `_action_mode()` at `executor.py:1330` — add `if state.action_type == "human_approval": return "human_approval"` (before the heuristic fallthrough)
- `_execute_state()` at `executor.py:780` — add dispatch branch before line 831 (similar to learning-state dispatch at line 797): `if state.action_type == "human_approval": return self._execute_human_approval_state(state, ctx)`
- New method `_execute_human_approval_state()`: emit event via `self._emit()`, block with `_interruptible_sleep()`-style polling (existing pattern at `executor.py:1647`), route by verdict
- Pros: simpler, single-file executor change, follows existing pattern
- Cons: couples HITL logic to executor core

**Option B: Extension-based (ActionProviderExtension)**
Implement as a contributed action via the extension protocol:
- Register via `ActionProviderExtension.provided_actions()` (`extension.py:81`)
- Wired through `wire_extensions()` at `extension.py:246` which populates `executor._contributed_actions`
- The executor already dispatches contributed actions in `_action_mode()` (line 1288) and `_run_action()` (line 980)
- Pros: decoupled, testable in isolation, follows extension architecture
- Cons: the contributed-action path runs through `_run_action()` which assumes fire-and-evaluate semantics — blocking on external response requires either extending the protocol or adding a dispatch branch in `_execute_state()` anyway

**Key corrections to issue assumptions:**
- **PushNotification does NOT exist** in the codebase (confirmed by grep). The `EventBus` (`events.py:70`) + transports (`transport.py`) are the closest notification infrastructure. v1 should render to terminal + emit an `LLEvent`; PushNotification/IM adapter is v2 scope.
- **`timeout` field already exists** on `StateConfig` at `schema.py:375` — can be reused for the HITL timeout without adding a new field.
- **`extra_routes`** on `StateConfig` (`schema.py:389`) already catches unrecognized `on_*` keys as dynamic routes — `on_edit` could be handled via `extra_routes` instead of a dedicated field, simplifying the schema change.
- **No `interactive` capability flag** exists on `HostCapabilities` (`host_runner.py:74`). Headless detection for the `LL_HOST_CLI=codex` requirement needs a new flag or a `sys.stdin.isatty()` check (currently only `sys.stdout.isatty()` checks exist in the codebase).
- **`ll-auto` and `ll-sprint` do NOT directly load FSM loop YAMLs** — they invoke Claude CLI slash commands. The "referenced by unattended automation" validation check would need a cross-reference mechanism that doesn't currently exist in `validate_fsm()`. Simplest v1 approach: warn whenever a `human_approval` state has no `timeout`, regardless of context.

**Reusable infrastructure identified:**
- `_interruptible_sleep()` at `executor.py:1647` — polling sleep with shutdown-signal respect, directly reusable for the HITL wait loop
- `_emit()` at `executor.py:1523` — event emission, emit `human_approval_request` on state entry
- `EventBus.register()` at `events.py:81` — subscribe to `human_response` events with glob filter
- `UnixSocketTransport._accept_loop()` at `transport.py:177` — socket-based polling with timeout, pattern for out-of-band response channel
- `SignalDetector` in `signal_detector.py` — detects in-band signals from action output; a `human_response` signal type could reuse this path
- `HandoffHandler` at `handoff_handler.py:68` — existing pause/spawn semantics; the HITL interrupt has analogous pause/resume behavior

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
- `scripts/little_loops/fsm/schema.py:309` — `StateConfig` dataclass: add `on_edit: str | None`, `on_timeout: str | None` fields; add `"on_edit"` and `"on_timeout"` to `_known_on_keys` set (line ~485); update `to_dict()`/`from_dict()`/`get_referenced_states()` (lines 395-575)
- `scripts/little_loops/fsm/executor.py:780` — `_execute_state()`: add dispatch branch for `action_type == "human_approval"` (before the generic action path at line 831, following the learning-state dispatch pattern at line 797)
- `scripts/little_loops/fsm/executor.py:1330` — `_action_mode()`: add `"human_approval"` to mode classification
- `scripts/little_loops/fsm/executor.py:943` — `_run_action()`: add branch for the new mode (emit `LLEvent`, block on external response, route by verdict)
- `scripts/little_loops/fsm/validation.py:374` — `_validate_state_action()`: add human_approval validations (warn if no `timeout`, require `on_yes`/`on_no`)
- `scripts/little_loops/fsm/validation.py:78` — Add `"human_approval"` to `NON_LLM_EVALUATOR_TYPES` awareness (it IS a non-LLM evaluator per MR-1)
- `scripts/little_loops/fsm/fsm-loop-schema.json:247` — Document `human_approval` as valid `action_type`, add `on_edit`/`on_timeout` properties
- `scripts/little_loops/host_runner.py:74` — `HostCapabilities`: add `interactive: bool` flag for headless detection
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add a new "HITL phase" section
- `skills/create-loop/reference.md:415` — document `human_approval` action_type and new routing fields

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:391` — `wire_extensions()`: may register human_approval if implemented as extension
- `scripts/little_loops/extension.py:81` — `ActionProviderExtension` protocol: alternative implementation path (contributed action)
- `scripts/little_loops/extension.py:246` — `wire_extensions()` populates `_contributed_actions` dict
- `scripts/little_loops/fsm/schema.py:539` — `get_referenced_states()`: must include `on_edit` and `on_timeout` targets

### Similar Patterns
- `action_type: mcp_tool` was added across 4 files (schema + executor + validator + JSON schema) — the exact pattern to follow. See `executor.py:1282` for the `_action_mode()` branch, `executor.py:967` for the `_run_action()` dispatch, `validation.py:388` for the `params`-only-with-mcp_tool check.
- `executor.py:1647` — `_interruptible_sleep()`: existing polling-with-timeout pattern for blocking while respecting shutdown signals — directly reusable for the HITL wait loop
- `executor.py:1523` — `_emit()`: existing event emission pattern — emit `human_approval_request` on state entry
- `events.py:70` — `EventBus` with `register()`/`emit()`/`add_transport()`: existing pub/sub infrastructure
- `transport.py:115` — `UnixSocketTransport._accept_loop()`: socket polling with timeout — pattern for out-of-band response channel
- `schema.py:389` — `extra_routes: dict[str, str]`: catches unrecognized `on_*` keys — `on_edit` could be handled via `extra_routes` instead of a dedicated field, simplifying the schema change
- **Correction**: `PushNotification` does NOT exist in the codebase (confirmed by grep). The event bus + `WebhookTransport` (`transport.py`) is the closest notification infrastructure. v1 should use terminal output + event bus; PushNotification/IM adapter is v2 scope.

### Tests
- `scripts/tests/test_fsm_executor.py:401` — `TestActionTypeMcpTool`: model new `TestActionTypeHumanApproval` class after this pattern (mock event callback, verify approve/reject/edit/timeout routing)
- `scripts/tests/test_fsm_schema.py:1801` — `TestMcpToolSchema`: model new `TestHumanApprovalSchema` class after this (field acceptance, round-trip, validation pass/fail)
- `scripts/tests/test_fsm_validation.py` — add tests for timeout warning on `human_approval` without `timeout:`
- `scripts/tests/test_fsm_executor.py:4246` — `TestContributedActionDispatch`: pattern if implementing as extension-based action type

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (phase chain table, decision guide, troubleshooting)
- `skills/create-loop/reference.md` (FSM field reference, line ~415 for `action_type` docs)

### Configuration
- `.ll/ll-config.json` — optional `hitl.default_timeout` and `hitl.notification_channel` keys (defer if not needed for v1)
- `LL_HOST_CLI` env var — already used by `host_runner.py:751` `resolve_host()` for host detection; headless hosts (codex) should force timeout path

## Implementation Steps

1. **Schema** (`fsm/schema.py:309`): Add `on_edit: str | None` and `on_timeout: str | None` to `StateConfig`; add `"on_edit"` and `"on_timeout"` to `_known_on_keys` (~line 485); update `to_dict()`/`from_dict()`/`get_referenced_states()`. Also update `fsm-loop-schema.json:247` to document `human_approval` as valid `action_type`.
   - Alternative: use `extra_routes` (`schema.py:389`) for `on_edit`/`on_timeout` to avoid schema changes — unrecognized `on_*` keys are already captured there.
2. **Validator** (`fsm/validation.py:374`): In `_validate_state_action()`, add: require `on_yes`/`on_no` when `action_type == "human_approval"`; WARNING if no `timeout` is set; add `"human_approval"` to `NON_LLM_EVALUATOR_TYPES` awareness at line 78 (it IS a non-LLM evaluator per MR-1).
3. **Executor dispatch** (`fsm/executor.py`): Add `"human_approval"` to `_action_mode()` (line 1280, before the heuristic fallthrough). In `_execute_state()` (line 772), add a dispatch branch before the generic action path at line 831 — follow the learning-state dispatch pattern at line 797: `if state.action_type == "human_approval": return self._execute_human_approval_state(state, ctx)`.
4. **HITL handler** (new method `_execute_human_approval_state()` in `fsm/executor.py`): Render prompt with `${captured.*}` interpolation, emit `human_approval_request` event via `self._emit()` (existing pattern at line 1339), block on response using `_interruptible_sleep()`-style polling (existing pattern at line 1463), route based on verdict/timeout. Terminal-only notification for v1.
5. **Host capability** (`host_runner.py:74`): Add `interactive: bool` flag to `HostCapabilities`. Set based on `sys.stdin.isatty()` (existing pattern in `hooks/__init__.py:111`). In the HITL handler, if not interactive, short-circuit to `on_timeout`/`on_no`.
6. **Tests**: Add `TestActionTypeHumanApproval` in `test_fsm_executor.py` (model after `TestActionTypeMcpTool` at line 401) — mock event callback, verify approve/reject/edit/timeout routing. Add `TestHumanApprovalSchema` in `test_fsm_schema.py` (model after `TestMcpToolSchema` at line 1801). Add timeout-warning test in `test_fsm_validation.py`.
7. **Docs**: Add HITL phase section to `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`; document `human_approval` action_type and new routing fields in `skills/create-loop/reference.md:415`; add example loop under `loops/examples/`.
8. **v2 scope** (defer): PushNotification integration (does not exist today), IM adapter (Slack/Telegram), multi-user approval quorum.

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

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: NEEDS_UPDATE** — Core architecture accurate but executor.py line numbers have drifted significantly since refinement:
- `PushNotification` confirmed absent from codebase ✓
- `StateConfig` at `schema.py:309` ✓; `HostCapabilities` at `host_runner.py:75` (issue says 74) ~
- `_execute_state()` at executor.py:780 (issue says 772, off by 8) ~
- `_action_mode()` at executor.py:1330 (issue says 1280, off by 50) ~
- `_emit()` at executor.py:1523 (issue says 1339, off by **184**) ✗
- `_interruptible_sleep()` at executor.py:1647 (issue says 1463, off by **184**) ✗
- Action: update executor.py anchor lines before implementation to avoid confusion

## Session Log
- `/ll:verify-issues` - 2026-06-01T03:08:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed2ec455-964e-4a94-92a4-e94218c08ad6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:53:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:refine-issue` - 2026-05-30T04:16:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e2daf50-26d6-4657-859b-a4e70fd08209.jsonl`
- `/ll:format-issue` - 2026-05-29T21:13:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b9fd7ee-19a7-49f3-85a1-70addaba91a5.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The Stop hook infrastructure introduced by FEAT-1680 (session-end sweep of stale cross-issue status refs) is an independent path from the HITL event bus path in this issue. FEAT-1680 registers a Stop hook in `hooks/hooks.json` for sweeping stale prose references; this issue adds a blocking `human_approval` FSM state that emits `LLEvent` messages via the existing event bus. The two hooks.json registrations target different events (Stop vs. in-loop FSM execution) and touch entirely different data. No coordination between FEAT-1680 and FEAT-1794 is required at implementation time.
