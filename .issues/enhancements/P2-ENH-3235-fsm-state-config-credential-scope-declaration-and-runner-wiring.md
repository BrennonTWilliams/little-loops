---
id: ENH-3235
type: ENH
title: FSM StateConfig credential scope declaration and fsm/runners.py wiring
priority: P2
status: done
parent: ENH-3203
epic: EPIC-3212
blocked_by:
- ENH-3395
- ENH-3396
discovered_by: /ll:issue-size-review
discovered_date: '2026-08-17'
completed_at: '2026-09-07T21:27:50Z'
testable: true
decision_needed: false
reconcile_attempted: true
verify_verdict: VALID
relates_to:
- ENH-3184
size: Very Large
confidence_score: 98
outcome_confidence: 76
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 17
score_change_surface: 20
---

# ENH-3235: FSM StateConfig credential scope declaration and fsm/runners.py wiring

## Summary

Add a per-state scope-declaration field to loop YAML (`StateConfig`), following the existing
`tools:` allowlist precedent, and wire it into `DefaultActionRunner`'s shell branch
(`fsm/runners.py:297`) — the primary FSM-loop consumer — so a declaring state is denied every
undeclared credential variable using the deny-capable `project_child_env()`/
`HostInvocation.env_allow` chokepoint landed in ENH-3233.

## Parent Issue

Decomposed from ENH-3203: Declare and enforce per-task credential scope via deny-by-default env
projection. This child covers the FSM `StateConfig`/loop-YAML declaration surface only; the
`ActionSpec` surface is ENH-3234. Both converge on the shared chokepoint from ENH-3233, which
this issue depends on.

**Why a separate surface from ActionSpec, not a shared one**: see ENH-3234's Parent Issue section
— the two `bash -c` call sites share no common per-task object today, and unifying them is
explicitly out of scope for ENH-3203.

## Current Behavior

`fsm/runners.py`'s `DefaultActionRunner` shell branch (`fsm/runners.py:297-305`) builds
`cmd = ["bash", "-c", action]` and calls
`subprocess.Popen(cmd, ..., env=project_child_env(extra={"LL_PYTHON": sys.executable}))` — it
already passes an `extra` kwarg to inject `LL_PYTHON`, but no `env_allow`/deny-list argument;
no `HostInvocation`, no scope, full inherit otherwise.

The `tools:` per-state allowlist (`fsm-loop-schema.json:590-596`, `StateConfig.tools: list[str] |
None = None`, `schema.py:686`) is the closest existing per-state declaration precedent: it flows
into `build_streaming(tools=...)` at `fsm/executor.py:2284`, only for prompt-mode states. Runners
that honor it read the flag directly (`ClaudeCodeRunner.build_streaming`, `host_runner.py:358-359`;
`OmpRunner`, `host_runner.py:1246-1247`); runners that decline it warn-and-drop via
`CapabilityNotSupported` (`CodexRunner`, `host_runner.py:645-654`; same shape in
`QwenRunner:1624-1627`, `KimiRunner:1411-1415`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Confirmed hard blocker still in force: `project_child_env()` (`host_runner.py:1865-1895`) has
  only its ENH-3184 signature (`invocation`, `extra`) today; `HostInvocation`
  (`host_runner.py:156-173`) has exactly its original 5 fields. A repo-wide grep for `env_allow`
  returns zero hits under `scripts/` — ENH-3233 (`status: open`) does not yet provide the
  `env_allow` kwarg this issue's AC7.1 requires, so `blocked_by: [ENH-3233]` remains a currently
  true, mandatory block, not stale bookkeeping.
- Several line citations in this issue have drifted since the 2026-09-03 Verification Notes pass:
  `StateConfig.tools` is now at `fsm/schema.py:727` (not 686), its `to_dict()` guard is at
  `schema.py:830-831` (not 721), its `from_dict()` line is at `schema.py:952` (not 911),
  `TestAgentToolsStateConfig` is at `test_fsm_schema.py:2536` (not 2502), `MockActionRunner` in
  `test_fsm_persistence.py` is at line 825 (not 766), and in `test_fsm_executor.py` at line 41
  (not 37). `fsm-loop-schema.json`'s `tools:` block is at lines 582-598 (was cited 590-596).
- The `tools:` field's `build_streaming()` wiring is not reached by `DefaultActionRunner`'s shell
  branch under any condition: `fsm/executor.py:2495-2505` passes `tools=state.tools if
  action_mode == "prompt" else None` — the shell branch always receives `tools=None` regardless of
  `state.tools`'s value, confirming there is no existing partial reach into the shell branch to
  build on.

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **Blocker status corrected (2026-09-07):** `ENH-3233`/`ENH-3395`/`ENH-3396` are all
  `status: done` — this issue is UNBLOCKED. `project_child_env()` (`host_runner.py:2027-2032`)
  now takes an explicit `env_allow: frozenset[str] | None = None` kwarg; `HostInvocation`
  (`host_runner.py:234-259`) now has a 6th field, `env_allow: frozenset[str] | None = None`; the
  credential-scope registry `CREDENTIAL_SCOPES` (`host_runner.py:124-163`) and fail-loud
  `resolve_scopes()` (`host_runner.py:166-183`) both exist. The repo-wide-zero-hits claim for
  `env_allow` in this issue's earlier Codebase Research Findings no longer holds.
- **Sibling surface (ENH-3234) is fully landed:** `runner_spec.py::ActionSpec.scopes:
  frozenset[str] | None = None` (`runner_spec.py:85-100`) and `_run_cmd()` (`runner_spec.py:237-261`)
  resolve `spec.scopes` via `resolve_scopes()` into `env_allow` when not `None`, catching
  `ValueError` locally and returning it as a failed `RunnerResult` (`exit_code=2`) rather than
  raising — confirmed by `test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing`
  (`test_runner_spec.py:237-253`). `project_child_env()`'s own docstring (`host_runner.py:2053-2058`)
  names both `fsm/runners.py`'s `DefaultActionRunner` shell branch and `runner_spec.py::_run_cmd()`
  as the two `bash -c` task-path spawns this kwarg exists for.
- **This issue's own deliverable remains fully unimplemented**, confirmed by targeted greps
  returning zero hits: `StateConfig` (`fsm/schema.py:621-760`) has no `scopes` field;
  `fsm/runners.py:305`'s shell branch still calls
  `project_child_env(extra={"LL_PYTHON": sys.executable})` with no `env_allow`;
  `fsm/validation/structural_rules.py` has no per-state `scopes` rule (AC9/AC10 unimplemented —
  only the unrelated loop-level singular `scope:` rule at lines 1358-1380 exists);
  `fsm/executor.py:2563-2573`'s dispatch call site passes no `scopes=`; `CREDENTIAL_SCOPES`/
  `resolve_scopes` are imported nowhere under `fsm/`.

## Expected Behavior

- Loop YAML gains a per-state scope-declaration field (schema: `fsm-loop-schema.json`;
  dataclass: `StateConfig`, `schema.py`), resolved against ENH-3233's capability registry.
- `fsm/runners.py`'s `DefaultActionRunner` shell branch resolves the declared scopes into an
  `env_allow` set and passes it via the explicit kwarg ENH-3233 provides for invocation-less
  call sites — `project_child_env(extra={"LL_PYTHON": sys.executable}, env_allow=...)` — so
  everything not declared is denied, alongside the existing `LL_PYTHON` injection. No synthetic
  `HostInvocation` is constructed.
- States with no declaration keep today's coarse (full-inherit) behavior — opt-in per state,
  matching ENH-3233's `env_allow=None` no-op default.
- **Field name pinned (2026-09-04): `scopes`.** Same name as ENH-3234's `ActionSpec.scopes` and
  the column ENH-3204 records, so all three surfaces agree. YAML: `scopes: [github]`.
- **Fail at validate/load time, not mid-run.** An unknown scope name must be rejected by
  `ll-loop validate` (a new structural rule in `fsm/validation/structural_rules.py`, resolving
  each state's `scopes` against ENH-3233's registry) and by FSM load in
  `StateConfig.from_dict()`/`FSMConfig` validation, so a typo surfaces before the loop starts —
  not as a `ValueError` inside the shell branch after N states have already run and mutated the
  tree. The run-time resolution in the shell branch stays as the last line of defence, but is
  never the *first* place a bad name is caught.
- `fsm-loop-schema.json` gains a `scopes` property on the state object (array of strings,
  not required), adjacent to the `tools` block at lines 590-596, so schema-driven tooling and docs see
  the field even though the state object tolerates unknown keys today.
- **`scopes:` on a non-shell state is a validate-time ERROR (added 2026-09-06).** The shell
  branch is this issue's only consumer; a loop author who writes `scopes: [github]` on a
  `/ll:manage-issue` (prompt-mode) state would otherwise get full inherit with no signal — the
  "looks like protection that isn't there" failure the parent warns about, on the branch where a
  broad env matters most (an agent running arbitrary Bash). A second structural rule therefore
  rejects `scopes` on any state whose mode is not `shell` per `FSMExecutor._action_mode()`
  (`fsm/executor.py:3325-3346`): `action_type` in `prompt`/`slash_command`/`mcp_tool`/
  `contract`/`human_approval`, a contributed `action_type`, or no `action_type` with a
  `/`-prefixed action. Message: "state '<name>' declares 'scopes' but is not a shell action;
  scopes are enforced only for shell actions (prompt-mode enforcement: see follow-on)". Lift the
  rule to a WARNING once prompt-mode enforcement lands. Prompt-mode enforcement itself is a
  follow-on, not this issue: the seam is `run_claude_command()`'s existing
  `project_child_env(invocation, extra=extra_env)` call (`subprocess_utils.py:529`) — add an
  `env_allow` kwarg there and pass `state.scopes` through `DefaultActionRunner.run()`'s prompt
  branch. File it when this issue lands.

## Proposed Solution

Follow the `tools:` per-state precedent structurally (array field, not required, in the schema; mirror
in the dataclass), but note the wiring gap the parent issue's research already surfaced: the
`tools:` field's existing wiring only reaches prompt-mode states via `build_streaming()`
(`fsm/executor.py:2284`) — the shell branch (`fsm/runners.py:297-305`) reads none of
`tools`/`agent`/`model`/`automation_profile` today. This issue must wire the new scope field into
the shell branch directly (not by reusing the `tools:` flow), since AC7.1 is specifically about
`DefaultActionRunner`'s `bash -c` path, which the `tools:` precedent does not already reach.

### Call Path
`StateConfig` (scope declared) → `fsm/runners.py::DefaultActionRunner` shell branch resolves
scopes → `env_allow` set → `project_child_env(env_allow=...)` (ENH-3233's kwarg; no
`HostInvocation` at this call site) → `subprocess.*`

### Round-trip
A new per-state field needs a symmetric `StateConfig.to_dict()` line (`fsm/schema.py:721`)
alongside whatever `from_dict()` addition lands, mirroring the existing `tools=data.get("tools")`
precedent at `fsm/schema.py:911` — otherwise the field silently fails to round-trip through
anything that serializes a `StateConfig` back to dict (loop export, `ll-loop show`, YAML
round-trip tests).

## Acceptance Criteria

- **AC1 (StateConfig half).** A loop-YAML state can declare the capability set its `bash -c`
  action requires.
- **AC7.1.** `fsm/runners.py:297` (`DefaultActionRunner` shell branch) — the FSM-loop path, the
  primary consumer — is covered by the same projection as the host-CLI paths, with a test proving
  an undeclared credential variable is absent from the shell action's environment. Mandatory:
  covering only the `ActionSpec` path (ENH-3234) leaves FSM loops unscoped.
- **AC5 (this surface).** States without a declaration keep working with today's coarse behavior —
  no regression to any existing loop YAML in `loops/*.yaml`.
- **AC9.** `ll-loop validate` reports an ERROR for a state whose `scopes` names a scope absent
  from ENH-3233's registry; the loop never starts. Test: a fixture YAML with `scopes: [githb]`
  fails validation with a message naming `githb`.
- **AC10.** `ll-loop validate` reports an ERROR for a state that declares `scopes` but is not a
  shell action. Tests: `scopes: [github]` on (a) an `action: /ll:manage-issue` state with no
  `action_type`, (b) an `action_type: prompt` state, (c) an `action_type: mcp_tool` state — each
  fails naming the state; (d) `scopes: [github]` on an `action_type: shell` state and on a
  bare non-`/` action pass this rule. Neither AC9's nor AC10's message may contain the substring
  `no 'scope:'` (see Message-collision risk below).

## Program Design

### Types
- `StateConfig.scopes: list[str] | None = None` — mirrors the existing
  `StateConfig.tools: list[str] | None = None` (`fsm/schema.py:727`, drifted from the field's
  earlier `schema.py:686` citation). Name pinned 2026-09-04 (was "not fixed here").

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `StateConfig.scopes` + `to_dict`/`from_dict` lines.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `scopes` property on the state object.
- `scripts/little_loops/fsm/validation/structural_rules.py` — two new rules: (1) every declared
  scope name resolves against ENH-3233's registry; unknown name is an ERROR (AC9); (2) `scopes`
  on a non-shell state is an ERROR (AC10). Both get a row in
  `skills/review-loop/reference.md`'s check table (see Documentation).
- `scripts/little_loops/fsm/runners.py` — `ActionRunner.run()` Protocol + `DefaultActionRunner`
  shell branch (`:297-305`) + `SimulationActionRunner.run()` `del` list.
- `scripts/little_loops/fsm/executor.py` — dispatch call site (`:2563-2573`,
  `self.action_runner.run(...)`) passes `scopes=state.scopes` **ungated** by `action_mode`.
- `docs/guides/LOOPS_GUIDE.md` — per-state field table (see Documentation).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue` — 2026-09-06:_
- `scripts/little_loops/cli/loop/scaffold_verify.py` — 10 direct `StateConfig(...)`
  construction sites (lines 66, 82, 88, 97, 132, 141, 152, 170, 175, 193), building
  states programmatically for `/ll:verify-issue-loop` outside the YAML parser.
  Confirmed unaffected — `scopes` is a new defaulted field, so these keyword
  constructions keep working unchanged; listed for completeness, not as a required edit.

_Wiring pass added by `/ll:wire-issue` — 2026-09-07:_
- `scripts/little_loops/cli/loop/testing.py:20,85` — `from little_loops.fsm.executor
  import DefaultActionRunner` then `runner = DefaultActionRunner()`, a production call
  site not previously listed. Confirmed unaffected — it instantiates the class with no
  args and doesn't pin `.run()`'s kwarg list.
- **Contributed-action call site does not receive `scopes` (gap, not a required edit
  for this issue).** `fsm/executor.py:2486-2505`'s `action_mode == "contributed"`
  branch (`runner = self._contributed_actions[state.action_type]; runner.run(...)`) is
  a second, distinct `ActionRunner.run()` call site from the primary dispatch this
  issue wires (`:2563-2573`). Third-party extension runners registered via
  `ActionProviderExtension.provided_actions()` (`extension.py:82-90`) will never get
  `scopes=` even if a state declares it. Not required by any AC — flagging so the
  asymmetry is a documented decision, not a silent gap, when this issue lands.
- `scripts/little_loops/fsm/__init__.py:139-156,177,213` — re-exports `StateConfig`
  and `ActionRunner` in `__all__`; no edit needed for the new field. Naming-collision
  note only: the module already exports an unrelated `resolve_scope` (singular,
  `fsm/concurrency.py:35`, a lock-scope resolver) — different symbol from this issue's
  `resolve_scopes` (plural, `host_runner.py`), but same namespace.

### Signatures
- `project_child_env(invocation: HostInvocation | None = None, *, extra: dict[str, str] | None = None, env_allow: frozenset[str] | None = None) -> dict[str, str]`
  (`host_runner.py:2027-2032`) — **current, confirmed signature**. `env_allow` now exists (landed
  via ENH-3395/ENH-3396, both `status: done`). `HostInvocation` (`host_runner.py:234-259`) has a
  6th field, `env_allow: frozenset[str] | None = None`. `CREDENTIAL_SCOPES`
  (`host_runner.py:124-163`) and fail-loud `resolve_scopes()` (`host_runner.py:166-183`) both
  exist. This issue's `blocked_by` (`ENH-3395`, `ENH-3396`) is satisfied; nothing external blocks
  this issue's own schema/validation/wiring work.

- `ActionRunner.run(self, action: str, timeout: int, is_slash_command: bool, ..., tools: list[str] | None = None, ...) -> ActionResult`
  (Protocol, `fsm/runners.py:40-95`) — there is no generic/dynamic passthrough from `StateConfig`
  to this Protocol; every field requires its own explicit named parameter here. The new scope
  field needs one, and it must reach both implementers: `DefaultActionRunner.run()`
  (`fsm/runners.py:117-134`) and `SimulationActionRunner.run()` (`fsm/runners.py:428-445`, which
  discards every defaulted param it doesn't use via an explicit `del (...)` at line 469).
  Existing `ActionRunner` test doubles (`RssActionRunner`, `MockActionRunner` ×4,
  `ShutdownAfterFirstActionRunner`, `_TamperingActionRunner`, `_ActionRunner`) all end their
  parameter list with `**kwargs: Any`, so this addition is safe and additive for every one of
  them — none enumerate every current parameter without a trailing catch-all.

### Call Path
`StateConfig.scopes` (declared) → `fsm/executor.py:2563-2573` (`self.action_runner.run(...)`
dispatch call site, corrected from an earlier `:2495-2505` mis-citation) — **must NOT** be gated
to `action_mode == "prompt"` the way `tools`/`agent`/`model` are today, since the new field's
target is the shell branch, not the prompt-mode branch → new named parameter on
`ActionRunner.run()` → `DefaultActionRunner.run()`'s shell branch (`fsm/runners.py:297-305`,
confirmed exact current call: `subprocess.Popen(cmd, ..., env=project_child_env(extra={"LL_PYTHON":
sys.executable}))`, no other kwargs) → `project_child_env(extra=..., env_allow=...)` (the
`env_allow` kwarg is landed — `host_runner.py:2027-2032`) → `subprocess.Popen`.

### Decision Rules
N/A — no new decision logic. This issue declares a scope list and resolves it against ENH-3233's
registry; the registry's fail-loud/allow/deny rules are ENH-3233's surface, not this one's.

### Tests
- `scripts/tests/test_fsm_schema.py::TestAgentToolsStateConfig` (line 2536) — the direct
  precedent for testing a new `StateConfig` field: default→`None`, construct→accepts, `to_dict`
  include-when-set/omit-when-none, `from_dict` deserialize/default, round-trip. The new per-state
  scope field should follow this same six/seven-test shape.
- New shell-branch test proving AC7.1 (undeclared credential variable absent from
  `DefaultActionRunner`'s `bash -c` environment) — no existing test targets this branch directly
  per the parent issue's research; add one alongside `fsm/runners.py`'s existing test coverage.
- FSM-path `ActionRunner` test doubles whose `.run()` signature may need a new kwarg if the
  per-state scope declaration is threaded through `.run()` (mirroring how `tools=`/`agent=` reach
  `fsm/executor.py:2284`): `RssActionRunner` (`scripts/tests/test_host_guard.py:55`),
  `MockActionRunner` (`scripts/tests/test_fsm_persistence.py:825`,
  `scripts/tests/test_usage_journal.py:17`, `scripts/tests/test_fsm_executor.py:41`),
  `ShutdownAfterFirstActionRunner` (`scripts/tests/test_fsm_executor.py:3880`) /
  `_TamperingActionRunner` (`scripts/tests/test_fsm_executor.py:11973`) / `_ActionRunner`
  (`scripts/tests/test_fsm_executor.py:12329`). Kept defaulted (matching the `tools=` precedent),
  these are unaffected — worth an explicit check pass either way.

- Verify `scripts/tests/test_enh3184_spawn_site_guard.py` still passes against the modified
  `project_child_env()` chokepoint (landed in ENH-3233, but this issue's wiring is a new consumer
  of it).

_Wiring pass added by `/ll:wire-issue` — 2026-09-06:_
- **Shared dispatch fixture.** The `self.action_runner.run(...)` call this issue wires
  `scopes=` into (`fsm/executor.py:2563-2573`, corrected above) is covered by exactly one
  shared test double, `MockActionRunner` (`scripts/tests/test_fsm_executor.py:47-138`),
  instantiated at 60+ call sites across the file. Its `run()` already ends in
  `**kwargs: Any` (line 79) then `del`s it (line 93), so adding `scopes=state.scopes` at
  the real call site breaks none of the 60+ existing constructions — but asserting the
  value was actually threaded through needs a new capture list on this same dataclass
  (mirroring the existing `working_dirs`/`idle_timeouts` pattern, lines 57-59/95-101), not
  a separate mock. **ENH-3204 targets the same call site and the same fixture** — whichever
  of the two issues lands first should add the `scopes` capture list; the second should
  reuse it rather than adding a parallel one.
- **Message-collision risk.** A distinct, existing top-level (loop-level, singular) `scope:`
  field already has its own structural rule (`fsm/validation/structural_rules.py:1366-1376`,
  message `"Loop declares no 'scope:'. ..."`) asserted via
  `test_ll_loop_commands.py:303,316` (`caplog.text.count("no 'scope:'")`). This issue's new
  per-state (plural) `scopes:` rule is a different field/concept — its error message must
  avoid the substring `"scope:'"` so a run that trips both rules doesn't corrupt that
  existing caplog-substring assertion.

_Wiring pass added by `/ll:wire-issue` — 2026-09-07:_
- **AC10 has a closer precedent than "no existing precedent to mirror exactly"
  (correcting the 2026-09-07 refine-issue Codebase Research Findings claim below).**
  `_validate_state_action()`'s `params`/`mcp_tool` check (`structural_rules.py:466-473`,
  `if state.params and state.action_type != "mcp_tool":`) is functionally an
  inclusion-only check — valid for exactly one `action_type`, the same shape AC10 needs
  for `scopes`/`shell`. Its test pair, `test_params_on_non_mcp_tool_state_fails_validation`
  and `test_params_on_shell_without_action_type_fails_validation`
  (`test_fsm_schema.py:2214-2253`), already covers the `action_type=None` shell-heuristic
  case AC10 item (a)/(d) need — mirror this pair's shape directly.
- **No dedicated test file for `structural_rules.py` was cited in this issue's Tests
  section before this pass.** `scripts/tests/test_fsm_validation_structural.py` is the
  paired test file (confirmed: imports `StateConfig`, has `TestParameterValidation` and
  the harbor-scorer unknown-type tests at 351-365/480-533 — the two-layer convention
  (unit-call the private `_validate_*` function, then an integration `validate_fsm(fsm)`
  call) both AC9 and AC10's new rules should follow). Grepped directly: zero existing
  `scopes` references in this file.
- **Two more ENH-3234 sibling tests to mirror, beyond the already-cited unknown-scope
  one** (`test_runner_spec.py:208-235`): `test_cmd_dispatch_no_scopes_keeps_full_inherit`
  (AC5 analog — undeclared `scopes` keeps full-inherit, asserted via a real subprocess
  reading back an ambient var) and `test_cmd_dispatch_declared_scope_allows_its_vars_denies_others`
  (AC7.1/7.2 analog — real `subprocess.Popen` + `monkeypatch.setenv` + shell
  interpolation reading the var back, e.g. `echo ${GH_TOKEN:-absent}:${ANTHROPIC_API_KEY:-absent}`
  — not a mocked `Popen` call-args assertion). This is the concrete shape for the new
  `TestDefaultActionRunnerShellPath` env-denial test.
- **Schema/dataclass lockstep presence-assertion test needed.** `fsm-loop-schema.json`'s
  `definitions.stateConfig` has `additionalProperties: false` with an explicit allowlist
  and no `patternProperties` catch-all (unlike `on_*` verdict keys) — omitting `scopes`
  from its `properties` would make a loop YAML declaring `scopes:` fail schema validation
  even though the Python loader accepts it. `TestTamperGuard`'s
  `test_schema_json_declares_state_and_loop_level_tamper_guard` /
  `test_schema_json_declares_state_and_loop_level_prepatch_check`
  (`test_fsm_schema.py:4852-4869`) is the established convention to mirror — assert
  `"scopes" in schema["definitions"]["stateConfig"]["properties"]`.
- `scripts/tests/test_worktree_utils.py:25,85` — imports and instantiates
  `DefaultActionRunner` via the `fsm.executor` re-export; worth an unchanged-behavior
  check pass, not flagged as needing a new test.
- `scripts/tests/test_cost_ceiling_enforcement.py:22-33` — one more `MockActionRunner`
  double ending in `**kwargs: Any` (additive-safe), not previously listed alongside the
  other test doubles above.

### Documentation
- `docs/guides/LOOPS_GUIDE.md:590` — the `tools:` per-state allowlist table is the natural
  insertion point for the new per-state scope-declaration row, following the
  `suppress_catalog:` staged-rollout wording precedent at line 633
  (`DECLARATIVE-ONLY (not yet implemented)`).
- `docs/reference/HOST_COMPATIBILITY.md` — the capability support matrix (~line 243) keyed on
  `agent_select`/`tool_allowlist`/etc., and the `CapabilityNotSupported` narrative section (~lines
  300, 325), are the established place a new scoping-capability row or decline-narrative would
  land, if any host runner declines scope enforcement for prompt-mode states that also use
  `tools:`.

_Wiring pass added by `/ll:wire-issue` — 2026-09-06:_
- `skills/review-loop/reference.md` §"First-Pass Checks (from `ll-loop validate`)" (lines
  17-53) is a hand-maintained table assigning a Check ID (V-1..V-18, MR-1..MR-14) and
  Severity to every known `ll-loop validate` rule; `skills/review-loop/SKILL.md` instructs
  readers not to re-implement these checks, only parse validator output against this table.
  No automated gate ties the table to the validator's actual rule set (searched
  `test_wiring_guides_and_meta.py` and related tests for `reference.md`/`check_id` — no
  hits), so the new "unknown scope name" rule needs its own row added by hand or it
  silently falls outside this table.

_Wiring pass added by `/ll:wire-issue` — 2026-09-07:_
- **`docs/reference/API.md` has three passages that will be factually wrong the moment
  this issue lands** (all forward-reference ENH-3235 as unimplemented):
  `:10189` (`### resolve_scopes` — *"The FSM `StateConfig`/loop-YAML declaration surface
  (ENH-3235) is a separate, not-yet-wired consumer"*), `:10220` (`### project_child_env`
  "Honesty note" — *"Populating `env_allow` from a real per-task declaration
  (`ActionSpec`/FSM `StateConfig`) is out of scope for this chokepoint — see
  ENH-3234/ENH-3235"*, needs the FSM half removed/updated). Both must be corrected as
  part of this issue's own change, not left stale.
- `docs/reference/API.md:6341-6373` (`#### ActionRunner Protocol`) — hand-maintained
  code block reproducing the full `run()` signature plus prose documenting the
  "kwarg-gated" precedent (agent/tools/model only passed when non-default). Since
  `scopes` is added **ungated** by `action_mode` (per Program Design), this section
  needs the signature updated and a note that `scopes` breaks from that gating
  precedent.
- `docs/reference/API.md:5852-5901` (`#### StateConfig`) — hand-maintained per-field
  annotated code block; needs a `scopes: list[str] | None = None` line, mirroring how
  prior fields were added. `docs/reference/API.md:10387` (`### ActionSpec` — the
  `scopes` prose already written for ENH-3234) is the doc-precedent template to mirror
  for wording consistency.
- `docs/generalized-fsm-loop.md:300-359` — a second, independent hand-written per-state
  YAML reference block (lines 357-358 list `agent:`/`tools:` as state-level fields);
  add `scopes:` alongside for consistency with `LOOPS_GUIDE.md`'s table.
- `docs/reference/CLI.md:908-938` (`#### ll-loop validate <loop>`) — a second,
  independent Check-ID/severity table (distinct from `skills/review-loop/reference.md`'s)
  listing MR-1..MR-14 plus named unnumbered rules; needs two new bullet entries for the
  "unknown-scope-name" and "scopes-on-non-shell-state" ERROR rules.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Test shape confirmed: `TestAgentToolsStateConfig` (`test_fsm_schema.py:2536`) and
  `TestModelStateConfig` (`test_fsm_schema.py:2624`) both use the same seven-test convention per
  field (`defaults_to_none`, `accepts_<field>`, `to_dict_includes_<field>_when_set`,
  `to_dict_excludes_<field>_when_none`, `from_dict_with_<field>`,
  `from_dict_without_<field>_defaults_none`, `round_trip_<field>`) — either one class per field or
  one class covering a closely-related pair are both established precedent.
- All `ActionRunner` test doubles end their parameter list with `**kwargs: Any`
  (`RssActionRunner` — `test_host_guard.py:62`; `MockActionRunner` — `test_fsm_executor.py:56-73`,
  `test_fsm_persistence.py:833-845`, `test_usage_journal.py:25-37`,
  `test_cost_ceiling_enforcement.py:29`; `ShutdownAfterFirstActionRunner` —
  `test_fsm_executor.py:3880-3895`; `_TamperingActionRunner` — `test_fsm_executor.py:11973`;
  `_ActionRunner` — `test_fsm_executor.py:12329`) — a new defaulted kwarg on `ActionRunner.run()` is
  additive-safe against every one of them.

- `test_enh3184_spawn_site_guard.py`'s per-module spawn-count table already has entries for
  `little_loops/fsm/runners.py` (line 26) and `little_loops/runner_spec.py` (line 28) — this
  issue's wiring is a new consumer of an already-tracked spawn site, not a new entry.
- ENH-3234 (the sibling `ActionSpec` surface) already has its own dispatch/env test precedents to
  mirror the shape of: `test_runner_spec.py::test_cmd_dispatch_matches_legacy_shape` (line 190)
  and `test_cmd_dispatch_sets_ll_python_env` (line 196).
- No shared "declare capability, decline gracefully" helper exists for `CapabilityNotSupported`
  warn-and-drop: `CodexRunner`, `GeminiRunner`, `KimiRunner`, `QwenRunner` each independently
  inline their own `if <param>: warnings.warn(..., CapabilityNotSupported, stacklevel=2)` block in
  `build_streaming()`. Not directly relevant to this issue's shell-branch-only scope (Scope
  Boundaries already excludes prompt-mode extension), but confirms there is nothing to reuse if
  that scope ever expands.
- The nearest shape precedent for a fixed-name-set resolved against a registry is
  `MUTATING_TOOLS` (`mcp_server/policy.py:55-65`, a bare `frozenset[str]` with no per-entry
  metadata and no fail-loud-on-unknown-name behavior) — a shape precedent only; the actual
  registry is ENH-3233's surface. "Resolve name against fixed set, raise directly on miss" (not
  warn-and-drop) is the codebase's convention elsewhere: `adapters/core.py::resolve_emitter`
  (line 76-78) and `CodexRunner._sandbox_args` (`host_runner.py:612-619`).

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **Signature correction (2026-09-07):** `project_child_env()`'s current signature is
  `project_child_env(invocation: HostInvocation | None = None, *, extra: dict[str, str] | None =
  None, env_allow: frozenset[str] | None = None) -> dict[str, str]` (`host_runner.py:2027-2032`) —
  the `env_allow` kwarg the Signatures subsection above describes as not-yet-existing is now
  landed (ENH-3395/ENH-3396, both `status: done`). This issue's `blocked_by` is therefore
  satisfied; nothing external blocks starting this issue's own schema/validation/wiring work.
- **Validate-time precedent for AC9 exists in this same file:** `_validate_evaluator()`
  (`structural_rules.py:91-101`) and `_validate_parameters()` (`structural_rules.py:231-240`) both
  check a declared name with `not in <fixed-set>` against a module-level registry and append a
  `ValidationError` (default severity ERROR) reading "Unknown <thing> '<value>'. Must be one of:
  <sorted set>" — the same message shape `resolve_scopes()` already raises
  (`host_runner.py:179-181`). `CREDENTIAL_SCOPES`/`resolve_scopes` are not imported anywhere under
  `fsm/` today.
- **AC10's shape has no existing precedent to mirror exactly:** every current field-restriction in
  `_validate_state_action()` (`structural_rules.py:408-473`, e.g. `model`/`effort` overrides,
  `params`) is phrased as an *exclusion* of certain `action_type`s, never as an
  inclusion-only-of-`"shell"` check — a repo-wide search for an `action_type == "shell"`-only
  validation rule returns no hits outside the mode-classifier `_action_mode()` itself
  (`executor.py:3325-3346`, not a validator).
- **Test precedent confirmed:** `test_fsm_runners.py::TestDefaultActionRunnerShellPath` (line 226)
  already covers `DefaultActionRunner`'s shell path, including an `LL_PYTHON` env-injection
  assertion (line 406) — the natural home for AC7.1's new env-denial test. The sibling
  run-time-failure path (unknown scope name at execution time) has a direct analog to mirror:
  `test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing` (`test_runner_spec.py:237-253`).

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **Concrete precedent lines for the shell-branch exception-handling gap flagged in Verification Notes (2026-09-07, B6):** `DefaultActionRunner.run()`'s prompt branch already wraps its own resolver/spawn call in `except Exception as exc: return ActionResult(...)` at `fsm/runners.py:264-272` — a live precedent in this same method for how the shell branch could contain a failed `resolve_scopes()` call instead of letting it propagate uncaught. The shell branch itself (`fsm/runners.py:297-306`) has no such wrapping today, confirmed by direct read.
- **The two nearby precedents differ in exception type caught, not just presence/absence of a try/except.** `runner_spec.py::_run_cmd()` (ENH-3234, lines 248-261) wraps `resolve_scopes()` specifically in `try/except ValueError`, returning `RunnerResult(exit_code=2, error=str(e))` — narrower than the prompt branch's `except Exception` above it in the same file. An implementer choosing which shape to mirror in the shell branch is picking between two live precedents that disagree on exception breadth, not inventing a new pattern from nothing.
- `resolve_scopes()`'s own existing test coverage — `test_host_runner.py::TestResolveScopes` (lines 446-481: `test_single_known_scope`, `test_multiple_scopes_union`, `test_unknown_scope_raises_with_name`, `test_every_scope_entry_has_a_justification_comment`) — confirms it raises `ValueError` with the bad scope name in the message, consistent with what both `runner_spec.py` and `resolve_scopes()`'s own callers rely on.

## Scope Boundaries

Out of scope for this child:

- The `ActionSpec` declaration surface and `runner_spec.py::_run_cmd()` wiring — that's ENH-3234.
- The chokepoint's deny logic, capability registry, and baseline — that's ENH-3233, a hard
  dependency of this issue.
- Extending the new scope field to prompt-mode states via `build_streaming()` — AC7.1 only
  requires the `DefaultActionRunner` shell branch; extending scope enforcement to host-CLI
  prompt-mode invocations is not required by any AC in the parent issue (those paths already
  route through `HostInvocation`/`project_child_env()` via ENH-3233's chokepoint once a caller
  populates `env_allow`, but no AC mandates populating it from `tools:`-style state config for
  prompt-mode states in this decomposition).
- Retrofitting declarations onto this repo's own existing `loops/*.yaml` — AC5 keeps undeclared
  states working; migrating real loops to declare scopes is follow-on work per ENH-3203's Scope
  Boundaries.

## Impact

- **Priority**: P2 — matches parent.
- **Effort**: Medium — schema field, dataclass field with round-trip, and new wiring into a shell
  branch that today reads none of the state config's per-state fields (no existing flow to
  piggyback on, unlike the `tools:` precedent for prompt-mode).

- **Risk**: Medium — `DefaultActionRunner`'s shell branch is the primary FSM-loop consumer; a
  baseline gap surfacing here (rather than in ENH-3233's own report-only testing) would break
  real loop runs. Mitigated by ENH-3233 landing and validating the baseline against this repo's
  own `loops/*.yaml` first.
- **Breaking Change**: No — declaration is opt-in per state.

## Blocks

- ENH-3204
- ENH-3205

## Status

**Open** | Created: 2026-08-17 | Priority: P2 | Blockers resolved: ENH-3395, ENH-3396 (both done)

## Verification Notes (2026-09-03)

- `fsm/runners.py` shell branch re-verified at lines 297-305 (was cited 266-275).
- Corrected the factual claim that the `project_child_env()` call passes "zero arguments" — it
  already passes `extra={"LL_PYTHON": sys.executable}`; only `env_allow` is missing.
- Added missing `## Blocks` backlink: ENH-3204 and ENH-3205 both declare
  `blocked_by: ENH-3235` but this issue had no `## Blocks` section.

## Verification Notes (2026-09-03, second pass)

- `_TamperingActionRunner`'s citation was wrong, not just drifted: the same `refine-issue` pass
  that corrected other lines introduced `test_fsm_executor.py:3981-3995` for it; the class is
  actually at line 11973 (confirmed by both `grep` and `ll-code defines`). Corrected in the Tests
  and Codebase Research Findings sections above.
- The `fsm-loop-schema.json` `tools:`-block "correction" to lines 582-598 was also backwards: the
  block is still at its originally-cited 590-596 (confirmed by `grep -n '"tools"'` and direct
  read) — 582-598 spans the unrelated `agent`/`tools`/`pruning_profile` neighborhood, not the
  `tools:` block itself. Left as-is above since the body text doesn't hard-cite the wrong range in
  a way that needs a line edit, but flagging here so a future pass doesn't re-introduce it.
- All other citations re-verified clean: `project_child_env()`/`HostInvocation` signatures
  (`host_runner.py:1865-1895`, `156-173`), `StateConfig.tools` (`schema.py:727`, `831`, `952`),
  `fsm/executor.py:2495-2505`'s prompt-mode gating, `ENH-3233` still `status: open`, decisions log
  present with no active required-rule conflict, `ll-verify-evidence` clean (0 findings).
- Verdict: **NEEDS_UPDATE** — the blocking dependency and technical claims all hold; only two
  stale/incorrect line citations needed correction.

## Review Notes (2026-09-04, pre-implementation epic review)

- Field name pinned to `scopes` (matches ENH-3234 and ENH-3204).
- Added validate/load-time rejection of unknown scope names (AC9, new structural rule) — run-time
  resolution alone would fail mid-loop after earlier states already ran.
- Added `fsm-loop-schema.json` property and a consolidated Files to Modify list.
- Doc note for LOOPS_GUIDE: a declaring shell state that spawns a nested host CLI (`claude -p`,
  `ll-loop`, `ll-auto`) loses env-borne API keys unless it declares the matching `*-api` scope;
  Keychain-backed OAuth is unaffected (see ENH-3233's honesty note).

## Review Notes (2026-09-06, pre-implementation cross-issue review)

- Added AC10 and a second structural rule: `scopes:` on a non-shell state is a validate-time
  ERROR, because the shell branch is the only consumer and a prompt-mode declaration would
  otherwise be silently ignored. Named `run_claude_command()` (`subprocess_utils.py:529`) as the
  prompt-mode enforcement seam for the follow-on issue.

## Verification Notes (2026-09-07)

- **Blocker status re-confirmed accurate**: `ENH-3233`, `ENH-3395`, `ENH-3396` are all
  `status: done`; `project_child_env()` (`host_runner.py:2027-2032`) has the `env_allow`
  kwarg, `HostInvocation.env_allow` exists (`host_runner.py:235-259`), and
  `CREDENTIAL_SCOPES`/`resolve_scopes` exist (`host_runner.py:124-163`, `166-183`). This
  matches the 2026-09-07 Codebase Research Findings correction.
- **Stale contradiction found**: the Program Design → **Signatures** subsection still
  asserts `project_child_env()` has no `env_allow` kwarg ("current, confirmed signature")
  and that `ENH-3233` is `status: open` / `blocked_by: [ENH-3233]` is a "mandatory,
  currently-true block." The Program Design → **Call Path** section likewise says "the
  `env_allow` kwarg does not exist yet — pending ENH-3233." Both statements are now false
  and directly contradicted by the newer 2026-09-07 Codebase Research Findings correction
  elsewhere in this same file — left uncorrected, a reader hitting the Signatures/Call Path
  subsections first (they precede the corrected findings) will act on stale info. Needs a
  line-level fix striking the "env_allow does not exist" / "ENH-3233 open" language from
  those two subsections.
- The `## Status` line ("Blocked by: ENH-3233") is also out of sync with this issue's own
  frontmatter `blocked_by: [ENH-3395, ENH-3396]` (never mentions ENH-3233 there) — a
  pre-existing drift, not newly introduced, but now doubly moot since all three named
  issues are done.
- **Proposal-consequence check (B6, advisory — does not change the verdict since a
  current-state claim above is false)**: the Program Design's Call Path for the
  `fsm/runners.py` shell-branch wiring specifies no exception handling around the
  `resolve_scopes()` call. The sibling `ENH-3234` implementation
  (`runner_spec.py::_run_cmd()`, confirmed at lines 247-252) wraps the equivalent call in
  `try/except ValueError` and returns a graceful failed `RunnerResult(exit_code=2,
  error=...)` before ever reaching `subprocess.Popen`
  (`test_cmd_dispatch_unknown_scope_fails_loud_and_spawns_nothing`,
  `test_runner_spec.py:237-253`). `DefaultActionRunner`'s shell branch
  (`fsm/runners.py:297-305`) has no such wrapping today, unlike the prompt branch directly
  above it in the same method (which has its own `except Exception as exc: return
  ActionResult(...)`). The Proposed Solution's "last line of defence" framing for the
  run-time resolution implies a contained per-state failure, not an uncaught `ValueError`
  crashing the executor's dispatch loop — implementers should mirror ENH-3234's catch-and-return
  shape here, and the Tests section should say so explicitly rather than only citing the
  ENH-3234 test as a shape "to mirror" without naming the missing try/except in Program
  Design.
- Decisions log: no active required-rule conflicts. `ll-verify-evidence`: clean (0
  findings). Deliverable still fully unimplemented in code (re-confirmed) — matches this
  issue's own 2026-09-07 Codebase Research Findings claim.
- Verdict: **NEEDS_UPDATE** — core proposal and blocker status are sound, but the stale
  Signatures/Call Path text above needs correcting before implementation starts from it.

## Verification Notes (2026-09-07, ready-issue pass)

- **`verify_verdict` refreshed NON_VALID → VALID.** The persisted NON_VALID came from the
  2026-09-07 `/ll:verify-issues` run that flagged a stale contradiction in the Program Design →
  Signatures/Call Path subsections (claiming `env_allow` didn't exist / `ENH-3233` was open). The
  subsequent `/ll:reconcile-issue` pass (same day, 21:06:41) already corrected both subsections —
  re-read directly and confirmed they now state the accurate, landed `env_allow` signature. Direct
  codebase greps re-confirm every citation in this issue independently: `project_child_env()`
  signature (`host_runner.py:2027-2032`), `HostInvocation.env_allow` (`host_runner.py:259`), the
  exact shell-branch block (`fsm/runners.py:297,305`), the dispatch call site
  (`fsm/executor.py:2563`), `_action_mode()` (`fsm/executor.py:3325`), and
  `TestDefaultActionRunnerShellPath` (`test_fsm_runners.py:226`) all match as cited. No `scopes`
  field exists yet anywhere (`fsm/schema.py`, `structural_rules.py`) — deliverable confirmed still
  fully unimplemented, matching the issue's own claim.
- **`## Status` line corrected**: still read "Blocked by: ENH-3233" despite frontmatter
  `blocked_by: [ENH-3395, ENH-3396]` (never ENH-3233) and despite all three named issues being
  `status: done`. Updated to reflect resolved-blocker state.
- `ll-issues format-check --format json`: clean except one `mislocated_symbol_ref` entry —
  `env_allow (claimed in scripts/little_loops/fsm/validation/structural_rules.py)`. Manually
  traced: no sentence in this issue actually asserts `env_allow` is defined in
  `structural_rules.py`; `env_allow` and nearby `structural_rules.py:LINE` citations appear in the
  same Program Design subsection but describing unrelated facts. Treated as heuristic noise from a
  wide proximity window, not a real mislocation — no text change made.
- `ll-issues check-design ENH-3235`: exit 0 (PASS). Decisions gate: no active required rules
  (skip/PASS). No `learning_tests_required` in frontmatter (skip/PASS). Both structured blockers
  (`ENH-3395`, `ENH-3396`) confirmed `status: done` via `ll-issues show`; `prose_dep_drift`/
  `stale_prose_dep` both empty — no blockers.
- Inspected branch: `epic/epic-3212-per-task-credential-scoping`, in the dedicated worktree
  checked out for this EPIC — the authoritative base for this issue's symbol-existence checks.

## Resolution

Implemented per the Program Design, matching the Call Path and Signatures exactly as pinned:

- `StateConfig.scopes: list[str] | None = None` added (`fsm/schema.py`), with `to_dict`/
  `from_dict` lines mirroring the `tools:` precedent, and a `scopes` property on
  `fsm-loop-schema.json`'s `stateConfig` definition.
- `fsm/runners.py`'s `DefaultActionRunner` shell branch resolves `scopes` via
  `resolve_scopes()` into `env_allow`, passed through to
  `project_child_env(extra={"LL_PYTHON": ...}, env_allow=...)` — mirroring
  `runner_spec.py::_run_cmd()`'s (ENH-3234) shape, including the `try/except ValueError`
  → failed `ActionResult` catch (Verification Notes 2026-09-07 B6) so a bad scope name
  fails only the declaring state, never crashes the executor's dispatch loop. `scopes` was
  added to the `ActionRunner` Protocol and `SimulationActionRunner`'s `del` list too.
- `fsm/executor.py`'s dispatch call site passes `scopes=state.scopes` **ungated** by
  `action_mode` (unlike `agent`/`tools`/`model`), per Program Design.
- Two new structural-validation rules in `fsm/validation/structural_rules.py`
  (`_validate_state_action`, plus a new `_is_shell_state()` helper mirroring
  `FSMExecutor._action_mode()`'s shell classification): AC9 rejects an unknown scope name
  against `host_runner.CREDENTIAL_SCOPES`; AC10 rejects `scopes` on any non-shell state.
  Both error messages avoid the substring `"scope:'"` to not collide with
  `_validate_missing_scope()`'s existing caplog assertion.
- Tests: `TestScopesStateConfig` (schema round-trip, `test_fsm_schema.py`),
  `TestScopesValidation` (AC9/AC10, `test_fsm_validation_structural.py`), three new cases
  in `TestDefaultActionRunnerShellPath` (AC5/AC7.1/AC7.2 — real-subprocess env-denial,
  mirroring ENH-3234's `test_runner_spec.py` sibling tests, `test_fsm_runners.py`), a
  schema-JSON presence assertion (`TestTamperGuard`-style, `test_fsm_schema.py`), and a
  `scopes_seen` capture list + dispatch test on `MockActionRunner`
  (`test_fsm_executor.py`) proving `scopes=` reaches `ActionRunner.run()` ungated.
- Full suite: `python -m pytest scripts/tests/` — 23321 passed, 43 skipped, 8 pre-existing
  failures unrelated to this change (bun/tsc type-def gaps in `test_omp_adapter.py`/
  `test_opencode_adapter.py`, an unrelated `verify-evidence` baseline drift on issue files
  this issue never touched, an unrelated `test_issue_parser.py` regex-allowlist drift, an
  unrelated `test_builtin_loops.py` failure, an unrelated SSE fan-in flake, and an
  unrelated golden-fixture byte-diff in `test_enh3035_artifact_template_kit.py`) — verified
  by running each finding's source location directly; none reference `fsm/`, `scopes`, or
  `host_runner`'s credential-scope surface.
- Out of scope per this issue's own Scope Boundaries (unchanged): `ActionSpec`/
  `runner_spec.py` wiring (ENH-3234), prompt-mode enforcement via
  `run_claude_command()`'s `project_child_env()` call (follow-on), and retrofitting
  `scopes:` onto this repo's own `loops/*.yaml`.

## Session Log
- `/ll:manage-issue` - 2026-09-07T21:27:05 - `e8b40fd1-94c8-45bd-bf83-716b79cb5f78.jsonl`
- `/ll:ready-issue` - 2026-09-07T21:13:44 - `6850486a-7d28-4d04-8318-c201c9a8b88c.jsonl`
- `/ll:confidence-check` - 2026-09-07T21:09:13 - `0b993f03-bc7f-4049-b2d5-655d6a61dde4.jsonl`
- `/ll:reconcile-issue` - 2026-09-07T21:06:41 - `76ca5aa7-0d75-4607-b7ba-082c46a2b0b2.jsonl`
- `/ll:verify-issues` - 2026-09-07T21:01:07 - `f7b69293-9189-4826-bb88-c9a4ff2f4657.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-07T20:58:52 - `39c172a1-6be4-447b-9f85-c1fbfc7bdb1a.jsonl`
- `/ll:verify-issues` - 2026-09-07T20:53:13 - `eead7325-7e35-4126-ae7b-99ac8a78ca15.jsonl`
- `/ll:wire-issue` - 2026-09-07T20:49:43 - `17eac873-40d2-4130-ba6a-f51d8a35f322.jsonl`
- `/ll:refine-issue` - 2026-09-07T20:37:58 - `190f4f33-7fb0-48f1-bd3c-d24cff2c258e.jsonl`
- `/ll:wire-issue` - 2026-09-07T03:48:28 - `24278e0c-f73c-4e7c-b229-0bf010cc0589.jsonl`
- `/ll:verify-issues` - 2026-09-03T20:03:03 - `e7ab64a8-d990-4865-a8d8-f889f6c44694.jsonl`
- `/ll:refine-issue` - 2026-09-03T19:17:32 - `35fa9aa4-b416-4202-92c2-dce942749180.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:issue-size-review` - 2026-08-17T16:32:35 - `bcf99734-092e-4d7b-9a71-2d6fb04c8246.jsonl`
