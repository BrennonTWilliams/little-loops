---
id: ENH-3395
type: ENH
title: Deny-by-default env projection chokepoint and baseline
priority: P2
status: done
parent: ENH-3233
epic: EPIC-3212
blocked_by: []
discovered_by: /ll:issue-size-review
discovered_date: '2026-09-07'
completed_at: '2026-09-07T19:17:17Z'
testable: true
decision_needed: false
verify_verdict: VALID
relates_to:
- ENH-3184
- ENH-3396
confidence_score: 100
outcome_confidence: 87
score_complexity: 19
score_test_coverage: 25
score_ambiguity: 23
score_change_surface: 20
---

# ENH-3395: Deny-by-default env projection chokepoint and baseline

## Summary

Give `project_child_env()` (the single chokepoint ENH-3184 centralized child-environment
construction behind) a deny-capable mode: a new `HostInvocation.env_allow: frozenset[str] |
None` field plus an explicit `env_allow` keyword on `project_child_env()` itself, a fixed
non-credential baseline (exact names + prefix families, guarded against credential-shaped
names) that survives regardless of declaration, DEBUG-level logging of denied variable names,
and a report-only mode that diffs real variable usage against the candidate baseline.

This is one of two sibling primitives decomposed from ENH-3233 ("chokepoint, capability
registry, and baseline"). The credential-scope registry (mapping scope names like `github` to
the env-var names they unlock) is ENH-3396 — a separate, independently testable primitive with
no runtime dependency on this issue: nothing in this decomposition calls the registry from
`project_child_env()`, and this issue's own `env_allow` frozenset is always supplied pre-resolved
(by a future caller, out of scope here — see Scope Boundaries). This issue is independently
testable and shippable on its own: call `project_child_env(invocation, env_allow=frozenset({...}))`
directly and assert the resulting dict.

## Parent Issue

Decomposed from ENH-3233: Deny-by-default env projection core — chokepoint, capability registry,
and baseline (itself decomposed from ENH-3203: Declare and enforce per-task credential scope via
deny-by-default env projection). This child covers the chokepoint mechanism and its always-on
baseline. The credential-scope registry is ENH-3396. Declaration-surface wiring for the two
`bash -c` paths remains out of scope here too, per ENH-3233's own Scope Boundaries — that's
ENH-3234 (`ActionSpec`/`runner_spec.py`) and ENH-3235 (FSM `StateConfig`/loop-YAML).

**Mechanism is env projection, not token minting** — see ENH-3203 Summary for the full framing;
that context is unchanged and not repeated here.

## Current Behavior

`project_child_env(invocation=None, *, extra=None)` (`scripts/little_loops/host_runner.py:1865-1896`,
ENH-3184's deliverable) is additive/override-only: `env = os.environ.copy(); env.update(invocation.env);
env.update(extra)`. There is no way to withhold a variable from the child. `HostInvocation`
(`host_runner.py:155-173`, frozen dataclass) has no field expressing an allow-set today.

`_apply_automation_env()` (`host_runner.py:1898-1917`) sets only `LL_AUTOMATION`/
`LL_AUTOMATION_PROFILE` in place and never deletes a key; its docstring already names ENH-3203
as the follow-on that changes this.

### Codebase Research Findings

_Carried forward from ENH-3233's `/ll:refine-issue` pass — 2026-09-03, re-verified 2026-09-03:_

`scripts/little_loops/host_runner.py` — `project_child_env()` at line 1865, `HostInvocation` at
line 156, `_apply_automation_env()` at line 1898, `HostCapabilities` at line 128,
`CapabilityNotSupported` at line 116. The module has no module-level `import os` or `import
logging` today — both are net-new for this issue's DEBUG-logging requirement.

`scripts/little_loops/worktree_utils.py` — BUG-3370 is `status: done`; its fix added
`env.pop("LL_PYTHON", None)` directly after the `project_child_env()` call in
`verify_epic_branch_before_merge()`, a call-site workaround rather than a chokepoint-level clear/
deny primitive. `project_child_env()` itself is unchanged by that fix, so the comment this issue
quotes there remains accurate.

`scripts/little_loops/mcp_server/policy.py` — `MUTATING_TOOLS`, the nearest existing bare
`frozenset[str]` allow-set precedent, is consulted via `tool_name in MUTATING_TOOLS` inside
`check_tool_call()`; it carries no per-entry metadata and no fail-loud-on-unknown-name behavior
— a shape precedent for a bare allow-set only, not for the credential-scope registry (see
ENH-3396 for that).

_Wiring pass added by `/ll:wire-issue` — 2026-09-07 (carried forward from ENH-3233):_

- **A second env-scrub workaround exists that this chokepoint cannot reach.**
  `scripts/little_loops/fleet_improve.py:111` does `env.pop("LL_AUTOMATION", None)` — same
  "descendant automation env leaks into a gate's pytest run" shape as the BUG-3370 workaround
  named above (`worktree_utils.py:730`) — but its `env` dict is built directly via
  `env = dict(os.environ)` at line 107, **not** through `project_child_env()` at all (it is not
  in the `project_child_env()` caller census, Integration Map or otherwise, and not in
  `test_enh3184_spawn_site_guard.py`'s `_TASK_PATH_MODULES` table). This issue's `env_allow`/
  baseline machinery cannot fix this site regardless of how deny mode is wired later — noted so
  nobody assumes this issue closes it; a separate issue would be needed to route
  `fleet_improve.py` through the chokepoint first.

## Expected Behavior

- `HostInvocation` gains `env_allow: frozenset[str] | None = None`, **and** `project_child_env()`
  gains an explicit `env_allow: frozenset[str] | None = None` keyword. The kwarg is required, not
  a convenience: both `bash -c` paths (`fsm/runners.py` shell branch, `runner_spec.py::_run_cmd()`)
  call the helper with **no `HostInvocation` at all**, and forcing ENH-3234/ENH-3235 to
  synthesize a fake invocation just to carry the field would be worse. If both are supplied, the
  explicit kwarg wins.
- With an allow-set in effect, `project_child_env()` constructs the child environment as: the
  names in the allow-set **selected from ambient `os.environ`** — the normal source of a declared
  credential (e.g. `GITHUB_TOKEN` from the operator's shell), so a declared name present only in
  `os.environ` **must** reach the child — plus the fixed baseline (also selected from
  `os.environ`), plus **every key in `invocation.env` and `extra`, unconditionally**. The
  allow-set filters *inheritance* only; caller-supplied keys are explicit intent, never ambient
  leakage, and must not be subject to it. (Review 2026-09-04: without this rule deny mode drops
  `GIT_DIR`/`GIT_WORK_TREE` (`host_runner.py:432-433,726-727,1068-1069`),
  `DANGEROUSLY_SKIP_PERMISSIONS` (`:409`), `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` (`:422-424`),
  `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` (`_apply_automation_env`), and the `LL_PYTHON` `extra`
  both `bash -c` sites pass — unless every one is hand-listed in the baseline. It also lets
  ENH-3205 inject `GH_TOKEN`/`GH_CONFIG_DIR` via `extra=` with no registry change.)
- **Baseline shape**: the baseline is *not* a plain `frozenset[str]` of exact names — the curated
  list below needs prefix families (`LL_*`, `XDG_*`, `HOMEBREW_*`). Specify it as exact names
  plus prefixes (e.g. `_BASELINE_NAMES: frozenset[str]` + `_BASELINE_PREFIXES: tuple[str, ...]`,
  matched via `str.startswith`). Verified 2026-09-04: no `LL_*` variable referenced under
  `scripts/little_loops/` carries a credential (`grep -rhoE '\bLL_[A-Z_]*(KEY|TOKEN|SECRET|PASS)'`
  hits only `LL_ARG_MAX_TOKENS`-style false positives), so the `LL_*` prefix is safe to inherit
  wholesale. Per-task declared scope names (`env_allow` itself) stay exact-name `frozenset[str]`
  — resolving a scope name into that frozenset is ENH-3396's concern, not this issue's.
- **Override polarity rule**: the only environment-driven overrides this chokepoint honors are
  two test/triage-only knobs, both narrowing or observational, never widening:
  `LL_ENV_PROJECTION_FORCE_ALLOW=1` (AC4 — treats an undeclared spec as `env_allow=frozenset()`,
  i.e. baseline-only; a flag, **not** a set to parse) and `LL_ENV_PROJECTION_REPORT=1` (AC6
  report-only — denies nothing, logs the would-deny names). No env var may ever *widen* an
  allow-set or disable deny mode — `LL_*` is baseline-inherited into every descendant, so a
  widening knob would propagate silently through the whole process tree. (Pinned 2026-09-06:
  the earlier text left report-only's trigger unspecified and wrote the force-allow value as
  `<candidate set>`, which was ambiguous between a flag and a parseable list.)
- **Credential-shape guard on prefix families**: a name admitted only via a baseline *prefix*
  (`LL_*`, `XDG_*`, `HOMEBREW_*`, and any others added by AC4) is still denied if it matches
  `API[_-]?KEY|APIKEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|ACCESS[_-]?KEY|PRIVATE[_-]?KEY`
  (case-insensitive). This makes prefix families safe against a future `LL_FOO_TOKEN` and lets
  a `CLAUDE_*`-style prefix be considered without blanket-inheriting `CLAUDE_CODE_OAUTH_TOKEN`.
  The guard never applies to exact-name baseline entries or to registry-resolved names — those
  are explicit. Precedent: the vendored oh-my-pi bundle (the untracked pi-coding-agent build under
  `hooks/adapters/omp/node_modules/`, search its bundled JS for `allowPrefixes`) ships exactly
  this allow-list + deny-regex shape, with an allow-list
  of `PATH HOME USER LOGNAME SHELL TERM LANG TEMP TMP TERM_PROGRAM SSH_AUTH_SOCK SSH_AGENT_PID
  DISPLAY TZ LD_LIBRARY_PATH DYLD_LIBRARY_PATH` plus `LC_`/`XDG_` prefixes — cite it in the
  baseline's justification comment.
- No allow-set in effect (`invocation.env_allow is None` and no kwarg — the default) preserves
  today's full-inherit behavior exactly — this is the escape hatch the two consumer issues rely
  on for undeclared specs.
- **Honesty note (mirror of ENH-3205's gh caveat)**: on macOS the host CLIs' own OAuth sessions
  (Claude Code, Codex, Gemini) live in the Keychain or under `$HOME`, not in env. Env projection
  therefore does **not** scope the host CLI's own auth when a declaring `bash -c` state spawns a
  nested `claude -p`/`ll-loop`/`ll-auto`; it only withholds the env-var-borne credentials the
  caller resolves into `env_allow`. State this plainly in the `project_child_env()` docstring and
  the API.md section so nobody reads "deny-by-default" as "the child cannot reach the operator's
  Claude session".
- When projection denies a variable, the helper logs the denied variable **names** at DEBUG
  level (names only, never values).
- A report-only mode runs the same diff logic without denying anything, for empirically deriving
  the baseline (see Acceptance Criteria).

## Motivation

Per-task credential scoping needs one enforcement seam that both `ActionSpec` (queue/harness/
action path) and FSM `StateConfig` (loop-YAML path) can independently resolve into. Building
that chokepoint first, with its own tests proving the undeclared-spec path is unchanged, lets
ENH-3234 and ENH-3235 each wire a declaration through it without re-deriving or duplicating deny
logic. This issue covers the mechanism half; ENH-3396 covers the scope→env-var mapping half so
the two declaration surfaces don't each invent their own registry.

## Proposed Solution

### Types
- `HostInvocation` (`host_runner.py:156-173`, `@dataclass(frozen=True)`): add `env_allow:
  frozenset[str] | None = None`. **No construction site changes** — the field is defaulted and
  none of the `build_*` methods have a scope input (see Signatures: do not add a kwarg there).
  (Corrected 2026-09-06: the earlier "every construction site needs to pass this through" line
  contradicted the Signatures section and was unnecessary work.)
- **Populator status — be honest about it.** Within this decomposition nothing sets
  `HostInvocation.env_allow`: ENH-3234 and ENH-3235 both wire the invocation-less `bash -c`
  paths via the explicit kwarg, and prompt-mode enforcement is out of scope. The field is kept
  deliberately as the prompt-mode seam: `run_claude_command()` (`subprocess_utils.py:517-529`)
  already builds the invocation and calls `project_child_env(invocation, extra=extra_env)`, so a
  follow-on that adds `env_allow` to `run_claude_command()`'s signature (or reads it off the
  invocation) is ~10 lines. File that follow-on when this lands (see ENH-3235's validator rule
  for why prompt-mode `scopes:` must be rejected until then). If the maintainer prefers YAGNI,
  dropping the field and keeping only the kwarg is acceptable — the kwarg is the load-bearing
  surface; the field is not.
- `env: dict[str, str]` on `HostInvocation` keeps its existing additive/override-only contract
  unchanged — do not repurpose it (see ENH-3203 Open Decision #4).

### Call Path
`resolve_host()` → `build_*()` → `HostInvocation` (now carrying `env_allow`) → `project_child_env()`
(deny-capable) → `subprocess.*`

### Baseline derivation (AC4)
The baseline must **not** be guessed. `bash -c` actions in this repo run pytest, git, ruff, and
`gh`; they depend on `VIRTUAL_ENV`, `PYTHONPATH`, `SSH_AUTH_SOCK` (git push over SSH fails
without it), `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`, `PYENV_ROOT`, `HOMEBREW_*`, `XDG_*`, `SHELL`,
`TERM`, `TZ`, in addition to `PATH`/`HOME`/`USER`/`LANG`/`TMPDIR`/`LL_*`.

**Seed the candidate list from what the package itself reads (2026-09-06).** A grep of
`os.environ[...]`/`os.environ.get(...)`/`os.getenv(...)` under `scripts/little_loops/` yields
non-credential names absent from the list above that a declaring shell state running a nested
`ll-*` or host CLI will break without:

```
CLAUDE_PLUGIN_ROOT  CLAUDE_PROJECT_DIR  CLAUDE_SESSION_ID  CLAUDE_CONFIG_DIR
CODEX_HOME  KIMI_CODE_HOME  PI_CONFIG_DIR  PI_TOOL_BRIDGE_URL  PI_TOOL_BRIDGE_SESSION
NO_COLOR  FORCE_COLOR  EDITOR  CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR
```

(`PI_TOOL_BRIDGE_TOKEN` from the same grep is a credential and is excluded; the shape guard
above would catch it anyway.) Also add to the candidates: `LC_*`, `PYTHON*` (e.g.
`PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`), `PYENV_*`, `CONDA_*`, `SSH_AGENT_PID`,
`TERM_PROGRAM`, `COLUMNS`/`LINES`, `CI`. `CLAUDE_*` cannot be a bare prefix (it would admit
`CLAUDE_CODE_OAUTH_TOKEN`) — use exact names, or the prefix **with** the credential-shape guard.
Make this grep a repeatable step (it is the input to the AC8 static test below), not a one-off.

Two honest limits shape the derivation method: **(1)** env projection cannot observe which
variables a child *actually read* — report-only mode can only log which ambient names fall
outside a candidate allow-set (would-be-denied names); **(2)** this repo's loops carry no
declarations (retrofitting is out of scope) and undeclared specs are full-inherit, so an
ordinary loop run cannot exercise deny mode at all until ENH-3235 lands. Therefore: ship a
**curated** baseline with a per-entry justification comment, and validate it two ways: (a) the
deterministic static test in AC8 below, and (b) a test-only flag
(`LL_ENV_PROJECTION_FORCE_ALLOW=1`, honored only by `project_child_env()`) that forces the
built-in baseline onto undeclared specs, used for *manual* spot-checks of individual loops —
not as an automated gate (see AC8). Report-only mode's would-deny name logging is the triage
evidence, not a read-trace.

### Logging (AC6)
`scripts/little_loops/host_runner.py` has no existing `logging` import or `logger` — this
introduces `logging` fresh into the module; there is no in-module precedent to match (nearest
same-module signaling precedent is the `warnings.warn` shape used for `CapabilityNotSupported`,
which is a different mechanism used for a different purpose — unknown host-capability names —
and is unaffected by this issue).

## Acceptance Criteria

- **AC2.** The projection helper projects a declared `env_allow` into the child environment at
  invocation; an *inherited* variable not in the allow-set is *absent from the child process*,
  not merely discouraged. Covered by direct calls to `project_child_env(invocation, ...)` — no
  consumer surface required.
- **AC2b.** With `env_allow` in effect, every key in `invocation.env` and `extra` still reaches
  the child unchanged (caller-supplied keys bypass the allow-set — see Expected Behavior). Test:
  `project_child_env(HostInvocation(..., env={"GIT_DIR": ...}, env_allow=frozenset()),
  extra={"LL_PYTHON": ...})` yields both keys.
- **AC2c.** The baseline matches prefix families (`LL_*`, `XDG_*`, `HOMEBREW_*`) as well as exact
  names; a test plants `LL_SENTINEL_X=1` in `os.environ` and asserts it survives deny mode.
- **AC2d.** A name admitted only via a baseline prefix but matching the credential-shape regex
  is denied: plant `LL_FAKE_TOKEN=1` and `XDG_SECRET=1` in `os.environ`, run deny mode, assert
  both are absent while `LL_SENTINEL_X` (AC2c) is present.
- **AC4.** A fixed baseline set of non-credential variables is always inherited regardless of
  declaration — curated and validated per "Baseline derivation" above, with each entry justified
  in a comment next to the set.
- **AC5.** `invocation.env_allow is None` (no declaration) preserves today's full-inherit
  behavior exactly. `scripts/tests/test_host_runner.py::TestProjectChildEnv::test_no_args_is_full_inherit`
  (lines 101-105) and `TestProjectChildEnvCrossRunnerParity::test_matches_hand_rolled_merge`
  (lines 152-159) must keep passing **unmodified** — if either needs to change, deny-by-default
  has leaked into the no-declaration case.
- **AC6.** Denied variable names are logged at DEBUG level (names only, never values). The same
  code path in report-only mode produces the AC4 would-deny evidence (ambient names outside the
  candidate set) — a triage aid, not a read-trace.
- **AC8 (partial — full close in ENH-3234/ENH-3235, and this clause's registry check depends on
  ENH-3396 landing).** `python -m pytest scripts/tests/` exits 0 for this chokepoint's own tests,
  **including a deterministic baseline-coverage test**: every env-var name referenced by
  `$NAME`/`${NAME}` in `scripts/little_loops/loops/*.yaml` shell actions and every name read via
  `os.environ`/`os.getenv` under `scripts/little_loops/` must be (i) in the baseline (exact or
  prefix, and not shape-denied), (ii) resolvable from some registry scope (ENH-3396's
  `CREDENTIAL_SCOPES` — if ENH-3396 has not yet landed when this issue is implemented, write
  this clause against whatever scope names exist at merge time and leave a `# TODO(ENH-3396)`
  marker rather than blocking on it), or (iii) on an explicit, commented exception list
  (loop-local variables the action itself assigns — `$DIR`, `$COUNT`, `$STATUS` etc. — will
  dominate this list; filter names the same YAML assigns with `NAME=`/`export NAME` before
  applying the check). Full AC8 (deny mode fully wired end-to-end) closes once ENH-3234 and
  ENH-3235 land. (Replaced 2026-09-06: the earlier "run this repo's own `loops/*.yaml` green
  under the forced-allow override" meant executing every LLM-driven loop end to end — not a
  realistic or repeatable gate. The flag stays for manual spot-checks.)

## Integration Map

### Dependent Files (Callers/Importers)

With an `invocation` (env merge is `os.environ` + `invocation.env` + `extra`; these are the
sites `env_allow` selection must account for):
- `scripts/little_loops/runner_spec.py` — lines 223, 333
- `scripts/little_loops/subprocess_utils.py` — line 529, the primary streaming path's actual
  `subprocess.Popen(..., env=env)` call
- `scripts/little_loops/session_store/lifecycle.py` — line 157
- `scripts/little_loops/fsm/evaluators.py` — lines 1207, 1463
- `scripts/little_loops/fsm/handoff_handler.py` — line 130
- `scripts/little_loops/learning_tests/extractor.py` — line 134
- `scripts/little_loops/cli/issues/decisions.py` — line 815
- `scripts/little_loops/parallel/worker_pool.py` — line 859
- `scripts/little_loops/host_runner.py` — line 2178, `run_blocking_json()` — an in-module call
  site (same file as the chokepoint itself)

With no `invocation` (pure `os.environ` inheritance today; unaffected by `env_allow` since there
is no `HostInvocation` to carry the field — these are exactly the two `bash -c` paths ENH-3234/
ENH-3235 will need to synthesize a declaration for):
- `scripts/little_loops/fsm/runners.py` — line 305
- `scripts/little_loops/runner_spec.py` — line 249, `_run_cmd`
- `scripts/little_loops/parallel/worker_pool.py` — line 106
- `scripts/little_loops/cli/loop/runner.py` — line 297
- `scripts/little_loops/cli/loop/summary.py` — line 185
- `scripts/little_loops/mcp_call.py` — line 199
- `scripts/little_loops/prepatch_check.py` — line 290
- `scripts/little_loops/worktree_utils.py` — line 721, followed by `env.pop("LL_PYTHON", None)` at
  line 730, the BUG-3370 call-site workaround (see Codebase Research Findings above)
- `scripts/little_loops/git_operations.py` — line 728

None of the above sites need to change for this issue — they continue passing `env_allow=None`
implicitly (via `HostInvocation`'s default) or no invocation at all, and get today's behavior.

## Program Design

### Signatures
- `build_streaming(*, prompt, working_dir=None, resume=False, agent=None, tools=None, model=None,
  automation_profile=None, disable_background_tasks=False, workspace_root=None) -> HostInvocation`
  (`host_runner.py:247-260`; the `HostRunner` Protocol signature — re-verified 2026-09-03:
  `automation_profile`/`disable_background_tasks` were not removed by the ENH-3095 refactor, they
  remain as deprecated keywords alongside the new `automation: AutomationContext | None = None`
  param — supplying either alongside an explicit `automation` emits a `DeprecationWarning` and
  `automation` wins; the guidance below stands unchanged) — **do not** add a `scope=`/`env_allow=`
  kwarg here.
  Threading scope through it means editing ~32 signatures (4
  build methods × 8 runner classes) for a value none of them interpret, and it puts the scoping
  decision inside the per-host runners — the one place it must not live, since `RunnerType.CMD`
  never calls `resolve_host()` at all (structurally excluded). Instead: the `env_allow` field is
  set on the constructed `HostInvocation` by whichever caller resolves the declaration
  (ENH-3234/ENH-3235's job), and `project_child_env()` reads it — this issue only needs
  `project_child_env()` and `HostInvocation` to support the field; it does not populate it from
  any real declaration.

### Call Path

`HostRunner.build_*()` (e.g. `ClaudeCodeRunner.build_streaming()`, `host_runner.py:353-440`) ->
constructs `HostInvocation` (`host_runner.py:156-173`) -> caller invokes
`project_child_env(invocation, extra=...)` (`host_runner.py:1865-1895`) -> result passed as
`subprocess.run`/`Popen(env=...)`, e.g. `run_blocking_json()` (`host_runner.py:2178`) and
`verify_epic_branch_before_merge()` (`worktree_utils.py:721`).

### Codebase Research Findings

_Carried forward from ENH-3203's `/ll:refine-issue`/`/ll:wire-issue` passes — verify line numbers
before implementing, as they were already noted as drifted once:_

- `project_child_env()` call sites confirmed (re-verified 2026-09-03; `cli/loop/_helpers.py` no
  longer exists — dissolved into `runner.py`/`summary.py`, commits `fc4f65436`/`43c762c64`):
  with an `invocation` — `runner_spec.py:223,333`,
  `subprocess_utils.py:529` (the actual `subprocess.Popen(..., env=env)` call for the primary
  streaming path), `session_store/lifecycle.py:157`, `fsm/evaluators.py:1207,1463` (2 sites, not
  3), `fsm/handoff_handler.py:130`, `learning_tests/extractor.py:134`, `cli/issues/decisions.py:815`,
  `parallel/worker_pool.py:859`. With no invocation (pure `os.environ` inheritance) —
  `fsm/runners.py:305`, `runner_spec.py:249` (`_run_cmd`), `worker_pool.py:106`,
  `cli/loop/runner.py:297`, `cli/loop/summary.py:185`, `mcp_call.py:199`, `prepatch_check.py:290`,
  `worktree_utils.py:721`, `git_operations.py:728`.
- `HostCapabilities` (`host_runner.py:119-144`) is the closest existing "declared support" shape
  but is per-runner-class, not per-task — not reusable for anything this issue needs.

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis (carried forward from
ENH-3233):_

- **Logging convention**: 40+ modules under `scripts/little_loops/` follow `import logging` near
  the top of the import block, then a single module-level `logger = logging.getLogger(__name__)`
  (e.g. `subprocess_utils.py:10,33`, `queue_store.py:27,55`, `fsm/concurrency.py:17,27`); one
  outlier uses an explicit dotted name (`history_reader/_base.py:50`,
  `logging.getLogger("little_loops.history_reader")`). `host_runner.py` has neither `import
  logging` nor a `logger` today — this issue is the first logging usage in that module. A
  separate, unrelated convention (`self.logger.debug(...)` as an instance attribute) is used
  inside larger stateful classes (e.g. `parallel/merge_coordinator.py`, `sync.py`) — not
  applicable to `project_child_env()`, which is a free function.
- **Prefix-matching convention**: `str.startswith(tuple_of_prefixes)` is the consistent mechanism
  for prefix-family matching codebase-wide (e.g. `design_tokens.py:70,74` with inline tuples,
  `:644` via a named module constant `_PRIMITIVE_COLOR_PREFIXES`; `worker_pool.py:1533`,
  `link_checker.py:470`). No settled convention on inline-vs-named tuple — both coexist even
  within `design_tokens.py` itself. (`design_tokens.py:72` is a single-string
  `.startswith("outline")`/equality check, not a tuple form — not a same-shape example.)
- **`LL_*` env-flag read convention**: the dominant idiom is a bare truthy-presence check,
  `os.environ.get("LL_X")` used directly in a boolean context (e.g. `hooks/session_start.py:88,165`,
  `hooks/drift_check.py:119`) — unset or `""` is falsy, any other string is truthy. No existing
  read-side `== "1"` comparison was found anywhere in the tree; the only `"1"` occurrences are on
  the write side (`host_runner.py:1911`, `env["LL_AUTOMATION"] = "1"`). A second idiom,
  `.get("LL_X", "") == "true"` / `.lower() == 'true'`, is used only inside FSM loop YAML `python:`
  blocks for `LL_ARG_*` CLI-plumbed values — not applicable here.

_Wiring pass added by `/ll:wire-issue` — 2026-09-07:_ three other functions already in
`host_runner.py` do their own function-local `import os` — `resolve_host()` (~line 2010),
`apply_host_cli_from_config()` (~line 2293), and `_active_oauth_token()` (~line 2490). Adding the
new module-level `import os` this issue requires does not break any of them (a local `import os`
just harmlessly rebinds the local name), but it leaves three now-redundant local imports in the
same file this issue's diff touches — worth a one-line cleanup per site while in the file, not a
separate issue.
- **Test fixture/parametrization detail**: `scripts/tests/test_host_runner.py:51-56` has an
  `isolated_env` fixture that clears `LL_HOST_CLI`/`LL_HOOK_HOST` before probe/override tests.
  `TestProjectChildEnvStubRunnersRaiseFirst` (lines 162-170) parametrizes separately over the two
  *unimplemented* stub runners, `[OpenCodeRunner, PiRunner]` — distinct from the six-item
  implemented-runner list (`ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner,
  QwenRunner`) used elsewhere.

### Tests
- `scripts/tests/test_host_runner.py::TestAutomationProfileEnvAcrossRunners` (lines 59-93: the
  `@pytest.mark.parametrize` decorator opens at 59, the class at 70, both test methods run through
  93) is the established table-driven, cross-all-runner-class pattern (BUG-3058 precedent) — new
  deny-mode tests should follow this shape, parametrized across `ClaudeCodeRunner, CodexRunner,
  GeminiRunner, OmpRunner, KimiRunner, QwenRunner` plus `OpenCodeRunner`/`PiRunner` stubs (tested
  individually, not through the parametrized table).
- New tests for: `env_allow` selection semantics (incl. a declared name present only in ambient
  `os.environ` reaching the child, and the explicit kwarg working with no invocation),
  baseline-always-present, credential-shape guard on prefix families (AC2d), DEBUG logging of
  denied names, report-only mode (`LL_ENV_PROJECTION_REPORT=1`) would-deny output, the
  forced-allow flag (`LL_ENV_PROJECTION_FORCE_ALLOW=1`), and the AC8 static baseline-coverage
  test. (Scope-registry fail-loud raise is ENH-3396's test, not this issue's.)
- No shared fixture exists for `HostInvocation` construction (`scripts/tests/conftest.py` has
  none) — follow the existing inline-keyword-construction convention.

_Wiring pass added by `/ll:wire-issue` — 2026-09-07 (carried forward from ENH-3233):_
- **Existing coverage that exercises the real merge path and must stay green unmodified**
  (none of these construct `HostInvocation` with `env_allow=`, so a `None`-default keeps them
  passing — same AC5 guarantee):
  `scripts/tests/test_runner_spec.py::test_prompt_dispatch_merges_invocation_env` (~154-172, real
  `project_child_env()` call, not mocked), `scripts/tests/test_subprocess_utils.py::TestRunClaudeCommandHostRunner`
  (~2410-2501, asserts exact env-key precedence including `CONFLICT_KEY` override and
  empty-string `LL_AUTOMATION` beating ambient env), `scripts/tests/test_cli_decisions.py` (~1700-1729,
  asserts `mock_run.call_args.kwargs["env"]["LL_NON_INTERACTIVE"]`/`["DANGEROUSLY_SKIP_PERMISSIONS"]`
  through the real merge), and `scripts/tests/test_worktree_utils.py::test_ll_python_scrubbed_from_child_env`
  (~1359-1388) — the test covering the exact BUG-3370 `env.pop("LL_PYTHON", None)` workaround this
  issue's `env_allow` is designed to eventually obsolete (obsoleting it is out of scope here; the
  test must still pass unmodified).
- **Structural guard whose invariant must not be silently broken**:
  `scripts/tests/test_enh3184_spawn_site_guard.py::TestSpawnSiteGuard` pins
  `little_loops/host_runner.py` at exactly `(1, 0)` (total spawns, exempted spawns) in its
  `_TASK_PATH_MODULES` census (line ~48) and asserts every `subprocess.run/Popen/check_output/call`
  site's `env=` resolves to a `project_child_env(...)` call. None of this issue's additions
  (`env_allow` field/kwarg, DEBUG logging, the report-only diff) are themselves spawn calls, so
  the guard stays green — **unless** the report-only-mode implementation shells out to anything;
  if it does, update the pinned `(1, 0)` count deliberately rather than let this test fail as a
  surprise.
- **Doc-coverage tests constraining the docs edit**: `scripts/tests/test_wiring_reference_docs.py`
  (~163-172) pins required literal substrings (`"HostInvocation"`, `"CapabilityNotSupported"`, etc.)
  inside `docs/reference/API.md` — the `### project_child_env` rewrite must not remove any pinned
  string while replacing the stale "no way to clear or deny" sentence.
- **New-test precedents**: DEBUG-logging of denied names →
  `scripts/tests/test_issue_history_parsing.py` (~225-239,
  `caplog.at_level("DEBUG", logger="little_loops.issue_history.parsing")` then
  `assert "..." in caplog.text`) is the closest caplog precedent, since `host_runner.py` has no
  logger today — use `logger="little_loops.host_runner"`; `LL_ENV_PROJECTION_FORCE_ALLOW`/
  `LL_ENV_PROJECTION_REPORT` env-flag tests → `monkeypatch.setenv(...)`/`monkeypatch.delenv(...,
  raising=False)` is the universal idiom in this suite (`test_host_runner.py:101-105`,
  `test_worktree_utils.py:1369`), not manual `os.environ` save/restore.

_Wiring pass added by `/ll:wire-issue` — 2026-09-07:_
- **Credential-shape guard (AC2d) test-shape precedent**: no existing "credential shape"/secret
  detector exists in this repo, but `scripts/little_loops/pii.py` + `scripts/tests/test_pii.py`
  is the closest structural analog — module-level compiled regex constants collected into a dict
  (`PII_PATTERNS`), a `detect_pii()`/`redact_pii()` pair, and a `TestDetectPii`/`TestRedactPii`
  test-class shape with one test per pattern type plus a "no match" and "multiple types" case.
  Model the new credential-shape regex's tests after this convention (one test per credential
  keyword — `TOKEN`, `SECRET`, `API_KEY`, etc. — plus a "prefix-matched but not credential-shaped
  survives" case, which AC2c/AC2d together already specify via `LL_SENTINEL_X`).
- **Autouse env-scrub fixture new deny-mode tests must account for**:
  `scripts/tests/conftest.py`'s `_restore_cmd_run_env_vars` (autouse, ~line 1072, scrubbing the
  `_CMD_RUN_ENV_VARS` tuple ~line 1060) force-clears `LL_AUTOMATION`, `LL_AUTOMATION_PROFILE`,
  `LL_HOST_CLI`, `LL_HOOK_HOST`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `LL_HANDOFF_THRESHOLD`,
  `LL_CONTEXT_LIMIT`, and `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` on **every** test in the
  suite, unconditionally. A new deny-mode/baseline test that expects one of these names to survive
  projection (e.g. asserting `LL_AUTOMATION` passes the baseline) will see it absent from
  `os.environ` regardless of baseline logic unless the test calls `monkeypatch.setenv(...)` on it
  first — this is fixture-driven absence, not a projection bug.

### Documentation
- `docs/reference/API.md` — the `### project_child_env` section (line ~10171-10191, stale
  sentence to rewrite at line ~10185 — re-verify before editing, this doc file has already drifted
  once) reproduces the docstring verbatim, including "this helper provides no way to clear or deny
  an inherited variable; that's deliberately out of scope (see ENH-3203)" — rewrite this line, it
  names a resolved issue directly and goes stale the moment deny semantics land. The
  `### HostInvocation` section (line ~9986-10011, field table at ~10002-10008 — same re-verify
  caveat) needs the new `env_allow` field added to the field table.
- `docs/ARCHITECTURE.md` — the `HostInvocation` row (~line 853-854; this is a single markdown
  table **cell** listing field names in prose — `` `binary`, `args`, `env`, `capabilities`, and
  `cleanup_paths` `` — not an enumerated per-field table) needs `, and \`env_allow\`` appended to
  that cell's prose list.

## Scope Boundaries

Out of scope for this child (belongs to ENH-3396, ENH-3234/ENH-3235, or is out of scope for the
whole ENH-3203 effort per its Scope Boundaries section):

- The credential-scope registry (`CREDENTIAL_SCOPES`, `resolve_scopes()`, fail-loud raise on an
  unknown scope name) — that's ENH-3396.
- Populating `env_allow` from a real per-task declaration — no `ActionSpec` or `StateConfig`
  field exists yet; this issue only makes the chokepoint capable of honoring the field when set.
- Wiring either `bash -c` path (`fsm/runners.py:297`, `runner_spec.py::_run_cmd()`) to construct
  an `HostInvocation` with `env_allow` populated — that's ENH-3234 (action path) and ENH-3235
  (FSM path).
- Disk-backed/keyring-backed credentials, token minting, MCP server credentials, secrets
  management, `gh`/`sync.py` scoping (ENH-3205), audit persistence (ENH-3204) — unchanged from
  ENH-3203's Scope Boundaries.

## Impact

- **Priority**: P2 — matches parent; this is the load-bearing piece the other two children of
  ENH-3233 depend on.
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
- ENH-3204
- ENH-3205

## Resolution

Implemented in `scripts/little_loops/host_runner.py`:
- `HostInvocation.env_allow: frozenset[str] | None = None` added.
- Module-level `import os`/`import logging` + `logger = logging.getLogger(__name__)`;
  the three now-redundant function-local `import os` statements (`resolve_host`,
  `apply_host_cli_from_config`, `_active_oauth_token`) removed.
- `_BASELINE_NAMES`/`_BASELINE_PREFIXES`/`_CREDENTIAL_SHAPE_RE`/`_is_baseline_allowed()`
  added per the curated "Baseline derivation" list.
- `project_child_env()` gained an `env_allow` kwarg (wins over `invocation.env_allow`,
  via `getattr` so pre-existing `SimpleNamespace`-based test doubles for
  `HostInvocation` keep working). Deny mode filters ambient `os.environ` through
  the allow-set + baseline, always merges `invocation.env`/`extra` unconditionally,
  and logs denied names (never values) at DEBUG. `LL_ENV_PROJECTION_FORCE_ALLOW=1`
  and `LL_ENV_PROJECTION_REPORT=1` implemented as specified — both narrowing/
  observational only.

Tests (TDD): `TestProjectChildEnvDenyMode` (AC2/AC2b/AC2c/AC2d/AC4/AC5/AC6, force-allow,
report-only) and `TestAC8BaselineCoverage::test_referenced_env_names_are_covered`
(deterministic scan of `loops/*.yaml` shell actions + `os.environ`/`os.getenv` call
sites under `scripts/little_loops/`, gated by baseline coverage + a `_KNOWN_EXCEPTIONS`
list carrying a `TODO(ENH-3396)` for the credential-shaped names pending the registry)
added to `scripts/tests/test_host_runner.py`. Pre-existing AC5 tests
(`test_no_args_is_full_inherit`, `test_matches_hand_rolled_merge`) verified unmodified
and passing.

Docs updated: `docs/reference/API.md` (`### HostInvocation` field table,
`### project_child_env` rewrite replacing the stale "no way to clear or deny"
sentence) and `docs/ARCHITECTURE.md` (`HostInvocation` field list).

Full suite: `python -m pytest scripts/tests/ -m "not integration and not conformance"`
— 22517 passed, 12 skipped, 5 failed. All 5 failures are pre-existing and unrelated
to this change (verified by inspecting each traceback): `test_verify_evidence`'s
evidence-drift gate flags quotes in unrelated issue files (BUG-2111, ENH-1441,
FEAT-959); `test_opencode_adapter`/`test_omp_adapter`'s `tsc --noEmit` checks fail
on a missing `bun` type-definition file (toolchain/environment gap, not source);
`test_enh3035_artifact_template_kit` and `test_builtin_loops` failures do not touch
`host_runner.py`. A regression this change did introduce and fix during
implementation: `test_learning_tests_extractor.py::TestDefaultLlmCall` used
`SimpleNamespace` stand-ins for `HostInvocation` lacking an `env_allow` attribute —
fixed via `getattr(invocation, "env_allow", None)` instead of direct attribute access.

One out-of-scope note carried into the codebase from this issue's own research:
`scripts/little_loops/fleet_improve.py:111` builds its env via `dict(os.environ)`
directly, bypassing `project_child_env()` entirely — this issue's `env_allow`/
baseline machinery cannot reach that site regardless of how deny mode is wired
later (documented in the issue body; a separate issue would be needed).

## Status

**Done** | Created: 2026-09-07 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-09-07T19:16:41 - `f9939931-e608-4e18-b427-5f8230c4754e.jsonl`
- `/ll:ready-issue` - 2026-09-07T18:59:11 - `54df96c7-36c7-487e-b1bf-bcb0aba82d4f.jsonl`
- `/ll:confidence-check` - 2026-09-07T18:56:57 - `0fadbe7f-8b9b-4156-8177-fa069f04b336.jsonl`
- `/ll:verify-issues` - 2026-09-07T18:55:42 - `d42bc5f9-48aa-4a4b-b466-479b9b058b4e.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-07T18:52:47 - `e35d5b6d-ea2d-4ad8-b310-b62708b1679d.jsonl`
- `/ll:verify-issues` - 2026-09-07T18:50:07 - `4e1fa1ca-b960-48b2-b2cb-f03c27f2ea80.jsonl`
- `/ll:wire-issue` - 2026-09-07T18:44:00 - `4a760742-0888-45a4-86da-707ee8f0e8b1.jsonl`
- `/ll:refine-issue` - 2026-09-07T18:35:14 - `4f07d79d-2a29-4108-9d20-c4f3a10dcf61.jsonl`
- `/ll:issue-size-review` - 2026-09-07T18:32:55 - `08ef3096-7021-4748-9fbe-8beb4da74092.jsonl`
