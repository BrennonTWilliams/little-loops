---
id: ENH-3233
type: ENH
title: Deny-by-default env projection core — chokepoint, capability registry, and baseline
priority: P2
status: open
parent: ENH-3203
epic: EPIC-3212
blocked_by: []
discovered_by: /ll:issue-size-review
discovered_date: '2026-08-17'
testable: true
decision_needed: false
relates_to:
- ENH-3184
---

# ENH-3233: Deny-by-default env projection core — chokepoint, capability registry, and baseline

## Summary

Give `project_child_env()` (the single chokepoint ENH-3184 centralized child-environment
construction behind) a deny-capable mode: a new `HostInvocation.env_allow: frozenset[str] |
None` field, a fixed non-credential baseline that survives regardless of declaration, a
capability registry that fails loudly on an unknown capability name, DEBUG-level logging of
denied variable names, and a report-only mode that diffs real variable usage against the
candidate baseline.

This is the shared enforcement layer both declaration surfaces converge on (see ENH-3234,
ENH-3235). It is independently testable and shippable without either consumer surface: call
`project_child_env(invocation, env_allow=frozenset({...}))` directly and assert the resulting
dict.

## Parent Issue

Decomposed from ENH-3203: Declare and enforce per-task credential scope via deny-by-default env
projection. This child covers the shared chokepoint; declaration-surface wiring for the two
`bash -c` paths is ENH-3234 (`ActionSpec`/`runner_spec.py`) and ENH-3235 (FSM
`StateConfig`/loop-YAML).

**Mechanism is env projection, not token minting** — see ENH-3203 Summary for the full framing;
that context is unchanged and not repeated here.

## Current Behavior

`project_child_env(invocation=None, *, extra=None)` (`scripts/little_loops/host_runner.py:1786-1816`,
ENH-3184's deliverable) is additive/override-only: `env = os.environ.copy(); env.update(invocation.env);
env.update(extra)`. There is no way to withhold a variable from the child. `HostInvocation`
(`host_runner.py:148-166`, frozen dataclass) has no field expressing an allow-set today.

`_apply_automation_env()` (`host_runner.py:1819-1834`) sets only `LL_AUTOMATION`/
`LL_AUTOMATION_PROFILE` in place and never deletes a key; its docstring already names ENH-3203
as the follow-on that changes this.

## Expected Behavior

- `HostInvocation` gains `env_allow: frozenset[str] | None = None`.
- `project_child_env()` accepts an invocation whose `env_allow` is set and constructs the child
  environment as: the declared allow-set (from `invocation.env`/`extra`, intersected with
  `env_allow`) plus a fixed baseline, and nothing else from `os.environ`.
- `invocation.env_allow is None` (the default) preserves today's full-inherit behavior exactly —
  this is the escape hatch the two consumer issues rely on for undeclared specs.
- A capability registry maps capability names to the env-var names they unlock; resolving a
  capability not in the registry raises at resolve time, naming the capability.
- When projection denies a variable, the helper logs the denied variable **names** at DEBUG
  level (names only, never values).
- A report-only mode runs the same diff logic without denying anything, for empirically deriving
  the baseline (see Acceptance Criteria).

## Motivation

Per-task credential scoping needs one enforcement seam that both `ActionSpec` (queue/harness/
action path) and FSM `StateConfig` (loop-YAML path) can independently resolve into, per the
issue's own Decision Rationale: "the two declaration surfaces, though independent, converge on a
single existing enforcement chokepoint regardless of which is chosen." Building that chokepoint
first, with its own tests proving the undeclared-spec path is unchanged, lets ENH-3234 and
ENH-3235 each wire a declaration through it without re-deriving or duplicating deny logic.

## Proposed Solution

### Types
- `HostInvocation` (`host_runner.py:148-166`, `@dataclass(frozen=True)`): add `env_allow:
  frozenset[str] | None = None`. Every `HostInvocation(...)` construction site inside each
  runner class's `build_streaming`/`build_blocking_json`/`build_detached` needs to pass this
  through (not every consumption site — those just read `.env`/`.binary`/`.args`).
- `env: dict[str, str]` on `HostInvocation` keeps its existing additive/override-only contract
  unchanged — do not repurpose it (see ENH-3203 Open Decision #4).

### Call Path
`resolve_host()` → `build_*()` → `HostInvocation` (now carrying `env_allow`) → `project_child_env()`
(deny-capable) → `subprocess.*`

### Baseline derivation (AC4)
The baseline must **not** be guessed. `bash -c` actions in this repo run pytest, git, ruff, and
`gh`; they depend on `VIRTUAL_ENV`, `PYTHONPATH`, `SSH_AUTH_SOCK` (git push over SSH fails
without it), `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`, `PYENV_ROOT`, `HOMEBREW_*`, `XDG_*`, `SHELL`,
`TERM`, `TZ`, in addition to `PATH`/`HOME`/`USER`/`LANG`/`TMPDIR`/`LL_*`. Derive it empirically:
run this repo's own `loops/*.yaml` under the report-only mode built here, diff variables
actually read against the candidate baseline, and justify each addition in a comment next to the
set.

### Failure polarity (AC3)
The one existing analog, `CapabilityNotSupported(UserWarning)` (`host_runner.py:109-117`), is
warn-and-drop at every site (`warnings.warn(..., CapabilityNotSupported, stacklevel=N)`). AC3
requires the opposite polarity for an undeclared-capability-name-vs-registry mismatch — decide
directly-raise vs. `warnings.simplefilter("error", ...)` promotion as part of this issue (this
resolves ENH-3203's Open Decision #3, which is otherwise unresolved).

### Logging (AC6)
`scripts/little_loops/host_runner.py` has no existing `logging` import or `logger` — this
introduces `logging` fresh into the module; there is no in-module precedent to match (nearest
same-module signaling precedent is the `warnings.warn` shape used for `CapabilityNotSupported`,
which is a different mechanism and stays as-is for AC3).

## Acceptance Criteria

- **AC2.** The projection helper projects a declared `env_allow` into the child environment at
  invocation; a variable not in the allow-set is *absent from the child process*, not merely
  discouraged. Covered by direct calls to `project_child_env(invocation, ...)` — no consumer
  surface required.
- **AC3.** Resolving a capability name not in the known-capability registry fails loudly at
  resolve time, naming the capability.
- **AC4.** A fixed baseline set of non-credential variables is always inherited regardless of
  declaration, empirically derived per "Baseline derivation" above with each addition justified
  in a comment next to the set.
- **AC5.** `invocation.env_allow is None` (no declaration) preserves today's full-inherit
  behavior exactly. `scripts/tests/test_host_runner.py::TestProjectChildEnv::test_no_args_is_full_inherit`
  (lines 94-98) and `TestProjectChildEnvCrossRunnerParity::test_matches_hand_rolled_merge`
  (lines 145-152) must keep passing **unmodified** — if either needs to change, deny-by-default
  has leaked into the no-declaration case.
- **AC6.** Denied variable names are logged at DEBUG level (names only, never values). The same
  code path in report-only mode produces the AC4 baseline evidence.
- **AC8 (partial — full close in ENH-3234/ENH-3235).** `python -m pytest scripts/tests/` exits 0
  for this chokepoint's own tests, and this repo's own `loops/*.yaml` run green under report-only
  mode. Full AC8 (deny mode fully wired end-to-end) closes once ENH-3234 and ENH-3235 land.

## Program Design

### Signatures
- `build_streaming(*, prompt, working_dir=None, resume=False, agent=None, tools=None, model=None,
  automation_profile=None, disable_background_tasks=False, workspace_root=None) -> HostInvocation`
  (`host_runner.py:217-229`) — **do not** add a `scope=`/`env_allow=` kwarg here. That's nine
  keyword-only parameters already; threading scope through it means editing ~32 signatures (4
  build methods × 8 runner classes) for a value none of them interpret, and it puts the scoping
  decision inside the per-host runners — the one place it must not live, since `RunnerType.CMD`
  never calls `resolve_host()` at all (structurally excluded). Instead: the `env_allow` field is
  set on the constructed `HostInvocation` by whichever caller resolves the declaration
  (ENH-3234/ENH-3235's job), and `project_child_env()` reads it — this issue only needs
  `project_child_env()` and `HostInvocation` to support the field; it does not populate it from
  any real declaration.

### Codebase Research Findings

_Carried forward from ENH-3203's `/ll:refine-issue`/`/ll:wire-issue` passes — verify line numbers
before implementing, as they were already noted as drifted once:_

- `project_child_env()` call sites confirmed: with an `invocation` — `runner_spec.py:205,315`,
  `subprocess_utils.py:450` (the actual `subprocess.Popen(..., env=env)` call for the primary
  streaming path), `session_store/lifecycle.py:157`, `fsm/evaluators.py:1152,1370,1626`,
  `fsm/handoff_handler.py:130`, `learning_tests/extractor.py:134`, `cli/issues/decisions.py:815`,
  `parallel/worker_pool.py:812`. With no invocation (pure `os.environ` inheritance) —
  `fsm/runners.py:274`, `runner_spec.py:231` (`_run_cmd`), `worker_pool.py:105`,
  `cli/loop/_helpers.py:1670,2106`, `mcp_call.py:197`, `prepatch_check.py:290`,
  `worktree_utils.py:570`, `git_operations.py:728`. None of these sites need to change for this
  issue — they continue passing `env_allow=None` implicitly (via `HostInvocation`'s default) or
  no invocation at all, and get today's behavior.
- `HostCapabilities` (`host_runner.py:119-144`) is the closest existing "declared support" shape
  but is per-runner-class, not per-task — not reusable for the capability registry here, which
  needs to map capability names to env-var sets, a different shape entirely. The nearest shape
  precedent for a bare allow-set is a module-level `frozenset[str]` constant consulted via `in`
  (e.g. `MUTATING_TOOLS`, `mcp_server/policy.py:55-62`).

### Tests
- `scripts/tests/test_host_runner.py::TestAutomationProfileEnvAcrossRunners` (lines 52-84,
  current line numbers may have drifted) is the established table-driven, cross-all-runner-class
  pattern (BUG-3058 precedent) — new deny-mode tests should follow this shape, parametrized
  across `ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner` plus
  `OpenCodeRunner`/`PiRunner` stubs (tested individually, not through the parametrized table).
- New tests for: `env_allow` intersection semantics, baseline-always-present, capability-registry
  fail-loud, DEBUG logging of denied names, report-only mode diff output.
- No shared fixture exists for `HostInvocation` construction (`scripts/tests/conftest.py` has
  none) — follow the existing inline-keyword-construction convention.

### Documentation
- `docs/reference/API.md` — the `### project_child_env` section (~line 9621-9637) reproduces the
  docstring verbatim, including "this helper provides no way to clear or deny an inherited
  variable; that is deliberately out of scope (see ENH-3203)" — rewrite this line, it names this
  issue directly and goes stale the moment deny semantics land. The `### HostInvocation` section
  (~line 9437-9458) needs the new `env_allow` field added to the field table.
- `docs/ARCHITECTURE.md` — the `HostInvocation` table row (~lines 835-848) needs `env_allow`
  appended if the field list stays enumerated there.

## Scope Boundaries

Out of scope for this child (belongs to ENH-3234/ENH-3235 or is out of scope for the whole
ENH-3203 effort per its Scope Boundaries section):

- Populating `env_allow` from a real per-task declaration — no `ActionSpec` or `StateConfig`
  field exists yet; this issue only makes the chokepoint capable of honoring the field when set.
- Wiring either `bash -c` path (`fsm/runners.py:266`, `runner_spec.py::_run_cmd()`) to construct
  an `HostInvocation` with `env_allow` populated — that's ENH-3234 (action path) and ENH-3235
  (FSM path).
- Disk-backed/keyring-backed credentials, token minting, MCP server credentials, secrets
  management, `gh`/`sync.py` scoping (ENH-3205), audit persistence (ENH-3204) — unchanged from
  ENH-3203's Scope Boundaries.

## Impact

- **Priority**: P2 — matches parent; this is the load-bearing piece the other two children
  depend on.
- **Effort**: Medium — one module (`host_runner.py`), but the baseline must be empirically
  derived (report-only run + diff), not written, and the deny-by-default inversion at a ~18-call-site
  chokepoint is architectural, not mechanical.
- **Risk**: Medium — getting AC4's baseline wrong means a shell action dies on an unrelated-looking
  error once ENH-3234/ENH-3235 wire a declaration through; this issue's own report-only-mode
  testing against real `loops/*.yaml` is the mitigation, done before either consumer lands.
- **Breaking Change**: No — `env_allow=None` (the default) is a strict no-op for every existing
  call site.


## Blocks

- ENH-3234
- ENH-3235

## Status

**Open** | Created: 2026-08-17 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-08-17T16:32:34 - `bcf99734-092e-4d7b-9a71-2d6fb04c8246.jsonl`
