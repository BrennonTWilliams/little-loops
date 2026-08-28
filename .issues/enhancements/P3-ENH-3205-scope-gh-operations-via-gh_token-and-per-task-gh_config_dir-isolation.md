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
decision_needed: true
---

# ENH-3205: Scope gh operations via GH_TOKEN and per-task GH_CONFIG_DIR isolation

## Summary

gh operations bypass `host_runner` entirely. `sync.py`'s `_run_gh_command()`/`_check_gh_auth()` rely on the ambient `gh auth login` session, which is repo- or org-broad, with no per-task token minted or injected anywhere.

**Env projection alone does not de-scope gh.** Its credential lives in the OS keyring / `~/.config/gh/hosts.yml`, not in `GITHUB_TOKEN`, so removing that variable from the child leaves the broad session fully usable. Constraining gh requires injecting an explicit `GH_TOKEN` **and** redirecting `GH_CONFIG_DIR` to a per-task directory so the ambient login is not visible. Both, or neither.

This is the one place where ENH-3203's guarantee visibly does not reach, and gh is what FSM loops actually use to make changes to the outside world — so it is the highest-value gap and the one most likely to be misread as already covered.

**Dependency status**: ENH-3203 was closed by *decomposition* into ENH-3233/3234/3235 — no projection code has landed yet. "Gated on a declaration" requires a declaration surface: the FSM shell path (this issue's primary gh surface, per Current Behavior) is ENH-3235, hence `blocked_by: [ENH-3233, ENH-3235]`. If gh scoping should also cover the `ll-action`/`ll-queue`/`ll-harness` path, add ENH-3234 to `blocked_by` when deciding scope. Decide this in or out explicitly; leaving it ambiguous is how the largest hole ships open.

## Current Behavior

- `scripts/little_loops/sync.py` — `_run_gh_command()`/`_check_gh_auth()` shell out to gh directly, bypassing the host-runner layer entirely, and inherit whatever session the operator logged in with.
- FSM loops invoke gh through `DefaultActionRunner`'s `bash -c` branch (`fsm/runners.py:266`), so the shell-action path is the larger surface, not `sync.py`.
- Even under ENH-3203's projection, stripping `GITHUB_TOKEN` from a child changes nothing: gh falls back to the keyring / `~/.config/gh/hosts.yml`, which `HOME` still points at.

## Expected Behavior

A task declaring GitHub access receives an explicit `GH_TOKEN` and a `GH_CONFIG_DIR` pointing at a per-task directory containing no ambient login. A task not declaring it can neither read `GH_TOKEN` nor reach the operator's gh session.

If this is not implemented, ENH-3203 must state plainly that gh is unscoped rather than imply coverage it does not deliver.

## Integration Map

### Files to Modify
- `scripts/little_loops/sync.py` — `_run_gh_command()`, `_check_gh_auth()`.
- The projection helper in `scripts/little_loops/host_runner.py` — `GH_CONFIG_DIR` redirection is a projection concern, not a `sync.py` one, since the `bash -c` path is where most gh calls originate.

### Tests
- A test proving a scoped child's `gh auth status` does not see the ambient login.

## Program Design

### Types
- No new type is required. The `GH_TOKEN`/`GH_CONFIG_DIR` pair is two entries in the allow-set ENH-3203 already computes.

### Signatures
- `_run_gh_command(args: list[str], logger: Logger, check: bool = True) -> subprocess.CompletedProcess[str]` — the sync-layer entry point that must receive a projected environment instead of inheriting one (`sync.py:98`).
- `_check_gh_auth(logger: Logger) -> bool` — the auth probe, which must report against the projected session rather than the ambient one (`sync.py:127`).

### Call Path
`resolve_host` → projection helper → `_run_gh_command` / `_check_gh_auth`

The shell branch `DefaultActionRunner` (`fsm/runners.py:266`) reaches the same CLI by the same route, which is why the redirect belongs in the helper rather than in the sync layer.

### Decision Rules
- Both `GH_TOKEN` and `GH_CONFIG_DIR` are set, or neither is. Setting only the token leaves the ambient login reachable and produces the appearance of scoping without the fact of it.
- Undeclared specs are unaffected, consistent with ENH-3203's AC5.

## Scope Boundaries

Explicitly **out of scope**:

- **Token minting.** No GitHub App installation tokens. Without minting, this projects an equally broad token to fewer processes — see Open Decision #1.
- **The declaration mechanism** — ENH-3203.
- **Other keyring-backed credentials** (`~/.aws/credentials`, `~/.netrc`, the macOS keychain). gh is singled out because it is what loops actually use to change the outside world, not because it is the only one.
- **`HOME` redirection.** `GH_CONFIG_DIR` is a targeted redirect; relocating `HOME` wholesale is a much larger change with its own breakage surface.

## Open Decisions

1. **Where does `GH_TOKEN` come from?** The operator's ambient env is the only source without minting — which means the "scope" is a projection of an equally broad token, not a narrower one. If genuine narrowing is wanted, that is GitHub App installation tokens, i.e. token minting, explicitly out of scope for this family. Decide whether projection-only gh scoping is worth having.
2. **Per-task `GH_CONFIG_DIR` lifecycle** — created per run, per spawn, or per declared spec, and who cleans it up.

## Impact

- **Priority**: P3 — the highest-value remaining gap, but its value is bounded by Open Decision #1: without minting, this isolates *which* processes see a broad token rather than narrowing the token itself.
- **Effort**: Medium — two call sites plus config-dir lifecycle, but the keyring interaction is easy to get subtly wrong.
- **Risk**: Medium — a `GH_CONFIG_DIR` redirect that breaks the operator's interactive gh usage, or a scoped child that silently falls back to the ambient session and appears to work while proving nothing.
- **Breaking Change**: No, if gated on a declaration.

## Status

**Open** | Created: 2026-08-15 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:56 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
