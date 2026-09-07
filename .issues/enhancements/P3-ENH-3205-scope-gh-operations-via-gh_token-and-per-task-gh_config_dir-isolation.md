---
id: ENH-3205
type: ENH
title: Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation
priority: P3
status: open
parent: EPIC-3212
epic: EPIC-3212
blocked_by:
- ENH-3233
- ENH-3235
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:28:30Z'
testable: true
decision_needed: false
learning_tests_required:
- gh
---

# ENH-3205: Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation

## Summary

gh operations bypass `host_runner` entirely. `sync.py`'s `_run_gh_command()`/`_check_gh_auth()` rely on the ambient `gh auth login` session, which is repo- or org-broad, with no per-task token minted or injected anywhere.

**Env projection alone does not de-scope gh.** Its credential lives in the OS keyring / `~/.config/gh/hosts.yml`, not in `GITHUB_TOKEN`, so removing that variable from the child leaves the broad session fully usable. Constraining gh requires injecting an explicit `GH_TOKEN` **and** redirecting `GH_CONFIG_DIR` to a per-task directory so the ambient login is not visible. Both, or neither.

This is the one place where ENH-3203's guarantee visibly does not reach, and gh is what FSM loops actually use to make changes to the outside world — so it is the highest-value gap and the one most likely to be misread as already covered.

**Dependency status**: ENH-3203 was closed by *decomposition* into ENH-3233/3234/3235 — no projection code has landed yet. "Gated on a declaration" requires a declaration surface: the FSM shell path (this issue's primary gh surface, per Current Behavior) is ENH-3235, hence `blocked_by: [ENH-3233, ENH-3235]`.

**Scope decided (2026-09-04): FSM loop-YAML path only.** The `ll-action`/`ll-queue`/`ll-harness` path (ENH-3234) is *not* covered here. Because the gh pairing is implemented inside the shared shell-branch helper that resolves `scopes` → `extra=` (see Proposed mechanism), ENH-3234's `_run_cmd()` gets it for free the moment it calls the same helper; that is ENH-3234's job to wire, not this issue's to block on.

**Learning test (2026-09-04, gh 2.86.0, macOS, keyring-backed login, no `GH_TOKEN`/`GITHUB_TOKEN` in env)** — recorded in `.ll/learning-tests/gh.md`:
- `GH_CONFIG_DIR=<empty dir> gh auth status` → "You are not logged into any GitHub hosts" (exit 0). `gh api user` under the same env → "please run: gh auth login … or populate GH_TOKEN". **The redirect does hide the keyring login**; the mechanism is sound.
- `gh auth token` (ambient env) → exit 0, 40-char token. **The operator's token is obtainable from the ambient session without an env var.**
- The operator on this machine has **no** `GH_TOKEN`/`GITHUB_TOKEN` in env at all. The issue's original design ("`GH_TOKEN` comes from the operator's ambient env") would therefore hand a declaring task an empty config dir and *no token* — gh unusable, i.e. exactly the "appears scoped, proves nothing" failure this issue warns about. See Decision 1.

## Current Behavior

- `scripts/little_loops/sync.py` — `_run_gh_command()`/`_check_gh_auth()` shell out to gh directly, bypassing the host-runner layer entirely, and inherit whatever session the operator logged in with.
- FSM loops invoke gh through `DefaultActionRunner`'s `bash -c` branch (`fsm/runners.py:297`), so the shell-action path is the larger surface, not `sync.py`.
- Even under ENH-3203's projection, stripping `GITHUB_TOKEN` from a child changes nothing: gh falls back to the keyring / `~/.config/gh/hosts.yml`, which `HOME` still points at.

## Expected Behavior

A task declaring GitHub access receives an explicit `GH_TOKEN` and a `GH_CONFIG_DIR` pointing at a per-task directory containing no ambient login. A task not declaring it can neither read `GH_TOKEN` nor reach the operator's gh session.

If this is not implemented, ENH-3203 must state plainly that gh is unscoped rather than imply coverage it does not deliver.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — a `gh_scope_extra(tmpdir) -> dict[str, str]` helper beside the credential-scope registry: returns `{"GH_TOKEN": <token>, "GH_CONFIG_DIR": str(tmpdir)}` or raises. Token source per Decision 1.
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner` shell branch (`:297-305`): when the resolved scopes include `github`, open a per-spawn `tempfile.TemporaryDirectory()` around the `Popen`, and merge `gh_scope_extra(...)` into the existing `extra=` dict. Caller-supplied `extra` keys bypass ENH-3233's allow-set (its AC2b), so no registry change is needed for `GH_CONFIG_DIR`.
- **`sync.py` — removed from scope (2026-09-04).** `_run_gh_command()`/`_check_gh_auth()` run inside the operator's own interactive `ll-sync` process, not inside a task; there is no declaration to gate on and nothing to isolate from. It is also absent from `test_enh3184_spawn_site_guard.py`'s pinned table, so leaving it untouched changes no gate. If it is ever brought under the chokepoint, that is a separate one-line ENH (add `env=project_child_env()` + table entry).

### Proposed mechanism
1. Shell branch resolves `scopes` → `env_allow` (ENH-3235).
2. If `"github" in scopes`: `with tempfile.TemporaryDirectory(prefix="ll-gh-") as d:` — `extra.update(gh_scope_extra(Path(d)))`; `Popen(..., env=project_child_env(extra=extra, env_allow=env_allow))`; the `with` block spans the wait, so the dir outlives the child.
3. `gh_scope_extra()` obtains the token: `os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")`, else `subprocess.run(["gh", "auth", "token"], env=project_child_env(), ...)` against the *ambient* config (no redirect), stripped stdout. If both fail → raise, and the shell branch returns a failed `ActionResult` naming the cause ("declared `github` scope but no token available: set GH_TOKEN or run `gh auth login`"). **Never** fall back to an un-redirected child — that is the silent-fallback failure mode from Impact/Risk.
4. The `gh auth token` probe is itself a `subprocess.run` in `host_runner.py` → bump the `test_enh3184_spawn_site_guard.py` count for `little_loops/host_runner.py` from `(1, 0)` to `(2, 0)`.

### Tests
- A test proving a scoped child's `gh auth status` does not see the ambient login: spawn `bash -c 'gh auth status; echo $GH_CONFIG_DIR'` through `DefaultActionRunner` with `scopes=["github"]` and a monkeypatched `GH_TOKEN=dummy`; assert the output's config-dir path is under the tempdir and is not `~/.config/gh`. Skip if `gh` is absent (per the CI policy in CLAUDE.md).
- Both-or-neither: with `scopes=["github"]` the child env has both `GH_TOKEN` and `GH_CONFIG_DIR`; with `scopes=[]` (declared, empty) it has neither, even when the parent has `GH_TOKEN` set.
- No-token path: `GH_TOKEN`/`GITHUB_TOKEN` unset and `gh auth token` mocked to fail → `ActionResult` failure naming the scope, no `Popen` of the action.
- Tempdir is removed after the child exits (both success and timeout paths).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- **Chokepoint convention**: subprocess env construction has a single chokepoint, `project_child_env()` (`scripts/little_loops/host_runner.py:1865`). An AST-based static test, `test_enh3184_spawn_site_guard.py`, enforces every task-path `subprocess.*` call in a pinned per-module table routes through it (directly, via a variable assigned from it, or via an inline `# ll-no-project:` exemption comment). `scripts/little_loops/sync.py` is **not currently in that pinned table** — `_run_gh_command()`'s `subprocess.run(cmd, capture_output=True, text=True, check=check)` (`sync.py:98-124`) passes no `env=` at all, so this guard enforces nothing about `sync.py` today.
- **No deny primitive yet**: `project_child_env()` only supports additive overrides (`invocation.env`, `extra={...}`) — it has no primitive to deny/clear an inherited variable. ENH-3233 (a direct `blocked_by` of this issue) specifies an `env_allow: frozenset[str] | None` parameter to add that capability, but as of this pass it exists only as design text in ENH-3233 — no `env_allow` symbol exists anywhere under `scripts/` yet.
- **One-off keys via `extra=`**: one-off env keys are passed as `project_child_env(extra={...})` rather than mutated onto the returned dict afterward — e.g. `git_operations.py:728`, `parallel/worker_pool.py:859-861`, `fsm/runners.py:305`.
- **Both-or-neither pairing has no validator**: existing "set together, never one without the other" pairs (`GIT_DIR`/`GIT_WORK_TREE` in `host_runner.py:425-433` and its `CodexRunner`/`GeminiRunner` counterparts; `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` in `_apply_automation_env()`, `host_runner.py:1898-1915`) achieve pairing only by code-block co-location. No runtime or test-level assertion enforces the pairing in either case — searched repo-wide, no such helper exists to reuse.
- **Per-task directory lifecycle, two existing shapes**: (a) a `tempfile.TemporaryDirectory()` scoped to a `with` block and reused across multiple subprocess calls sharing one `env` dict (`git_operations.py::preserve_dirty_tree()`, lines 725-749); (b) a heavier explicit create → out-of-tree registry entry → in-tree pid marker → cleanup pairing (`worktree_utils.py::setup_worktree()`/`cleanup_worktree()`, lines 283-472, with `_write_registry_entry()`/`_remove_registry_entry()`). Neither is GH_CONFIG_DIR-specific.
- **Nearest allow-set shape precedent**: `MUTATING_TOOLS`, a bare module-level `frozenset[str]` consulted via `in` (`scripts/little_loops/mcp_server/policy.py:55-63`). ENH-3233's own research already names this as "shape precedent only" — no per-entry metadata, no fail-loud-on-unknown-name behavior.
- **Test convention for "child cannot see ambient credential"**: this codebase asserts it two ways — (a) spawn a subprocess whose own `python3 -c` one-liner inspects its own `os.environ` and communicates via exit code (`test_worktree_utils.py::test_ll_python_scrubbed_from_child_env`, lines 1359-1388, and the positive-case sibling `test_verify_gate_marker_set_in_child_env`, lines 1336-1357); (b) assert directly on `project_child_env()`'s returned dict with no subprocess spawned (`test_host_runner.py::TestProjectChildEnv`, lines 96-139; the adjacent `TestProjectChildEnvCrossRunnerParity`, lines 142-159, carries the `@pytest.mark.parametrize("runner_cls", ...)` across every `HostRunner` subclass). No shared/reusable "assert credential not visible" fixture exists — every instance inlines its own check.
- **Searched, no hits**: `GH_TOKEN`/`GH_CONFIG_DIR` literals, `env_allow`, a both-or-neither validator, and token-minting code were all searched repo-wide across `scripts/` with no filter — none exist in shipped code.

## Program Design

### Types
- No new type is required. The `GH_TOKEN`/`GH_CONFIG_DIR` pair is two entries in the allow-set ENH-3203 already computes.

### Signatures
- `gh_scope_extra(config_dir: Path) -> dict[str, str]` (new, `host_runner.py`) — returns exactly `{"GH_TOKEN", "GH_CONFIG_DIR"}`; raises `RuntimeError` when no token is obtainable. Pure apart from the `gh auth token` probe.
- `DefaultActionRunner.run(..., scopes: list[str] | None = None, ...)` — ENH-3235's new kwarg; this issue adds the `github` branch inside the shell path, no further signature change.
- (`sync.py`'s `_run_gh_command`/`_check_gh_auth` — no longer modified; see Files to Modify.)

### Call Path
`StateConfig.scopes` → `FSMExecutor` dispatch → `DefaultActionRunner` shell branch (`fsm/runners.py:297`) → [`github` declared] `TemporaryDirectory` + `gh_scope_extra()` → `project_child_env(extra=..., env_allow=...)` → `subprocess.Popen(["bash", "-c", action])`

### Decision Rules
- Both `GH_TOKEN` and `GH_CONFIG_DIR` are set, or neither is. Setting only the token leaves the ambient login reachable and produces the appearance of scoping without the fact of it. Enforced by a single helper that returns both keys or raises — there is no code path that yields one.
- A declared `github` scope with no obtainable token **fails the state**, never falls back to the ambient session.
- Undeclared states are unaffected, consistent with ENH-3203's AC5.
- Git-over-SSH is unscoped by this issue: this repo's operator uses `git_protocol: ssh`, so `git push` authenticates via `SSH_AUTH_SOCK` (ENH-3233 baseline), not gh. No global `credential.helper` is configured either. Only `gh` API/CLI calls and HTTPS git via `gh auth git-credential` are constrained.

## Scope Boundaries

Explicitly **out of scope**:

- **Token minting.** No GitHub App installation tokens. Without minting, this projects an equally broad token to fewer processes — see Open Decision #1.
- **The declaration mechanism** — ENH-3203.
- **Other keyring-backed credentials** (`~/.aws/credentials`, `~/.netrc`, the macOS keychain). gh is singled out because it is what loops actually use to change the outside world, not because it is the only one.
- **`HOME` redirection.** `GH_CONFIG_DIR` is a targeted redirect; relocating `HOME` wholesale is a much larger change with its own breakage surface.
- **SSH-keyed git operations** (see Decision Rules) — `SSH_AUTH_SOCK` is baseline; scoping SSH agent access is a different mechanism entirely.
- **`sync.py`** — operator-interactive, not a task path (see Files to Modify).
- **The `ll-action`/`ll-queue` path** — ENH-3234 wires the same helper when it lands.

## Decisions (resolved 2026-09-04, pre-implementation epic review)

1. **Where does `GH_TOKEN` come from?** — **Projection-only, sourced from the ambient session.** Order: `GH_TOKEN` env → `GITHUB_TOKEN` env → `gh auth token` (ambient config, no redirect). The learning test shows the third source is the *only* one available on this machine, so without it the feature is dead on arrival. No minting; the token is exactly as broad as the operator's. What this buys is real but bounded: an *undeclared* state can no longer reach gh at all (empty config dir is not applied to undeclared states — they are full-inherit — but a declaring state that omits `github` gets neither token nor keyring), and a *declaring* state gets the token only in its own process tree. Worth having because it closes the "gh is what loops use to change the world" gap; the narrowing question is deferred to a future minting issue.
   - **Exposure note**: today the operator's token is keyring-only and never in any env. After this change a declaring state's child env *contains* the token in plaintext — visible to `env`, `ps e`, crash dumps, and any `set -x` output the action logs. That is a strictly wider exposure for the declaring task's subtree than the status quo. Mitigation is in ENH-3204's names-only rule (never log the value) and a note in LOOPS_GUIDE that `scopes: [github]` puts a live token in the shell environment.
2. **Per-task `GH_CONFIG_DIR` lifecycle** — **Per-spawn `tempfile.TemporaryDirectory()`** scoped to the `Popen`+wait in the shell branch (the `git_operations.py::preserve_dirty_tree()` shape, lines 725-749). gh writes nothing into the config dir under token auth, so there is no state to preserve across spawns and no registry/pid marker needed; the `worktree_utils` registry shape is over-engineering here. Cleanup is the context manager's exit, including the timeout/kill path.

## Impact

- **Priority**: P3 — the highest-value remaining gap, but its value is bounded by Open Decision #1: without minting, this isolates *which* processes see a broad token rather than narrowing the token itself.
- **Effort**: Medium — two call sites plus config-dir lifecycle, but the keyring interaction is easy to get subtly wrong.
- **Risk**: Medium — a `GH_CONFIG_DIR` redirect that breaks the operator's interactive gh usage, or a scoped child that silently falls back to the ambient session and appears to work while proving nothing.
- **Breaking Change**: No, if gated on a declaration.

## Status

**Open** | Created: 2026-08-15 | Priority: P3

## Verification Notes (2026-09-03)

- `fsm/runners.py:266` citations corrected to `:297` (bash-c branch moved).
- `worker_pool.py:859-861` citation corrected to `parallel/worker_pool.py:859-861` (no file exists at the un-prefixed path).
- `test_host_runner.py::TestProjectChildEnv` citation corrected: the "parametrized across every `HostRunner` subclass" characterization belongs to the adjacent `TestProjectChildEnvCrossRunnerParity` class (lines 142-159), not `TestProjectChildEnv` itself (96-139).
- All other Codebase Research Findings citations (sync.py, host_runner.py, git_operations.py, worktree_utils.py, mcp_server/policy.py, test_worktree_utils.py) confirmed accurate at their stated lines.
- Graph: provider=`codegraph` freshness=`fresh`.
- **DEP_ISSUES**: `ENH-3233` (a `blocked_by` entry) has no `ENH-3205` entry in its own `## Blocks` section — MISSING_BACKLINK. Not corrected here (out of this issue's own-file scope); `ENH-3233`'s file needs the backlink added.
- Evidence-quote check (`ll-verify-evidence`): clean, no fabricated spans.
- No active required decision rules found in the decisions log.

## Review Notes (2026-09-04, pre-implementation epic review)

- Ran the required `gh` learning test (gh 2.86.0): `GH_CONFIG_DIR` redirect hides the keyring
  login; `gh auth token` yields the ambient token. Recorded in `.ll/learning-tests/gh.md`.
- Found the design's token source was empty on this machine (no `GH_TOKEN`/`GITHUB_TOKEN` in
  env); Decision 1 now sources via `gh auth token` with fail-closed on no token.
- Decision 2 resolved (per-spawn `TemporaryDirectory`). `decision_needed` → `false`.
- `sync.py` removed from scope (operator-interactive, not a task path). Scope pinned to the FSM
  path; ENH-3234 not added to `blocked_by`.
- Added SSH-git and exposure notes. Concrete mechanism, signatures, and tests written.
- Cleared stale `verify_verdict: NON_VALID` — its only finding (ENH-3233 missing backlink) was
  fixed in ENH-3233's 2026-09-03 verify pass. Re-run `/ll:verify-issues` before `ready-issue`.

## Session Log
- `/ll:wire-issue` - 2026-09-07T03:48:29 - `24278e0c-f73c-4e7c-b229-0bf010cc0589.jsonl`
- `/ll:verify-issues` - 2026-09-03T20:10:57 - `433c9d43-d77e-48a9-ae6d-2a38645d30bb.jsonl`
- `/ll:refine-issue` - 2026-09-03T19:37:52 - `e69aa141-6d57-4757-9f35-bf5dfd784b25.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:56 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
