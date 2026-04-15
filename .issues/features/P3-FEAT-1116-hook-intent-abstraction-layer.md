---
id: FEAT-1116
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
related: [FEAT-959, FEAT-960, FEAT-961, FEAT-962, FEAT-957, FEAT-992, FEAT-1117]
confidence_score: 78
outcome_confidence: 48
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
---

# FEAT-1116: Hook-Intent Abstraction Layer for Multi-Host Support

## Summary

Define little-loops hooks in terms of *intents* (PreToolUse, PostToolUse, PreCompact, SessionStart) with a small set of per-host adapters, instead of per-host reimplementations of every hook script. This reshapes the in-flight OpenCode work (FEAT-959/960/961/962) and unblocks Codex (FEAT-957) and Pi (FEAT-992) compatibility.

## Motivation

Current OpenCode migration issues (FEAT-959/960/961/962) take the "abstract paths, then port each shell hook to TS plugin" approach. That scales linearly with (hosts × hooks). Adding Codex and Pi multiplies the work.

Context-mode (github.com/mksglu/context-mode) supports 12 host agents (Claude Code, Gemini CLI, Cursor, Copilot, OpenCode, Codex, Kiro, Zed, Pi, etc.) by defining hook logic once as intent handlers and shipping thin per-host adapters: shell commands for Claude Code / Gemini CLI, TS plugins for OpenCode, native gateway plugins for OpenClaw, etc. This is exactly the multiplier little-loops needs as it fans out beyond Claude Code.

## Current Behavior

- All hooks are shell scripts under `hooks/scripts/` wired via `hooks/hooks.json` (Claude-Code-specific format)
- FEAT-960 proposes porting each shell hook to accept `${LL_STATE_DIR}` — a path fix, not an interface change
- FEAT-961 proposes a parallel JS/TS plugin for OpenCode — a second copy of the logic
- No shared contract; adding Codex would mean a third copy

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **8 shell hooks** live under `hooks/scripts/`: `session-start.sh`, `session-cleanup.sh`, `user-prompt-check.sh`, `check-duplicate-issue-id.sh`, `context-monitor.sh`, `issue-completion-log.sh`, `precompact-state.sh`, plus shared `lib/common.sh`
- **Claude Code hook protocol** (`hooks/hooks.json:4-91`): scripts `cat` a JSON blob from stdin (e.g. `context-monitor.sh:17`); respond via exit code (`0` pass, `2` + stderr injects feedback into context) or structured stdout JSON for `PreToolUse` permission decisions (`check-duplicate-issue-id.sh:18`)
- **Python hook infrastructure does not yet exist** — no `scripts/little_loops/hooks/` directory. The shell hook layer and the Python extension layer (`events.py` / `extension.py`) are entirely disconnected today. FEAT-1116 sits in exactly that gap.
- **`LLEvent` (`scripts/little_loops/events.py:28-65`) is a ready-made model** for `LLHookEvent`: `@dataclass` with `type: str`, `timestamp: str`, `payload: dict`, plus `to_dict()` / `from_dict()` / `from_raw_event()` — the `from_raw_event` helper is already how `wire_extensions()` converts dicts to typed events
- **`LLExtension` Protocol (`scripts/little_loops/extension.py:35-98`) is the adapter-pattern precedent** — `@runtime_checkable` Protocol for core surface (`on_event`), optional methods detected via `hasattr()` (`InterceptorExtension` at line 59). Intent handlers should reuse this pattern rather than invent a new one.
- **`ExtensionLoader.from_config` (`extension.py:123`) already supports dotted `"module:Class"` registration** and `importlib.metadata` entry points under group `"little_loops.extensions"` — intent handlers can plug into the same discovery path
- **Test pattern** (`scripts/tests/test_hooks_integration.py`): one test class per hook, subprocess-invokes the shell script with JSON stdin and asserts on returncode/stderr. Python-direct handler tests don't exist yet — add them alongside the subprocess tests

## Expected Behavior

- New `hooks/core/` directory contains host-agnostic intent handlers (Python modules under `scripts/little_loops/hooks/`):
  - `pre_tool_use.py`, `post_tool_use.py`, `pre_compact.py`, `session_start.py`, `session_end.py`
  - Each exports a pure function: `(event: LLHookEvent) -> LLHookResult`
- Per-host adapters are thin shells that:
  1. Parse the host's event format into `LLHookEvent`
  2. Invoke the core handler (via `python -m little_loops.hooks.<intent>` or in-process for TS hosts)
  3. Translate `LLHookResult` back to the host's expected response
- Adapters live under `hooks/adapters/{claude-code,opencode,codex,pi}/`
- `hooks/hooks.json` generated from a single source of truth per host
- Extension authors write intent handlers once; they work on every supported host

## Acceptance Criteria

- `LLHookEvent` / `LLHookResult` dataclasses in `scripts/little_loops/hooks/types.py`
- At least 2 intents migrated (SessionStart, PreCompact) with Claude Code + OpenCode adapters
- FEAT-960 shell-path-abstraction work continues for legacy scripts but new hooks go through the abstraction
- FEAT-961 OpenCode plugin is rewritten as an adapter, not a reimplementation
- Developer docs: "How to write a little-loops hook" covers the intent model
- Extension registry (FEAT-917) surfaces intent-based hook contributions

## Integration Map

### Files to Modify

- `hooks/hooks.json` — currently hand-written Claude Code event config (events: `SessionStart`, `UserPromptSubmit`, `PreToolUse` matcher `Write|Edit`, `PostToolUse` `*` + `Bash`, `Stop`, `PreCompact`); will become generated output or thin adapter wire-up
- `hooks/scripts/session-start.sh` — candidate for first migration; loads config, deep-merges `ll.local.md`, validates feature flags
- `hooks/scripts/precompact-state.sh` — candidate for first migration; snapshots state to `.ll/ll-precompact-state.json`
- `hooks/scripts/lib/common.sh` — shared shell utilities (`acquire_lock`, `atomic_write_json`, `ll_resolve_config`, `ll_feature_enabled`); behavior must be ported to Python core or invoked from adapter
- `scripts/little_loops/events.py:28-65` — existing `LLEvent` dataclass (`type`, `timestamp`, `payload`) is the model for `LLHookEvent`; consider whether to extend or add a sibling type
- `scripts/little_loops/extension.py:35-98` — existing `LLExtension` / `InterceptorExtension` Protocols are the model for intent handler registration

### New Files to Create

- `scripts/little_loops/hooks/__init__.py`
- `scripts/little_loops/hooks/types.py` — `LLHookEvent`, `LLHookResult` dataclasses
- `scripts/little_loops/hooks/pre_tool_use.py`, `post_tool_use.py`, `pre_compact.py`, `session_start.py`, `session_end.py`, `user_prompt_submit.py`
- `scripts/little_loops/hooks/__main__.py` — dispatch `python -m little_loops.hooks <intent>` (delegating pattern per `scripts/little_loops/cli/loop/__main__.py:1-6`)
- `hooks/adapters/claude-code/` — thin bash or Python wrappers that cat stdin → `python -m little_loops.hooks <intent>` → translate result to exit code + JSON stdout
- `hooks/adapters/opencode/` — TS plugin adapter (replaces FEAT-961's parallel reimplementation)
- `hooks/adapters/codex/`, `hooks/adapters/pi/` — stubs for FEAT-957 / FEAT-992

### Dependent Files (Callers / Importers)

- `scripts/little_loops/extension.py:188-258` — `wire_extensions()` already bridges dict → `LLEvent`; new hook layer should follow the same wrapping convention to stay consistent
- `scripts/little_loops/fsm/executor.py` — referenced by hook-adjacent Python code; verify no event-type collision with FSM events
- `scripts/little_loops/cli/create_extension.py:40-56` — scaffolds `[project.entry-points."little_loops.extensions"]`; intent-handler extensions may reuse this entry-point group or add a new `little_loops.hook_intents` group

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — re-exports `LLEvent`, `LLExtension`, `wire_extensions`, etc. in `__all__`; if `LLHookEvent`/`LLHookResult` are intended as public API, this file must be updated with new imports and `__all__` entries
- `scripts/little_loops/testing.py` — imports `EventBus`, `LLEvent`; `TYPE_CHECKING` import of `LLExtension`; stable unless `LLEvent` signature changes
- `scripts/little_loops/cli/loop/lifecycle.py:257` — calls `wire_extensions(executor.event_bus, config.extensions, executor=executor)`
- `scripts/little_loops/cli/loop/run.py:222` — calls `wire_extensions(executor.event_bus, _config.extensions, executor=executor)`
- `scripts/little_loops/cli/sprint/run.py:399-400` — calls `wire_extensions(event_bus, config.extensions)`
- `scripts/little_loops/cli/parallel.py:222-226` — calls `wire_extensions(event_bus, config.extensions)`
- `scripts/little_loops/extensions/reference_interceptor.py` — implements `InterceptorExtension` from `extension.py`; stable unless the Protocol changes
- `hooks/scripts/user-prompt-check.sh` — sources `lib/common.sh`; calls `ll_resolve_config`, `ll_feature_enabled`; affected if `lib/common.sh` is ported to Python
- `hooks/scripts/check-duplicate-issue-id.sh` — sources `lib/common.sh`; calls `ll_resolve_config`, `acquire_lock`; affected if `lib/common.sh` is ported to Python
- `hooks/scripts/context-monitor.sh` — sources `lib/common.sh`; calls `ll_resolve_config`, `ll_feature_enabled`, `atomic_write_json`, `acquire_lock`; affected if `lib/common.sh` is ported to Python
- `hooks/scripts/issue-completion-log.sh` — sources `lib/common.sh`; affected if `lib/common.sh` is ported to Python

### Similar Patterns to Follow

- **Dataclass style**: `scripts/little_loops/events.py:28-65` (`LLEvent`) and `scripts/little_loops/fsm/types.py:16-54` (`ExecutionResult`, `ActionResult`) — use `@dataclass`, `from __future__ import annotations`, `to_dict()` that skips `None` optionals, classmethod `from_dict()`
- **Protocol-based host abstraction**: `scripts/little_loops/extension.py:35-98` — `@runtime_checkable` Protocol for required surface (`on_event`), `hasattr()` detection for optional methods (`InterceptorExtension`, `ActionProviderExtension`)
- **Module CLI entry**: delegating `__main__.py` at `scripts/little_loops/cli/loop/__main__.py:1-6` — `main() -> int` + `raise SystemExit(main())`
- **Config-driven registration**: `ExtensionLoader.from_config` at `extension.py:123` — `"module.path:ClassName"` string format

### Tests

- `scripts/tests/test_hooks_integration.py` — existing pattern: test class per hook, fixture resolves `hooks/scripts/<name>.sh`, `subprocess.run([script], input=json.dumps(input_data), capture_output=True, text=True, timeout=6)`, asserts `result.returncode` + `result.stderr/stdout`
- New tests should exercise the Python core handlers directly (no subprocess), plus an adapter round-trip test that still goes through the bash adapter for Claude Code parity

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break when shell scripts migrate to adapters — update required:**
- `scripts/tests/test_hooks_integration.py:1318-1465` (`TestSessionStartValidation`) — asserts exact stderr strings from `session-start.sh` (e.g., `"sync.enabled is true but sync.github is not configured"`); fixtures point to `hooks/scripts/session-start.sh`; update fixture path to `hooks/adapters/claude-code/session-start.sh` or add a parallel adapter test class
- `scripts/tests/test_hooks_integration.py:1468-1542` (`TestPrecompactState`) — asserts `returncode == 2` and JSON state from `precompact-state.sh`; fixture points to `hooks/scripts/precompact-state.sh`; same update needed
- `scripts/tests/test_hooks_integration.py:1192-1316` (`TestSharedConfigFunctions`) — bash-sources `lib/common.sh` directly at line 1198 and asserts on stdout/exit codes; **breaks entirely if `lib/common.sh` functions are ported to Python**; requires a new Python-direct test class to replace this

**Existing tests that are stable but whose patterns to follow for new tests:**
- `scripts/tests/test_events.py:27-75` — `LLEvent` dataclass round-trip pattern (`to_dict`/`from_dict`/`roundtrip`/`from_dict_missing_fields`); follow this exactly for `LLHookEvent` and `LLHookResult` in the new `test_hook_intents.py`
- `scripts/tests/test_extension.py:19-50` — Protocol-satisfaction structural test pattern; follow for any new Protocol types in `hooks/types.py`
- `scripts/tests/test_extension.py:87-132` — `ExtensionLoader.from_config("module:ClassName")` test pattern; follow if `LLHookIntent` handlers use the same discovery path
- `scripts/tests/test_extension.py:465-543` (`TestNewProtocols`) — smoke-import pattern (`from little_loops import X; assert X is not None`); add analogues for `LLHookEvent`, `LLHookResult`, any new Protocol
- `scripts/tests/test_create_extension.py:14-58` — `patch("sys.argv", [...])` + `main_fn()` pattern for `__main__.py` dispatch; follow for `scripts/little_loops/hooks/__main__.py` tests

**New adapter round-trip tests to add to `test_hooks_integration.py`:**
- `TestClaudeCodePrecompactAdapter` — same subprocess pattern as `TestPrecompactState`, fixture pointing to `hooks/adapters/claude-code/precompact.sh`
- `TestClaudeCodeSessionStartAdapter` — same subprocess pattern as `TestSessionStartValidation`, fixture pointing to `hooks/adapters/claude-code/session-start.sh`

### Documentation

- `docs/claude-code/hooks-reference.md` — needs a section on the intent model
- `docs/claude-code/automate-workflows-with-hooks.md` — needs adapter flow diagram
- New: "How to write a little-loops hook" guide (called out in Acceptance Criteria)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:84-95` — `hooks/scripts/` directory tree is listed by name; new `hooks/adapters/` and `hooks/core/` directories need to be added; Extension Architecture section (lines 454-512) documents `LLExtension`, `InterceptorExtension`, `wire_extensions()` — update if new Protocol classes are introduced; line 969 names `hooks/scripts/issue-completion-log.sh` by exact path
- `docs/development/TROUBLESHOOTING.md:750-941` — **highest-density stale-path risk**: lists `chmod +x` instructions (line 750-753) and manual test invocations (lines 835-941) for `context-monitor.sh`, `user-prompt-check.sh`, `precompact-state.sh`, `check-duplicate-issue-id.sh` by exact `hooks/scripts/` paths; paths become stale when first two migrate to `hooks/adapters/claude-code/`
- `docs/reference/CONFIGURATION.md:617` — documents `extensions` config key and `LLExtension` protocol; add `little_loops.hook_intents` entry-point group description if a separate group is introduced
- `docs/reference/API.md:36-37` — Module Overview table does not have a `little_loops.hooks` row; Extension API section (lines 5163-5339) documents `LLExtension`, `ExtensionLoader`, `wire_extensions()` — if new public protocols are added, this section needs new entries
- `docs/reference/EVENT-SCHEMA.md` — describes the `LLEvent` wrapping convention that the intent layer reuses; cross-link the new `LLHookEvent` type once it exists
- `docs/development/TESTING.md:774-781` — `hook_script: Path` fixture pattern documented; update to show both legacy shell and adapter fixture variants once adapters exist

### Configuration

- `.ll/ll-config.json` — may need a `hooks.host` field so adapters know which host they're running under; today the shell hooks detect Claude Code implicitly

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — **no `hooks` section exists today**; the root object uses `additionalProperties: false`-style strictness, so adding `hooks.host` to `ll-config.json` without adding a `"hooks"` property block to the schema will cause validation failures; must add a `"hooks"` property block before any `hooks.*` config key is used
- `scripts/pyproject.toml:67-69` — defines `[project.entry-points."little_loops.extensions"]` (currently empty); if a separate `little_loops.hook_intents` entry-point group is introduced for intent handler discovery, a new `[project.entry-points."little_loops.hook_intents"]` section must be added here
- `templates/extension/extension.py.tmpl` — imports `LLEvent` from `little_loops` and implements `on_event(self, event: LLEvent)`; if intent handlers use `LLHookEvent` instead, this template diverges and `ll-create-extension` would scaffold incorrect code for hook intent authors
- `templates/extension/pyproject.toml.tmpl` — registers `little_loops.extensions` entry-point group; needs a flag or second code path if intent handlers use `little_loops.hook_intents`

## Design Decisions

_Locked in during `/ll:confidence-check` review on 2026-04-15. These resolve the open architectural forks flagged in the Confidence Check Notes below._

### Decision 1: `LLHookEvent` is a sibling type, not an extension of `LLEvent`

**Decision**: Define `LLHookEvent` and `LLHookResult` as fresh `@dataclass` types in `scripts/little_loops/hooks/types.py`, following the *style* of `LLEvent` (`events.py:28-65`) but not inheriting from it.

**Rationale**: `LLEvent` is pub/sub — fire-and-forget notifications through `EventBus` with no return value. Hook intents are request/response — the host blocks on an `LLHookResult` that decides permit/deny/inject-feedback. Shoving request/response semantics into a pub/sub type forces `wire_extensions()` to learn a "collect the result back" side channel, which is contract drift. Different lifecycles → different types.

**Consequences**:
- Slight dataclass boilerplate duplication (both types re-implement `to_dict`/`from_dict`/`from_raw_event` in the same style)
- `EVENT-SCHEMA.md` must cross-link the two types so readers understand the relationship
- Hook handlers can evolve independently of FSM/extension event shape

### Decision 2: Reuse the `little_loops.extensions` entry-point group; add `LLHookIntentExtension` as an optional Protocol

**Decision**: Do not introduce a second entry-point group. Add `LLHookIntentExtension` as a new `@runtime_checkable` Protocol alongside `InterceptorExtension` and `ActionProviderExtension` in `scripts/little_loops/extension.py`, detected via `hasattr()` inside `wire_extensions()`.

**Rationale**: The codebase already handles optional extension capabilities through the "one discovery path, multiple optional Protocols" pattern (`extension.py:35-98`). Hook intents fit that precedent cleanly. Introducing `little_loops.hook_intents` as a second EP group would force branching in `pyproject.toml.tmpl`, `create_extension.py`, `ExtensionLoader`, and `config-schema.json` — real churn for a speculative benefit that no current host demands.

**Consequences**:
- The base extension surface grows one more optional Protocol (documentation burden)
- An extension class can mix FSM event handling and hook intents in a single module — authors should be guided toward one or the other for clarity
- `ll-create-extension` scaffolding stays unchanged for now
- **Deferred**: FEAT-1117 tracks revisiting this decision when/if a host-specific driver demands discovery-time separation (e.g., a hook-only host or an extension registry that needs to surface hook-intent contributors independently)

### Decision 3: OpenCode adapter ships as shell-out first; in-process sidecar is a measured follow-up

**Decision**: The OpenCode TS plugin adapter invokes `python -m little_loops.hooks <intent>` per hook call. No FFI, no persistent sidecar in the MVP.

**Rationale**: Shell-out works identically across every host, has no new failure modes, and is reversible. The acceptance criteria scope the MVP to `SessionStart` and `PreCompact` — both low-frequency intents where ~100–200ms Python cold-start is invisible. The hot-path concern (PreToolUse/PostToolUse firing on every tool call) is real but not in the MVP's critical path, and should be resolved by measurement, not guessing. A persistent sidecar (not FFI) is the preferred optimization path if measurement shows it's needed — sidecar is reversible, FFI is not.

**Consequences**:
- OpenCode adapter is shippable this cycle
- PreToolUse/PostToolUse adapter work should include latency measurement as an explicit deliverable before they land, so the sidecar decision is data-driven
- A follow-up issue should be opened to track sidecar optimization if measurements justify it (not pre-emptively filed)

## Implementation Steps

1. **Define types** — Add `scripts/little_loops/hooks/types.py` with `LLHookEvent` and `LLHookResult` as **sibling** dataclasses to `LLEvent` (Decision 1), following the `LLEvent` style at `events.py:28-65` but not inheriting. Include a `host: str` field on `LLHookEvent` so core handlers can branch on host quirks when unavoidable. Add a cross-link to `LLEvent` in `docs/reference/EVENT-SCHEMA.md`.
2. **Port one intent end-to-end** — Start with `precompact-state.sh` → `scripts/little_loops/hooks/pre_compact.py`. It is the smallest self-contained hook and has no shell-only dependencies on `lib/common.sh` beyond `atomic_write_json`.
3. **Port `lib/common.sh` primitives** — Move `atomic_write_json`, `acquire_lock`, `ll_resolve_config`, `ll_feature_enabled` into a Python module (e.g. `scripts/little_loops/hooks/common.py`) so core handlers are not shell-dependent.
4. **Build Claude Code adapter** — `hooks/adapters/claude-code/precompact.sh` = 3-line wrapper: `INPUT=$(cat); echo "$INPUT" | python -m little_loops.hooks pre_compact; exit $?`. Update `hooks/hooks.json` to point `PreCompact` at the adapter instead of the legacy script.
5. **Port `session_start`** — second intent; exercises deep-merge of `ll.local.md` which is the most complex shell logic.
6. **Write an OpenCode adapter** — TS plugin that shells out to `python -m little_loops.hooks <intent>` per Decision 3 (no FFI, no sidecar in MVP). This replaces FEAT-961's parallel reimplementation; coordinate with that issue before executing. When extending beyond `SessionStart`/`PreCompact` to hot-path intents (`PreToolUse`/`PostToolUse`), include latency measurement as an explicit deliverable so any sidecar follow-up is data-driven.
7. **Tests** — add `scripts/tests/test_hook_intents.py` that imports core handlers directly and asserts on `LLHookResult` fields; keep `test_hooks_integration.py` running against the Claude Code adapter for regression coverage.
8. **Docs** — write "How to write a little-loops hook" under `docs/claude-code/`, cross-link from `hooks-reference.md`.
9. **Extension registry wiring (FEAT-917)** — per Decision 2, reuse the `little_loops.extensions` entry-point group and add `LLHookIntentExtension` as a new optional `@runtime_checkable` Protocol in `scripts/little_loops/extension.py` alongside `InterceptorExtension` / `ActionProviderExtension`. `wire_extensions()` detects hook intent handlers via `hasattr()` following the existing pattern. No changes to `ll-create-extension` scaffolding or `pyproject.toml` entry-point sections. FEAT-1117 tracks a possible future second EP group if a host-specific driver demands discovery-time separation.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Decide `LLHookEvent`/`LLHookResult` public API surface** — determine if these types belong in `scripts/little_loops/__init__.py` exports; if yes, add imports and `__all__` entries alongside `LLEvent`
11. **Update `config-schema.json`** — add a `"hooks"` property block (with `host: string`) before any `hooks.*` key is used in `ll-config.json`; the root schema uses `additionalProperties: false`-equivalent strictness
12. **`scripts/pyproject.toml` — no changes required** — per Decision 2, hook intent handlers are discovered through the existing `[project.entry-points."little_loops.extensions"]` group. Skip this step unless FEAT-1117 reopens the EP group split.
13. **Migrate `TestSharedConfigFunctions`** — when `lib/common.sh` is ported to Python (`common.py`), this test class (lines 1192-1316 in `test_hooks_integration.py`) bash-sources the shell file directly and will break entirely; replace with a Python-direct test class for `common.py`
14. **Update adapter fixture paths in `test_hooks_integration.py`** — when `session-start.sh` and `precompact-state.sh` move to `hooks/adapters/claude-code/`, update `TestSessionStartValidation` and `TestPrecompactState` fixture paths (or add parallel `TestClaudeCodeSessionStartAdapter` / `TestClaudeCodePrecompactAdapter` classes and retire the legacy fixtures)
15. **`templates/extension/` — no changes required** — per Decision 2, intent handlers use the same EP group and share `LLExtension` as a base. `extension.py.tmpl` continues to import `LLEvent` for the base `on_event` surface; authors who want to contribute hook intents add `LLHookIntentExtension` methods alongside. No scaffolding divergence. Skip unless FEAT-1117 reopens the split.

### Verification

- `python -m pytest scripts/tests/test_hook_intents.py scripts/tests/test_hooks_integration.py -v`
- `python -m mypy scripts/little_loops/hooks/`
- `ruff check scripts/little_loops/hooks/`
- Manual: trigger a Claude Code PreCompact event and confirm `.ll/ll-precompact-state.json` is still written

## Dependencies & Impact

- **Reshapes**: FEAT-959, FEAT-960, FEAT-961, FEAT-962 — recommend re-reading these against this plan before executing
- **Unblocks**: FEAT-957 (Codex), FEAT-992 (Pi) — additional host support becomes adapter-only
- **Related**: FEAT-917 extension registry (intent-based contributions); FEAT-1117 deferred decision revisit on splitting the entry-point group for hook intents

## References

- Inspiration: context-mode platform-agnostic hook design across 12 host agents
- Recommended next step: `/ll:iterate-plan FEAT-1116` to validate the boundary between core handlers and adapters before touching the OpenCode work


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-15_

**Readiness Score**: 78/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 48/100 → LOW

### Concerns
- FEAT-959/960/961/962 are all still active and need reshaping coordination before this issue proceeds; no gate prevents them from merging independently and conflicting
- `lib/common.sh` porting (Step 3) breaks `TestSharedConfigFunctions` and all 4 scripts that source it — higher blast radius than the implementation plan implies

### Outcome Risk Factors
- Staged migration boundary is ambiguous: ACs say "at least 2 intents" but Step 3 includes full `lib/common.sh` port; if scope expands mid-implementation the work balloons significantly
- OpenCode adapter timing is uncontrolled: if FEAT-961 merges as a parallel reimplementation before this lands, the adapter approach arrives too late to replace it

### Resolved Design Decisions
The three architectural forks originally flagged have been decided and are now documented in the `## Design Decisions` section above:
1. `LLHookEvent`/`LLHookResult` are sibling types to `LLEvent`, not subclasses
2. Reuse `little_loops.extensions` EP group with a new `LLHookIntentExtension` optional Protocol; FEAT-1117 tracks a future split if needed
3. OpenCode adapter ships shell-out first; sidecar is a measured follow-up

## Session Log
- `/ll:refine-issue` - 2026-04-15T22:47:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42380a24-4141-40a0-985b-e93647a4e8dc.jsonl`
- `/ll:wire-issue` - 2026-04-15T23:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42380a24-4141-40a0-985b-e93647a4e8dc.jsonl`
- `/ll:confidence-check` - 2026-04-15T23:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42380a24-4141-40a0-985b-e93647a4e8dc.jsonl`
