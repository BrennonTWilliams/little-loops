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

`project_child_env(invocation=None, *, extra=None)` (`scripts/little_loops/host_runner.py:1865-1896`,
ENH-3184's deliverable) is additive/override-only: `env = os.environ.copy(); env.update(invocation.env);
env.update(extra)`. There is no way to withhold a variable from the child. `HostInvocation`
(`host_runner.py:155-173`, frozen dataclass) has no field expressing an allow-set today.

`_apply_automation_env()` (`host_runner.py:1898-1917`) sets only `LL_AUTOMATION`/
`LL_AUTOMATION_PROFILE` in place and never deletes a key; its docstring already names ENH-3203
as the follow-on that changes this.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

Re-verified 2026-09-03. `scripts/little_loops/host_runner.py` — `project_child_env()` at line
1865, `HostInvocation` at line 156, `_apply_automation_env()` at line 1898, `HostCapabilities`
at line 128, `CapabilityNotSupported` at line 116. The module has no module-level `import os` or
`import logging` today — both are net-new for this issue's DEBUG-logging requirement.

`scripts/little_loops/worktree_utils.py` — BUG-3370 is `status: done`; its fix added
`env.pop("LL_PYTHON", None)` directly after the `project_child_env()` call in
`verify_epic_branch_before_merge()`, a call-site workaround rather than a chokepoint-level clear/
deny primitive. `project_child_env()` itself is unchanged by that fix, so the comment this issue
quotes there remains accurate.

`scripts/little_loops/mcp_server/policy.py` — `MUTATING_TOOLS`, the nearest existing bare
`frozenset[str]` allow-set precedent, is consulted via `tool_name in MUTATING_TOOLS` inside
`check_tool_call()`; it carries no per-entry metadata and no fail-loud-on-unknown-name behavior,
so it is a shape precedent only, not a reusable registry.

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
  wholesale. `env_allow` itself (the per-task declaration) stays exact-name `frozenset[str]`.
- **Override polarity rule**: the only environment-driven overrides the chokepoint honors are
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
- A credential-scope registry maps scope names to the env-var names they unlock; resolving a
  scope name not in the registry **raises directly** (e.g. `ValueError`) at resolve time, naming
  the scope. Direct raise, not `warnings.simplefilter("error", ...)` promotion — promotion is
  opt-in per process and this check is fail-loud security. (This pins ENH-3203 Open Decision #3.)
- **Registry naming**: do not call this a "capability" registry in code. `host_runner.py` already
  uses the capability vocabulary for host-feature support (`HostCapabilities`, `CapabilityEntry`,
  `CapabilityNotSupported`, `describe_capabilities`) — a second meaning of "capability" in the
  same module invites confusion. Use "scope" (e.g. `CREDENTIAL_SCOPES`, `resolve_scopes(...)`).
- The registry ships with an initial entry set so ENH-3234/ENH-3235 don't each invent their own.
  **Enumerate it from the credential names the codebase already references** (repo-wide grep
  2026-09-04, `\b(ANTHROPIC|CLAUDE|OPENAI|GEMINI|GITHUB|GH|CODEX|KIMI|QWEN|OPENCODE)_[A-Z_]*(KEY|TOKEN|SECRET)\b`
  under `scripts/little_loops/`), not from two examples. Starting set:
  - `github` → `{GH_TOKEN, GITHUB_TOKEN, GH_ENTERPRISE_TOKEN, GITHUB_ENTERPRISE_TOKEN,
    GITHUB_ACCESS_TOKEN}`
  - `anthropic-api` → `{ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_OAUTH_TOKEN,
    CLAUDE_CODE_OAUTH_TOKEN}`
  - `openai-api` → `{OPENAI_API_KEY, OPENAI_CODEX_OAUTH_TOKEN}`
  - `gemini-api` → `{GEMINI_API_KEY}`
  - `kimi-api` → `{KIMI_API_KEY}`
  - `qwen-api` → `{QWEN_OAUTH_TOKEN, QWEN_PORTAL_API_KEY}`
  - `opencode-api` → `{OPENCODE_API_KEY}`

  Finalize during implementation with a justification comment per entry; drop any name that
  turns out to be a non-credential (`*_STATE_KEY`, `*_METADATA_KEY`, `*_CLIENT_KEY` hits from the
  same grep are deliberately excluded above).
- **Honesty note (mirror of ENH-3205's gh caveat)**: on macOS the host CLIs' own OAuth sessions
  (Claude Code, Codex, Gemini) live in the Keychain or under `$HOME`, not in env. Env projection
  therefore does **not** scope the host CLI's own auth when a declaring `bash -c` state spawns a
  nested `claude -p`/`ll-loop`/`ll-auto`; it only withholds the env-var-borne credentials in the
  registry. State this plainly in the `project_child_env()` docstring and the API.md section so
  nobody reads "deny-by-default" as "the child cannot reach the operator's Claude session".
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

### Failure polarity (AC3) — decided
The one existing analog, `CapabilityNotSupported(UserWarning)` (`host_runner.py:109-117`), is
warn-and-drop at every site (`warnings.warn(..., CapabilityNotSupported, stacklevel=N)`). AC3
requires the opposite polarity for an unknown-scope-name-vs-registry mismatch — **decided:
direct raise** (see Expected Behavior). This resolves ENH-3203's Open Decision #3;
`simplefilter` promotion was rejected because it is opt-in per process and this check must
fail loudly everywhere.

### Logging (AC6)
`scripts/little_loops/host_runner.py` has no existing `logging` import or `logger` — this
introduces `logging` fresh into the module; there is no in-module precedent to match (nearest
same-module signaling precedent is the `warnings.warn` shape used for `CapabilityNotSupported`,
which is a different mechanism and stays as-is for AC3).

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
- **AC3.** Resolving a scope name not in the credential-scope registry fails loudly at resolve
  time via direct raise, naming the scope (see "Failure polarity" — pins ENH-3203 Open
  Decision #3).
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
- **AC2d.** A name admitted only via a baseline prefix but matching the credential-shape regex
  is denied: plant `LL_FAKE_TOKEN=1` and `XDG_SECRET=1` in `os.environ`, run deny mode, assert
  both are absent while `LL_SENTINEL_X` (AC2c) is present.
- **AC8 (partial — full close in ENH-3234/ENH-3235).** `python -m pytest scripts/tests/` exits 0
  for this chokepoint's own tests, **including a deterministic baseline-coverage test**: every
  env-var name referenced by `$NAME`/`${NAME}` in `scripts/little_loops/loops/*.yaml` shell
  actions and every name read via `os.environ`/`os.getenv` under `scripts/little_loops/` must be
  (i) in the baseline (exact or prefix, and not shape-denied), (ii) resolvable from some registry
  scope, or (iii) on an explicit, commented exception list (loop-local variables the action
  itself assigns — `$DIR`, `$COUNT`, `$STATUS` etc. — will dominate this list; filter names the
  same YAML assigns with `NAME=`/`export NAME` before applying the check). Full AC8 (deny mode
  fully wired end-to-end) closes once ENH-3234 and ENH-3235 land. (Replaced 2026-09-06: the
  earlier "run this repo's own `loops/*.yaml` green under the forced-allow override" meant
  executing every LLM-driven loop end to end — not a realistic or repeatable gate. The flag stays
  for manual spot-checks.)

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
  line 730, the BUG-3370 call-site workaround (see Codebase Research Findings below)
- `scripts/little_loops/git_operations.py` — line 728

### Configuration

_Wiring pass added by `/ll:wire-issue` — 2026-09-06:_
- **Registry starting-set gap.** This repo's own built-in loops already read three
  credential-shaped env vars via undeclared shell states that are in none of the
  Expected Behavior registry's 7 starting scopes and none of the `LL_*`/`XDG_*`/
  `HOMEBREW_*` baseline: `VISION_API_KEY` (`scripts/little_loops/loops/rlhf-svg-evaluate.yaml:248,396`,
  `openscad-model-generator.yaml:313,411`, `svg-image-generator.yaml:153,207`,
  `flux-image-generator.yaml:265,334`, `interactive-component-generator.yaml:512,524,558`,
  `html-website-generator.yaml:189,202,253`), and `OPENROUTER_API_KEY`/`AUTOFIGURE_API_KEY`
  (`scripts/little_loops/loops/adversarial-redesign.yaml:16`, consumed by
  `scripts/autofigure_wrapper.py`, invoked at lines 52/107). None of these are
  problems for an undeclared state (`env_allow=None` stays full-inherit), but they
  are candidates for the registry (e.g. `vision-api`, `openrouter-api`,
  `autofigure-api` scopes) so a state that later declares `scopes: [...]` for one
  of these loops doesn't lose ambient access to a var the registry doesn't know
  about. Finalize alongside the AC4 baseline-derivation pass, not as a blocker for
  this issue's own tests.

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
  `worktree_utils.py:721`, `git_operations.py:728`. None of these sites need to change for this
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
- New tests for: `env_allow` selection semantics (incl. a declared name present only in ambient
  `os.environ` reaching the child, and the explicit kwarg working with no invocation),
  baseline-always-present, credential-shape guard on prefix families (AC2d), scope-registry
  fail-loud direct raise, DEBUG logging of denied names, report-only mode
  (`LL_ENV_PROJECTION_REPORT=1`) would-deny output, the forced-allow flag
  (`LL_ENV_PROJECTION_FORCE_ALLOW=1`), and the AC8 static baseline-coverage test.
- No shared fixture exists for `HostInvocation` construction (`scripts/tests/conftest.py` has
  none) — follow the existing inline-keyword-construction convention.

### Documentation
- `docs/reference/API.md` — the `### project_child_env` section (line 10104-10125) reproduces the
  docstring verbatim, including "this helper provides no way to clear or deny an inherited
  variable; that's deliberately out of scope (see ENH-3203)" — rewrite this line, it names this
  issue directly and goes stale the moment deny semantics land. The `### HostInvocation` section
  (line 9919-9945) needs the new `env_allow` field added to the field table.
- `docs/ARCHITECTURE.md` — the `HostInvocation` table row (~lines 835-848) needs `env_allow`
  appended if the field list stays enumerated there.

## Scope Boundaries

Out of scope for this child (belongs to ENH-3234/ENH-3235 or is out of scope for the whole
ENH-3203 effort per its Scope Boundaries section):

- Populating `env_allow` from a real per-task declaration — no `ActionSpec` or `StateConfig`
  field exists yet; this issue only makes the chokepoint capable of honoring the field when set.
- Wiring either `bash -c` path (`fsm/runners.py:297`, `runner_spec.py::_run_cmd()`) to construct
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
- ENH-3204
- ENH-3205

## Status

**Open** | Created: 2026-08-17 | Priority: P2

## Verification Notes (2026-09-03)

- Re-verified all `project_child_env()`/`HostInvocation`/`_apply_automation_env()` line citations
  against current code; several had drifted (function bodies moved ~80 lines since last check).
- `cli/loop/_helpers.py:1670,2106` no longer exists — that file was dissolved into
  `cli/loop/runner.py` and `cli/loop/summary.py` (commits `fc4f65436`/`43c762c64`); citations
  updated to `runner.py:297` and `summary.py:185`.
- `fsm/evaluators.py` now has 2 `project_child_env(invocation)` sites (`:1207,1463`), not 3.
- Added missing `## Blocks` backlinks: ENH-3204 and ENH-3205 both declare `blocked_by: ENH-3233`
  but were absent from this issue's `## Blocks` section.

### Verification Notes (2026-09-03, /ll:verify-issues re-pass)

Re-ran after the same day's `/ll:refine-issue` pass (18:57:37, later than this file's prior
verify at 17:47:54); corrected drift the refine pass introduced or left unchecked. Graph:
provider=`codegraph` freshness=`fresh`. `ll-verify-evidence --json` → `"ok": true, "count": 0`
(no fabricated evidence spans). Decisions log gate: no active required rules found (query
succeeded, empty result). All `## Blocks` backlinks (ENH-3234, ENH-3235, ENH-3204, ENH-3205)
and all Integration Map call-site line citations (both "with invocation" and "with no
invocation" buckets) confirmed accurate against current code — no further change needed there.

Corrected in this pass (all citation-only; no claim about current behavior was false):
- **Program Design > Signatures**: `build_streaming` Protocol citation was `host_runner.py:217-229`
  (that range actually falls inside `CapabilityReport`'s docstring / the `HostRunner` Protocol's
  class docstring, not the method signature) — corrected to `247-260`. Also corrected the claim
  that ENH-3095 "collapsed `automation_profile`/`disable_background_tasks` into `automation`" —
  both deprecated kwargs remain in the live signature alongside `automation`, folded internally
  via `resolve_automation()` rather than removed; a `DeprecationWarning` fires if both are passed.
- **Types section**: `HostInvocation` citation `host_runner.py:148-166` corrected to `156-173`
  (matches the precise citation already used elsewhere in this same issue).
- **AC5 test citations**: `test_no_args_is_full_inherit` was `lines 94-98`, actual `101-105`;
  `test_matches_hand_rolled_merge` was `lines 145-152`, actual `152-159`.
- **Documentation section**: `docs/reference/API.md`'s `### project_child_env` section was cited
  `~line 9621-9637`, actual `10104-10125` (~480-line drift — the doc file grew since this citation
  was written); `### HostInvocation` was cited `~line 9437-9458`, actual `9919-9945`.

Verdict: **NEEDS_UPDATE** (now corrected) — the issue's factual claims about current behavior all
held; only line-number citations had drifted, most since the 17:47 verify pass's `refine-issue`
follow-on added or left them unchecked.

## Review Notes (2026-09-04, pre-implementation epic review)

- Expected Behavior gained three pinned rules: caller-supplied keys (`invocation.env`/`extra`)
  bypass the allow-set; the baseline is exact-names-plus-prefixes, not a bare `frozenset[str]`;
  no env var may widen an allow-set. AC2b/AC2c added to enforce the first two.
- Registry starting set enumerated from the credential names already referenced under
  `scripts/little_loops/` (7 scopes) instead of two examples.
- Added the macOS Keychain honesty note: projection withholds env-borne credentials only.
- Also resolves a wiring consequence for ENH-3205: `GH_CONFIG_DIR` injection via `extra=` needs
  no registry entry once caller-supplied keys pass through.

## Review Notes (2026-09-06, pre-implementation cross-issue review)

- `HostInvocation.env_allow`: removed the contradictory "pass through at every construction
  site" instruction; recorded that nothing in this decomposition populates the field and named
  `run_claude_command()` as the prompt-mode follow-on seam.
- Pinned both env knobs as flags: `LL_ENV_PROJECTION_FORCE_ALLOW=1`, `LL_ENV_PROJECTION_REPORT=1`.
- Added the credential-shape guard on prefix families (AC2d) with the oh-my-pi precedent.
- Seeded the AC4 candidate list from the package's own `os.environ` reads (12 names the curated
  list was missing, e.g. `CLAUDE_PLUGIN_ROOT`, `CODEX_HOME`).
- Replaced the unrunnable "all loops green under forced-allow" AC8 clause with a static
  baseline-coverage test.

## Session Log
- `/ll:wire-issue` - 2026-09-07T03:48:27 - `24278e0c-f73c-4e7c-b229-0bf010cc0589.jsonl`
- `/ll:verify-issues` - 2026-09-03T19:57:33 - `4261573e-8608-488b-a923-28da6aae0cad.jsonl`
- `/ll:refine-issue` - 2026-09-03T18:57:37 - `81f9ded4-f3d7-410d-9fd5-2bd50814262a.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:54 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:issue-size-review` - 2026-08-17T16:32:34 - `bcf99734-092e-4d7b-9a71-2d6fb04c8246.jsonl`
