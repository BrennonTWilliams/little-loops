---
id: ENH-3184
title: Add per-task credential scoping to host_runner so scheduled agents hold only
  what their task needs
type: ENH
priority: P2
status: open
testable: true
discovered_date: '2026-08-15'
labels: []
confidence_score: 85
outcome_confidence: 48
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
decision_needed: true
---

## Summary

`host_runner` passes broad credentials today. `--cwd` isolates the working directory, but the token scope is coarse: a scheduled agent doing a docs sweep holds the same authority as one opening pull requests.

Add per-task credential scoping. A runner spec declares which secrets and capabilities the task actually needs, and `host_runner` restricts the child process to exactly that set at invocation time — the operational pattern of a fine-grained PAT scoped to one repository with read+write on Issues and nothing else.

**Scope decision (v1 = projection, not minting).** "Restricts" above has two possible mechanisms that differ by an order of magnitude, and this issue implements only the first:

1. **Env projection (in scope).** Deny-by-default construction of the child environment: the child receives only the credential variables its declaration names, plus a fixed baseline. Purely local, no provider integration, and fully satisfies AC2 — an undeclared credential is genuinely absent from the child process.
2. **Token minting (out of scope; file separately if wanted).** Exchanging a broad credential for a genuinely narrower provider-side one (GitHub App installation tokens, AWS STS `AssumeRole`). Requires per-provider integration and credential-exchange plumbing that does not exist anywhere in this codebase — `_active_oauth_token()` (`host_runner.py:2064-2076`) only *selects* among ambient vars, it does not mint.

Prose in this issue that reads as minting ("scoped token") means projection unless stated otherwise.

## Current Behavior

Every child process spawned for automation inherits the parent's full environment, including every credential the operator happens to have loaded.

- `HostInvocation.env` is documented and implemented as **override-only**: each spawn site does `os.environ.copy()` (or `{**os.environ, **inv.env}`) and merges the invocation's keys on top. Absence of a key means "inherit the parent's value" — there is no way to express "clear" or "deny."
- The per-host `build_*()` methods add only orchestration signals (`LL_NON_INTERACTIVE`, `LL_AUTOMATION`, `GIT_DIR`/`GIT_WORK_TREE`) via `_apply_automation_env()` (`host_runner.py:1784-1799`). None of them constrain which credential variables reach the child.
- Twelve independent spawn sites hand-roll the child environment (census in the Integration Map), and the overwhelming majority of the package's **145** `subprocess.run`/`Popen`/`check_output`/`call` sites pass no `env=` at all and inherit implicitly.
- `DefaultActionRunner`'s shell branch (`fsm/runners.py:266`) runs `bash -c <action>` with the operator's complete ambient environment. **This — not `runner_spec.py::_run_cmd()` — is how FSM loops do their real work**, including every `gh` invocation from a loop.
- The LLM-judge path (`fsm/evaluators.py:1139`, `1332`, `1584`) spawns the host CLI with no `env=` on every `llm_structured` / blind-comparator / contract evaluation — the single highest-volume credential-bearing spawn in the system.
- `gh` operations (`sync.py`) bypass `host_runner` entirely and use the ambient `gh auth login` session, which is repo- or org-broad.
- Nothing anywhere records what authority a given run held.

Net: a scheduled docs-sweep agent and a scheduled release agent run with identical, unbounded authority. `--cwd` bounds where they work, not what they can reach.

## Expected Behavior

A runner spec declares the credentials and capabilities its task needs. At invocation, a single shared helper constructs the child environment deny-by-default: the declared credentials plus a fixed non-credential baseline, and nothing else. An undeclared credential variable is genuinely absent from the child process — for host-CLI paths and `bash -c` shell actions alike.

A spec declaring a capability the registry doesn't know fails at resolve time, naming it. Specs with no declaration keep today's coarse behaviour behind a deprecation path, so nothing in flight breaks. Each run records the capability names it was granted (names only, never values), so an audit can answer after the fact what a given run could reach.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `HostInvocation` is documented as override-only: its `env` dict is merged over a full copy of the parent process's environment at every spawn site (class docstring). Per-host `build_streaming()`/`build_blocking_json()`/`build_detached()` (`ClaudeCodeRunner`, `CodexRunner`, `GeminiRunner`, `OmpRunner`, `KimiRunner`, `QwenRunner`) only ever add orchestration-signal keys (`LL_NON_INTERACTIVE`, `LL_AUTOMATION`, `GIT_DIR`/`GIT_WORK_TREE`, etc. via `_apply_automation_env()`, lines 1784-1799) — none constrain which ambient credential vars (`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, cloud SDK creds) reach the child.
- `scripts/little_loops/runner_spec.py` — `ActionSpec` (frozen dataclass: `name`, `runner`, `target`, `args: dict[str, Any]`, `timeout`) is the only "spec" object in this path but carries no capability/secret declaration field. `_run_prompt()` (line 304) passes no `env=` kwarg to `subprocess.run()` at all, so the child gets Python's default full parent-environment inheritance with zero `HostInvocation.env` overlay.
- **`scripts/little_loops/fsm/runners.py::DefaultActionRunner` shell branch (line 266) — the largest exposure, and the one an earlier draft of this issue misattributed.** It runs `subprocess.Popen(["bash", "-c", action], cwd=..., start_new_session=True)` with **no `env=` kwarg and no `HostInvocation` at any point**. This is the `bash -c` path every FSM loop's shell action takes — `runner_spec.py` is *not* imported by `fsm/executor.py` at all (its only importers are `cli/action.py`, `cli/queue.py`, `cli/harness.py`, i.e. `ll-action`/`ll-queue`/`ll-harness`). Covering this path is mandatory; AC8 is meaningless without it.
- **`scripts/little_loops/fsm/evaluators.py:1139, 1332, 1584` — host-CLI spawns with no `env=`.** `evaluate_llm_structured()`, `evaluate_blind_comparator()`, and the `contract` evaluator each do `subprocess.run([invocation.binary, *args], ...)` and **discard `invocation.env` entirely** — they never merge it. Every `llm_structured` evaluation in every loop spawns a host CLI holding the full ambient environment. Highest-volume credential-bearing spawn in the system, and absent from the original census. (`evaluators.py:637` is a lower-stakes implicit-inherit `git diff` spawn in the same file.)
- `scripts/little_loops/runner_spec.py::_run_cmd()` (line 215) — same `bash -c`, no-`env=`, never-calls-`resolve_host()` shape as `fsm/runners.py:266`, but on the `ll-action`/`ll-queue`/`ll-harness` path rather than the FSM-loop path. Real, and in scope for AC8 — just not the dominant one.
- `scripts/little_loops/cli/loop/_helpers.py:1659` (detached `ll-loop` self-spawn, no `env=`) and `:2101` (`dict(os.environ)` + `LL_HOST_CLI` override for cross-host runs) — **launcher** sites that re-exec `ll-loop` itself. Projection must either survive the re-exec or be re-applied by the child; a scope enforced only in the parent evaporates here.
- `scripts/little_loops/subprocess_utils.py:450` — `run_claude_command()` does `env = os.environ.copy(); env.update(invocation.env)` — the primary streaming path for FSM loops, `ll-parallel`, `ll-sprint`.
- `scripts/little_loops/parallel/worker_pool.py:812` — `_detect_worktree_model_via_api()` uses the identical `os.environ.copy()` + `env.update(invocation.env)` merge for per-worktree probe calls.
- `scripts/little_loops/fsm/handoff_handler.py:131` — `env={**os.environ, **invocation.env}` merge site.
- `scripts/little_loops/mcp_call.py:197` — `env = os.environ.copy()` then updates before the MCP subprocess call.
- `scripts/little_loops/worktree_utils.py:568` — `env: dict[str, str] = os.environ.copy()`; hand-rolled child env, not covered by the five sites originally surveyed.
- `scripts/little_loops/learning_tests/extractor.py:135` — `env={**os.environ, **inv.env}`; hand-rolled child env, not covered by the five sites originally surveyed.
- `scripts/little_loops/session_store/lifecycle.py:158` — `env={**os.environ, **inv.env}`; hand-rolled child env, not covered by the five sites originally surveyed.
- `scripts/little_loops/sync.py` — `_run_gh_command()`/`_check_gh_auth()` bypass `host_runner.py` entirely; `gh` operations rely on the ambient `gh auth login` session (repo/org-broad), with no per-task token minted or injected anywhere in this file. **Env projection alone does not de-scope `gh`:** its credential lives in the OS keyring / `~/.config/gh/hosts.yml`, not in `GITHUB_TOKEN`, so removing that variable from the child leaves the broad session fully usable. Constraining `gh` requires injecting an explicit `GH_TOKEN` *and* redirecting `GH_CONFIG_DIR` to a per-task directory so the ambient login is not visible. Either do both or state explicitly that `gh` is out of scope for v1.

**Spawn-site census (re-derived 2026-08-15, second pass — the first pass was both undercounted and miscategorised).**

The census must be taken over `subprocess.(run|Popen|check_output|call)`, **not** over `os.environ.copy()`. Grepping for env-construction finds only the sites that build an environment; it structurally cannot find the sites that build *none*, which are the majority and include the two largest exposures. The first pass grepped for env construction and therefore missed `fsm/runners.py:266` and `fsm/evaluators.py:1139/1332/1584` entirely while promoting `runner_spec.py::_run_cmd()` to "largest exposure" on the strength of a call path the FSM executor does not use.

- **Explicit hand-rolled child env — 12 sites** (was 8): `host_runner.py:1837`, `worktree_utils.py:568`, `git_operations.py:722`, `mcp_call.py:197`, `prepatch_check.py:287`, `subprocess_utils.py:450`, `runner_spec.py:206`, `parallel/worker_pool.py:812`, `fsm/handoff_handler.py:131`, `cli/loop/_helpers.py:2101`, `learning_tests/extractor.py:135`, `session_store/lifecycle.py:158`. Note four of these use `dict(os.environ)` rather than `os.environ.copy()` or `{**os.environ}` — a guard matching only the latter two forms misses a third of the explicit sites.
- **Implicit inheritance (no `env=` kwarg) — the dominant category.** The package contains **145** `subprocess.(run|Popen|check_output|call)` call sites in total; all but the 12 above inherit implicitly. Not every one is on a task path, but the two that matter most are: `fsm/runners.py:266` and `fsm/evaluators.py:1139/1332/1584`. `runner_spec.py::_run_cmd()`/`_run_prompt()` are also here.

Consequence for AC6: **an `os.environ.copy()`-shaped lint is the wrong guard.** It would have passed clean on a tree where the FSM shell path and the entire LLM-judge path leak everything. The guard must key on spawn calls in task paths that lack an `env=` derived from the projection helper — a harder lint, specified in AC6.

The census has now grown twice under review (8 → 12 explicit, plus an uncounted implicit majority). That track record is itself the argument for landing split (a) first: centralization with zero behaviour change, proven by the guard, before any deny-by-default semantics are switched on.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py`, `scripts/little_loops/fsm/evaluators.py` — dispatch actions through `host_runner`/`run_action()`.
- `scripts/little_loops/cli/action.py`, `scripts/little_loops/cli/harness.py`, `scripts/little_loops/cli/loop/run.py`, `scripts/little_loops/cli/parallel.py`, `scripts/little_loops/cli/sprint/run.py` — all invoke `resolve_host()`/`run_action()` for scheduled/unattended work.

### Conventions in Force
- Feature-capability declarations use a frozen dataclass of booleans set once per runner class (`HostCapabilities`, `host_runner.py:119-144`, e.g. `streaming`, `tool_allowlist`, `workspace_sandboxed`) — per-runner, not per-task. This is the closest existing analog to "declare a capability set," but its granularity (per host, not per invocation) doesn't fit AC1's "a runner spec can declare the capability set a task requires."
- An undeclared/unsupported capability today triggers `CapabilityNotSupported(UserWarning)` (`host_runner.py:108-116`) — a warn-and-drop, not a hard failure (module docstring notes it can be promoted via `warnings.simplefilter("error", CapabilityNotSupported)` for strict contexts). This is the opposite polarity from AC3 ("fails loudly, naming the capability"); no existing hard-fail-on-undeclared-capability path exists in this module to build on.
- Per-task capability declaration living in loop YAML already has one precedent: the `tools:` allowlist field (`fsm-loop-schema.json:590-596`, `fsm/schema.py:684`) is a per-*state* (not per-runner-class) field that flows into `HostRunner.build_streaming(tools=...)` — the same call surface this issue targets. Some runners honor it (`ClaudeCodeRunner`), others decline it with a `CapabilityNotSupported` warning.
- Staged-rollout precedent for AC5 ("existing runner specs without a declaration keep working... deprecation path"): `suppress_catalog` (`fsm-loop-schema.json:415-419`, `fsm/schema.py:457-460`) lands a schema field explicitly marked `"DECLARATIVE-ONLY (not yet implemented)"` in both the JSON Schema description and the Python dataclass docstring, enforced only by a validator warning (MR-12) until a runtime consumer exists.
- Deprecation in this codebase is documented via a `[DEPRECATED: ...]` text marker in the JSON Schema `description` plus a matching inline comment (`config-schema.json:113,118`; `config/features.py:209-210`) — not the JSON Schema `"deprecated": true` keyword and not a `warnings.warn(DeprecationWarning, ...)` call at read time (no corroborated example of the latter was found in `config/core.py` despite a docstring claim attributing it there).
- `_apply_automation_env()` (`host_runner.py:1784-1799`) is the one existing shared per-runner env-injection helper, and documents the "absence in `env` means inherit the parent's value, never clear" contract explicitly — a new scoped-credential helper needs to state its own contract (allow/deny/inherit) just as explicitly, since it changes that default.
- No token-minting/narrowing utility exists anywhere in this module today. `_active_oauth_token()` (`host_runner.py:2064-2076`) only *selects* among ambient env vars by precedence order (a read-only probe of `os.environ`) — it does not mint or scope a credential.

### Tests
- `scripts/tests/test_host_runner.py` — `TestAutomationProfileEnvAcrossRunners` (lines 52-84) is the established table-driven, cross-all-runner-classes pattern (cited "BUG-3058 precedent" for why per-runner env behavior must be tested this way, to avoid drift). New credential-scoping tests should follow this same shape, parametrized across `ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner` plus the `OpenCodeRunner`/`PiRunner` stubs (which raise `HostNotConfigured` before building any env).
- `scripts/tests/test_runner_spec.py`, `scripts/tests/test_subprocess_utils.py` — existing coverage for the two other env-merge call sites that would need equivalent tests.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

Findings above (Files to Modify, Dependent Files, Conventions in Force, Tests) are the result of this pass's `codebase-locator`, `codebase-analyzer`, and `codebase-pattern-finder` research.

## Motivation

Per-task scoping is a distinct axis from `--cwd`'s per-repo working directory, on the same runner. It matters for three reasons: a narrower scope is easier to audit; an over-broad scope hides failure modes until the run that exploits it; and an unattended agent holding write authority it never needed is the kind of exposure that is cheap to prevent and expensive to explain.

This becomes load-bearing wherever a scheduled agent touches a system whose credentials cannot be casually over-granted.

## Acceptance Criteria

- **AC1.** A runner spec can declare the capability set a task requires.
- **AC2.** `host_runner` projects that declaration into the child environment at invocation; an undeclared credential variable is *absent from the child process*, not merely discouraged.
- **AC3.** A runner spec declaring a capability that is not in the known-capability registry fails loudly at resolve time, naming the capability.
  - _Reworded from "a task requesting a capability outside its declaration fails loudly."_ `host_runner` cannot observe an LLM deciding to shell out to `gh pr create`; there is no interception point, and the original wording invited an implementation that cannot exist. What is actually observable is a **declaration-vs-registry** mismatch at spec-resolution time. The runtime consequence of a task reaching for an undeclared credential is that the credential is absent and the child fails on its own terms — an opaque downstream failure, by design. If a loud runtime failure is genuinely wanted, it needs a wrapper that intercepts the child's credential reads, which is a separate and much larger piece of work.
- **AC4.** The declared scope is recorded with the run, so an audit can answer what authority a given run actually held. The record stores **capability and variable *names* only — never values**, and the issue must name the destination before implementation (candidate: a column on the existing `loop_events` ledger, or a new `.ll/history.db` table; unresolved — see Open Decisions).
- **AC5.** Existing runner specs without a declaration keep working, with the coarse behaviour and a deprecation path.
- **AC6.** No spawn site constructs the child environment by hand. A single shared projection helper is the only place a child env is built.
  - The guard test must key on **spawn calls, not env construction**: it enumerates `subprocess.(run|Popen|check_output|call)` sites in task paths and fails on any whose `env=` does not come from the projection helper — including sites that pass **no `env=` at all**. An `os.environ.copy()`-shaped guard is explicitly insufficient and must not be shipped as the AC6 test: it passes clean on today's tree while `fsm/runners.py:266` and `fsm/evaluators.py:1139/1332/1584` leak the full environment. It also misses the four `dict(os.environ)` sites.
  - Because a whole-package spawn lint over 145 sites is impractical to land green in one step, the guard is scoped to an explicit **task-path allowlist** of modules (at minimum: `fsm/runners.py`, `fsm/evaluators.py`, `runner_spec.py`, `subprocess_utils.py`, `mcp_call.py`, `worktree_utils.py`, `parallel/worker_pool.py`, `fsm/handoff_handler.py`, `learning_tests/extractor.py`, `session_store/lifecycle.py`, `git_operations.py`, `prepatch_check.py`, `cli/loop/_helpers.py`), with the allowlist itself asserted so adding a module to a task path without adding it to the guard fails.
- **AC6b.** `fsm/evaluators.py`'s three host-CLI spawns merge `invocation.env` before spawning. They discard it entirely today, which is a pre-existing bug independent of scoping: `LL_AUTOMATION`, `LL_NON_INTERACTIVE`, and every other orchestration signal `_apply_automation_env()` computes never reach the LLM judge. Fixing this is a prerequisite for projection on that path, and should be verified not to change judge behaviour on its own.
- **AC7.** A fixed baseline set of non-credential variables is always inherited regardless of declaration. Deny-by-default without this strips `PATH`/`HOME` and the host binary fails to launch at all. The helper documents its allow/deny/inherit contract as explicitly as `_apply_automation_env()` documents its "absence means inherit" contract, since it inverts that default.
  - **The baseline named in earlier drafts (`PATH`, `HOME`, `USER`, `LANG`, `TMPDIR`, `LL_*`) is too small and must not be shipped as-is.** `bash -c` actions in this repo run pytest, git, ruff, and `gh`; those depend on `VIRTUAL_ENV`, `PYTHONPATH`, `SSH_AUTH_SOCK` (git push over SSH fails without it), `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`, `PYENV_ROOT`, `HOMEBREW_*`, `XDG_*`, `SHELL`, `TERM`, `TZ`. A too-narrow baseline does not fail loudly — it produces a shell action that dies on an unrelated-looking error.
  - The baseline is therefore **empirically derived, not guessed**: run this repo's own `loops/*.yaml` under projection in report-only mode (AC9), diff the variables actually read against the candidate baseline, and justify each addition in a comment next to the set.
- **AC8.** Every `bash -c` path is covered by the same projection as the host-CLI paths, with a test per path proving an undeclared credential variable is absent from a shell action's environment. There are **two**, and covering only the second leaves FSM loops — the primary consumer — unscoped:
  1. `fsm/runners.py:266` (`DefaultActionRunner` shell branch) — the FSM-loop path. Mandatory.
  2. `runner_spec.py::_run_cmd()` — the `ll-action`/`ll-queue`/`ll-harness` path. **Projection applies only where a declaration is present** — consistent with AC5, a spec with no declaration gets today's full-inheritance behaviour on the CMD path too. Deny-by-default is a property of *declared* specs, not a global flip; the alternative silently breaks every existing shell action in every local-editable project on this machine at once.
- **AC9.** When projection denies a variable, the helper logs the denied variable **names** at DEBUG level (names only, never values — same rule as AC4). AC3's rationale deliberately accepts that a task reaching for a stripped credential fails opaquely on its own terms; this AC keeps that runtime behaviour while making the cause recoverable in one log line instead of an hour of bisection. The same code path in report-only mode is what produces the AC7 baseline evidence.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Types
- No existing credential/capability-scope dataclass exists to extend. The nearest shape is `HostCapabilities` (`host_runner.py:119-144`, frozen dataclass of booleans, e.g. `streaming: bool`, `tool_allowlist: bool`) — but it is per-runner-class, not per-task, and describes host feature support, not required secrets.
- `ActionSpec` (`runner_spec.py`, frozen dataclass: `name: str`, `runner: RunnerType`, `target: str`, `args: dict[str, Any]`, `timeout: float | None`) is the only per-task spec object in this call path; it has no field for a capability/secret declaration today.

### Signatures
- `build_streaming(*, prompt, working_dir=None, resume=False, agent=None, tools=None, model=None, automation_profile=None, disable_background_tasks=False, workspace_root=None) -> HostInvocation` — the call surface every per-host runner implements (`host_runner.py:217-229`). Note this is **nine keyword-only parameters**, not the three-parameter abbreviation cited in earlier drafts.
- **Do not thread the scope declaration through `build_*()`.** Adding a `scope=` kwarg means editing ~32 signatures (4 build methods × 8 runner classes) to pass a value none of them interpret, and it puts the scoping decision inside the per-host runners — the one place it must *not* live, since `RunnerType.CMD` (AC8) never calls `resolve_host()` at all and would be structurally excluded. Per Open Decision #5, the allow-set is a new `HostInvocation` field (e.g. `env_allow: frozenset[str] | None`) populated by the shared projection helper at spawn time, so the helper is the single chokepoint for both host-CLI and `bash -c` paths and the runner classes stay unchanged.
- `env: dict[str, str]` — the `HostInvocation` field that is currently additive-only ("merge `env` into the child process environment"); AC2 ("an undeclared capability is unavailable at runtime, not merely discouraged") requires this to become allow/deny-capable rather than purely additive.
- `_apply_automation_env(env: dict[str, str], automation_profile: str | None)` — the one existing shared per-runner env-injection helper (`host_runner.py:1784-1799`); its "absence means inherit" contract is what a new scoping helper must either match or explicitly override.

### Call Path
`resolve_host` -> `build_streaming` -> `env` -> `run_claude_command`

### Decision Rules
- Gate: a task's declared capability set (AC1) vs. the capability the runner spec actually requests at invocation (AC3). Exact inputs: no existing schema field carries this declaration — `ActionSpec.args` and the FSM `tools:` field are the closest per-task precedents but neither expresses "declare a secret/capability," only "declare a tool-allowlist."
- Escape hatch (AC5): existing runner specs without a declaration must keep working with today's coarse (unscoped) behavior. This codebase's established staged-rollout pattern for exactly this situation is `suppress_catalog`'s `"DECLARATIVE-ONLY (not yet implemented)"` marker (`fsm-loop-schema.json:415-419`) paired with a validator-only warning (MR-12) until enforcement lands — a candidate shape for AC5's deprecation path, not a mandated one.
- Failure polarity (AC3, "fails loudly, naming the capability"): the codebase's one existing analog, `CapabilityNotSupported(UserWarning)` (`host_runner.py:108-116`), is warn-and-drop by default, not a hard failure — AC3 requires the opposite polarity, and no existing hard-fail path in this module can be reused as-is; whether the new failure raises directly or is promoted via `warnings.simplefilter("error", ...)` is unresolved by the issue text.

## Open Decisions

Resolve these before writing code; each changes what gets built.

1. **Mechanism — settled.** v1 is env projection, not token minting (see Summary). If minting is wanted, file it as its own issue; it is provider-specific work with no existing foothold in this module.
2. **Is `gh` in scope for v1?** Env projection alone cannot constrain it (keyring-backed session). Either implement `GH_TOKEN` + `GH_CONFIG_DIR` isolation, or declare `gh`/`sync.py` explicitly out of scope so the issue doesn't imply coverage it won't deliver. Leaving this ambiguous is how the largest hole ships open.
3. **Where does the AC4 audit record land?** No table is named today. `loop_events` is the closest existing per-run ledger; `harness_events`/`verdict_events` are wrong-shaped. Note that `SCHEMA_VERSION` is currently **40** (`session_store/schema.py:21`), so a new migration is **v41**.
4. **Does the declaration live on `ActionSpec`, in loop YAML per-state, or both?** The `tools:` allowlist (`fsm-loop-schema.json:590-596`) is the per-state precedent; `ActionSpec` is the per-task object. AC1 says "runner spec," which maps to `ActionSpec`, but FSM states are where authors actually write things down.
5. **`HostInvocation.env` must not be repurposed.** Its documented contract is additive/override-only ("absence means inherit"), relied on at all 8 spawn sites. Deny capability needs a *new* field (e.g. `env_allow: frozenset[str]`), not a semantic change to `env` — changing `env` in place is a breaking behavioural change across every spawn site simultaneously.

## Sizing note

With AC6 (centralize 12 explicit sites plus the implicit-inherit task paths), AC6b (the `evaluators.py` `invocation.env` fix), AC7 (baseline contract), and AC8 (two `bash -c` paths), this is materially larger than a single-file enhancement — and larger than the first draft assumed, since the census grew on re-verification.

**The split is now recommended rather than contingent.** Land (a) alone first:

- **(a) Centralization, zero behaviour change.** One projection helper; every task-path spawn routed through it; AC6's guard armed; AC6b's `invocation.env` fix. Ships a provable invariant with no deny semantics and therefore no way to break a shell action. This is the step that makes everything after it safe, and it is independently worth having.
- **(b)** Declaration field + registry + AC2/AC3 enforcement + AC9 report-only mode (which produces AC7's empirical baseline).
- **(c)** AC4 audit persistence (migration v41).
- **(d)** `gh` scoping, if Open Decision #2 resolves it in.

Doing (a) and (b) as one change means switching on deny-by-default across a spawn-site map that has already been wrong twice.

## Scope Boundaries

**What "scoped" does and does not mean.** Env projection restricts what the child can see **in its environment block**. It does not restrict what the child can read **from disk**, and AC7 inherits `HOME`. So every file-backed credential on the machine remains fully reachable from a fully-scoped child: `~/.aws/credentials`, `~/.claude/.credentials.json`, `~/.config/gh/hosts.yml`, `~/.netrc`, `~/.ssh/`, the macOS keychain, and any ambient agent socket in the AC7 baseline (`SSH_AUTH_SOCK`).

The issue states this only about `gh` (Open Decisions #2), but it is the general case, and it is the difference between what AC2 says and what AC2 delivers. AC2's "an undeclared credential variable is *absent from the child process*" is exactly true of **variables** and materially false of **credentials**. Whoever implements this should not describe the result as sandboxing a task's authority; the honest claim is that it stops env-borne credentials from propagating by accident. Constraining disk-backed credentials needs `HOME` redirection to a per-task directory, which is a much larger change with its own breakage surface (every tool that reads user config) and is not attempted here.

Explicitly **out of scope**:

- **Disk-backed and keyring-backed credentials.** See above. No `HOME` redirection, no per-task config directories (except the conditional `GH_CONFIG_DIR` case in Open Decisions #2), no keychain scoping.
- **Token minting / credential exchange.** No GitHub App installation tokens, no AWS STS `AssumeRole`, no provider-side narrowing of any kind. v1 restricts what the child can *see*, not what the credential can *do*. File separately if wanted.
- **Runtime interception of credential use.** No wrapper that observes the child reading a variable or shelling out to `gh`. A task reaching for an undeclared credential fails on its own terms, opaquely, because the credential is absent — that is the designed consequence, not a gap to close here (see AC3).
- **Secrets management.** No vault integration, no encrypted-at-rest secret store, no rotation. Credentials still arrive via the operator's ambient environment; this issue only decides which of them propagate.
- **MCP server credentials.** `mcp_call.py` is listed as a spawn site for AC6 centralization only; scoping the credentials MCP servers themselves hold is separate work.
- **`gh` / `sync.py` scoping** is *conditionally* out of scope — see Open Decisions #2. If `GH_TOKEN` + `GH_CONFIG_DIR` isolation is not implemented, the issue must say so rather than imply coverage.
- **Retrofitting declarations onto existing loops.** AC5 keeps undeclared specs working; migrating the repo's own `loops/*.yaml` to declare scopes is follow-on work.

## Impact

- **Priority**: P2 — a real exposure, but a latent one: it becomes load-bearing when a scheduled agent touches a system whose credentials can't be casually over-granted. Nothing is broken today, and no current run is known to have exploited the over-broad scope. Not P1 because there is no active incident; not P3 because the cost of adding it grows with every new spawn site (three appeared since the first survey).
- **Effort**: Large — 12 explicit spawn sites plus the implicit-inherit task paths to centralize, a declaration field, a capability registry, two `bash -c` paths, the `evaluators.py` `invocation.env` fix, an audit record with a new schema migration, and cross-runner tests over 8 runner classes. The Sizing note's 4-way split is now the recommended path, not a fallback.
- **Risk**: High — deny-by-default on process environments is the kind of change that fails closed in production. Getting AC7's baseline set wrong means a shell action dies on an unrelated-looking error (missing `VIRTUAL_ENV`, `SSH_AUTH_SOCK`, a proxy var), not a clean "credential denied"; missing a spawn site means the guarantee is silently false. **The census having been wrong twice is the load-bearing risk fact here**: the first pass missed the FSM shell path and the entire LLM-judge path because it grepped for env construction rather than for spawns, so any confidence that the map is now complete should be treated as provisional until AC6's guard is armed and green. Both failure modes are worse than the status quo, because they look like protection that isn't there. A third, quieter risk is *overclaiming*: shipping this and describing tasks as authority-scoped when every disk-backed credential is still readable (see Scope Boundaries). Mitigations: land the centralization step (a) with zero behaviour change first and prove all 8 sites route through one helper; derive the AC7 baseline from a report-only run over this repo's own loops (AC9) rather than by guessing; keep projection opt-in per declared spec (AC8) so undeclared specs cannot regress.
- **Breaking Change**: No — AC5 preserves coarse behaviour for undeclared specs. But note that any change to `HostInvocation.env`'s documented "absence means inherit" contract *would* be breaking across all 8 sites at once, which is why Open Decisions #5 requires a new field instead.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-15_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 48/100 → LOW

### Concerns
- Architecture Compliance (15/20): the design requires genuinely new machinery — a capability registry, a new `HostInvocation.env_allow`-style field, and a hard-fail-on-unknown-capability path with no existing precedent of that exact polarity in this module (`CapabilityNotSupported` today is warn-and-drop). The reasoning for each choice is sound and well-documented (Open Decision #5 explicitly rules out repurposing `env`), but it's new shape, not a drop-in extension of an existing pattern.
- Issue Well-Specified (10/20, capped): three of the five Open Decisions are explicitly unresolved and the issue itself states they must be resolved before writing code — (2) whether `gh`/`sync.py` is in scope for v1, (3) where the AC4 audit record lands (candidate: `loop_events` column vs new `.ll/history.db` table, migration v41), and (4) whether the capability declaration lives on `ActionSpec`, in loop YAML per-state, or both. Only (1) and (5) are settled.
- Outcome confidence is LOW (48/100), driven by: Complexity 10/25 (8 spawn sites to centralize plus a new schema migration and registry — moderate depth, 6-15 site breadth), and Change Surface 10/25 (8 spawn sites is a genuine Pattern A blast radius, not a uniform mechanical substitution — each site's fix differs: some need only a helper call, `_run_cmd` needs new env= wiring from scratch, one file needs a schema migration).

### Outcome Risk Factors
- Deep per-site complexity risk: AC7's baseline env set (`PATH`, `HOME`, `VIRTUAL_ENV`, `SSH_AUTH_SOCK`, proxy vars, etc.) is explicitly "empirically derived, not guessed" per the issue — getting it wrong doesn't fail loudly, it makes an unrelated shell action die mysteriously (missing `SSH_AUTH_SOCK` breaks `git push` over SSH, missing a proxy var breaks network calls). This is the single highest-consequence failure mode named in the issue's own Risk section.
- Broad enumeration across sites risk: 8 independently hand-rolled spawn sites (verified exact via codebase grep: `subprocess_utils.py:450`, `parallel/worker_pool.py:812`, `fsm/handoff_handler.py:131`, `mcp_call.py:197`, `worktree_utils.py:568`, `learning_tests/extractor.py:135`, `session_store/lifecycle.py:158`, `runner_spec.py:206`, plus `_run_cmd`/`_run_prompt` with no `env=` at all) must all be centralized through one helper (AC6) with a test that fails on any new raw construction — a missed site silently defeats the entire guarantee.
- Adjacent gap discovered during this check (not previously flagged in the issue): `runner_spec.py::_run_prompt()` (line 304) calls `resolve_host().build_blocking_json(...)` and receives a computed `HostInvocation.env`, but never merges it into the `subprocess.run()` call at all — unlike `_run_skill`, which does `env={**os.environ, **inv.env}`. Today this means `_run_prompt` invocations get zero runner-computed env (not even `LL_AUTOMATION`). Worth deciding explicitly whether AC6's centralization also fixes this pre-existing gap or scopes around it.

## Session Log
- Pre-implementation review (second pass) - 2026-08-15 - **corrected the largest-exposure misattribution**: `fsm/runners.py:266` (`DefaultActionRunner` shell branch), not `runner_spec.py::_run_cmd()`, is the `bash -c` path FSM loops use — `runner_spec` is not imported by `fsm/executor.py` at all. Added `fsm/evaluators.py:1139/1332/1584` (host-CLI spawns that discard `invocation.env` entirely) and `cli/loop/_helpers.py:1659/2101` (launcher re-exec). Re-derived the census over `subprocess.*` instead of `os.environ.copy()`: 12 explicit sites (was 8), 145 total spawn sites, implicit inheritance dominant. Rewrote AC6's guard to key on spawns rather than env construction, added AC6b, expanded AC8 to both `bash -c` paths, promoted the 4-way split to recommended.
- `/ll:confidence-check` - 2026-08-15T20:37:09 - `418ba343-3272-4147-b043-1745e73ae713.jsonl`
- `/ll:refine-issue` - 2026-08-15T19:46:44 - `ccda3253-f4ab-44ac-a167-7fd374e66499.jsonl`
- Pre-implementation review - 2026-08-15 - corrected the `build_streaming` signature (9 kwargs, not 3) and ruled out threading scope through `build_*()` as contradicting Open Decision #5; scoped AC8's projection to declared specs only; replaced AC7's guessed baseline with an empirically-derived one; added AC9 (DEBUG log of denied names, report-only mode); named the disk-backed-credential limitation in Scope Boundaries so AC2 is not read as authority sandboxing. Spawn-site census re-verified: 8 sites, exact.

## Status

**Open** | Created: 2026-08-15 | Priority: P2
