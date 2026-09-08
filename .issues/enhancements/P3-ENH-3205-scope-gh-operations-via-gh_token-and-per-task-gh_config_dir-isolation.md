---
id: ENH-3205
type: ENH
title: Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation
priority: P3
status: done
parent: EPIC-3212
epic: EPIC-3212
blocked_by:
- ENH-3395
- ENH-3396
- ENH-3235
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T22:28:30Z'
completed_at: '2026-09-07T23:07:14Z'
testable: true
decision_needed: false
verify_verdict: NON_VALID
learning_tests_required:
- gh
size: Very Large
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

A task declaring GitHub access receives an explicit `GH_TOKEN` and a `GH_CONFIG_DIR` pointing at a per-task directory containing no ambient login. A **declaring** task that omits `github` gets the `GH_CONFIG_DIR` redirect (empty dir) but no `GH_TOKEN`, so it can neither read a token nor reach the operator's keyring session. An **undeclared** task (`scopes` absent) is full-inherit and unaffected (ENH-3203 AC5).

**Invariant corrected (2026-09-06 review; sentinel added 2026-09-08 for BUG-3402).** The earlier "both `GH_TOKEN` and `GH_CONFIG_DIR`, or neither" rule was wrong: gating the redirect on `"github" in scopes` leaves `HOME` intact for a declaring-but-non-github state, so gh silently falls back to `~/.config/gh/hosts.yml` and works fully — the exact failure the Summary warns about. The correct rule is: **redirect `GH_CONFIG_DIR` whenever `scopes is not None`; inject `GH_TOKEN` iff `"github" in scopes`, else inject the `GH_SCOPED_NO_TOKEN` sentinel.** On keychain-backed macOS `gh`, an unset/empty `GH_TOKEN` is not enough — `gh auth token` reads the login Keychain by hostname independent of `GH_CONFIG_DIR`, so a non-github-declaring state (or a nested `github` state that inherits the sentinel) could still mint the operator's real token via that command (BUG-3402). `gh_scope_extra()` closes this by injecting a non-empty, obviously-invalid `GH_SCOPED_NO_TOKEN` sentinel instead of leaving `GH_TOKEN` unset, and treating an inherited sentinel (via env or probe stdout) as "no token" on the `with_token=True` path. Consequence worth stating: the token is non-escalating across nested loops — an inner `github` state spawned under an outer non-github declaring state inherits the sentinel, which is rejected by both the env lookup and the `gh auth token` probe, so it fails closed with the existing "no token available" error rather than reaching the operator's keyring. A non-github-declaring child's own `gh` commands now get an HTTP 401 "Bad credentials" from the network instead of a local "run gh auth login" message, and other `GH_TOKEN`-honoring tools lose their anonymous fallback inside such a child.

If this is not implemented, ENH-3203 must state plainly that gh is unscoped rather than imply coverage it does not deliver.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — a `gh_scope_extra(tmpdir, *, with_token: bool) -> dict[str, str]` helper beside the credential-scope registry: always returns `{"GH_CONFIG_DIR": str(tmpdir)}`; when `with_token=True` also returns `"GH_TOKEN": <token>` or raises. Token source per Decision 1.
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner` shell branch (`:297-305`): whenever `scopes is not None`, open a per-spawn `tempfile.TemporaryDirectory()` around the `Popen`, and merge `gh_scope_extra(Path(d), with_token="github" in scopes)` into the existing `extra=` dict. Caller-supplied `extra` keys bypass ENH-3233's allow-set (its AC2b), so no registry change is needed for `GH_CONFIG_DIR`.
- **Config loss note**: redirecting `GH_CONFIG_DIR` also hides the operator's `config.yml` (`git_protocol`, `editor`, aliases). gh then defaults to `git_protocol: https`, which works with `GH_TOKEN` via `gh auth git-credential` but differs from this operator's `ssh` setting. Document in LOOPS_GUIDE alongside the exposure note; do not copy `config.yml` into the tempdir (it would re-introduce a path to ambient state).
- **Probe cost**: `gh auth token` is a keyring read per spawn (~100ms on macOS). Acceptable for v1; a per-process cache keyed on the ambient `GH_CONFIG_DIR`/`HOME` is a possible follow-on, not part of this issue.
- **`sync.py` — removed from scope (2026-09-04).** `_run_gh_command()`/`_check_gh_auth()` run inside the operator's own interactive `ll-sync` process, not inside a task; there is no declaration to gate on and nothing to isolate from. It is also absent from `test_enh3184_spawn_site_guard.py`'s pinned table, so leaving it untouched changes no gate. If it is ever brought under the chokepoint, that is a separate one-line ENH (add `env=project_child_env()` + table entry).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/testing.py:85` — a second production call site, `runner = DefaultActionRunner()`, used for ad-hoc loop-testing invocation outside `FSMExecutor`. No code change needed here: it goes through the same shell branch, so a future `scopes=` argument at this call site would automatically get the `gh_scope_extra` treatment. Noted only so the caller inventory is complete. [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py:300` (`self.action_runner: ActionRunner = action_runner or DefaultActionRunner()`) is the sole production `FSMExecutor` instantiation site — already implied by the issue's Call Path but not previously listed as a file. [Agent 1 finding]

### Proposed mechanism
1. Shell branch resolves `scopes` → `env_allow` (ENH-3235).
2. If `scopes is not None`: `with tempfile.TemporaryDirectory(prefix="ll-gh-") as d:` — `extra.update(gh_scope_extra(Path(d), with_token="github" in scopes))`; `Popen(..., env=project_child_env(extra=extra, env_allow=env_allow))`; the `with` block spans the wait, so the dir outlives the child. The redirect is unconditional for declaring states; only the token is gated on `github`.
3. `gh_scope_extra(..., with_token=True)` obtains the token: `os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")`, else `subprocess.run(["gh", "auth", "token"], env=project_child_env(), ...)` against the *ambient* config (no redirect), stripped stdout. If both fail → raise, and the shell branch returns a failed `ActionResult` naming the cause ("declared `github` scope but no token available: set GH_TOKEN or run `gh auth login`"). **Never** fall back to an un-redirected child — that is the silent-fallback failure mode from Impact/Risk.
4. The `gh auth token` probe is itself a `subprocess.run` in `host_runner.py` → bump the `test_enh3184_spawn_site_guard.py` count for `little_loops/host_runner.py` from `(1, 0)` to `(2, 0)`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `test_enh3184_spawn_site_guard.py` — bump the `little_loops/host_runner.py` tuple `(1, 0)` → `(2, 0)` **and** update the explanatory comment at lines 44-47 to name the new `gh auth token` probe spawn.
- Update `test_fsm_runners.py::test_shell_declared_scope_allows_its_vars_denies_others` (415-428) to also assert the child's `GH_CONFIG_DIR` is redirected to a tempdir path, not just that `GH_TOKEN` passes through.
- Add `### gh_scope_extra` to `docs/reference/API.md` alongside the existing `### resolve_scopes`/`### project_child_env` entries.
- Add a `scopes:` row (plus the exposure and `git_protocol`/`config.yml`-loss notes) to `docs/guides/LOOPS_GUIDE.md`'s `### Subprocess Agent and Tool Scoping` table (line 589) — do not confuse with the unrelated `### Scope-Based Concurrency` section (line 826).

### Tests
- A test proving a scoped child's `gh auth status` does not see the ambient login: spawn `bash -c 'gh auth status; echo $GH_CONFIG_DIR'` through `DefaultActionRunner` with `scopes=["github"]` and a monkeypatched `GH_TOKEN=dummy`; assert the output's config-dir path is under the tempdir and is not `~/.config/gh`. Skip if `gh` is absent (per the CI policy in CLAUDE.md).
- Redirect-always / token-iff-github: with `scopes=["github"]` the child env has both `GH_TOKEN` and `GH_CONFIG_DIR`; with `scopes=[]` (declared, empty) it has `GH_CONFIG_DIR` (under the tempdir) and **no** `GH_TOKEN`, even when the parent has `GH_TOKEN` set; with `scopes=None` (undeclared) it has neither injected and inherits whatever the parent had.
- Keyring hidden for declaring-non-github: spawn `bash -c 'gh auth status'` with `scopes=[]` on a machine with an ambient `gh auth login`; assert the output says not logged in. Skip if `gh` is absent. This is the test that would have caught the original both-or-neither bug.
- Non-escalation: an inner `DefaultActionRunner` spawn with `scopes=["github"]` run with `GH_CONFIG_DIR` already pointing at an empty dir and no `GH_TOKEN`/`GITHUB_TOKEN` in env (simulating an outer non-github declaring state) fails the state; no `Popen` of the action.
- No-token path: `GH_TOKEN`/`GITHUB_TOKEN` unset and `gh auth token` mocked to fail → `ActionResult` failure naming the scope, no `Popen` of the action.
- Tempdir is removed after the child exits (both success and timeout paths).

_Wiring pass added by `/ll:wire-issue`:_
- `test_fsm_runners.py::test_shell_declared_scope_allows_its_vars_denies_others` (lines 415-428, un-mocked real `Popen` spawn) already sets `scopes=["github"]` and `monkeypatch.setenv("GH_TOKEN", "gh-secret")`, asserting the child echoes `GH_TOKEN=gh-secret`. Under Decision 1's token-source order this assertion's value still holds post-change, but the test gives **no coverage of the `GH_CONFIG_DIR` redirect** — update it to also assert the child's `GH_CONFIG_DIR` is a tempdir path, not `~/.config/gh`. [Agent 3 finding]
- `test_host_runner.py` test-class line ranges are stale again as of this pass: `TestProjectChildEnv` is 98-141, `TestProjectChildEnvDenyMode` is 144-268, `TestProjectChildEnvCrossRunnerParity` is 271-289 (not "98-184" as the issue's own 2026-09-07 Codebase Research Findings entry states) — re-verify anchors immediately before citing these lines in new deny-mode-adjacent tests. [Agent 3 finding]
- No existing test mocks `gh auth token` specifically. Nearest patterns to follow: dispatch-by-argv (`test_orchestrator.py::test_opens_pr_when_open_pr_true`, ~lines 2047-2077, a `fake_run` that branches on `args[0]/args[1]`) vs. patch-the-wrapper-function (`test_sync.py::TestGitHubCLIHelpers`, ~lines 306-350, `patch("little_loops.sync._run_gh_command")`). `host_runner.py` has no gh wrapper function to patch, so new tests for `gh_scope_extra`'s token-probe path should use the dispatch-by-argv shape, patching `little_loops.host_runner.subprocess.run`. [Agent 3 finding]
- `test_enh3184_spawn_site_guard.py:44-47`'s explanatory comment above the pinned-table entry ("Holds the helper itself plus `run_blocking_json`'s spawn...") will itself go stale once `gh_scope_extra`'s `gh auth token` probe lands — update the comment to name that third spawn, not just bump the tuple `(1, 0)` → `(2, 0)`. [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — the `### Subprocess Agent and Tool Scoping` section (line 589)'s field table has rows for `agent:`, `tools:`, `model:`, `effort:` but **no row for `scopes:` at all** — the state-level credential-scope field (ENH-3235) was never documented here. This is the anchor for both this issue's exposure note ("`scopes: [github]` puts a live token in the shell environment... visible to `env`, `ps e`, crash dumps") and the `git_protocol`/`config.yml`-loss note. Caution: this file also has an unrelated `### Scope-Based Concurrency` section (line 826) about loop-lock `scope:` — a different concept; do not conflate. [Agent 2 finding]
- `docs/reference/API.md` — `### resolve_scopes` (~line 10174) and `### project_child_env` (~line 10198) are documented; there is no `### gh_scope_extra` entry yet. Add one following the same convention (signature block, behavior bullets, fail-loud notes). [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- **Chokepoint convention**: subprocess env construction has a single chokepoint, `project_child_env()` (`scripts/little_loops/host_runner.py:2027`). An AST-based static test, `test_enh3184_spawn_site_guard.py`, enforces every task-path `subprocess.*` call in a pinned per-module table routes through it (directly, via a variable assigned from it, or via an inline `# ll-no-project:` exemption comment). `scripts/little_loops/sync.py` is **not currently in that pinned table** — `_run_gh_command()`'s `subprocess.run(cmd, capture_output=True, text=True, check=check)` (`sync.py:98-124`) passes no `env=` at all, so this guard enforces nothing about `sync.py` today.
- **No deny primitive yet**: `project_child_env()` only supports additive overrides (`invocation.env`, `extra={...}`) — it has no primitive to deny/clear an inherited variable. ENH-3233 (a direct `blocked_by` of this issue) specifies an `env_allow: frozenset[str] | None` parameter to add that capability, but as of this pass it exists only as design text in ENH-3233 — no `env_allow` symbol exists anywhere under `scripts/` yet.
- **One-off keys via `extra=`**: one-off env keys are passed as `project_child_env(extra={...})` rather than mutated onto the returned dict afterward — e.g. `git_operations.py:728`, `parallel/worker_pool.py:859-861`, `fsm/runners.py:305`.
- **Both-or-neither pairing has no validator**: existing "set together, never one without the other" pairs (`GIT_DIR`/`GIT_WORK_TREE` in `host_runner.py:425-433` and its `CodexRunner`/`GeminiRunner` counterparts; `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` in `_apply_automation_env()`, `host_runner.py:1898-1915`) achieve pairing only by code-block co-location. No runtime or test-level assertion enforces the pairing in either case — searched repo-wide, no such helper exists to reuse.
- **Per-task directory lifecycle, two existing shapes**: (a) a `tempfile.TemporaryDirectory()` scoped to a `with` block and reused across multiple subprocess calls sharing one `env` dict (`git_operations.py::preserve_dirty_tree()`, lines 725-760); (b) a heavier explicit create → out-of-tree registry entry → in-tree pid marker → cleanup pairing (`worktree_utils.py::setup_worktree()`/`cleanup_worktree()`, lines 283-472, with `_write_registry_entry()`/`_remove_registry_entry()`). Neither is GH_CONFIG_DIR-specific.
- **Nearest allow-set shape precedent**: `MUTATING_TOOLS`, a bare module-level `frozenset[str]` consulted via `in` (`scripts/little_loops/mcp_server/policy.py:55-63`). ENH-3233's own research already names this as "shape precedent only" — no per-entry metadata, no fail-loud-on-unknown-name behavior.
- **Test convention for "child cannot see ambient credential"**: this codebase asserts it two ways — (a) spawn a subprocess whose own `python3 -c` one-liner inspects its own `os.environ` and communicates via exit code (`test_worktree_utils.py::test_ll_python_scrubbed_from_child_env`, lines 1359-1388, and the positive-case sibling `test_verify_gate_marker_set_in_child_env`, lines 1336-1357); (b) assert directly on `project_child_env()`'s returned dict with no subprocess spawned (`test_host_runner.py::TestProjectChildEnv`, lines 96-139; the adjacent `TestProjectChildEnvCrossRunnerParity`, lines 142-159, carries the `@pytest.mark.parametrize("runner_cls", ...)` across every `HostRunner` subclass). No shared/reusable "assert credential not visible" fixture exists — every instance inlines its own check.
- **Searched, no hits**: `GH_TOKEN`/`GH_CONFIG_DIR` literals, `env_allow`, a both-or-neither validator, and token-minting code were all searched repo-wide across `scripts/` with no filter — none exist in shipped code.

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **Validator already covers `github`**: `fsm/validation/structural_rules.py:492-521` (ENH-3235 AC9/AC10) validates `state.scopes` against `CREDENTIAL_SCOPES` and requires the state be shell-only. `CREDENTIAL_SCOPES["github"]` already exists (`host_runner.py:124-163`), so `scopes: [github]` on a shell state passes this validator today — no validator change is needed for this issue.
- **`test_enh3184_spawn_site_guard.py:48`** confirmed: the pinned table entry is `"little_loops/host_runner.py": (1, 0)` — this is what bumps to `(2, 0)` once `gh_scope_extra()`'s `gh auth token` probe subprocess call lands.
- **Session-store audit gap**: `session_store/writers.py:1945` `write_credential_scope()` (table `credential_scope_events`, `session_store/schema.py:1317`, called from `fsm/executor.py:2567-2582`) records only the declared scope names and their resolved env-var *names* (e.g. `GH_TOKEN`) at spawn time — it has no field for `GH_CONFIG_DIR` or for whether a token was actually obtained. The after-the-fact audit trail cannot distinguish "declared `github`, token available" from "declared `github`, `gh_scope_extra` raised" from session-store data alone.
- **Stale test-class line citations**: `test_host_runner.py`'s `TestProjectChildEnv` now spans lines 98-184 and includes a sibling `TestProjectChildEnvDenyMode` class (added since ENH-3395 landed) — the line ranges cited in this issue's 2026-09-03 pass (96-139 / 142-159) have shifted; re-verify anchors before adding new deny-mode-adjacent tests.
- **`sync.py` confirmed unchanged**: `_run_gh_command()`/`_check_gh_auth()` still call `subprocess.run` with no `env=` kwarg, across 16 call sites (lines 357, 448, 480, 517, 556, 575, 780, 782, 832, 855, 896, 924, 976, 1021, 1059, 1094, 1122) — the out-of-scope framing for `sync.py` in this issue remains accurate.

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **No precedent for a `TemporaryDirectory()` spanning a `Popen`+selector-loop with multiple exit paths**: the only existing `TemporaryDirectory()`+subprocess pairing in this codebase (`git_operations.py::preserve_dirty_tree`, ~lines 725-760) wraps a single synchronous `subprocess.run()` call and its immediate returncode check — a straight-line path with no timeout-kill branch. `fsm/runners.py`'s shell branch holds its `Popen` object (`:326-333`) across a `selectors`-driven read loop with two distinct exit branches (timeout/idle-kill around `:409-426`, normal `process.wait()` around `:428-436`); no existing file wraps a tempdir around a `Popen` that must outlive both. [Agent 3 finding]
- **Existing catch/convert shape any `gh_scope_extra` error must follow**: `ENH-3235`'s `resolve_scopes()` call in the shell branch is already wrapped in `try/except ValueError`, converting the exception into a failed `ActionResult` (`fsm/runners.py:~314-324`) rather than letting it propagate — this preserves `DefaultActionRunner.run()`'s "never raises" contract. Test precedent for this shape: `test_fsm_runners.py::test_shell_unknown_scope_fails_loud_and_spawns_nothing` patches `little_loops.fsm.runners.subprocess.Popen`, asserts `mock_popen.assert_not_called()`, and asserts the returned `ActionResult` has a non-zero `exit_code` with the offending identifier substring-matched in `result.stderr`. A `gh_scope_extra` `RuntimeError` would need the same catch-and-convert treatment to keep the runner's contract. [Agent 3 finding]
- **`sync.py`'s `_run_gh_command()` confirmed module-private**: grep confirms it is imported/used only inside `sync.py` and its own test file (`test_sync.py`) — no reusable "run a gh subcommand" wrapper exists anywhere in the codebase for `gh_scope_extra`'s `gh auth token` probe to call into; it would need its own bespoke `subprocess.run` call. Corroborates the Tests section's existing note that `host_runner.py` has no gh wrapper function to patch. [Agent 3 finding]

## Program Design

### Types
- No new type is required. The `GH_TOKEN`/`GH_CONFIG_DIR` pair is two entries in the allow-set ENH-3203 already computes.

### Signatures
- `gh_scope_extra(config_dir: Path, *, with_token: bool) -> dict[str, str]` (new, `host_runner.py`) — always returns `GH_CONFIG_DIR`; with `with_token=True` also returns `GH_TOKEN` or raises `RuntimeError` when no token is obtainable. Pure apart from the `gh auth token` probe. There is no code path that yields a token without the redirect.
- `DefaultActionRunner.run(..., scopes: list[str] | None = None, ...)` — ENH-3235's new kwarg; this issue adds the `github` branch inside the shell path, no further signature change.
- (`sync.py`'s `_run_gh_command`/`_check_gh_auth` — no longer modified; see Files to Modify.)

### Call Path
`StateConfig.scopes` → `FSMExecutor` dispatch → `DefaultActionRunner` shell branch (`fsm/runners.py:297`) → [`github` declared] `TemporaryDirectory` + `gh_scope_extra()` → `project_child_env(extra=..., env_allow=...)` → `subprocess.Popen(["bash", "-c", action])`

### Decision Rules
- **Redirect whenever declaring; token iff `github`.** `GH_CONFIG_DIR` is set for every state with `scopes is not None`; `GH_TOKEN` is additionally set only when `"github" in scopes`. A token without the redirect is impossible (single helper), and a declaring state without the redirect is impossible (unconditional on `scopes is not None`). Setting only the token, or skipping the redirect for a non-github declaring state, leaves the ambient login reachable and produces the appearance of scoping without the fact of it.
- A declared `github` scope with no obtainable token **fails the state**, never falls back to the ambient session.
- Undeclared states are unaffected, consistent with ENH-3203's AC5.
- Git-over-SSH is unscoped by this issue: this repo's operator uses `git_protocol: ssh`, so `git push` authenticates via `SSH_AUTH_SOCK` (ENH-3233 baseline), not gh. No global `credential.helper` is configured either. Only `gh` API/CLI calls and HTTPS git via `gh auth git-credential` are constrained.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **Exact insertion point in `fsm/runners.py`'s shell branch**: the `resolve_scopes` try/except ends at line 325; `cmd = ["bash", "-c", action]` follows at line 326; the bare `subprocess.Popen(...)` call (no `with`, `process` assigned directly) spans lines 327-335, with `self._current_process = process` at line 336. A per-spawn `TemporaryDirectory` must wrap not just the `Popen` call but through both the timeout-return path (~409-426) and the normal-exit return path (~428-436) — the function's existing `finally:` block only closes the selector and clears `self._current_process`; nothing today scopes a resource across the whole function tail.
- **Nearest existing tempdir shape, corrected citation**: `preserve_dirty_tree()`'s temp-dir block (`git_operations.py`) is lines 725-760 (not 725-749 as previously cited) — `with tempfile.TemporaryDirectory() as tmpdir:` wrapping two sequential `subprocess.run()` calls sharing one `env=project_child_env(extra={"GIT_INDEX_FILE": tmp_index})` dict. Closest available shape, but it uses `subprocess.run` twice, not a single `Popen`+wait spanning a selector loop.
- **No convention exists for scrubbing a secret obtained via subprocess**: searched repo-wide (`gh auth token`, `token`, `secret`, redaction terms) — the only "sensitive value" convention found is names-only logging in `project_child_env()` (`host_runner.py:2051`,`:2103`,`:2112`) and `pii.py:39`'s `redact_pii()`, which redacts free-text PII for log/SFT export, not credential values in subprocess env or exceptions. `gh_scope_extra`'s `RuntimeError` on no-token-obtainable must be written to name the failure without echoing any partial token or the probe subprocess's stderr.
- **Fail-loud precedents confirmed precise**: `resolve_scopes()`'s `ValueError` (`host_runner.py:166-183`) and `project_child_env()`'s narrowing-only env overrides `LL_ENV_PROJECTION_FORCE_ALLOW`/`LL_ENV_PROJECTION_REPORT` (`host_runner.py:2062-2067`, documented as "can never widen an allow-set or disable deny mode") are the two existing fail-loud/never-widen precedents `gh_scope_extra` should match.
- **No both-or-neither/co-requirement validator exists anywhere in this codebase** (confirmed again): every "pairing" hit found (`cli_args.py:267,292`, `worktree_utils.py:326`, `fsm/schema.py`, `structural_rules.py:523,588`) is a mutual-*exclusion* check, not a co-requirement check.

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **Second fail-loud precedent, with a caveat**: `BlockingJsonError` (`host_runner.py:2267-2280`) is a custom `RuntimeError` subclass carrying a `details` dict, raised by `run_blocking_json()` on subprocess timeout/missing-binary/non-zero-exit. It sits alongside `resolve_scopes()` as an existing raise-on-failure shape in this codebase — but it embeds `proc.stderr.strip()` **verbatim** into both the exception message and `details` dict with no scrubbing. `gh_scope_extra`'s `RuntimeError` must not copy that part of the shape, per this issue's existing requirement to name the failure without echoing the probe's stderr. [Agent 3 finding]
- **Fail-loud-on-no-token is a deliberate departure from every existing `gh` call site**: every current `gh` subprocess call site in this codebase (`github_utils.py::is_pr_merged`, `orchestrator.py::_open_pr_for_branch` — docstring: "Degrades gracefully if gh is missing or unauthenticated" — `sync.py::_check_gh_auth`, `fsm/host_guard.py`) fails soft (returns `False`/`None`, logs and returns) on a failed/missing/unauthenticated `gh`; none raise. `gh_scope_extra` raising when no token is obtainable is new relative to every `gh`-specific precedent, though it matches the non-`gh`-specific fail-loud precedents above (`resolve_scopes`, `BlockingJsonError`). [Agent 3 finding]
- **Env-var-chain-then-probe has one precedent, but it degrades silently**: `host_runner.py::_active_oauth_token()` (`:2703-2714`) and an inline equivalent in `fsm/executor.py` (`:3458-3472`) both check env vars first, then fall through to a heavier probe (an in-process SDK call, `default_credentials()`, not a subprocess) — but both return `None`/`False` on probe failure rather than raising. Confirms the ordering shape `gh_scope_extra` proposes has precedent; the subprocess-based probe and the raise-on-failure ending do not. [Agent 3 finding]

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

1. **Where does `GH_TOKEN` come from?** — **Projection-only, sourced from the ambient session.** Order: `GH_TOKEN` env → `GITHUB_TOKEN` env → `gh auth token` (ambient config, no redirect). The learning test shows the third source is the *only* one available on this machine, so without it the feature is dead on arrival. No minting; the token is exactly as broad as the operator's. What this buys is real but bounded: an *undeclared* state is full-inherit and unchanged; a *declaring* state that omits `github` gets the empty-config-dir redirect and therefore neither token nor keyring (see the corrected invariant in Expected Behavior — the redirect must not be gated on `github`); and a *declaring* `github` state gets the token only in its own process tree. Worth having because it closes the "gh is what loops use to change the world" gap; the narrowing question is deferred to a future minting issue.
   - **Exposure note**: today the operator's token is keyring-only and never in any env. After this change a declaring state's child env *contains* the token in plaintext — visible to `env`, `ps e`, crash dumps, and any `set -x` output the action logs. That is a strictly wider exposure for the declaring task's subtree than the status quo. Mitigation is in ENH-3204's names-only rule (never log the value) and a note in LOOPS_GUIDE that `scopes: [github]` puts a live token in the shell environment.
2. **Per-task `GH_CONFIG_DIR` lifecycle** — **Per-spawn `tempfile.TemporaryDirectory()`** scoped to the `Popen`+wait in the shell branch (the `git_operations.py::preserve_dirty_tree()` shape, lines 725-760). gh writes nothing into the config dir under token auth, so there is no state to preserve across spawns and no registry/pid marker needed; the `worktree_utils` registry shape is over-engineering here. Cleanup is the context manager's exit, including the timeout/kill path.

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

## Verification Notes (2026-09-07)

- **Dependency status stale but resolved favorably**: all three `blocked_by` entries
  (`ENH-3395`, `ENH-3396`, `ENH-3235`) are now `status: done`, and each carries a
  correct `## Blocks` backlink to `ENH-3205` — no `DEP_ISSUES`. The Summary's "no
  projection code has landed yet" line is stale (the blockers have since landed),
  but this issue's own scope (the `gh`-specific `GH_TOKEN`/`GH_CONFIG_DIR` pairing)
  is confirmed still unimplemented: `gh_scope_extra` does not exist anywhere under
  `scripts/`, and `fsm/runners.py`'s shell branch resolves `scopes` → `env_allow`
  (ENH-3235, landed) but has no `github`/`GH_TOKEN`/`GH_CONFIG_DIR`/
  `TemporaryDirectory` handling yet.
- **Anchor relocation (2 citations, graph=`fallback`/`fresh`)**:
  - `project_child_env()` cited at `host_runner.py:1865` (Codebase Research
    Findings, 2026-09-03 pass) — actual current line is **2027** (`ll-code defines`
    confirms; the registry/`resolve_scopes` additions from ENH-3396 pushed later
    definitions down).
  - `git_operations.py::preserve_dirty_tree()` cited at lines `725-749` (2026-09-03
    pass) and re-cited `725-760` (2026-09-07 "corrected" pass, Program Design) —
    actual current def line is **651** (`ll-code defines` confirms); both citations
    are now stale.
  - All other checked citations (16/16 `sync.py` gh call sites; `fsm/runners.py`
    lines 315-336 and 403-436 insertion points; `host_runner.py` `CREDENTIAL_SCOPES`
    124-163, `resolve_scopes` 166, `BlockingJsonError` 2268, `_active_oauth_token`
    2703; `fsm/executor.py:300`; `session_store/writers.py:1945` and
    `schema.py:1317`; `structural_rules.py` 492-521; `cli/loop/testing.py:85`;
    `test_enh3184_spawn_site_guard.py:44-48`; `test_fsm_runners.py:415,430`;
    `test_host_runner.py` class ranges 98/144/271-289) are confirmed accurate at
    their stated lines.
  - Minor: `github_utils.py::is_pr_merged` / `orchestrator.py::_open_pr_for_branch`
    (Program Design causal-precedent bullet) are missing the `parallel/` path
    prefix (actual: `parallel/github_utils.py`, `parallel/orchestrator.py`); both
    functions and the cited "degrades gracefully" docstring exist as described.
- **Learning-test claims confirmed directly**: `.ll/learning-tests/gh.md` exists
  and its recorded assertions (keyring hidden under an empty `GH_CONFIG_DIR`, `gh
  auth token` yields the ambient token with no `GH_TOKEN`/`GITHUB_TOKEN` set) match
  what Decision 1 and the Summary's Learning Test bullet claim.
- Evidence-quote check (`ll-verify-evidence`): clean, no fabricated spans.
- No active required decision rules found in the decisions log.
- Proposal-vs-code consequence check (B6): the Program Design's exact insertion
  points (`fsm/runners.py:315-336`, `:403-436`) verified byte-accurate against
  current code; no exception-handler, test-fixture, or AC-coverage defect found in
  the Proposed Solution as written.
- Graph: provider=`fallback` freshness=`fresh`.
- **Verdict: OUTDATED** (anchor relocation on 2 citations above). Corrected lines
  supplied; no other correctness defect found.

## Review Notes (2026-09-06, pre-implementation cross-issue review)

- **Invariant bug fixed**: "both or neither" gated the `GH_CONFIG_DIR` redirect on `"github" in
  scopes`, so a declaring-but-non-github state kept the keyring reachable via `HOME`. Replaced
  with "redirect whenever `scopes is not None`; token iff `github`". `gh_scope_extra` gained a
  `with_token` kwarg; tests updated (keyring-hidden and non-escalation cases added).
- Added `config.yml` loss note (`git_protocol` defaults to https under the redirect) and the
  per-spawn `gh auth token` probe-cost note.

## Implementation Notes (2026-09-07, `/ll:manage-issue`)

- Implemented `gh_scope_extra()` (`host_runner.py`) and wired it into `fsm/runners.py`'s
  shell branch exactly per the Proposed Mechanism / Program Design sections: redirect
  `GH_CONFIG_DIR` whenever `scopes is not None`, inject `GH_TOKEN` iff `"github" in
  scopes`, per-spawn `tempfile.TemporaryDirectory` cleaned up in a `finally` spanning
  both the timeout and normal-exit return paths.
- **Gap discovered during implementation, not previously covered by the 2026-09-04
  learning test**: on this machine's macOS/Keychain-backed `gh` install, `gh auth
  token` reads the OAuth token from the login Keychain by a fixed per-hostname service
  name, independent of `GH_CONFIG_DIR`/`hosts.yml`. Verified directly:
  `GH_CONFIG_DIR=<freshly-created empty dir> gh auth status` correctly reports "not
  logged in", but `gh auth token` under the *same* env still exits 0 with the real
  token. Recorded as a new `fail`-result assertion in `.ll/learning-tests/gh.md`.
  Consequence: the Decision Rules' non-escalation claim ("an inner `github` state
  spawned under an outer non-github declaring state... `gh auth token` fails against
  the inherited empty config dir") does **not** hold on keychain-backed `gh` — a
  nested `github`-scoped spawn can still mint a token via this same probe even when it
  inherits an outer state's empty `GH_CONFIG_DIR`. The redirect still correctly hides
  the ambient session from `gh auth status`/`gh api`/interactive commands run *inside*
  a declaring state's own action, which is this issue's primary goal; only the
  cross-nesting non-escalation guarantee is narrower than stated. Documented as a
  caveat on `gh_scope_extra()`'s docstring; the originally-planned non-escalation test
  (real `gh auth token` under an inherited empty config dir) was removed since it
  asserted a behavior that does not hold — the mocked no-token-obtainable test
  (`test_shell_github_scope_no_token_fails_state_spawns_nothing`) still covers the
  fail-closed path when the probe itself fails or returns no token.
- Follow-on (not this issue): minting a short-lived, narrowly-scoped token instead of
  reusing the operator's own broad `gh auth token` session — already out of scope per
  this issue's own Scope Boundaries — would also close this specific gap, since a
  minted token would not live in the shared Keychain entry.

## Session Log
- `/ll:manage-issue` - 2026-09-07T23:07:04 - `08401f9e-dd7d-4170-a737-bc49b5226e19.jsonl`
- `/ll:ready-issue` - 2026-09-07T22:53:40 - `a61aa2ef-5a44-424c-b1ad-ffa5843a135c.jsonl`
- `/ll:confidence-check` - 2026-09-07T22:51:30 - `23f69ef5-7f56-4be4-a214-cae0d8f52268.jsonl`
- `/ll:reconcile-issue` - 2026-09-07T22:49:32 - `6c0cd877-ad50-49ab-b049-c0092bd933ba.jsonl`
- `/ll:verify-issues` - 2026-09-07T22:45:16 - `88b56b84-e9e7-4e23-82e9-4d0c1c2bd644.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-07T22:40:40 - `9f78fddf-7eb7-4733-aae9-13e98b13e8a1.jsonl`
- `/ll:wire-issue` - 2026-09-07T22:31:00 - `aa0318e8-086b-48fe-8d57-1af0e08ac0c1.jsonl`
- `/ll:refine-issue` - 2026-09-07T22:23:53 - `94a52359-9913-43a1-a470-30b5f8e5d9a6.jsonl`
- `/ll:wire-issue` - 2026-09-07T03:48:29 - `24278e0c-f73c-4e7c-b229-0bf010cc0589.jsonl`
- `/ll:verify-issues` - 2026-09-03T20:10:57 - `433c9d43-d77e-48a9-ae6d-2a38645d30bb.jsonl`
- `/ll:refine-issue` - 2026-09-03T19:37:52 - `e69aa141-6d57-4757-9f35-bf5dfd784b25.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:47:55 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:56 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
