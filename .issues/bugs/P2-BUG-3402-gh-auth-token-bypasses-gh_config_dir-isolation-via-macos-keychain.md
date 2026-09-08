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
- BUG-3400 (CMD/queue-runner path being wired to call `gh_scope_extra()`) — inherits whichever fix/limitation this issue settles on

### Similar Patterns
- N/A — no other entry in `CREDENTIAL_SCOPES` (`host_runner.py:124`) has a documented OS-keychain bypass; this is specific to `github`/`gh`

### Tests
- `scripts/tests/test_host_runner.py` — `TestGhScopeExtra` (~line 496); add a case asserting `GH_TOKEN` is set to the invalid sentinel when `with_token=False`
- `.ll/learning-tests/gh.md` / `.ll/learning-tests/raw/gh.txt` — the "ENH-3205 gap" claim (`result: fail`) should be re-verified via `ll-learning-tests check gh` and flipped once (a) ships, or reworded if (b) is chosen instead

### Documentation
- ENH-3205's Decision Rules (non-escalation guarantee text)
- `docs/ARCHITECTURE.md`, `docs/guides/LOOPS_GUIDE.md` — wherever the `GH_CONFIG_DIR`-redirect guarantee is described

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
- `/ll:format-issue` - 2026-09-08T00:41:36 - `e2e1620c-1ab1-45d3-8135-fca9b61f9221.jsonl`
- `/ll:capture-issue` - 2026-09-08T00:37:04 - `818ac84c-8dd8-46bc-9d1e-d582e9b2e72e.jsonl`
