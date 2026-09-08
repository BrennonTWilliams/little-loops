---
id: BUG-3402
type: BUG
title: gh auth token bypasses GH_CONFIG_DIR isolation via macOS Keychain
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T00:36:57Z'
completed_at: '2026-09-08T01:52:15Z'
parent: EPIC-3212
learning_tests_required:
- gh
confidence_score: 95
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3402: gh auth token bypasses GH_CONFIG_DIR isolation via macOS Keychain

## Summary

On keychain-backed macOS `gh`, `gh auth token` still succeeds and prints the operator's token (exit 0) even when `GH_CONFIG_DIR` is redirected to a freshly-created empty directory and `GH_TOKEN`/`GITHUB_TOKEN` are unset. `gh` stores the OAuth token in the login Keychain under a fixed service name (`gh:github.com`), keyed by hostname only — not gated by `GH_CONFIG_DIR`/`hosts.yml` the way `gh auth status`/`gh api` are.

## Current Behavior

The `GH_CONFIG_DIR`-redirect-based non-escalation guarantee that ENH-3205's Decision Rules promise ("an inner github state spawned under an outer non-github declaring state... `gh auth token` fails against the inherited empty config dir") does NOT hold on keychain-backed macOS `gh`. A nested or sibling github-scoped spawn can still mint a valid token via `gh auth token` regardless of an inherited/redirected empty `GH_CONFIG_DIR`, because the probe reads Keychain directly rather than the config dir.

This is already recorded as a failing assertion in the learning-test registry: `ll-learning-tests check gh` reports 1 failing claim dated 2026-09-07, tagged "ENH-3205 gap", stored in `.ll/learning-tests/gh.md` / `.ll/learning-tests/raw/gh.txt` (overall status=proven, but this specific assertion result=fail).

Surfaced during `/ll:wire-issue BUG-3400 --auto` (2026-09-08): BUG-3400 fixes the CMD/queue runner path to call `gh_scope_extra()` (mirroring the FSM path's existing `GH_CONFIG_DIR`-redirect approach), but BUG-3400's acceptance criteria only assert `gh auth status` inside the scoped child does not see the operator login — they do not test `gh auth token`. So BUG-3400's fix will satisfy its own acceptance criteria while this deeper isolation gap remains live on macOS: `gh_scope_extra()`'s own probe (and any child's own `gh auth token` call) can still mint the operator's real token via Keychain regardless of the `GH_CONFIG_DIR` redirect.

## Steps to Reproduce

1. On macOS with a keychain-backed `gh` login (`gh auth login` completed against the login Keychain, not a `GH_TOKEN`/token-file login).
2. Create a fresh empty directory and set `GH_CONFIG_DIR` to it; unset `GH_TOKEN` and `GITHUB_TOKEN` in the shell.
3. Run `gh auth status` under that environment — it correctly reports "not logged in", confirming the `GH_CONFIG_DIR` redirect hides `hosts.yml`.
4. Run `gh auth token` under the same environment — it exits 0 and prints the operator's real OAuth token, because `gh` looks the token up in the login Keychain by hostname, independent of `GH_CONFIG_DIR`.
5. Observe: step 4 should fail (or return no token) to match step 3's isolation, but instead silently leaks the ambient credential.

## Expected Behavior

Either:
(a) find/add a Keychain-defeating mechanism — force `GH_TOKEN` to an explicit, **non-empty**, obviously-invalid sentinel value in the scoped child's env when `github` is not declared, since a non-empty env `GH_TOKEN`/`GITHUB_TOKEN` takes precedence over Keychain per the registry's own passing assertions. An empty string does NOT work: verified 2026-09-08 against gh 2.86.0 that `GH_CONFIG_DIR=<empty> GH_TOKEN= gh auth token` still prints the 40-char Keychain token (gh treats an empty env var as unset); or
(b) explicitly document this as an accepted platform limitation of the credential-scoping feature on macOS and narrow the isolation claim in ENH-3205/`docs/ARCHITECTURE.md`/`docs/guides/LOOPS_GUIDE.md` accordingly.

## Motivation

Credential scoping (EPIC-3212) exists so a spawned child session cannot exfiltrate the operator's real GitHub token. `gh_scope_extra()`'s `GH_CONFIG_DIR` redirect is the documented isolation mechanism for that guarantee, but its own docstring (`host_runner.py:200-211`) already concedes it does not block `gh auth token` on keychain-backed macOS `gh`. Left unfixed or undocumented, any code that relies on the redirect alone for non-escalation — including BUG-3400's CMD/queue-runner fix, whose acceptance criteria only test `gh auth status` — inherits a false isolation guarantee: a scoped child can mint the operator's real token with no error, silently, on the one platform (macOS) where the team's own dev/CI machines are most likely to run it.

## Proposed Solution

Two options, matching the Expected Behavior disjunction:

**(a) Keychain-defeating sentinel (recommended).** In `gh_scope_extra()` (`host_runner.py:186`), when `with_token=False` — i.e. the calling state does not declare the `github` scope — set `extra["GH_TOKEN"]` to a module-level constant sentinel (`GH_SCOPED_NO_TOKEN = "ll-scoped-no-github-token"`) alongside the existing `GH_CONFIG_DIR` redirect, instead of leaving `GH_TOKEN` unset. The sentinel must be non-empty (see Expected Behavior). The `gh` learning-test registry (`.ll/learning-tests/gh.md`, commit 0dedad139) already carries two passing "BUG-3402 fix" claims proving that under `GH_CONFIG_DIR=<empty> GH_TOKEN=ll-scoped-no-github-token`, `gh auth status` reports "The token in GH_TOKEN is invalid." (exit 1) and `gh auth token` prints the sentinel itself, not the Keychain token. This is a small, local change with no new dependency.

**The `with_token=True` path IS affected via env inheritance and must reject the sentinel.** An inner `github`-declaring state spawned under an outer non-`github` declaring state inherits `GH_TOKEN=<sentinel>`. `gh_scope_extra(with_token=True)` reads `os.environ.get("GH_TOKEN")` first, so without a guard it would inject the sentinel as the child's "real" token and the state would fail at runtime with HTTP 401 instead of failing at spawn with the existing "declared 'github' scope but no token available" `RuntimeError`. Skipping the env read is not enough: the `gh auth token` probe runs under the inherited env, and env precedence short-circuits Keychain, so the probe's stdout is the sentinel too. Therefore `gh_scope_extra()` must treat `GH_SCOPED_NO_TOKEN` as "no token" in **both** the env lookup and the probe stdout, and fall through to the existing `RuntimeError`. This is what makes ENH-3205's non-escalation rule ("an inner github state under an outer non-github declaring state fails closed") actually hold on keychain-backed macOS.

**Observable behavior change for non-`github` declaring children:** any `gh` command now fails with HTTP 401 "Bad credentials" (verified: `gh api user` → `{"message": "Bad credentials"}`) after a network round-trip, instead of the previous local exit-4 "run gh auth login" message. Any other tool that honors `GH_TOKEN` loses anonymous fallback inside such a child. This is the intended isolation, but it must be documented (see Documentation).

**(b) Document as an accepted platform limitation.** Narrow the isolation claim in ENH-3205's Decision Rules, `docs/ARCHITECTURE.md`, and `docs/guides/LOOPS_GUIDE.md` to state that the `GH_CONFIG_DIR` redirect hides the ambient *session* (`gh auth status`/`gh api`/interactive commands) but does not, by itself, prevent `gh auth token` re-minting a token from the Keychain on macOS.

Recommend shipping (a) as the primary fix, and doing (b) regardless — the doc language should reflect whatever the actual guarantee is after (a) lands, since (a) only defeats the non-`github`-declaring case and the underlying Keychain behavior itself is unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `gh_scope_extra()` (option a: add the invalid-sentinel branch); its docstring's "Known gap" section needs updating either way

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runners.py:338` — sole caller of `gh_scope_extra()`, invoked during FSM state execution
  > ⚠ Superseded — BUG-3400 landed; runner_spec.py now a caller too
- BUG-3400 (CMD/queue-runner path being wired to call `gh_scope_extra()`) — inherits whichever fix/limitation this issue settles on

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/runner_spec.py:286` (`_run_cmd`) — second production caller of `gh_scope_extra()` (import at line 41). BUG-3400 has already landed on `main`, so this CMD/queue-runner dispatch path calls `gh_scope_extra()` the same way `fsm/runners.py:338` does. It automatically inherits the sentinel fix since the change lives inside `gh_scope_extra()` itself — no code change needed here, only the test/doc coverage listed below [Agent 1 finding]

### Similar Patterns
- N/A — no other entry in `CREDENTIAL_SCOPES` (`host_runner.py:124`) has a documented OS-keychain bypass; this is specific to `github`/`gh`

### Tests
- `scripts/tests/test_host_runner.py` — `TestGhScopeExtra` (~line 496); add a case asserting `GH_TOKEN == GH_SCOPED_NO_TOKEN` when `with_token=False`. The existing `test_without_token_only_redirects_config_dir` (~line 498-500) asserts an exact-dict equality with no `GH_TOKEN` key — this specific assertion breaks and must be updated, not just extended. Add two nested-case tests for `with_token=True`: (i) `monkeypatch.setenv("GH_TOKEN", GH_SCOPED_NO_TOKEN)` with `GITHUB_TOKEN` unset and the probe mocked to print the sentinel → `RuntimeError` naming the scope; (ii) both env vars unset and the probe stdout equal to the sentinel → same `RuntimeError`. Use the dispatch-by-argv `subprocess.run` patch shape the existing probe tests use
- `.ll/learning-tests/gh.md` / `.ll/learning-tests/raw/gh.txt` — commit 0dedad139 already added the two passing "BUG-3402 fix" claims (sentinel → `gh auth status` fails; sentinel → `gh auth token` prints the sentinel) with raw evidence. Remaining: reword the "ENH-3205 gap" `result: fail` claim as the ambient-only scenario (no env vars set; still true and unchanged by this fix), and add a third claim covering the nested case: `GH_TOKEN=<sentinel> gh auth token` prints the sentinel, so a nested probe cannot reach Keychain

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_runners.py::test_shell_declared_empty_scopes_redirects_config_dir_no_token` (~line 438) — asserts the child sees `GH_TOKEN` as `absent` under `scopes=[]` with an ambient `GH_TOKEN` set via `monkeypatch.setenv`; will break once the sentinel is injected — update to assert the sentinel value instead [Agent 3 finding]
- `scripts/tests/test_fsm_runners.py::test_shell_declared_non_github_scope_hides_ambient_gh_login` (~line 465) — exercises the real `gh` binary via `gh auth status`, skipped if `gh` isn't installed. **Will break, not "may":** with the sentinel set, `gh auth status` prints "Failed to log in to github.com using token (GH_TOKEN)" and exits 1, and it becomes a network call because gh validates the token against the API. Rewrite it to run `gh auth token` and assert stdout equals `GH_SCOPED_NO_TOKEN` — offline, deterministic, and it tests the actual bug [Agent 3 finding, revised 2026-09-08]
- `scripts/tests/test_runner_spec.py` — no existing test covers the CMD/queue path's `with_token=False` branch; add a case asserting the sentinel is present in the merged env for a non-`github`-declaring `ActionSpec`, mirroring `TestGhScopeExtra` [Agent 2/3 finding]

### Documentation
- ENH-3205's "Invariant corrected (2026-09-06 review)" paragraph (~line 61) — the non-escalation sentence ("finds no `GH_TOKEN` in env and `gh auth token` fails against the inherited empty config dir") is what this fix makes true; reword to name the sentinel + rejection mechanism
- `docs/guides/LOOPS_GUIDE.md` § "Credential scoping on shell states" (~line 614-618) — replace the "Known non-escalation gap" bullet (line 618) with the post-fix guarantee, and add a bullet for the observable behavior change (non-`github` declaring children get HTTP 401 "Bad credentials" from `gh`, not the local "run gh auth login" message; `GH_TOKEN`-honoring tools lose anonymous fallback)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `gh_scope_extra` (~line 10227-10242) — mirrors the docstring's "Known gap" text verbatim and names only `fsm/runners.py`'s `DefaultActionRunner` as the caller; update for the new sentinel behavior and add `runner_spec.py::_run_cmd` as a second caller [Agent 2 finding]
- Note: `docs/ARCHITECTURE.md` was searched exhaustively (`GH_CONFIG_DIR`, `gh_scope_extra`, `ENH-3205`, `CREDENTIAL_SCOPES`, `non-escalation`) and contains no isolation-guarantee prose — only an unrelated v47 schema-table row for `credential_scope_events`. It is NOT a doc target for this issue [Agent 2 finding]
- `.ll/learning-tests/gh.md` / `raw/gh.txt` — see Tests above; the "scoped child under `gh_scope_extra`" claims already exist (commit 0dedad139), only the ambient-claim rewording and the nested-case claim remain [Agent 2 finding, revised 2026-09-08]

### Configuration
- N/A

## Program Design

### Types

- N/A — no new data types; `gh_scope_extra()`'s return stays `dict[str, str]`

### Signatures

- `GH_SCOPED_NO_TOKEN: str = "ll-scoped-no-github-token"` — new module-level constant in `host_runner.py`, next to `CREDENTIAL_SCOPES`; the single source of truth for the sentinel, referenced by the `with_token=False` injection, the `with_token=True` rejection, and every test
- `gh_scope_extra(config_dir: Path, *, with_token: bool) -> dict[str, str]` — signature unchanged. `with_token=False`: returns `{"GH_CONFIG_DIR": ..., "GH_TOKEN": GH_SCOPED_NO_TOKEN}`. `with_token=True`: an env `GH_TOKEN`/`GITHUB_TOKEN` equal to the sentinel is treated as unset, and a probe stdout equal to the sentinel is treated as "no token"; both fall through to the existing `RuntimeError`

### Call Path

`fsm/runners.py` (state execution, `runners.py:338`) and `runner_spec.py` (`_run_cmd`, `runner_spec.py:286`) -> `host_runner.gh_scope_extra()` -> env-override dict merged (via `project_child_env(extra=...)`, which applies `extra` unconditionally regardless of `env_allow`) into the spawned `bash -c` subprocess environment

## Implementation Steps

1. Add `GH_SCOPED_NO_TOKEN` to `host_runner.py` and inject it as `GH_TOKEN` in `gh_scope_extra()`'s `with_token=False` branch. Update the docstring's "Known gap" section to describe the sentinel and the residual ambient-only limitation.
2. In the `with_token=True` branch, treat an env `GH_TOKEN`/`GITHUB_TOKEN` equal to `GH_SCOPED_NO_TOKEN` as unset, and treat probe stdout equal to `GH_SCOPED_NO_TOKEN` as "no token", so a nested `github` state under an outer non-`github` declaring state raises the existing `RuntimeError` at spawn.
3. Update `TestGhScopeExtra` in `test_host_runner.py`: fix the exact-dict assertion, add the sentinel-present case, and add the two nested-rejection cases (sentinel via env; sentinel via probe stdout).
4. Update `.ll/learning-tests/gh.md`: reword the "ENH-3205 gap" fail claim as ambient-only, add the nested-case claim (`GH_TOKEN=<sentinel> gh auth token` prints the sentinel), and re-run `ll-learning-tests check gh`.
5. Update the isolation-guarantee language in ENH-3205 (~line 61), `docs/guides/LOOPS_GUIDE.md` (~line 614-618), and `docs/reference/API.md` § `gh_scope_extra` (~line 10237-10242), including the HTTP 401 behavior change for non-`github` declaring children.
6. Verification: `python -m pytest scripts/tests/test_host_runner.py scripts/tests/test_fsm_runners.py scripts/tests/test_runner_spec.py`, then the full suite, plus a manual macOS check that a non-`github`-declaring child's `gh auth token` prints the sentinel and a nested `github` state under it fails at spawn with the "no token available" error.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Note `scripts/little_loops/runner_spec.py:286` (`_run_cmd`) as a second live caller of `gh_scope_extra()` — BUG-3400 already landed this on `main`; no code change needed there, the sentinel fix applies automatically, but its test/doc coverage below is still required
- Update `scripts/tests/test_fsm_runners.py::test_shell_declared_empty_scopes_redirects_config_dir_no_token` — assert `token == GH_SCOPED_NO_TOKEN` instead of `"absent"`
- Rewrite `scripts/tests/test_fsm_runners.py::test_shell_declared_non_github_scope_hides_ambient_gh_login` to run `gh auth token` and assert stdout equals `GH_SCOPED_NO_TOKEN` (the `gh auth status` form breaks and becomes network-dependent)
- Add a new test in `scripts/tests/test_runner_spec.py` covering the CMD/queue path's `with_token=False` branch (sentinel present in the child env)
- Update `docs/reference/API.md`'s `gh_scope_extra` section to document the sentinel, the nested rejection, and the 401 behavior change; it already lists `runner_spec.py::_run_cmd` as a caller
- Reword the ambient-only `.ll/learning-tests/gh.md` claim and add the nested-case claim (the scoped-child claims already exist, commit 0dedad139)

## Impact

- **Priority**: P2 — a security-isolation gap in a feature already merged to `main` (EPIC-3212), silent (no error, just a token that shouldn't be mintable), and platform-specific (macOS Keychain) so may not reproduce in CI.
- **Breaking Change**: No

## Relates To

- ENH-3205 (gh isolation design — this is a gap in that design's own guarantee)
- BUG-3400 (the fix being wired assumes `GH_CONFIG_DIR` redirection is sufficient isolation for both `gh auth status` and `gh auth token`; it is not, for `gh auth token` on keychain-backed macOS `gh`)
- Found via `/ll:wire-issue BUG-3400 --auto` on 2026-09-08, cross-checking the `gh` learning-test registry.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-08T01:50:52 - `f98e0583-6721-4db6-92c5-ce8267fbec9c.jsonl`
- `/ll:ready-issue` - 2026-09-08T01:32:37 - `55c58021-b88c-49e4-93bf-e5ed51ec17bb.jsonl`
- `/ll:confidence-check` - 2026-09-08T01:25:44 - `f1b42f65-5d8a-4ce5-a5e9-6f906a3adabc.jsonl`
- `/ll:wire-issue` - 2026-09-08T01:01:13 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:52:38 - `f6f85f70-0f74-4fad-b98e-66827bb86886.jsonl`
- `/ll:format-issue` - 2026-09-08T00:41:36 - `e2e1620c-1ab1-45d3-8135-fca9b61f9221.jsonl`
- `/ll:capture-issue` - 2026-09-08T00:37:04 - `818ac84c-8dd8-46bc-9d1e-d582e9b2e72e.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-09-08
- **Status**: Completed

### Changes Made
- `scripts/little_loops/host_runner.py`: added `GH_SCOPED_NO_TOKEN` sentinel constant; `gh_scope_extra(with_token=False)` now injects it as `GH_TOKEN`; `with_token=True` treats an inherited sentinel (via `GH_TOKEN`/`GITHUB_TOKEN` env or `gh auth token` probe stdout) as "no token" and falls through to the existing `RuntimeError`; docstring updated.
- `scripts/tests/test_host_runner.py`: updated `TestGhScopeExtra`'s exact-dict assertion for the sentinel; added `test_with_token_rejects_inherited_sentinel_env` and `test_with_token_rejects_sentinel_probe_stdout`.
- `scripts/tests/test_fsm_runners.py`: updated `test_shell_declared_empty_scopes_redirects_config_dir_no_token` to assert the sentinel; rewrote `test_shell_declared_non_github_scope_hides_ambient_gh_login` to exercise `gh auth token` (offline, deterministic) instead of `gh auth status` (which becomes network-dependent under the sentinel).
- `scripts/tests/test_runner_spec.py`: updated `test_cmd_dispatch_empty_scopes_redirects_config_dir_no_token` to assert the sentinel value (the CMD/queue path inherits the fix automatically via `gh_scope_extra()`).
- `.ll/learning-tests/gh.md` / `raw/gh.txt`: reworded the "ENH-3205 gap" claim as ambient-only (re-verified unchanged), added a nested-case claim verifying `GH_TOKEN=<sentinel> gh auth token` prints only the sentinel.
- `.issues/enhancements/P3-ENH-3205-...md`, `docs/guides/LOOPS_GUIDE.md`, `docs/reference/API.md`: updated isolation-guarantee language for the sentinel mechanism and the HTTP 401 behavior change for non-`github`-declaring children.

### Verification Results
- Tests: PASS (targeted: `test_host_runner.py`, `test_fsm_runners.py`, `test_runner_spec.py` all green; full suite has 37 pre-existing failures unrelated to this change, confirmed present on `main` before this fix — `test_cli_loop_lifecycle.py::TestCmdResume*` and `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence`)
- Lint: PASS (`ruff check` on all changed files)
- Types: PASS (`mypy scripts/little_loops/host_runner.py`)
- Manual macOS verification: confirmed against `gh` 2.86.0 (keychain-backed login) that `GH_TOKEN=<sentinel> gh auth token` prints only the sentinel (nested-rejection case), and that the residual ambient-only gap (no `GH_TOKEN` set at all) is unchanged
- Integration: PASS
