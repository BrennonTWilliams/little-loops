---
id: ENH-3234
type: ENH
title: ActionSpec credential scope declaration and runner_spec.py wiring
priority: P2
status: open
parent: ENH-3203
epic: EPIC-3212
blocked_by: [ENH-3233]
discovered_by: /ll:issue-size-review
discovered_date: '2026-08-17'
testable: true
decision_needed: false
relates_to:
- ENH-3184
verify_verdict: VALID
---

# ENH-3234: ActionSpec credential scope declaration and runner_spec.py wiring

## Summary

Add a scope-declaration field to `ActionSpec` and wire it into the `ll-action`/`ll-queue`/
`ll-harness` call path so a task run through this path can declare the capability set it needs,
and its `bash -c` execution in `runner_spec.py::_run_cmd()` is denied everything else — using the
deny-capable `project_child_env()`/`HostInvocation.env_allow` chokepoint landed in ENH-3233.

## Parent Issue

Decomposed from ENH-3203: Declare and enforce per-task credential scope via deny-by-default env
projection. This child covers the `ActionSpec` declaration surface only; the FSM `StateConfig`/
loop-YAML surface is ENH-3235. Both converge on the shared chokepoint from ENH-3233, which this
issue depends on.

**Why a separate surface from FSM, not a shared one**: `fsm/runners.py`'s shell branch never
constructs or touches an `ActionSpec` (zero matches for `ActionSpec` under
`scripts/little_loops/fsm/`), and `runner_spec.py::_run_cmd()` never calls `resolve_host()` or
reads a `StateConfig`/loop-YAML object. A single declaration surface cannot structurally reach
both `bash -c` paths without a larger unification the parent issue explicitly does not attempt —
see ENH-3203's Decision Rationale (Option C).

## Current Behavior

`ActionSpec` (`runner_spec.py:77-89`, `@dataclass(frozen=True)`) fields today: `name: str`,
`runner: RunnerType`, `target: str`, `args: dict[str, Any]`, `timeout: int | None = 120`. No
declaration field exists. `args` is the established untyped grab-bag already smuggling per-call
options (`automation_profile`, `disable_background_tasks`, `trace_mode`, `tools`, `model`, etc.)
into `_run_skill`/`_run_cmd`/`_run_mcp`/`_run_prompt` via `spec.args.get(...)`. Confirmed
production construction sites: `queue_store.py:247`, `cli/loop/run.py:132`,
`cli/action.py:239,292`, `cli/harness.py:735,769,811,844`, `cli/queue.py:163,171,186,195`.

`runner_spec.py::_run_cmd()` (`runner_spec.py:232-303`) calls
`project_child_env(extra={"LL_PYTHON": sys.executable})` at line 249 — it already passes an
`extra` kwarg to inject `LL_PYTHON`, but no `env_allow`/deny-list argument, and no `HostInvocation`
exists at this call site today; the function never calls `resolve_host()` anywhere.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Construction-site line numbers have drifted since this section was last written; corrected against current code: `queue_store.py:254` (`_deserialize_action()`, not 247), `cli/action.py:242,295` (not 239,292), `cli/harness.py:825,859,901,934` — `cmd_skill`, `cmd_cmd` (the `RunnerType.CMD` site), `cmd_mcp`, `_run_prompt_action` respectively (not 735,769,811,844), `cli/queue.py:164,172,187,196` (not 163,171,186,195, each off by +1). `cli/loop/run.py:132` is unchanged.
- `runner_spec.py`'s other two `project_child_env()` call sites — `_run_skill()` at line 223 and `_run_prompt()` at line 333 — already pass a real `HostInvocation` (`project_child_env(inv)`); `_run_cmd()` at line 249 is the only one of the three with no invocation in scope, confirming the issue's framing that this call site needs the standalone `env_allow` kwarg ENH-3233 adds to `project_child_env()` directly, not a `HostInvocation`-mediated path.
- `scripts/tests/test_enh3184_spawn_site_guard.py` pins a per-module `subprocess.*` spawn-count table; its entry for `runner_spec.py` is `(3, 0)` — 3 total spawns, 0 exempted, matching lines 223, 249, 333. Adding an `env_allow=` kwarg to the existing `project_child_env(...)` call at line 249 keeps the call routed through the chokepoint, so this guard's count should not need updating for this issue's change alone.
- `_run_cmd()` has no `try/except FileNotFoundError` around its `subprocess.Popen` call (`runner_spec.py:243-250`), unlike `_run_skill()` (line 228) and `_run_prompt()` (line 338), which both catch it. Not itself a gap this issue must close, but relevant if a scope-resolution raise is expected to surface through the same `RunnerResult` error path as a missing-binary failure — today it would propagate as an uncaught exception instead.
- Confirmed via repo-wide grep: `env_allow` has zero matches under `scripts/` (only appears in `.issues/*.md` prose). `HostInvocation` (`host_runner.py:156-166`) has exactly 5 fields today (`binary`, `args`, `env`, `capabilities`, `cleanup_paths`) — no `env_allow`. ENH-3233 remains `status: open`; the parent ENH-3203 is `done` only via decomposition into its children (issue-tracker bookkeeping), not because any of this chokepoint work has landed. `blocked_by: ENH-3233` is current and accurate, not stale.

## Expected Behavior

- `ActionSpec` gains a scope-declaration field naming the capabilities a task needs (resolved
  against ENH-3233's capability registry).
- Every production `ActionSpec` construction site that can reach `_run_cmd()` can populate it.
  `cli/loop/run.py:132` is excluded (corrected 2026-09-06): it builds a `RunnerType.LOOP` spec
  that is never dispatched through `run_action()` (see the comment at that site), so a `scopes`
  value there would be inert.
- `runner_spec.py::_run_cmd()` resolves the declared scopes into an `env_allow` set and passes
  it via the explicit kwarg ENH-3233 provides for invocation-less call sites —
  `project_child_env(extra={"LL_PYTHON": sys.executable}, env_allow=...)` — so everything not
  declared is denied, alongside the existing `LL_PYTHON` injection. No synthetic
  `HostInvocation` is constructed.
- `ActionSpec`s with no declaration keep today's coarse (full-inherit) behavior — the `env_allow`
  path is opt-in per spec, matching ENH-3233's `env_allow=None` no-op default.
- **Queue round-trip preserves the field.** `queue_store.py::_serialize_action()` (line 240-250)
  and `_deserialize_action()` (line 252-260) enumerate `ActionSpec` fields by hand
  (`name`/`runner`/`target`/`args`/`timeout`); a `scopes` field added to the dataclass alone
  **silently vanishes** for every action that goes through `ll-queue`. Both functions must gain
  a `scopes` line (serialize `sorted(scopes)` or `None`; deserialize back to `frozenset` or
  `None`), with a round-trip test. (Review 2026-09-04 — this was missing from every prior pass.)

## Proposed Solution

**Decided: a typed field** (e.g. `scopes: frozenset[str] | None = None`), deliberately diverging
from `ActionSpec`'s established `args: dict[str, Any]` grab-bag convention
(`runner_spec.py:120-136`; no typed field added since ENH-2668). Rationale: this is a security
control — with an `args` key, a typo'd key name (`"scope"` vs `"scopes"`) silently yields an
**unscoped** task with no error anywhere, exactly the "looks like protection that isn't there"
failure mode the parent issue warns about. A typed field also stays symmetric with ENH-3235's
typed `StateConfig` field. Resolve the declared names against ENH-3233's credential-scope
registry at spec-construction or resolve time (AC3's fail-loud direct raise applies here).

### Call Path
`ActionSpec` (scope declared) → `runner_spec.py::_run_cmd()` resolves scopes → `env_allow`
set → `project_child_env(env_allow=...)` (ENH-3233's kwarg; no `HostInvocation` at this call
site) → `subprocess.*`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- The codebase has an established "resolve a declared name against a fixed registry, raise directly on miss" convention this issue's fail-loud resolution can follow: `adapters/core.py:63-81` (`resolve_emitter`), `queue_store.py:232-237` (`_priority_rank`), `pii.py:54-75` (`apply_pii_action`), `init/cli.py:346-366` (`_feature_choices_from_args`), `host_runner.py:601-619` (`CodexRunner._sandbox_args`) — each raises `ValueError` (or a subclass) directly, no `warnings.warn`, and names the offending value plus the valid set in the message. The one opposite-polarity counter-example in the same module family is `host_runner.py:116-124`'s `CapabilityNotSupported(UserWarning)` — warn-and-drop, not raise — for unsupported *host-feature* capability requests; ENH-3233's own issue text already distinguishes this by name as the wrong polarity for credential scopes.
- Backward-compat testing precedent for widening a frozen dataclass already exists on `ActionSpec` itself: `test_runner_spec.py::TestActionSpecFrozen::test_timeout_none_is_constructible` (BUG-2928) is the existing regression test proving a prior field-behavior widening didn't break old construction sites — the natural model for an equivalent `scopes`-omitted-means-unscoped test under AC5.

## Acceptance Criteria

- **AC1 (ActionSpec half).** An `ActionSpec` can declare the capability set a task requires.
- **AC7.2.** `runner_spec.py::_run_cmd()` — the `ll-action`/`ll-queue`/`ll-harness` `bash -c`
  path — is covered by the same projection as the host-CLI paths, with a test proving an
  undeclared credential variable is absent from the shell action's environment.
- **AC5 (this surface).** `ActionSpec`s without a declaration keep working with today's coarse
  behavior — no regression to any existing `ll-action`/`ll-queue`/`ll-harness` caller.

## Program Design

### Types
- `ActionSpec.scopes: frozenset[str] | None = None` — new field, appended after `timeout`
  (`runner_spec.py:95`), following the same defaulted-field-append convention already used on
  this exact dataclass (`timeout` was widened `int` → `int | None = 120` for BUG-2928) and on its
  sibling value objects (`RunnerResult.tool_trace: list[dict[str, Any]] | None = None`,
  `runner_spec.py:80`; `HostCapabilities.workspace_sandboxed: bool = False`, `host_runner.py`) —
  appending a defaulted field keeps every existing keyword-only `ActionSpec(...)` construction
  site unaffected.
- `HostInvocation.env_allow: frozenset[str] | None = None` — ENH-3233's field, not yet present on
  `HostInvocation` (`host_runner.py:156-166`; currently 5 fields: `binary`, `args`, `env`,
  `capabilities`, `cleanup_paths`). Never constructed at `_run_cmd()`'s call site — listed here
  only to confirm the sibling shape this issue does not itself add.

### Signatures
- `project_child_env(invocation: HostInvocation | None = None, *, extra: dict[str, str] | None = None) -> dict[str, str]`
  (`host_runner.py:1865`) — current signature. ENH-3233 adds `env_allow: frozenset[str] | None = None`
  as an additional keyword-only parameter; that parameter does not exist in the tree yet
  (confirmed via repo-wide grep — zero `env_allow` matches under `scripts/`).
- `_run_cmd(spec: ActionSpec) -> RunnerResult` (`runner_spec.py:232`) — signature is unchanged by
  this issue; the new logic lives in the function body, between the `spec.timeout` assertion
  (line 241) and the `subprocess.Popen(...)` call (lines 243-250).

### Call Path
`ActionSpec(scopes=...)` construction site (e.g. `cli/harness.py:859`, `cli/queue.py:196`) →
`run_action()` dispatch (`runner_spec.py:350`, via `_DISPATCH[RunnerType.CMD]`) → `_run_cmd()`
(`runner_spec.py:232`) resolves `spec.scopes` against ENH-3233's registry (not yet implemented —
ENH-3234's own Proposed Solution defers to it) → resolved `env_allow: frozenset[str]` →
`project_child_env(extra={"LL_PYTHON": sys.executable}, env_allow=...)` (`runner_spec.py:249`,
kwarg not yet available) → `subprocess.Popen(["bash", "-c", spec.target], ..., env=<projected dict>)`
(`runner_spec.py:243-250`).

### Decision Rules
- **Resolution point — decided (2026-09-04): resolve in `_run_cmd()`, not at construction.**
  `ActionSpec` is not only built by callers; it is deserialized in bulk from the queue
  (`queue_store.py::_deserialize_action()`, called per row at line 298). A construction-time
  raise (`__post_init__`) on one bad scope name would abort the *entire* queue load rather than
  fail that one action. Resolve-time validation inside `_run_cmd()`, immediately before building
  `env_allow`, confines the blast radius to the offending action. The raise is still ENH-3233's
  direct `ValueError` — only *where* it fires changes.
- **Error surfacing — decided:** `_run_cmd()` catches the resolution `ValueError` and returns a
  failed `RunnerResult` (non-zero exit, message naming the unknown scope), mirroring how
  `_run_skill()`/`_run_prompt()` turn `FileNotFoundError` into a `RunnerResult` error (lines
  228, 338) rather than letting it propagate uncaught. A queue worker must never die on one bad
  entry.
- **CLI surface — decided: out of scope here.** No `--scope` flag is added to `ll-action`/
  `ll-queue`/`ll-harness` in this issue; AC1 is satisfied programmatically (dataclass field +
  queue JSON round-trip). A `--scope <name>` flag on `ll-queue add` (and `ll-harness`'s
  `cmd` subcommand) is a follow-on once ENH-3235's loop-YAML surface has proven the declaration shape; file it when
  this lands rather than widening this issue.

### Files to Modify
- `scripts/little_loops/runner_spec.py` — `ActionSpec.scopes` field; `_run_cmd()` resolution +
  `env_allow=` kwarg + `ValueError` → `RunnerResult` handling.
- `scripts/little_loops/queue_store.py` — `_serialize_action()`/`_deserialize_action()`
  (lines 240-260) gain the `scopes` field.
- `scripts/tests/test_runner_spec.py`, `scripts/tests/test_queue_store.py` (round-trip).

### Tests
- `scripts/tests/test_queue_store.py` — round-trip: enqueue an `ActionSpec(scopes=frozenset({"github"}))`,
  dequeue, assert `scopes` survives; and `scopes=None` round-trips to `None` (not empty set).
- `scripts/tests/test_runner_spec.py` — `_run_cmd()` with an unknown scope returns a failed
  `RunnerResult` naming the scope and spawns nothing.
- `scripts/tests/test_runner_spec.py::TestRunActionDispatch::test_cmd_dispatch_matches_legacy_shape`
  (line 190, not lines 172-176 as previously cited — corrected against current code) — the
  closest existing real-subprocess `RunnerType.CMD` test (spawns `echo hi`, no `Popen` mocking);
  a candidate site to extend for AC7.2.
- `scripts/tests/test_runner_spec.py::TestRunActionDispatch::test_cmd_dispatch_sets_ll_python_env`
  (lines 196-206, ENH-3365) — closer precedent than the test above for AC7.2 specifically: it
  already asserts on an env var's presence in `_run_cmd()`'s output via
  `target="echo $LL_PYTHON"` + `result.stdout.strip() == sys.executable`. The AC7.2 test (assert
  an *undeclared* var is *absent*) is the same shape inverted.
- `scripts/tests/test_runner_spec.py`, `scripts/tests/test_subprocess_utils.py` — general
  coverage location per ENH-3203's Tests section.

### Documentation
- No dedicated doc section for `ActionSpec` scope was identified in the parent's wiring pass
  beyond the `project_child_env`/`HostInvocation` updates already covered by ENH-3233; if the
  chosen field shape (typed field vs. `args` key) merits documentation, add it alongside the
  existing `ActionSpec` field description in `docs/reference/API.md`.

## Scope Boundaries

Out of scope for this child:

- The FSM `StateConfig`/loop-YAML declaration surface and `fsm/runners.py:266` wiring — that's
  ENH-3235.
- The chokepoint's deny logic, capability registry, and baseline — that's ENH-3233, a hard
  dependency of this issue.
- Retrofitting declarations onto existing `ll-action`/`ll-queue`/`ll-harness` callers in this
  repo — AC5 keeps undeclared specs working; migrating real callers to declare scopes is
  follow-on work per ENH-3203's Scope Boundaries.

## Impact

- **Priority**: P2 — matches parent.
- **Effort**: Small-Medium — one field/convention on `ActionSpec`, one call site
  (`_run_cmd()`) to wire, cross-referenced against ENH-3233's already-built chokepoint.
- **Risk**: Low-Medium — confined to the `RunnerType.CMD` path; `ActionSpec`'s other runner
  branches (`_run_skill`, `_run_mcp`, `_run_prompt`) are unaffected unless the declaration is
  extended to them later (out of scope here — AC7.2 only requires the `_run_cmd()` shell path).
- **Breaking Change**: No — declaration is opt-in per `ActionSpec`.

## Blocks

_None._ (ENH-3204 previously listed here; dropped 2026-09-04 — the audit record is written from
`FSMExecutor` on the loop-YAML path and needs only ENH-3233 + ENH-3235. ActionSpec-path
recording is a follow-on to ENH-3204, not a blocker relationship.)

## Status

**Open** | Created: 2026-08-17 | Priority: P2 | Blocked by: ENH-3233

## Review Notes (2026-09-04, pre-implementation epic review)

- Added the `queue_store.py` serialization gap (field would silently drop on `ll-queue` round-trip).
- Pinned the open resolution-point decision: resolve in `_run_cmd()`, `ValueError` → failed
  `RunnerResult`. Rationale: bulk queue deserialization must not abort on one bad entry.
- Pinned CLI `--scope` flag as out of scope / follow-on.
- Removed ENH-3204 from `## Blocks` (see ENH-3204's `blocked_by` change).

## Verification Notes (2026-09-03)

- `runner_spec.py::_run_cmd()` re-verified at line 232 (was cited 214-286); its
  `project_child_env()` call is line 249, not 225-232.
- Corrected the factual claim that the call passes "zero arguments" — it already passes
  `extra={"LL_PYTHON": sys.executable}`; only `env_allow` is missing.
- Added missing `## Blocks` backlink: ENH-3204 declares `blocked_by: ENH-3234` but this issue
  had no `## Blocks` section.

## Review Notes (2026-09-06, pre-implementation cross-issue review)

- No design gaps found. Dropped `cli/loop/run.py:132` from the populatable construction sites
  (it is a `RunnerType.LOOP` spec that never reaches `_run_cmd()`).
- When ENH-3205 lands, `_run_cmd()` should call the same shell-branch helper that resolves
  `scopes` → `extra=` (redirect `GH_CONFIG_DIR` whenever `scopes is not None`; inject `GH_TOKEN`
  iff `github`), per ENH-3205's corrected invariant — not a `github`-gated copy.

## Session Log
- `/ll:wire-issue` - 2026-09-07T03:48:28 - `24278e0c-f73c-4e7c-b229-0bf010cc0589.jsonl`
- `/ll:verify-issues` - 2026-09-03T20:00:04 - `76759f98-2b4f-455f-95bd-9b2a916e74ab.jsonl`
- `/ll:refine-issue` - 2026-09-03T19:08:53 - `14341300-8a35-47fc-8e9f-786c7178b7c9.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:54 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:issue-size-review` - 2026-08-17T16:32:35 - `bcf99734-092e-4d7b-9a71-2d6fb04c8246.jsonl`
