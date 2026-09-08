---
id: BUG-3402
type: BUG
title: gh auth token bypasses GH_CONFIG_DIR isolation via macOS Keychain
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-08'
captured_at: '2026-09-08T00:36:57Z'
parent: EPIC-3212
learning_tests_required:
- gh
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
(a) find/add a Keychain-defeating mechanism — e.g. force `GH_TOKEN` to an explicit empty/invalid sentinel value in the scoped child's env when `github` is not declared, since env `GH_TOKEN`/`GITHUB_TOKEN` do take precedence over Keychain per the registry's own passing assertions; or
(b) explicitly document this as an accepted platform limitation of the credential-scoping feature on macOS and narrow the isolation claim in ENH-3205/`docs/ARCHITECTURE.md`/`docs/guides/LOOPS_GUIDE.md` accordingly.

## Motivation

Credential scoping (EPIC-3212) exists so a spawned child session cannot exfiltrate the operator's real GitHub token. `gh_scope_extra()`'s `GH_CONFIG_DIR` redirect is the documented isolation mechanism for that guarantee, but its own docstring (`host_runner.py:200-211`) already concedes it does not block `gh auth token` on keychain-backed macOS `gh`. Left unfixed or undocumented, any code that relies on the redirect alone for non-escalation — including BUG-3400's CMD/queue-runner fix, whose acceptance criteria only test `gh auth status` — inherits a false isolation guarantee: a scoped child can mint the operator's real token with no error, silently, on the one platform (macOS) where the team's own dev/CI machines are most likely to run it.

## Proposed Solution

Two options, matching the Expected Behavior disjunction:

**(a) Keychain-defeating sentinel (recommended).** In `gh_scope_extra()` (`host_runner.py:186`), when `with_token=False` — i.e. the calling state does not declare the `github` scope — set `extra["GH_TOKEN"]` to an explicit, obviously-invalid sentinel value (e.g. `""` or `"ll-scoped-no-github-token"`) alongside the existing `GH_CONFIG_DIR` redirect, instead of leaving `GH_TOKEN` unset. The `gh` learning-test registry's own passing assertion (`.ll/learning-tests/gh.md`) already confirms `GH_TOKEN`/`GITHUB_TOKEN` env vars take precedence over the Keychain lookup, so an explicit sentinel closes the gap for any child (or nested grandchild) that calls `gh auth token` itself while inheriting this environment. This is a small, local change with no new dependency, and does not touch the `with_token=True` path, which legitimately needs a real token.

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
- `scripts/tests/test_host_runner.py` — `TestGhScopeExtra` (~line 496); add a case asserting `GH_TOKEN` is set to the invalid sentinel when `with_token=False`. The existing `test_without_token_only_redirects_config_dir` (~line 498-500) asserts an exact-dict equality with no `GH_TOKEN` key — this specific assertion breaks and must be updated, not just extended
- `.ll/learning-tests/gh.md` / `.ll/learning-tests/raw/gh.txt` — the "ENH-3205 gap" claim (`result: fail`) should be re-verified via `ll-learning-tests check gh` and flipped once (a) ships, or reworded if (b) is chosen instead

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_runners.py::test_shell_declared_empty_scopes_redirects_config_dir_no_token` (~line 438) — asserts the child sees `GH_TOKEN` as `absent` under `scopes=[]` with an ambient `GH_TOKEN` set via `monkeypatch.setenv`; will break once the sentinel is injected — update to assert the sentinel value instead [Agent 3 finding]
- `scripts/tests/test_fsm_runners.py::test_shell_declared_non_github_scope_hides_ambient_gh_login` (~line 465) — exercises the real `gh` binary via `gh auth status`, skipped if `gh` isn't installed; verify it still reports "not logged into" once `GH_TOKEN` is set to an invalid sentinel (gh may report a different status line for a set-but-invalid token) — may need updating [Agent 3 finding]
- `scripts/tests/test_runner_spec.py` — no existing test covers the CMD/queue path's `with_token=False` branch; add a case asserting the sentinel is present in the merged env for a non-`github`-declaring `ActionSpec`, mirroring `TestGhScopeExtra` [Agent 2/3 finding]

### Documentation
- ENH-3205's Decision Rules (non-escalation guarantee text)
- `docs/ARCHITECTURE.md`, `docs/guides/LOOPS_GUIDE.md` — wherever the `GH_CONFIG_DIR`-redirect guarantee is described

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` § `gh_scope_extra` (~line 10227-10242) — mirrors the docstring's "Known gap" text verbatim and names only `fsm/runners.py`'s `DefaultActionRunner` as the caller; update for the new sentinel behavior and add `runner_spec.py::_run_cmd` as a second caller [Agent 2 finding]
- Note: `docs/ARCHITECTURE.md` was searched exhaustively (`GH_CONFIG_DIR`, `gh_scope_extra`, `ENH-3205`, `CREDENTIAL_SCOPES`, `non-escalation`) and contains no isolation-guarantee prose — only an unrelated v47 schema-table row for `credential_scope_events`. The line above citing it may be stale; `docs/guides/LOOPS_GUIDE.md` § "Credential scoping on shell states" (~line 614-618) is the actual location of this guarantee text [Agent 2 finding]
- `.ll/learning-tests/gh.md` / `raw/gh.txt` — the existing failing claim's wording covers only the "ambient, no env vars set" scenario (still fails/unchanged after this fix); needs a wording split or a second claim distinguishing it from the "scoped child under `gh_scope_extra`" scenario (should pass after this fix), plus a fresh raw probe run under the new sentinel for evidence [Agent 2 finding]

### Configuration
- N/A

## Program Design

### Types

- N/A — no new data types; `gh_scope_extra()`'s return stays `dict[str, str]`

### Signatures

- `gh_scope_extra(config_dir: Path, *, with_token: bool) -> dict[str, str]` — signature unchanged; the `with_token=False` branch gains an explicit invalid `GH_TOKEN` sentinel instead of leaving the key unset

### Call Path

`fsm/runners.py` (state execution, `runners.py:338`) -> `host_runner.gh_scope_extra()` -> env-override dict merged into the spawned host CLI's subprocess environment

## Implementation Steps

1. Add the Keychain-defeating `GH_TOKEN` sentinel to `gh_scope_extra()`'s `with_token=False` branch (`host_runner.py`).
2. Extend `TestGhScopeExtra` in `test_host_runner.py` to assert the sentinel is present and obviously invalid.
3. Re-run `ll-learning-tests check gh` (or add a new registry claim) to confirm the previously-failing "ENH-3205 gap" assertion now passes for the non-`github`-declaring case.
4. Update the isolation-guarantee language in ENH-3205, `docs/ARCHITECTURE.md`, and `docs/guides/LOOPS_GUIDE.md` to match the actual post-fix guarantee.
5. Verification: `python -m pytest scripts/tests/test_host_runner.py -k gh_scope_extra`, plus a manual macOS check that a non-`github`-declaring child's `gh auth token` call no longer returns the operator's real token.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Note `scripts/little_loops/runner_spec.py:286` (`_run_cmd`) as a second live caller of `gh_scope_extra()` — BUG-3400 already landed this on `main`; no code change needed there, the sentinel fix applies automatically, but its test/doc coverage below is still required
- Update `scripts/tests/test_fsm_runners.py::test_shell_declared_empty_scopes_redirects_config_dir_no_token` — assert the sentinel value instead of `"absent"`
- Verify `scripts/tests/test_fsm_runners.py::test_shell_declared_non_github_scope_hides_ambient_gh_login` still passes against real `gh` with the sentinel set; update if `gh auth status` reports differently
- Add a new test in `scripts/tests/test_runner_spec.py` covering the CMD/queue path's `with_token=False` branch
- Update `docs/reference/API.md`'s `gh_scope_extra` section to document the sentinel and list `runner_spec.py::_run_cmd` as a second caller
- Split or reword the `.ll/learning-tests/gh.md` claim to distinguish "ambient, no env set" (still fails) from "scoped child" (should pass), then re-probe for raw evidence

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
- `/ll:wire-issue` - 2026-09-08T01:01:13 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:52:38 - `f6f85f70-0f74-4fad-b98e-66827bb86886.jsonl`
- `/ll:format-issue` - 2026-09-08T00:41:36 - `e2e1620c-1ab1-45d3-8135-fca9b61f9221.jsonl`
- `/ll:capture-issue` - 2026-09-08T00:37:04 - `818ac84c-8dd8-46bc-9d1e-d582e9b2e72e.jsonl`
