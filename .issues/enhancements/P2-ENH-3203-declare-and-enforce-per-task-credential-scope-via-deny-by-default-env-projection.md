---
id: ENH-3203
type: ENH
title: Declare and enforce per-task credential scope via deny-by-default env projection
priority: P2
status: open
parent: EPIC-3212
epic: EPIC-3212
blocked_by:
- ENH-3184
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:26:51Z'
testable: true
decision_needed: false
confidence_score: 95
outcome_confidence: 43
score_complexity: 0
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
---

# ENH-3203: Declare and enforce per-task credential scope via deny-by-default env projection

## Summary

A runner spec declares which credentials and capabilities its task actually needs, and the projection helper landed by ENH-3184 restricts the child process to exactly that set — the operational pattern of a fine-grained PAT scoped to one repository with read+write on Issues and nothing else.

Today a scheduled docs-sweep agent and a scheduled release agent run with identical, unbounded authority. `--cwd` bounds *where* they work, not *what they can reach*.

**Mechanism is env projection, not token minting.** The child receives only the credential variables its declaration names, plus a fixed baseline. Purely local, no provider integration. Exchanging a broad credential for a genuinely narrower provider-side one (GitHub App installation tokens, AWS STS `AssumeRole`) is separate work with no foothold in this codebase — `_active_oauth_token()` (`host_runner.py:2064-2076`) only *selects* among ambient vars, it does not mint. Prose in this issue that reads as minting ("scoped token") means projection unless stated otherwise.

**ENH-3184 is done, so this issue is unblocked.** It switches on deny-by-default across the spawn-site map that ENH-3184 centralized; attempting it before that chokepoint existed and was guarded would have meant a missed spawn site silently making the guarantee false — which is worse than the status quo, because it looks like protection that isn't there. The census has already been re-derived wrong twice, which is why ENH-3184 landed the guard first.

## Current Behavior

ENH-3184 centralizes child-environment construction behind a single projection helper, but that helper's default policy is "inherit everything, apply overrides" — today's behaviour, expressed once instead of twelve times. There is no way for a task to say what it needs, and no way for the helper to withhold anything.

`HostInvocation.env` is additive/override-only by documented contract (`_apply_automation_env()`, `host_runner.py:1784-1799`): absence of a key means "inherit the parent's value," never "clear."

## Expected Behavior

A runner spec declares the credentials and capabilities its task needs. At invocation, the shared helper constructs the child environment deny-by-default: the declared credentials plus a fixed non-credential baseline, and nothing else. An undeclared credential variable is genuinely absent from the child process — for host-CLI paths and `bash -c` shell actions alike.

A spec declaring a capability the registry doesn't know fails at resolve time, naming it. Specs with no declaration keep today's coarse behaviour behind a deprecation path, so nothing in flight breaks.

## Motivation

Per-task scoping is a distinct axis from `--cwd`'s per-repo working directory, on the same runner. A narrower scope is easier to audit; an over-broad scope hides failure modes until the run that exploits it; and an unattended agent holding write authority it never needed is the kind of exposure that is cheap to prevent and expensive to explain.

This becomes load-bearing wherever a scheduled agent touches a system whose credentials cannot be casually over-granted.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

**Option A**: Declaration lives on `ActionSpec` only. Add a scope field to `ActionSpec` (`runner_spec.py:77-89`); every `ll-action`/`ll-queue`/`ll-harness` construction site (`queue_store.py:247`, `cli/loop/run.py:132`, `cli/action.py:239,292`, `cli/harness.py:735,769,811,844`, `cli/queue.py:163,171,186,195`) can populate it, and `_run_cmd()`'s `bash -c` branch (`runner_spec.py:214-286`) can read it directly since it already has the `ActionSpec` in scope. Gap: `fsm/runners.py`'s `DefaultActionRunner` shell branch (`fsm/runners.py:266-275`, AC7's other mandatory path) executes a raw FSM state, not an `ActionSpec` — this option does not by itself reach that call site.

**Option B**: Declaration lives on the loop YAML per-state, following the `tools:` allowlist precedent (`fsm-loop-schema.json:590-596`, `StateConfig.tools`, `schema.py:686`), flowing through `fsm/executor.py:2284` into `build_streaming(...)`. Gap: `runner_spec.py::_run_cmd()` never calls `resolve_host()` (confirmed by direct read) and has no `HostInvocation` or loop-state object in scope — this option does not by itself reach the `ll-action`/`ll-queue`/`ll-harness` path.

**Option C (both)**:

> **Selected:** Option C (both) — only option that satisfies AC7's mandatory dual `bash -c` coverage; Options A and B each leave one AC7-required path structurally unreachable.

Declare on both surfaces independently — `ActionSpec` for the queue/harness/action path, loop-YAML per-state for the FSM path — since AC7 names two structurally separate `bash -c` call sites (`fsm/runners.py:266`, `runner_spec.py::_run_cmd()`) neither of which shares a common per-task object with the other today, and neither of which constructs a `HostInvocation`. A single declaration surface cannot structurally reach both without first unifying the two call paths, which is out of scope here.

**Recommended**: Option C — AC7 makes coverage of both `bash -c` paths mandatory, and the research above confirms neither existing per-task object (`ActionSpec`, FSM `StateConfig`) is visible to the other call path. Declaring on one surface only leaves the other AC7 path structurally unscopable without a larger unification the issue explicitly does not attempt. This resolves Open Decision #2 in favor of "both," which the issue's original open question flagged as a live possibility but did not decide.

### Decision Rationale

_Added by `/ll:decide-issue` — 2026-08-17:_

**Selected: Option C (both)** — declare the scope independently on `ActionSpec` (for the `ll-action`/`ll-queue`/`ll-harness` path) and on FSM `StateConfig`/loop YAML (for the FSM-loop path).

**Reasoning**: AC7 mandates test coverage proving an undeclared credential variable is absent from *both* `bash -c` call sites — `fsm/runners.py:266` and `runner_spec.py::_run_cmd()`. Codebase evidence gathered per option confirms this isn't a preference but a hard constraint: `fsm/runners.py`'s shell branch never constructs or touches an `ActionSpec` (zero matches for `ActionSpec` under `scripts/little_loops/fsm/`), and `runner_spec.py::_run_cmd()` never calls `resolve_host()` or reads a `StateConfig`/loop-YAML object. A declaration on either single surface leaves the other AC7-mandated path with no way to receive it — not a gap to close later, but a path the option cannot reach at all. Only Option C satisfies AC7 by construction.

Evidence also surfaced that the two declaration surfaces, though independent, converge on a single existing enforcement chokepoint regardless of which is chosen: `project_child_env()` (`host_runner.py:1786-1816`), which both `bash -c` sites already call (with zero arguments today) and whose docstring already names ENH-3203 as the seam this issue is expected to extend. The duplication cost of Option C is confined to the *declaration* layer, not the *enforcement* layer — the two schemas/dataclasses stay independent, but both are expected to resolve into the same helper.

**Scoring**:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — `ActionSpec` only | 2 | 2 | 1 | 0 | 5/12 |
| B — loop YAML only | 2 | 1 | 1 | 0 | 4/12 |
| C — both (selected) | 2 | 1 | 2 | 2 | 7/12 |

**Key evidence**:
- `ActionSpec`'s established extension convention is threading new behavior through the untyped `args: dict[str, Any]` grab-bag (`runner_spec.py:120-136`), not new typed dataclass fields — `ActionSpec` has never grown a typed field since its introduction (ENH-2668).
- The `tools:` per-state precedent (Option B's closest analog) requires touching 9+ sites end-to-end to reach every host runner (schema × 2, `fsm/executor.py:2284`, the `ActionRunner` Protocol plus 2 implementations' `run()` signatures, `run_claude_command()`, and every `HostRunner.build_streaming()` implementation) — and even after all that wiring, the shell branch itself still ignores the parameter (`fsm/runners.py:266-275` reads none of `tools`/`agent`/`model`/`automation_profile`).
- No existing case in this codebase duplicates a capability/scope concept as independently-typed fields on both `ActionSpec` and `StateConfig` that must be kept in sync by convention; the closest analog (`timeout` on both, with different default semantics) has no history of drift bugs or reconciliation tooling — a mild risk factor for Option C, offset by AC7 leaving no alternative.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — the projection helper from ENH-3184 gains deny semantics and the baseline set; a new `HostInvocation` field (e.g. `env_allow: frozenset[str] | None`) carries the allow-set. **`HostInvocation.env` must not be repurposed** — see Open Decisions.
- `scripts/little_loops/runner_spec.py` — `ActionSpec` (frozen dataclass: `name`, `runner`, `target`, `args: dict[str, Any]`, `timeout`) is the per-task spec object and has no declaration field today.
- `scripts/little_loops/fsm/schema.py`, `scripts/little_loops/fsm/fsm-loop-schema.json` — if the declaration lives in loop YAML (Open Decision #2), the per-state `tools:` allowlist (`fsm-loop-schema.json:590-596`, `fsm/schema.py:684`) is the precedent.
- The capability registry — new; no existing module owns one.

### Dependent Files (Callers/Importers)
- Every task-path spawn site routed through the helper by ENH-3184. That issue's census is authoritative: 12 explicit hand-rolled env sites, 145 total spawn sites, implicit inheritance dominant.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/schema.py:721` (`StateConfig.to_dict()`) — a new per-state scope field needs a symmetric `to_dict()` line alongside whatever `from_dict()` addition lands (mirrors the existing `tools=data.get("tools")` precedent at `fsm/schema.py:911`); otherwise the field silently fails to round-trip through anything that serializes a `StateConfig` back to dict (loop export, `ll-loop show`, YAML round-trip tests). [Agent 2 finding]
- `scripts/tests/test_enh3184_spawn_site_guard.py` — ENH-3184's spawn-site guard test targets the same `project_child_env()` chokepoint this issue adds deny semantics to; verify it still passes and extend if it asserts anything about the helper's current additive-only behavior. [Agent 1 finding]
- FSM-path `ActionRunner` test doubles whose `.run()` signature may need a new kwarg if the per-state scope declaration is threaded through `.run()` (mirroring how `tools=`/`agent=` reach `fsm/executor.py:2284`): `RssActionRunner` (`scripts/tests/test_host_guard.py:55`), `MockActionRunner` (`scripts/tests/test_fsm_persistence.py:766`, `scripts/tests/test_usage_journal.py:17`, `scripts/tests/test_fsm_executor.py:37`), `ShutdownAfterFirstActionRunner` / `_TamperingActionRunner` / `_ActionRunner` (`scripts/tests/test_fsm_executor.py`). Kept optional (matching the `tools=` precedent), these are unaffected — worth an explicit check pass either way. [Agent 2 finding]

### Conventions in Force
- **Feature-capability declarations** use a frozen dataclass of booleans set once per runner class (`HostCapabilities`, `host_runner.py:119-144`, e.g. `streaming`, `tool_allowlist`, `workspace_sandboxed`) — per-runner, not per-task. Closest existing analog to "declare a capability set," but the granularity doesn't fit AC1.
- **Failure polarity.** An undeclared/unsupported capability today triggers `CapabilityNotSupported(UserWarning)` (`host_runner.py:108-116`) — warn-and-drop, promotable via `warnings.simplefilter("error", CapabilityNotSupported)`. AC3 requires the opposite polarity; no existing hard-fail-on-undeclared-capability path exists in this module to build on.
- **Per-task capability declaration in loop YAML** has one precedent: the `tools:` allowlist is a per-*state* field flowing into `HostRunner.build_streaming(tools=...)`. Some runners honor it (`ClaudeCodeRunner`), others decline with a `CapabilityNotSupported` warning.
- **Staged rollout** (for AC5): `suppress_catalog` (`fsm-loop-schema.json:415-419`, `fsm/schema.py:457-460`) lands a schema field marked `"DECLARATIVE-ONLY (not yet implemented)"` in both the JSON Schema description and the Python dataclass docstring, enforced only by a validator warning (MR-12) until a runtime consumer exists.
- **Deprecation** is documented via a `[DEPRECATED: ...]` text marker in the JSON Schema `description` plus a matching inline comment (`config-schema.json:113,118`; `config/features.py:209-210`) — not the JSON Schema `"deprecated": true` keyword and not a `warnings.warn(DeprecationWarning, ...)` call at read time.

### Tests
- `scripts/tests/test_host_runner.py::TestAutomationProfileEnvAcrossRunners` (lines 52-84) is the established table-driven, cross-all-runner-classes pattern (BUG-3058 precedent). Scoping tests follow this shape, parametrized across `ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner` plus the `OpenCodeRunner`/`PiRunner` stubs.
- `scripts/tests/test_runner_spec.py`, `scripts/tests/test_subprocess_utils.py`.

_Wiring pass added by `/ll:wire-issue`:_
- **Will break** — `scripts/tests/test_host_runner.py::TestProjectChildEnv::test_no_args_is_full_inherit` (lines 94-98): asserts `project_child_env() == dict(os.environ)` exactly for the no-args call. This test's own docstring locks in "byte-identical to pre-ENH-3184 full-inherit" — exactly the default AC5 says must survive for undeclared specs, so this test should keep passing for the undeclared-spec path; if it breaks, deny-by-default has leaked into the no-declaration case. [Agent 3 finding]
- **Will break** — `scripts/tests/test_host_runner.py::TestProjectChildEnvCrossRunnerParity::test_matches_hand_rolled_merge` (lines 145-152): asserts `project_child_env(invocation) == {**os.environ, **invocation.env}` exactly across `ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner`. Same AC5 concern — must keep passing for invocations with no `env_allow` declared. [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py::TestAgentToolsStateConfig` (line 2502) — the direct precedent for testing a new `StateConfig` field: default→`None`, construct→accepts, `to_dict` include-when-set/omit-when-none, `from_dict` deserialize/default, round-trip. A new per-state scope field should follow this same six/seven-test shape. [Agent 3 finding]
- `scripts/tests/test_runner_spec.py::TestRunActionDispatch::test_cmd_dispatch_matches_legacy_shape` (lines 172-176) — the closest existing real-subprocess `RunnerType.CMD` test (spawns `echo hi`, no `Popen` mocking); the natural site to extend for AC7's `runner_spec.py::_run_cmd()` coverage (`monkeypatch.setenv(...)` + a shell command that echoes the var, then assert absence). [Agent 3 finding]
- No shared fixture exists for `ActionSpec`/`HostInvocation` construction (`scripts/tests/conftest.py` has none) — new scope-declaration tests should follow the existing inline-keyword-construction convention rather than add one. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `### project_child_env` section (~line 9621-9637) reproduces the current docstring verbatim, including the line "this helper provides no way to clear or deny an inherited variable; that is deliberately out of scope (see ENH-3203)" — this line names this issue directly and goes stale the moment deny semantics land. The `### HostInvocation` section (~line 9437-9458) reproduces the dataclass body and field table and needs the new `env_allow` field added to both. [Agent 2 finding]
- `docs/ARCHITECTURE.md` — the architecture overview table's `HostInvocation` row (~lines 835-848, "holding `binary`, `args`, `env`, `capabilities`, and `cleanup_paths`") needs `env_allow` appended if the field list stays enumerated there. [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:590` — the `tools:` per-state allowlist table is the natural insertion point for the new per-state scope-declaration row, following the `suppress_catalog:` staged-rollout wording precedent at line 633 (`DECLARATIVE-ONLY (not yet implemented)`) that this issue's own Conventions section already cites. [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — the capability support matrix (~line 243) keyed on `agent_select`/`tool_allowlist`/etc., and the `CapabilityNotSupported` narrative section (~lines 300, 325), are the established place a new scoping-capability row or decline-narrative would land, if any host runner declines scope enforcement. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

### Conventions in Force (pattern-finder additions)
- **Per-state declaration precedent.** The `tools:` allowlist is `array[string]`/optional (`fsm-loop-schema.json:590-596`; `StateConfig.tools: list[str] | None = None`, `schema.py:686`), flows into `build_streaming(tools=...)` at `fsm/executor.py:2284`, only for prompt-mode states. Runners that honor it read the flag directly (`ClaudeCodeRunner.build_streaming`, `host_runner.py:358-359`; `OmpRunner`, `host_runner.py:1246-1247`); runners that decline it warn-and-drop via `CapabilityNotSupported` (`CodexRunner`, `host_runner.py:645-654`; same shape in `QwenRunner:1624-1627`, `KimiRunner:1411-1415`), gated on each runner's `capabilities.tool_allowlist` flag.
- **Staged-rollout wording precedent.** `suppress_catalog` uses the literal phrase `DECLARATIVE-ONLY (not yet implemented)` in the JSON Schema `description` (`fsm-loop-schema.json:415-419`) and an equivalent `.. warning::`-block docstring in `schema.py:457-468` naming MR-12 as the sole consumer (no runtime consumer reads the field).
- **Deprecation-marker precedent.** `[DEPRECATED: <replacement guidance>]` prefixed in the JSON Schema `description` (`config-schema.json:113,118`) paired with a same-line `# DEPRECATED: ...` Python comment (`config/features.py:209-210`) — not the JSON Schema `"deprecated": true` keyword (that keyword is used elsewhere, in the unrelated `templates/enh-sections.json:24` issue-template family) and not a live `warnings.warn(DeprecationWarning, ...)` call (none found under `scripts/little_loops/`, despite `CapabilityNotSupported`'s docstring claiming that precedent).
- **Cross-runner test-table precedent.** `TestAutomationProfileEnvAcrossRunners` (`scripts/tests/test_host_runner.py:54-86`, current line numbers — drifted from the issue's cited 52-84) decorates the *class* with `@pytest.mark.parametrize("runner_cls", [ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner])`; every method runs once per runner class. Note: this table omits `OpenCodeRunner`/`PiRunner`, which the issue's Tests section says to include — those two are exercised individually elsewhere in the file, not through this parametrized table.
- **Declared-capability-set shape.** `HostCapabilities` (`host_runner.py:121-145`) is the only frozen-dataclass-of-bools "declared support" shape in this codebase; the more common "allow-set" shape is a bare module-level `frozenset[str]` constant consulted via `in` (e.g. `MUTATING_TOOLS`, `mcp_server/policy.py:55-62`; `_VALID_SANDBOX_MODES`, `host_runner.py:554`), not a dataclass field.
- **Registry-validation precedent (contested — two shapes coexist).** `HOST_CAPABILITIES` (`adapters/capabilities.py`) is looked up two ways: silent-fallback via `.get()` with a default (`cli/adapt.py:126-127`) and direct bracket access assuming membership, raising `KeyError` if absent (`cli/verify_host_map.py:118`; `adapters/omp.py:44`). A third shape validates a string against an `Enum`-derived `frozenset` at a CLI parse step and returns an explicit stderr error (not an exception) on mismatch (`cli/issues/set_status.py:21-25,276-293`, against `DeferReason`/`ClosureReason` in `issue_lifecycle.py:65-113`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/schema.py::StateConfig.to_dict()` — add the symmetric line for whatever per-state scope field lands in `from_dict()`, so it round-trips.
- Verify `scripts/tests/test_host_runner.py::TestProjectChildEnv::test_no_args_is_full_inherit` and `TestProjectChildEnvCrossRunnerParity::test_matches_hand_rolled_merge` still pass unmodified for the undeclared-spec (legacy/AC5) path; if either needs to change, that is a signal deny-by-default has leaked into the no-declaration case.
- Update `docs/reference/API.md` — rewrite the `project_child_env` docstring reproduction (it currently names this issue and states the pre-fix "no deny" invariant) and add `env_allow` to the `HostInvocation` section.
- Update `docs/ARCHITECTURE.md` — add `env_allow` to the `HostInvocation` table row.
- Update `docs/guides/LOOPS_GUIDE.md` — document the new per-state scope field next to the `tools:` table (line 590), following the `suppress_catalog:` staged-rollout wording precedent.
- `scripts/little_loops/host_runner.py` has no existing `logging` import or `logger` — AC6's DEBUG-level denied-variable logging introduces `logging` fresh into this module; there is no in-module precedent to match (nearest same-module signaling precedent is `warnings.warn(..., CapabilityNotSupported, ...)`, which is a different mechanism).
- Verify `scripts/tests/test_enh3184_spawn_site_guard.py` still passes against the modified `project_child_env()` chokepoint.

## Acceptance Criteria

- **AC1.** A runner spec can declare the capability set a task requires.
- **AC2.** The projection helper projects that declaration into the child environment at invocation; an undeclared credential variable is *absent from the child process*, not merely discouraged.
- **AC3.** A runner spec declaring a capability that is not in the known-capability registry fails loudly at resolve time, naming the capability.
  - This is a **declaration-vs-registry** check at spec-resolution time, not runtime interception. `host_runner` cannot observe an LLM deciding to shell out to `gh pr create`; there is no interception point. The runtime consequence of a task reaching for an undeclared credential is that the credential is absent and the child fails on its own terms — an opaque downstream failure, by design. A loud runtime failure would need a wrapper intercepting the child's credential reads: separate and much larger work.
- **AC4.** A fixed baseline set of non-credential variables is always inherited regardless of declaration. Deny-by-default without this strips `PATH`/`HOME` and the host binary fails to launch at all. The helper documents its allow/deny/inherit contract as explicitly as `_apply_automation_env()` documents its "absence means inherit" contract, since this inverts that default.
  - **A baseline of `PATH`, `HOME`, `USER`, `LANG`, `TMPDIR`, `LL_*` is too small and must not be shipped as-is.** `bash -c` actions in this repo run pytest, git, ruff, and `gh`; those depend on `VIRTUAL_ENV`, `PYTHONPATH`, `SSH_AUTH_SOCK` (git push over SSH fails without it), `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`, `PYENV_ROOT`, `HOMEBREW_*`, `XDG_*`, `SHELL`, `TERM`, `TZ`. A too-narrow baseline does not fail loudly — it produces a shell action that dies on an unrelated-looking error.
  - The baseline is therefore **empirically derived, not guessed**: run this repo's own `loops/*.yaml` under projection in report-only mode (AC6), diff the variables actually read against the candidate baseline, and justify each addition in a comment next to the set.
- **AC5.** Existing runner specs without a declaration keep working, with the coarse behaviour and a deprecation path. **Projection applies only where a declaration is present.** Deny-by-default is a property of *declared* specs, not a global flip; the alternative silently breaks every existing shell action in every local-editable project on this machine at once.
- **AC6.** When projection denies a variable, the helper logs the denied variable **names** at DEBUG level (names only, never values). AC3's rationale deliberately accepts that a task reaching for a stripped credential fails opaquely; this keeps that runtime behaviour while making the cause recoverable in one log line instead of an hour of bisection. The same code path in report-only mode produces the AC4 baseline evidence.
- **AC7.** Both `bash -c` paths are covered by the same projection as the host-CLI paths, with a test per path proving an undeclared credential variable is absent from a shell action's environment:
  1. `fsm/runners.py:266` (`DefaultActionRunner` shell branch) — the FSM-loop path. Mandatory; covering only the second leaves FSM loops, the primary consumer, unscoped.
  2. `runner_spec.py::_run_cmd()` — the `ll-action`/`ll-queue`/`ll-harness` path.
- **AC8.** `python -m pytest scripts/tests/` exits 0, and this repo's own `loops/*.yaml` run green under report-only mode before deny mode is enabled.

## Program Design

### Types
- No existing credential/capability-scope dataclass exists to extend. `HostCapabilities` (`host_runner.py:119-144`) is per-runner-class and describes host feature support, not required secrets.
- `ActionSpec` (`runner_spec.py`) is the only per-task spec object in this call path; it has no declaration field today.

### Signatures
- `build_streaming(*, prompt, working_dir=None, resume=False, agent=None, tools=None, model=None, automation_profile=None, disable_background_tasks=False, workspace_root=None) -> HostInvocation` — the call surface every per-host runner implements (`host_runner.py:217-229`).
- **Do not thread the scope declaration through `build_*()`.** That signature is **nine keyword-only parameters**; a `scope=` kwarg means editing ~32 signatures (4 build methods × 8 runner classes) to pass a value none of them interpret, and it puts the scoping decision inside the per-host runners — the one place it must *not* live, since `RunnerType.CMD` (AC7) never calls `resolve_host()` at all and would be structurally excluded.
- Instead: a new `HostInvocation` field (e.g. `env_allow: frozenset[str] | None`) populated by the shared projection helper at spawn time, so the helper is the single chokepoint for both host-CLI and `bash -c` paths and the runner classes stay unchanged.
- `env: dict[str, str]` on `HostInvocation` keeps its additive/override-only contract.

### Call Path
`resolve_host()` → `build_*()` → `HostInvocation` → **projection helper (deny-capable)** → `subprocess.*`

### Decision Rules
- Gate: a task's declared capability set (AC1) vs. the known-capability registry (AC3), at spec-resolution time.
- Escape hatch (AC5): no declaration → today's coarse behaviour.
- Failure polarity (AC3): the codebase's one existing analog, `CapabilityNotSupported(UserWarning)`, is warn-and-drop; AC3 requires the opposite and no existing hard-fail path can be reused as-is.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- `_apply_automation_env()` lives at `scripts/little_loops/host_runner.py:1819-1834` (not 1784-1799 as originally cited — line drift; re-verify before implementing). It mutates its `env` dict in place, setting only `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE`; it never deletes a key. Its own docstring already states the additive-only invariant and names ENH-3203 directly as the follow-on that changes it.
- The real single chokepoint that turns `(os.environ, HostInvocation.env, extra)` into the literal dict passed to `subprocess.*` is `project_child_env(invocation=None, *, extra=None)` (`host_runner.py:1786-1816`, ENH-3184's deliverable) — `env = os.environ.copy(); env.update(invocation.env); env.update(extra)`. This is the seam for adding deny semantics, not `_apply_automation_env()` itself.
- `HostInvocation` (`host_runner.py:148-166`, `@dataclass(frozen=True)`) fields today: `binary: str`, `args: list[str]`, `env: dict[str, str]`, `capabilities: HostCapabilities`, `cleanup_paths: tuple[Path, ...]`. A new `env_allow: frozenset[str] | None` field means editing every `HostInvocation(...)` construction site inside each runner class's `build_streaming`/`build_blocking_json`/`build_detached` (not every consumption site — those just read `.env`/`.binary`/`.args`).
- `project_child_env()` call sites confirmed: with an `invocation` — `runner_spec.py:205,315`, `subprocess_utils.py:450` (the actual `subprocess.Popen(..., env=env)` call for the primary streaming path), `session_store/lifecycle.py:157`, `fsm/evaluators.py:1152,1370,1626`, `fsm/handoff_handler.py:130`, `learning_tests/extractor.py:134`, `cli/issues/decisions.py:815`. With no invocation (pure `os.environ` inheritance) — `fsm/runners.py:274`, `runner_spec.py:231` (`_run_cmd`), `worker_pool.py:105`, `cli/loop/_helpers.py:1670,2106`, `mcp_call.py:197`, `prepatch_check.py:290`, `worktree_utils.py:570`, `git_operations.py:728`.
- `ActionSpec` (`runner_spec.py:77-89`, `@dataclass(frozen=True)`) fields: `name: str`, `runner: RunnerType`, `target: str`, `args: dict[str, Any]`, `timeout: int | None = 120`. No declaration field today. `args` is the existing untyped grab-bag already smuggling per-call options (`automation_profile`, `disable_background_tasks`, `trace_mode`, `tools`, `model`, etc.) into `_run_skill`/`_run_cmd`/`_run_mcp`/`_run_prompt` via `spec.args.get(...)`. Confirmed production construction sites: `queue_store.py:247`, `cli/loop/run.py:132`, `cli/action.py:239,292`, `cli/harness.py:735,769,811,844`, `cli/queue.py:163,171,186,195`.
- Both AC7 shell paths call `project_child_env()` with **zero arguments** — no `HostInvocation` exists at either call site: `fsm/runners.py:266-275` (`cmd = ["bash", "-c", action]` then `subprocess.Popen(cmd, ..., env=project_child_env())`) and `runner_spec.py::_run_cmd()` at `runner_spec.py:214-286` (same shape, lines 225-232). `runner_spec.py::_run_cmd()` never calls `resolve_host()` anywhere in the function — `RunnerType.CMD` is structurally excluded from any scope declaration threaded only through `HostInvocation`.
- `HostCapabilities` (`host_runner.py:120-146`, `@dataclass(frozen=True)`, all-`bool` fields) is confirmed a fixed **class attribute** per runner class (e.g. `ClaudeCodeRunner.capabilities = HostCapabilities(...)` at `host_runner.py:299-309`), not per-task/per-invocation — matches the issue's "wrong granularity" claim.
- `CapabilityNotSupported` (`host_runner.py:109-117`) is `class CapabilityNotSupported(UserWarning)`, raised via `warnings.warn(..., CapabilityNotSupported, stacklevel=N)` at multiple sites (e.g. `host_runner.py:582-590,633-640,1030-1046,1228-1236,1416-1425,1621-1628`) and every site warns-and-continues with the parameter dropped — confirmed warn-and-drop, not fail-closed; no existing hard-fail path to reuse as-is.

## Open Decisions

Resolve before writing code; each changes what gets built.

1. **Mechanism — settled.** v1 is env projection, not token minting (see Summary).
2. **Does the declaration live on `ActionSpec`, in loop YAML per-state, or both?** The `tools:` allowlist (`fsm-loop-schema.json:590-596`) is the per-state precedent; `ActionSpec` is the per-task object. AC1 says "runner spec," which maps to `ActionSpec`, but FSM states are where authors actually write things down.
   See Option A/B/C decision under Proposed Solution → Codebase Research Findings.
3. **Does AC3's failure raise directly, or is it promoted via `warnings.simplefilter("error", ...)`?** Unresolved by the issue text; the existing `CapabilityNotSupported` machinery supports both shapes.
4. **`HostInvocation.env` must not be repurposed — settled.** Its documented contract is additive/override-only, relied on at all twelve explicit spawn sites. Deny capability needs a *new* field; changing `env` in place is a breaking behavioural change across every spawn site simultaneously.

## Scope Boundaries

**What "scoped" does and does not mean.** Env projection restricts what the child can see **in its environment block**. It does not restrict what the child can read **from disk**, and AC4 inherits `HOME`. So every file-backed credential on the machine remains fully reachable from a fully-scoped child: `~/.aws/credentials`, `~/.claude/.credentials.json`, `~/.config/gh/hosts.yml`, `~/.netrc`, `~/.ssh/`, the macOS keychain, and any ambient agent socket in the AC4 baseline (`SSH_AUTH_SOCK`).

AC2's "an undeclared credential variable is *absent from the child process*" is exactly true of **variables** and materially false of **credentials**. Whoever implements this should not describe the result as sandboxing a task's authority; the honest claim is that it stops env-borne credentials from propagating by accident. Constraining disk-backed credentials needs `HOME` redirection to a per-task directory, which is a much larger change with its own breakage surface (every tool that reads user config) and is not attempted here.

Explicitly **out of scope**:

- **Spawn-site centralization** — ENH-3184 (done).
- **Audit persistence of the granted scope** — ENH-3204.
- **`gh`/`sync.py` scoping** — ENH-3205. Env projection alone does not de-scope `gh`: its credential lives in the OS keyring / `~/.config/gh/hosts.yml`, not in `GITHUB_TOKEN`, so removing that variable leaves the broad session fully usable.
- **Disk-backed and keyring-backed credentials.** No `HOME` redirection, no per-task config directories, no keychain scoping.
- **Token minting / credential exchange.** File separately if wanted.
- **Runtime interception of credential use.** See AC3.
- **Secrets management.** No vault integration, no encrypted-at-rest store, no rotation. Credentials still arrive via the operator's ambient environment; this issue only decides which of them propagate.
- **MCP server credentials.** Scoping the credentials MCP servers themselves hold is separate work.
- **Retrofitting declarations onto existing loops.** AC5 keeps undeclared specs working; migrating this repo's own `loops/*.yaml` to declare scopes is follow-on work.

## Impact

- **Priority**: P2 — a real exposure, but a latent one. Nothing is broken today, and no current run is known to have exploited the over-broad scope. Not P1 because there is no active incident; not P3 because the cost grows with every new spawn site.
- **Effort**: Large — declaration field, capability registry, deny-capable helper, empirically-derived baseline, report-only mode, two `bash -c` paths, cross-runner tests over eight runner classes.
- **Risk**: High — deny-by-default on process environments fails closed in production. Getting AC4's baseline wrong means a shell action dies on an unrelated-looking error (missing `VIRTUAL_ENV`, `SSH_AUTH_SOCK`, a proxy var), not a clean "credential denied"; missing a spawn site means the guarantee is silently false. Both failure modes are worse than the status quo, because they look like protection that isn't there. A third, quieter risk is *overclaiming*: describing tasks as authority-scoped when every disk-backed credential is still readable (see Scope Boundaries). Mitigations: ENH-3184 lands the chokepoint with a guard first; derive the baseline from a report-only run over this repo's own loops (AC6) rather than by guessing; keep projection opt-in per declared spec (AC5) so undeclared specs cannot regress.
- **Breaking Change**: No — AC5 preserves coarse behaviour for undeclared specs.

## Status

**Open** | Created: 2026-08-15 | Priority: P2 | Unblocked: 2026-08-16 (ENH-3184 done)


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 43/100 → LOW

### Outcome Risk Factors
- Broad enumeration across 16+ sites: `HostInvocation`/`ActionSpec` new fields touch `host_runner.py` (deny-capable `project_child_env()`, new capability registry, 8 runner classes' construction sites), `runner_spec.py`, `fsm/schema.py`/`fsm-loop-schema.json`, `fsm/runners.py`, plus 4 docs files and 4+ test files — wide breadth even though each individual site's change is scoped.
- Deep per-site complexity at the core chokepoint: `project_child_env()` gains deny-by-default semantics that invert `_apply_automation_env()`'s documented additive-only contract, and AC4's baseline set must be empirically derived (report-only run + diff), not simply written — this is architectural, not mechanical.
- `project_child_env()` has ~18 confirmed call sites (9 with an `HostInvocation`, 9 without) — a very wide blast radius for a chokepoint change; getting AC4's baseline wrong fails a shell action on an unrelated-looking error rather than a clean denial.
- Open Decision #3 (does AC3's failure raise directly or promote via `warnings.simplefilter`) is still unresolved in the issue text — minor, but worth settling before AC3's implementation.

## Session Log
- `/ll:wire-issue` - 2026-08-17T15:52:14 - `aa07a6fa-b5bb-47c3-b8d4-077fa1c9e302.jsonl`
- `/ll:decide-issue` - 2026-08-17T15:38:28 - `86adafaa-70d2-4c08-ac9c-a7da1b885403.jsonl`
- `/ll:refine-issue` - 2026-08-17T15:33:51 - `82413b78-5f49-49d2-809f-b74ee621f3c7.jsonl`
