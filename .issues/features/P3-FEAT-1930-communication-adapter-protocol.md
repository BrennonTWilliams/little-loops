---
id: FEAT-1930
title: Communication adapter protocol for async HITL channels
type: FEAT
priority: P3
captured_at: "2026-06-04T00:00:00Z"
discovered_date: 2026-06-04
discovered_by: scope-epic
status: open
parent: EPIC-1929
relates_to:
- FEAT-1794
- FEAT-1931
- EPIC-2196
blocks:
- FEAT-2102
- FEAT-1794
- FEAT-1931
labels:
  - fsm
  - harness
  - hitl
  - extension
verify_verdict: VALID
---

# FEAT-1930: Communication adapter protocol for async HITL channels

## Summary

Define a `CommunicationAdapter` abstract protocol that decouples the FSM
`human_approval` state from transport-specific I/O. The protocol provides two
operations — `send_alert()` for outbound delivery and `await_response()` for
inbound verdict collection — and registers through the extension system so
adapters are discoverable and config-swappable.

This is the **foundational child** of EPIC-1929. FEAT-1794 (FSM state) and
FEAT-1931 (terminal adapter) depend on this interface being stabilized first.

## Re-scope (2026-06-20) — two adapters, EventBus not bespoke push

The Hermes integration (EPIC-2196, `done`) changed what this protocol needs to
abstract over. The original framing — a rich multi-transport protocol spanning
terminal, push, Slack, Telegram, SMS, webhook, with little-loops owning each
transport — is obsolete: **Hermes already reaches the operator on every one of
those channels** (text, Telegram, etc.) and consumes little-loops events via its
webhook and the EventBus/extension surface.

The protocol's surface (`send_alert()` / `await_response()` / `supports_async()`)
and the `CommunicationAdapterExtension` registration decision (Option B, below)
are **unchanged**. What shrinks is the set of adapters this protocol must prove
itself against:

- **`terminal`** — dev/debug/fallback channel (FEAT-1931). Unchanged.
- **`eventbus`** — emit a `human_approval_requested` event; resume when a
  matching `human_response` event arrives. This is the async channel Hermes
  consumes and relays to whatever channel the operator is on. **Replaces the
  cancelled bespoke PushNotification adapter (FEAT-1932).**

This also **resolves Open Question #2** (event bus vs. file-poller for the inbound
callback) in favor of the **event bus** — that is precisely the surface Hermes
already subscribes to, so no new inbound transport is needed. Designing the
protocol for these two adapters (sync terminal + async eventbus) still proves the
abstraction; third-party adapters (a direct Slack adapter, a custom webhook) can
be added later against the same protocol without touching `executor.py`.

> Downstream: FEAT-1932 **cancelled**; FEAT-2102 (adapter-swap test) **deferred**
> until the `eventbus` adapter lands, then retargeted to terminal↔eventbus.

## Current Behavior

The FSM executor currently has no abstraction layer for human-in-the-loop (HITL)
communication channels. Any `human_approval` state would need transport-specific
I/O hardcoded directly in `executor.py` — there is no adapter protocol, no
extension-based discovery, and no config-driven channel selection.

## Expected Behavior

1. A `CommunicationAdapter` abstract class / protocol defining:
   - `send_alert(loop_name, state_name, prompt, captured_context, timeout) → alert_id`
   - `await_response(alert_id, timeout) → HumanResponse | TimeoutResponse`
   - `supports_async() → bool` — whether the channel can reach an operator who
     isn't watching the terminal
2. Adapters register via the extension system through a new
   `CommunicationAdapterExtension` Protocol (decided 2026-06-12 — see
   Decision Rationale in Proposed Solution).
3. Config-driven channel selection: `.ll/ll-config.json` key `hitl.channel`
   selects the active adapter (default: `terminal`).
4. The FSM executor resolves the configured adapter and calls the protocol
   methods — it never imports a specific adapter directly.

## Motivation

Without this protocol, the `human_approval` state type would hardcode transport
logic in `executor.py` — terminal `input()` today, ripped out and replaced with
push tomorrow, Slack the day after. An adapter protocol is a one-time abstraction
cost that pays back every time a new channel is added.

## Use Case

**Who**: A platform developer wiring ll's human-in-the-loop workflow to an async
relay (the EventBus adapter consumed by Hermes), or adding a further channel
later.

**Context**: An FSM loop reaches a `human_approval` state and needs operator input
before proceeding. The operator might be watching the terminal, or might be away
and reachable only through Hermes (text, Telegram, etc.), which relays the
EventBus-published prompt and feeds the verdict back.

**Goal**: The developer implements a `CommunicationAdapter` subclass for their
channel without modifying `executor.py`, `extension.py`, or any existing adapter.

**Outcome**: Setting `hitl.channel: "eventbus"` in `.ll/ll-config.json` routes all
`human_approval` prompts through the EventBus adapter (relayed by Hermes) — no
code changes to the FSM runner. Switching back to `hitl.channel: "terminal"` for
local dev is the same one-line config change.

## Acceptance Criteria

- [ ] `CommunicationAdapter` abstract interface defined with `send_alert()`,
  `await_response()`, and `supports_async()`
- [ ] Extension registration path established (adapter discovery via
  `wire_extensions()` or equivalent)
- [ ] Config schema: `hitl.channel` in `.ll/ll-config.json` selects active
  adapter; falls back to `terminal` if unset
- [ ] FSM executor resolves adapter via config + extension registry, not
  hardcoded import
- [ ] `ll-loop validate` warns when `hitl.channel` is unset and host is
  non-interactive (no adapter can reach the operator)
- [ ] Tests: mock adapter implementation, verify executor calls protocol methods
  not transport-specific code

## Proposed Solution

Model after the existing transport abstraction (`transport.py`:
`UnixSocketTransport`, `WebhookTransport`) and the extension protocol
(`extension.py:81` `ActionProviderExtension`).

Key design decision: extend `ActionProviderExtension` (adds
`provided_adapters()`) vs. create a new `CommunicationAdapterExtension`.

> **Selected:** Option B — new `CommunicationAdapterExtension` Protocol class — matches the codebase's one-Protocol-per-capability convention (4 existing precedents), and Option A's claimed `_run_action()` dispatch reuse does not hold (adapter resolution is `hitl.channel` config-key-driven, not `action_type`-driven).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-12.

**Selected**: Option B — create a new `CommunicationAdapterExtension` Protocol class with a single `provided_adapters()` method, detected via `hasattr()` in `wire_extensions()`.

**Reasoning**: `extension.py` already contains four separate capability Protocols (`InterceptorExtension` :61, `ActionProviderExtension` :81, `EvaluatorProviderExtension` :92, `LLHookIntentExtension` :104), each with a narrow typed return and its own `hasattr()` gate in `wire_extensions()` (:246–273) — and the most recently added capability (`LLHookIntentExtension`) was created as a new Protocol rather than appended to an existing one. Option A would create the codebase's first fat interface and force `ActionProviderExtension` to carry two methods returning unrelated types (`dict[str, ActionRunner]` vs adapters); its core rationale — reusing the contributed-action dispatch in `_run_action()` — does not survive inspection, because adapter lookup is keyed by the `hitl.channel` config value, not by `state.action_type`. The net-new infrastructure (a `_contributed_adapters` registry on `FSMExecutor` alongside `_contributed_actions`/`_contributed_evaluators` at `executor.py:272–274`, the `hitl.channel` config property, and the resolution call site) is identical under both options, so separation costs nothing extra.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — extend `ActionProviderExtension` | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |
| B — new `CommunicationAdapterExtension` | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |

**Key evidence**:
- **Option A**: `wire_extensions()` loop and conflict-detection guards are reusable, but no existing extension class mixes `provided_*` methods from different capability types; `provided_actions()` is precisely typed as `dict[str, ActionRunner]`, which a `CommunicationAdapter` does not satisfy.
- **Option B**: replicates a mechanical 4-precedent pattern end-to-end — Protocol class, `hasattr()` gate, `_contributed_*` executor slot, `ValueError` duplicate guard, `__init__.py` export, `TestNewProtocols` smoke/protocol-satisfied tests (`test_extension.py:524–691`), and a one-line addition to the `ll-create-extension` scaffold docstring (`create_extension.py:84`).

**Follow-through for implementation**: register via `hasattr(ext, "provided_adapters")` in `wire_extensions()`; add `_contributed_adapters: dict[str, CommunicationAdapter]` to `FSMExecutor.__init__`; resolve the active adapter from `hitl.channel` with `terminal` fallback; update the `ll-create-extension` docstring and `__init__.py` exports; FEAT-1931 (terminal) and the EventBus adapter (per the 2026-06-20 re-scope; replaces the cancelled FEAT-1932) implement adapters against the new Protocol.

## API/Interface

The `CommunicationAdapter` abstract protocol defines the public contract:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class HumanResponse:
    approved: bool
    reason: Optional[str] = None
    modified_prompt: Optional[str] = None

@dataclass
class TimeoutResponse:
    timed_out: bool = True
    elapsed_seconds: float = 0.0

class CommunicationAdapter:
    """Abstract protocol for async HITL communication channels."""

    def send_alert(
        self,
        loop_name: str,
        state_name: str,
        prompt: str,
        captured_context: dict,
        timeout: float,
    ) -> str:
        """Deliver an approval request to the operator. Returns alert_id."""
        ...

    def await_response(
        self, alert_id: str, timeout: float
    ) -> HumanResponse | TimeoutResponse:
        """Block until the operator responds or timeout expires."""
        ...

    def supports_async(self) -> bool:
        """True if this channel can reach an operator not watching the terminal."""
        ...
```

Extension registration (via the new `CommunicationAdapterExtension` — see
Decision Rationale):

```python
class TerminalAdapter(CommunicationAdapter):
    ...

class TerminalAdapterExtension(CommunicationAdapterExtension):
    def provided_adapters(self) -> list[type[CommunicationAdapter]]:
        return [TerminalAdapter]
```

## Integration Map

### Files to Create
- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter`
  abstract class, `HumanResponse` / `TimeoutResponse` dataclasses
- `scripts/tests/test_communication_adapter.py` — mock adapter, protocol contract
  tests

### Files to Modify
- `scripts/little_loops/extension.py:81` — either extend
  `ActionProviderExtension` or add new `CommunicationAdapterExtension`
- `scripts/little_loops/extension.py:246` — `wire_extensions()`: wire adapters
  into executor
- `scripts/little_loops/fsm/executor.py` — resolve adapter from config +
  registry
- `.ll/ll-config.json` schema — add `hitl.channel` key

### Similar Patterns
- `transport.py:115` — `UnixSocketTransport._accept_loop()`: transport
  abstraction with timeout
- `extension.py:81` — `ActionProviderExtension.provided_actions()`: extension
  registration pattern
- `host_runner.py:74` — `HostCapabilities`: capability detection pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

Additional callers, precedent anchors, and config-wiring call sites found beyond what the sections above already cite:

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py:321` — calls `wire_extensions(event_bus, config.extensions)`
- `scripts/little_loops/cli/sprint/run.py:800` — calls `wire_extensions(event_bus, config.extensions)`
- `scripts/little_loops/cli/loop/run.py:622` — calls `wire_extensions(executor.event_bus, _config.extensions, executor=executor)`
- `scripts/little_loops/cli/loop/lifecycle.py:736` — calls `wire_extensions(executor.event_bus, config.extensions, executor=executor)`

### Additional Confirmed Anchors
- `scripts/little_loops/extension.py:103-111` — `LLHookIntentExtension`, the most recently added of the 4 capability Protocols; nearest structural precedent for a new `CommunicationAdapterExtension`
- `scripts/little_loops/extension.py:234-277` — `wire_extensions()` registration body: `hasattr()` detection loop, the `fsm_executor is not None:` block populating `_contributed_actions`/`_contributed_evaluators`/`_interceptors`, and the separate final loop wiring `provided_hook_intents`
- `scripts/little_loops/fsm/executor.py:494-497` — `FSMExecutor.__init__`: `_contributed_actions`/`_contributed_evaluators`/`_interceptors` declared together; exact site for a parallel `_contributed_adapters: dict[str, CommunicationAdapter] = {}`
- `scripts/little_loops/cli/create_extension.py:80-94` (`_render_extension()`) — hardcodes a 4-item Protocol-name list (`InterceptorExtension, ActionProviderExtension, EvaluatorProviderExtension, LLHookIntentExtension`) in the scaffolded extension docstring; a 5th Protocol needs manual addition here (no data-driven registry exists)
- `scripts/little_loops/templates/extension/extension.py.tmpl:8-14` — a second, independent copy of the same docstring sentence, already out of sync with `create_extension.py` (lists only 3 of the current 4 Protocols, missing `LLHookIntentExtension`) — pre-existing drift, not introduced by this issue
- `scripts/little_loops/config/core.py:332-333` — `BRConfig._parse_config()`: `self._orchestration = OrchestrationConfig.from_dict(self._raw_config.get("orchestration", {}))` — pattern a new `hitl` namespace's wiring would follow
- `scripts/little_loops/config/core.py:461-463` — `BRConfig.orchestration` property accessor — a `hitl` namespace needs the equivalent
- `scripts/little_loops/config/core.py:863+` — `to_dict()`-style serialization block that mirrors each config namespace back out; a third call site any new namespace must also touch
- `scripts/little_loops/config-schema.json:1239-1244` (`learning_tests.release_gate`) and `:1307-1312` (`dependency_mapping.conflict_threshold`) — closest existing precedents for a single string/enum key with both a JSON `"default"` and a dataclass-level default, the shape `hitl.channel` would follow (compare `orchestration.host_cli`, `:1741-1749`, which has no JSON `"default"` and instead documents an env-var-wins fallback in prose)
- `scripts/little_loops/host_runner.py:127-152` (`HostCapabilities`) — confirmed: no `interactive`/non-interactive-host field exists today (fields are `streaming`, `permission_skip`, `agent_select`, `tool_allowlist`, `structured_output`, `workspace_sandboxed`); AC #5's "warns ... when host is non-interactive" has no existing signal to key on and would need one added
- `scripts/little_loops/cli/loop/config_cmds.py:14` — `cmd_validate`, the actual `ll-loop validate` entry point (anchor-drifted from `cli/loop/__init__.py:1089`); warnings flow through `ValidationError(message=..., path=..., severity=ValidationSeverity.WARNING)` (`scripts/little_loops/fsm/validation/_base.py:15-41`), with `_validate_state_action()` (`scripts/little_loops/fsm/validation/structural_rules.py:408-448`) as a concrete WARNING-emission precedent

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

Concrete types, signatures, and the call path this protocol plugs into, derived from `extension.py`'s existing 4-Protocol capability pattern and `FSMExecutor`'s contributed-registry mechanics.

### Types
- `CommunicationAdapter` (abstract class, `scripts/little_loops/fsm/communication_adapter.py`, new file) — `send_alert()`/`await_response()`/`supports_async()`, per API/Interface above
- `CommunicationAdapterExtension(Protocol)` (new, `scripts/little_loops/extension.py`) — single method `provided_adapters() -> list[type[CommunicationAdapter]]`; note this return shape (`list[type[X]]`) has no existing precedent — all 4 current capability Protocols (`provided_actions`, `provided_evaluators`, `provided_hook_intents`) return `dict[str, X]`, never a list
- The adapter-return dataclass currently named `HumanResponse` in this issue's own API/Interface collides with `HumanResponse(LLEvent)` already defined in FEAT-1794's API/Interface (`verdict: Literal["approve","reject","edit"]`) — both would import into `executor.py`'s namespace. This issue's own `## Scope Boundary` section (added 2026-06-25) already records this and calls for renaming to `AdapterResponse`/`HumanApprovalDecision` plus adding a `verdict: Literal[...]` field; reconfirmed as still unresolved on both issues as of 2026-09-03 — see Scope Boundary section below

### Signatures
- `wire_extensions(bus: EventBus, config_paths: list[str] | None = None, executor: FSMExecutor | PersistentExecutor | None = None) -> list[LLExtension]` (`extension.py:201`) — existing signature the new `hasattr(ext, "provided_adapters")` gate plugs into; the executor-registry effect is an in-place mutation of the passed `executor=` kwarg, not the return value
- `FSMExecutor.__init__` declares `_contributed_actions: dict[str, ActionRunner] = {}` / `_contributed_evaluators: dict[str, Evaluator] = {}` (`executor.py:494-497`) with no constructor parameter for pre-seeding — both start empty and are only filled by a later `wire_extensions(..., executor=fsm_executor)` call; a `_contributed_adapters: dict[str, CommunicationAdapter] = {}` would follow the identical shape
- `BRConfig._parse_config()` wires each namespace as `self._<ns> = <Ns>Config.from_dict(self._raw_config.get("<ns>", {}))` (`config/core.py:332-333` shows the `orchestration` case) — a `hitl` namespace needs a matching `HitlConfig.from_dict(...)` call plus the `BRConfig.hitl` property (pattern at `config/core.py:461-463`) and a `to_dict()` entry (`:863+`)

### Call Path
`cli/loop/run.py:622` (or `cli/loop/lifecycle.py:736`) → `wire_extensions(executor.event_bus, config.extensions, executor=executor)` (`extension.py:201`) → `hasattr(ext, "provided_adapters")` gate (new, alongside the existing gates at `extension.py:246-273`) → `fsm_executor._contributed_adapters.update(ext.provided_adapters())` (new, mirrors `:248-256`) → (not yet implemented anywhere) a `human_approval` state handler in `executor.py` resolves the active adapter from `_contributed_adapters` keyed by the `hitl.channel` config value, falling back to `"terminal"` → `adapter.send_alert(...)` → `adapter.await_response(...)`

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold; `hitl.channel` is a plain config-key channel selector with a documented default, not a classification rule.

## Implementation Steps

1. Define `CommunicationAdapter` abstract class with `send_alert()`,
   `await_response()`, and `supports_async()` in a new
   `scripts/little_loops/fsm/communication_adapter.py`
2. Add adapter registration to the extension system — create a new
   `CommunicationAdapterExtension` Protocol with `provided_adapters()` in
   `extension.py` (decided; see Decision Rationale)
3. Wire adapter discovery into `wire_extensions()` so the executor can
   resolve registered adapters
4. Update FSM executor in `executor.py` to resolve the configured adapter
   from config + registry and call protocol methods (never a direct import)
5. Add `hitl.channel` key to `.ll/ll-config.json` schema with `terminal`
   default
6. Add `ll-loop validate` warning when `hitl.channel` is unset on a
   non-interactive host
7. Write protocol contract tests with a mock adapter implementation,
   verifying the executor calls protocol methods not transport-specific code

## Impact

- **Priority**: P2 — prerequisite for FEAT-1794, FEAT-1931, and the EventBus adapter
- **Effort**: Small — abstract class, registration hook, config key
- **Risk**: Low — no user-facing change until adapters are implemented
- **Breaking Change**: No

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-25): Two conflicts with FEAT-1794 require resolution before implementing `communication_adapter.py`:

1. **Class name collision** — This issue's `API/Interface` defines a dataclass `HumanResponse` with `approved: bool, reason, modified_prompt`. FEAT-1794's `API/Interface` also defines `HumanResponse(LLEvent)` with `verdict: Literal["approve","reject","edit"], edited_text`. Importing both into `executor.py` will cause a name collision. Rename this issue's adapter return type to `AdapterResponse` (or `HumanApprovalDecision`) to avoid the collision; FEAT-1794's `HumanResponse(LLEvent)` event-bus type keeps its name.

2. **Binary vs. three-way verdict** — This issue's `HumanResponse` encodes only `approved: bool`, but FEAT-1794 requires three-way FSM routing (`on_yes`/`on_no`/`on_edit`). The protocol cannot unambiguously express an `edit` verdict via `approved: bool` alone. Add an explicit `verdict: Literal["approve", "reject", "edit"]` field to this issue's return dataclass (replacing `approved: bool`) so `await_response()` can return all three verdict types FEAT-1794's routing table requires.

---

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

**Reconfirmed 2026-09-03**: both open conflicts remain unresolved on both sides.
This issue's `## API/Interface` section still defines `HumanResponse` with
`approved: bool` (unrenamed). FEAT-1794's `## API/Interface`
(`.issues/features/P3-FEAT-1794-hitl-interrupt-fsm-state-type.md`) still
defines, verbatim and unchanged since this conflict was first logged:

```python
@dataclass
class HumanResponse(LLEvent):
    """Emitted when the operator responds to a human_approval request."""
    loop_name: str
    state_name: str
    verdict: Literal["approve", "reject", "edit"]
    edited_text: str | None  # populated for edit verdict
```

Neither issue has applied its half of the agreed resolution (rename this
issue's adapter dataclass to `AdapterResponse`/`HumanApprovalDecision`; add a
`verdict: Literal["approve", "reject", "edit"]` field in place of
`approved: bool`). No code exists yet for either type, so there is no
executor-level collision today — but the rename should land before FEAT-1931
or the EventBus adapter implement `await_response()` against this issue's
current `HumanResponse` shape.

## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

2026-06-18 (UNSTARTED): `scripts/little_loops/fsm/communication_adapter.py` does not exist. No `CommunicationAdapterExtension` in `extension.py`. No `hitl.channel` config key. FEAT-1794, FEAT-1931, FEAT-1932 remain correctly blocked on this issue. Dependency graph is accurate.

## Status

open

## Related Key Documentation

- `docs/ARCHITECTURE.md` — this protocol is a new abstraction layer inside the FSM loop engine (`human_approval` state, `executor.py` adapter resolution), which the architecture doc covers at the FSM-executor-design level.
- `docs/reference/API.md` — directly extends the documented `fsm/*` (executor) and `extension.py` module surfaces with a new `CommunicationAdapter` protocol and `CommunicationAdapterExtension`.
- `CONTRIBUTING.md` — adding a new extension-registered protocol (`CommunicationAdapterExtension`, `provided_adapters()`) is exactly the extension-authoring pattern (`LLExtension` protocol convention) this doc documents.

## Session Log
- `/ll:refine-issue` - 2026-09-03T18:25:58 - `08ecfe64-9510-40b1-a733-9cb70ecbc67a.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:08:30 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- backlog-grooming - 2026-07-03T00:00:00Z - Downgraded P2 -> P3 with parent EPIC-1929 (stalled since early June; epic downgraded rather than left distorting the P2 band).
- `/ll:audit-issue-conflicts` - 2026-06-25T21:24:01 - `91915c5b-d793-486c-a140-be4dd3d8ca1f.jsonl`
- `/ll:verify-issues` - 2026-06-25T00:51:21 - `3417b033-6605-44ca-9411-53f9fd585b45.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:14:14 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:decide-issue` - 2026-06-12T16:30:50 - `5f156fda-1001-478e-926c-73ffddf7e4b1.jsonl`
- `/ll:format-issue` - 2026-06-05T22:16:53 - `8041e61d-a9eb-4655-91d2-d32792836de3.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
