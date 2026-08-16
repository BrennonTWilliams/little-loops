---
id: ENH-3203
type: ENH
title: Declare and enforce per-task credential scope via deny-by-default env projection
priority: P2
status: open
blocked_by: [ENH-3184]
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:26:51Z'
testable: true
decision_needed: true
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

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — the projection helper from ENH-3184 gains deny semantics and the baseline set; a new `HostInvocation` field (e.g. `env_allow: frozenset[str] | None`) carries the allow-set. **`HostInvocation.env` must not be repurposed** — see Open Decisions.
- `scripts/little_loops/runner_spec.py` — `ActionSpec` (frozen dataclass: `name`, `runner`, `target`, `args: dict[str, Any]`, `timeout`) is the per-task spec object and has no declaration field today.
- `scripts/little_loops/fsm/schema.py`, `scripts/little_loops/fsm/fsm-loop-schema.json` — if the declaration lives in loop YAML (Open Decision #2), the per-state `tools:` allowlist (`fsm-loop-schema.json:590-596`, `fsm/schema.py:684`) is the precedent.
- The capability registry — new; no existing module owns one.

### Dependent Files (Callers/Importers)
- Every task-path spawn site routed through the helper by ENH-3184. That issue's census is authoritative: 12 explicit hand-rolled env sites, 145 total spawn sites, implicit inheritance dominant.

### Conventions in Force
- **Feature-capability declarations** use a frozen dataclass of booleans set once per runner class (`HostCapabilities`, `host_runner.py:119-144`, e.g. `streaming`, `tool_allowlist`, `workspace_sandboxed`) — per-runner, not per-task. Closest existing analog to "declare a capability set," but the granularity doesn't fit AC1.
- **Failure polarity.** An undeclared/unsupported capability today triggers `CapabilityNotSupported(UserWarning)` (`host_runner.py:108-116`) — warn-and-drop, promotable via `warnings.simplefilter("error", CapabilityNotSupported)`. AC3 requires the opposite polarity; no existing hard-fail-on-undeclared-capability path exists in this module to build on.
- **Per-task capability declaration in loop YAML** has one precedent: the `tools:` allowlist is a per-*state* field flowing into `HostRunner.build_streaming(tools=...)`. Some runners honor it (`ClaudeCodeRunner`), others decline with a `CapabilityNotSupported` warning.
- **Staged rollout** (for AC5): `suppress_catalog` (`fsm-loop-schema.json:415-419`, `fsm/schema.py:457-460`) lands a schema field marked `"DECLARATIVE-ONLY (not yet implemented)"` in both the JSON Schema description and the Python dataclass docstring, enforced only by a validator warning (MR-12) until a runtime consumer exists.
- **Deprecation** is documented via a `[DEPRECATED: ...]` text marker in the JSON Schema `description` plus a matching inline comment (`config-schema.json:113,118`; `config/features.py:209-210`) — not the JSON Schema `"deprecated": true` keyword and not a `warnings.warn(DeprecationWarning, ...)` call at read time.

### Tests
- `scripts/tests/test_host_runner.py::TestAutomationProfileEnvAcrossRunners` (lines 52-84) is the established table-driven, cross-all-runner-classes pattern (BUG-3058 precedent). Scoping tests follow this shape, parametrized across `ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner` plus the `OpenCodeRunner`/`PiRunner` stubs.
- `scripts/tests/test_runner_spec.py`, `scripts/tests/test_subprocess_utils.py`.

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

## Open Decisions

Resolve before writing code; each changes what gets built.

1. **Mechanism — settled.** v1 is env projection, not token minting (see Summary).
2. **Does the declaration live on `ActionSpec`, in loop YAML per-state, or both?** The `tools:` allowlist (`fsm-loop-schema.json:590-596`) is the per-state precedent; `ActionSpec` is the per-task object. AC1 says "runner spec," which maps to `ActionSpec`, but FSM states are where authors actually write things down.
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
